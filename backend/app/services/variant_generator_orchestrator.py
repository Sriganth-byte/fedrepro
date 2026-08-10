"""VariantGeneratorOrchestrator — coordinates the full variant generation
pipeline from requirements interpretation through ranking.

Background task pattern: callers pass job_id (int) only; the orchestrator
opens its own DB session to avoid request-session lifecycle issues.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.models.entities import (
    Dataset,
    DatasetConfiguration,
    DatasetFingerprint,
    DatasetProfileReport,
    DatasetRegistration,
    DatasetVersion,
    DiagnosisReport,
    LineageEvent,
    Study,
    VariantGenerationJob,
    VariantGenerationRecord,
)
from app.services.dataset_workflow_service import DatasetWorkflowService
from app.services.explanation_engine_service import ExplanationEngineService
from app.services.fingerprint_service import FingerprintService
from app.services.issue_interpreter_service import IssueInterpreterService
from app.services.pipeline_planner_service import PipelinePlannerService
from app.services.variant_builder_service import VariantBuilderService
from app.services.variant_evaluator_service import VariantEvaluatorService
from app.utilities.hashing import canonical_hash, sha256_file

logger = logging.getLogger(__name__)

LETTERS = "ABCDEFGH"


class VariantGeneratorOrchestrator:
    """Runs the full variant generation workflow for a single job."""

    def run_job(self, job_id: int, db: Session) -> None:
        job: VariantGenerationJob | None = db.get(VariantGenerationJob, job_id)
        if not job:
            logger.error("VariantGenerationJob %s not found", job_id)
            return

        try:
            self._execute(job, db)
        except Exception as exc:
            logger.exception("Unhandled error in VariantGeneratorOrchestrator for job %s", job_id)
            try:
                job.status = "failed"
                job.error_message = f"Orchestrator error: {exc}"
                db.commit()
            except Exception:
                db.rollback()

    def _execute(self, job: VariantGenerationJob, db: Session) -> None:
        # ── 1. Load source version + dependencies ────────────────────────────
        source_version: DatasetVersion = db.get(DatasetVersion, job.source_version_id)
        if not source_version:
            raise ValueError(f"Source version {job.source_version_id} not found")

        configuration: DatasetConfiguration = db.get(DatasetConfiguration, source_version.configuration_id)
        dataset: Dataset = db.get(Dataset, source_version.dataset_id)

        diagnosis_report: DiagnosisReport | None = (
            db.get(DiagnosisReport, job.diagnosis_report_id)
            if job.diagnosis_report_id
            else db.query(DiagnosisReport).filter(DiagnosisReport.version_id == source_version.id).first()
        )
        if not diagnosis_report:
            raise ValueError("No diagnosis report found for source version")

        profile_report: DatasetProfileReport | None = (
            db.query(DatasetProfileReport)
            .filter(DatasetProfileReport.version_id == source_version.id)
            .first()
        )
        if not profile_report:
            raise ValueError("No profile report found for source version")

        # ── 2. Mark running ──────────────────────────────────────────────────
        job.status = "running"
        db.commit()

        # ── 3. Build dataset_config dict for ProfilingService / DiagnosisService
        dataset_config: dict = {
            "task_type": configuration.task_type,
            "target_column": configuration.target_column,
            "primary_metric": configuration.primary_metric,
            "validation_strategy": configuration.validation_strategy,
            "feature_selection_mode": configuration.feature_selection_mode,
            "selected_features": configuration.selected_features_json or [],
            "scaling_strategy": configuration.scaling_strategy,
        }

        # ── 4. Interpret issues ──────────────────────────────────────────────
        requirements = IssueInterpreterService().interpret(diagnosis_report, profile_report)

        # ── 5. Plan pipelines ────────────────────────────────────────────────
        constraints: dict = job.constraints_json or {}
        n_pipelines: int = constraints.pop("n_pipelines", 4) if isinstance(constraints, dict) else 4
        goal: str = job.optimization_goal

        pipelines = PipelinePlannerService().plan(requirements, goal, constraints, n_pipelines)
        job.total_variants_planned = len(pipelines)
        db.commit()

        # ── 6. Execute each pipeline ─────────────────────────────────────────
        source_mlrs = float(diagnosis_report.mlrs_score)
        records_created: list[VariantGenerationRecord] = []

        for i, pipeline in enumerate(pipelines):
            letter = LETTERS[i % len(LETTERS)]
            pipeline_id = f"V{job.id}-Pipeline-{letter}"
            pipeline["pipeline_id"] = pipeline_id

            # Create record (pending)
            record = VariantGenerationRecord(
                job_id=job.id,
                pipeline_id=pipeline_id,
                pipeline_hash=pipeline.get("pipeline_hash", ""),
                pipeline_steps_json=pipeline.get("steps", []),
                estimated_cost=pipeline.get("estimated_cost"),
                mlrs_before=source_mlrs,
                missing_values_pct_before=float(
                    profile_report.report_json.get("summary", {}).get("missing_ratio", 0) * 100
                ),
                status="running",
            )
            db.add(record)
            db.flush()
            db.commit()

            # Unique seed per record
            random_seed = 42 + record.id

            try:
                # ── a. Build variant ─────────────────────────────────────────
                build_result = VariantBuilderService().build(
                    source_csv_path=source_version.immutable_file_path,
                    pipeline=pipeline,
                    requirements=requirements,
                    job_id=job.id,
                    random_seed=random_seed,
                )

                if build_result.error:
                    record.status = "failed"
                    record.error_message = build_result.error
                    db.commit()
                    continue

                # ── b. Evaluate (profile + diagnose + VRS) ───────────────────
                eval_result = VariantEvaluatorService().evaluate(
                    build_result=build_result,
                    source_mlrs=source_mlrs,
                    goal=goal,
                    pipeline=pipeline,
                    dataset_config=dataset_config,
                )

                # ── c. Explanation passport ───────────────────────────────────
                eval_summary = {
                    "goal_satisfaction": eval_result.goal_satisfaction,
                    "vrs_score": eval_result.vrs_score,
                    "lrs_caveat": eval_result.lrs_caveat,
                    "vrs_components": {
                        "mlrs_risk_reduction": eval_result.mlrs_risk_reduction,
                        "missing_reduction": eval_result.missing_reduction,
                        "class_balance_score": eval_result.class_balance_score,
                        "feature_score": eval_result.feature_score,
                        "cost_score": eval_result.cost_score,
                    },
                }
                explanation = ExplanationEngineService().explain_pipeline(
                    pipeline, requirements, goal, eval_summary
                )

                # ── d. Register variant as child DatasetVersion ───────────────
                variant_version = self._register_variant_version(
                    db=db,
                    build_result=build_result,
                    source_version=source_version,
                    dataset=dataset,
                    configuration=configuration,
                    pipeline_id=pipeline_id,
                    job=job,
                )

                # ── e. Update record ─────────────────────────────────────────
                record.variant_version_id = variant_version.id
                record.random_seed = random_seed
                record.execution_time_seconds = build_result.execution_time_seconds
                record.library_versions_json = build_result.library_versions
                record.mlrs_after = eval_result.mlrs_after
                record.lrs_after = eval_result.lrs_after
                record.lrs_caveat = eval_result.lrs_caveat
                record.missing_values_pct_after = build_result.missing_values_pct_after
                record.class_balance_score_before = build_result.class_balance_score_before
                record.class_balance_score_after = build_result.class_balance_score_after
                record.feature_count_before = build_result.column_count_before
                record.feature_count_after = build_result.column_count_after
                record.row_count_before = build_result.row_count_before
                record.row_count_after = build_result.row_count_after
                record.vrs_score = eval_result.vrs_score
                record.goal_satisfaction = eval_result.goal_satisfaction
                record.explanation_json = explanation
                record.status = "completed"

                records_created.append(record)
                job.total_variants_completed += 1
                db.commit()

            except Exception as exc:
                logger.exception("Pipeline %s failed for job %s", pipeline_id, job.id)
                record.status = "failed"
                record.error_message = str(exc)
                db.commit()

        # ── 7. Rank completed records by VRS desc ────────────────────────────
        completed = [r for r in records_created if r.status == "completed" and r.vrs_score is not None]
        completed.sort(key=lambda r: r.vrs_score, reverse=True)
        for rank, r in enumerate(completed, start=1):
            r.vrs_rank = rank
        db.commit()

        # ── 8. Mark job done ─────────────────────────────────────────────────
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("VariantGenerationJob %s completed — %d/%d variants", job.id, job.total_variants_completed, job.total_variants_planned)

    def _register_variant_version(
        self,
        db: Session,
        build_result,
        source_version: DatasetVersion,
        dataset: Dataset,
        configuration: DatasetConfiguration,
        pipeline_id: str,
        job: VariantGenerationJob,
    ) -> DatasetVersion:
        """Create a synthetic DatasetRegistration + DatasetVersion for the variant CSV.

        DatasetVersion.registration_id is unique=True and NOT NULL, so each variant
        needs its own registration row (status='variant').
        """
        variant_path = Path(build_result.output_csv_path)
        variant_df = pd.read_csv(str(variant_path))

        # Determine next version number for this dataset
        from sqlalchemy import func as sqlfunc
        existing_max = db.query(sqlfunc.max(DatasetVersion.version_number)).filter(
            DatasetVersion.dataset_id == dataset.id
        ).scalar() or 0
        version_number = existing_max + 1

        # Promote the variant CSV to the immutable datasets directory
        from app.storage.local_storage import LocalFileStorage
        storage = LocalFileStorage()
        dest_dir = storage.datasets / f"study-{dataset.study_id}" / f"dataset-{dataset.id}"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"v{version_number}.csv"
        import shutil
        if not dest_path.exists():
            shutil.copy2(str(variant_path), str(dest_path))

        metadata = {
            "row_count": build_result.row_count_after,
            "column_count": build_result.column_count_after,
            "column_names": list(variant_df.columns),
            "data_types": {c: str(variant_df[c].dtype) for c in variant_df.columns},
            "missing_values": {c: int(variant_df[c].isna().sum()) for c in variant_df.columns},
            "missing_total": int(variant_df.isna().sum().sum()),
            "duplicate_count": int(variant_df.duplicated().sum()),
            "memory_usage_bytes": int(variant_df.memory_usage(deep=True).sum()),
        }

        # Synthetic registration
        registration = DatasetRegistration(
            dataset_id=dataset.id,
            original_filename=f"{pipeline_id}.csv",
            staged_file_path=str(dest_path),
            file_size=dest_path.stat().st_size,
            version_notes=f"Variant generated by job {job.id} — {pipeline_id}",
            metadata_json=metadata,
            validation_json={"valid_csv": True, "schema_valid": True, "warnings": []},
            status="variant",
        )
        db.add(registration)
        db.flush()

        # Synthetic configuration (copy from source, same hash)
        variant_config = DatasetConfiguration(
            dataset_id=dataset.id,
            registration_id=registration.id,
            task_type=configuration.task_type,
            target_column=configuration.target_column,
            primary_metric=configuration.primary_metric,
            validation_strategy=configuration.validation_strategy,
            feature_selection_mode=configuration.feature_selection_mode,
            selected_features_json=configuration.selected_features_json,
            scaling_strategy=configuration.scaling_strategy,
            configuration_hash=configuration.configuration_hash,
        )
        db.add(variant_config)
        db.flush()

        # Fingerprint
        config_hash = canonical_hash({
            "task_type": configuration.task_type,
            "target_column": configuration.target_column,
            "pipeline_id": pipeline_id,
            "job_id": job.id,
        })
        fingerprint_data = FingerprintService().generate(
            str(dest_path), variant_df, metadata, config_hash
        )

        version = DatasetVersion(
            dataset_id=dataset.id,
            registration_id=registration.id,
            configuration_id=variant_config.id,
            parent_version_id=source_version.id,
            version_number=version_number,
            immutable_file_path=str(dest_path),
            version_notes=f"Auto-generated variant — {pipeline_id} (Job {job.id})",
            file_hash=fingerprint_data["file_hash"],
            row_count=build_result.row_count_after,
            column_count=build_result.column_count_after,
            generation_method="variant_generator",
        )
        db.add(version)
        db.flush()

        db.add(DatasetFingerprint(version_id=version.id, **fingerprint_data))
        db.add(LineageEvent(
            dataset_id=dataset.id,
            source_version_id=source_version.id,
            destination_version_id=version.id,
            event_type="variant.generated",
            evidence_json={
                "pipeline_id": pipeline_id,
                "job_id": job.id,
                "generation_method": "variant_generator",
            },
        ))
        db.flush()
        study = db.get(Study, dataset.study_id)
        if study:
            DatasetWorkflowService(db).run_diagnosis(study, None, version.id, generate_ai=True)
        return version


def run_variant_job_background(job_id: int) -> None:
    """Entry point for FastAPI BackgroundTasks.

    Opens its OWN database session — never use the request's db session here.
    """
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        VariantGeneratorOrchestrator().run_job(job_id, db)
    except Exception as exc:
        logger.exception("Background variant job %s crashed: %s", job_id, exc)
        try:
            job = db.get(VariantGenerationJob, job_id)
            if job and job.status not in ("completed", "failed"):
                job.status = "failed"
                job.error_message = f"Unhandled background error: {exc}"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
