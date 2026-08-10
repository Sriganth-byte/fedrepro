"""Variant Generator API routes.

Endpoints:
  POST   /versions/{version_id}/variant-jobs          — create job
  GET    /versions/{version_id}/variant-jobs          — list jobs for version
  GET    /variant-jobs/{job_id}                       — get job (polling)
  POST   /variant-jobs/{job_id}/records/{record_id}/register — promote variant
  GET    /versions/{version_id}/variant-tree          — lineage tree
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.entities import (
    Dataset,
    DatasetConfiguration,
    DatasetVersion,
    DiagnosisReport,
    User,
    VariantGenerationJob,
    VariantGenerationRecord,
)
from app.schemas.contracts import VariantJobCreate, VariantJobRead, VariantRecordRead
from app.services.study_service import StudyService
from app.services.variant_generator_orchestrator import (
    VariantGeneratorOrchestrator,
    run_variant_job_background,
)
from app.utilities.hashing import canonical_hash

router = APIRouter(tags=["variant generator"])

VALID_GOALS = {
    "maximize_accuracy",
    "faster_training",
    "lightweight_dataset",
    "improve_recall",
    "fairness",
    "explainable_model",
}

SYNC_ROW_THRESHOLD = 5000


# ── Helpers ──────────────────────────────────────────────────────────────────

def _job_to_read(job: VariantGenerationJob) -> VariantJobRead:
    records = [VariantRecordRead.from_orm_record(r) for r in (job.records or [])]
    records_sorted = sorted(
        records,
        key=lambda r: (r.vrs_rank or 9999, r.id),
    )
    return VariantJobRead(
        id=job.id,
        source_version_id=job.source_version_id,
        optimization_goal=job.optimization_goal,
        constraints_json=job.constraints_json or {},
        status=job.status,
        total_variants_planned=job.total_variants_planned,
        total_variants_completed=job.total_variants_completed,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
        records=records_sorted,
    )


def _get_version_owned(version_id: int, user_id: int, db: Session) -> DatasetVersion:
    version = (
        db.query(DatasetVersion)
        .join(Dataset, DatasetVersion.dataset_id == Dataset.id)
        .filter(
            DatasetVersion.id == version_id,
            Dataset.study.has(owner_id=user_id),
        )
        .first()
    )
    if not version:
        raise ValueError("Dataset version not found or access denied")
    return version


def _get_job_owned(job_id: int, user_id: int, db: Session) -> VariantGenerationJob:
    job = db.get(VariantGenerationJob, job_id)
    if not job:
        raise ValueError("Variant job not found")
    # Verify ownership via source version → dataset → study
    _get_version_owned(job.source_version_id, user_id, db)
    return job


# ── POST /versions/{version_id}/variant-jobs ─────────────────────────────────

@router.post("/versions/{version_id}/variant-jobs", status_code=201)
def create_variant_job(
    version_id: int,
    payload: VariantJobCreate,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    version = _get_version_owned(version_id, user.id, db)

    # ── Validate goal ────────────────────────────────────────────────────────
    if payload.optimization_goal not in VALID_GOALS:
        raise ValueError(
            f"Invalid optimization_goal '{payload.optimization_goal}'. "
            f"Must be one of: {', '.join(sorted(VALID_GOALS))}"
        )

    # ── Validate constraints ─────────────────────────────────────────────────
    c = payload.constraints
    if c.max_features is not None and c.max_features >= version.column_count:
        raise ValueError(
            f"max_features ({c.max_features}) must be less than the dataset's "
            f"column count ({version.column_count}) to leave room for the target column"
        )
    if c.max_preprocessing_seconds is not None and c.max_preprocessing_seconds < 10:
        raise ValueError("max_preprocessing_seconds must be at least 10")

    # ── Verify a completed DiagnosisReport exists ────────────────────────────
    diagnosis_report = (
        db.query(DiagnosisReport)
        .filter(DiagnosisReport.version_id == version_id)
        .first()
    )
    if not diagnosis_report:
        raise ValueError(
            "No diagnosis report found for this version. "
            "Run data diagnosis before generating variants."
        )

    # ── Idempotency check ────────────────────────────────────────────────────
    constraints_dict = c.model_dump()
    constraints_dict["n_pipelines"] = payload.n_pipelines
    job_hash = canonical_hash(payload.optimization_goal + json.dumps(constraints_dict, sort_keys=True))

    if not payload.force_regenerate:
        existing_job = (
            db.query(VariantGenerationJob)
            .filter(
                VariantGenerationJob.source_version_id == version_id,
                VariantGenerationJob.job_constraints_hash == job_hash,
                VariantGenerationJob.status == "completed",
            )
            .order_by(VariantGenerationJob.created_at.desc())
            .first()
        )
        if existing_job:
            response.headers["X-Variant-Job-Reused"] = "true"
            response.status_code = 200
            return _job_to_read(existing_job)

    # ── Create job record ────────────────────────────────────────────────────
    # Embed n_pipelines into constraints_json for the orchestrator to pick up
    full_constraints = constraints_dict

    job = VariantGenerationJob(
        source_version_id=version_id,
        diagnosis_report_id=diagnosis_report.id,
        optimization_goal=payload.optimization_goal,
        constraints_json=full_constraints,
        job_constraints_hash=job_hash,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # ── Run sync or async ────────────────────────────────────────────────────
    if version.row_count <= SYNC_ROW_THRESHOLD:
        # Small dataset — run synchronously
        VariantGeneratorOrchestrator().run_job(job.id, db)
        db.refresh(job)
        return _job_to_read(job)
    else:
        # Large dataset — background task with own session
        background_tasks.add_task(run_variant_job_background, job_id=job.id)
        response.status_code = 202
        return _job_to_read(job)


# ── GET /versions/{version_id}/variant-jobs ──────────────────────────────────

@router.get("/versions/{version_id}/variant-jobs")
def list_variant_jobs(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _get_version_owned(version_id, user.id, db)
    jobs = (
        db.query(VariantGenerationJob)
        .filter(VariantGenerationJob.source_version_id == version_id)
        .order_by(VariantGenerationJob.created_at.desc())
        .all()
    )
    return [_job_to_read(j) for j in jobs]


# ── GET /variant-jobs/{job_id} ────────────────────────────────────────────────

@router.get("/variant-jobs/{job_id}")
def get_variant_job(
    job_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _get_job_owned(job_id, user.id, db)
    return _job_to_read(job)


# ── POST /variant-jobs/{job_id}/records/{record_id}/register ─────────────────

@router.post("/variant-jobs/{job_id}/records/{record_id}/register")
def register_variant_record(
    job_id: int,
    record_id: int,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _get_job_owned(job_id, user.id, db)
    record: VariantGenerationRecord | None = db.query(VariantGenerationRecord).filter(
        VariantGenerationRecord.id == record_id,
        VariantGenerationRecord.job_id == job.id,
    ).first()
    if not record:
        raise ValueError("Variant record not found")
    if record.status != "completed" or not record.variant_version_id:
        raise ValueError("Variant record is not completed or has no associated version")

    version = db.get(DatasetVersion, record.variant_version_id)
    if not version:
        raise ValueError("Variant version not found")

    # Optionally update the version label
    if payload:
        new_label = payload.get("version_label")
        if new_label:
            version.version_notes = str(new_label)[:500]
            db.commit()

    return {
        "id": version.id,
        "version_number": version.version_number,
        "version_notes": version.version_notes,
        "row_count": version.row_count,
        "column_count": version.column_count,
        "generation_method": version.generation_method,
        "parent_version_id": version.parent_version_id,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


# ── GET /versions/{version_id}/variant-tree ──────────────────────────────────

@router.get("/versions/{version_id}/variant-tree")
def variant_tree(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    root = _get_version_owned(version_id, user.id, db)

    def build_node(v: DatasetVersion) -> dict:
        children = (
            db.query(DatasetVersion)
            .filter(DatasetVersion.parent_version_id == v.id)
            .order_by(DatasetVersion.version_number)
            .all()
        )
        return {
            "id": v.id,
            "version_number": v.version_number,
            "version_notes": v.version_notes,
            "generation_method": v.generation_method,
            "row_count": v.row_count,
            "column_count": v.column_count,
            "parent_version_id": v.parent_version_id,
            "children": [build_node(c) for c in children],
        }

    return build_node(root)
