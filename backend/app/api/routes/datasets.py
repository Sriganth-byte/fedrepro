import json
import tempfile
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.entities import ActivityLog, Dataset, DatasetConfiguration, DatasetProfileReport, DatasetRegistration, DatasetVersion, DiagnosisReport, SemanticDiffReport, User, VariantGenerationRecord
from app.repositories.sqlalchemy import DatasetRepository
from app.schemas.contracts import ConfigurationCreate
from app.services.dataset_workflow_service import DatasetWorkflowService
from app.services.dataset_explanation_report_service import DatasetExplanationReportService
from app.services.diagnosis_contract_service import DiagnosisContractService
from app.services.diagnosis_report_service import DiagnosisReportExportService
from app.services.fingerprint_service import FingerprintService
from app.services.diagnosis_service import DiagnosisService
from app.services.profiling_service import ProfilingService
from app.services.semantic_diff_service import SemanticDiffService
from app.api.routes.ai import resolve_evidence
from app.services.ai_explanation_service import AIExplanationService
from app.services.study_service import StudyService
from app.utilities.hashing import canonical_hash

router = APIRouter(tags=["dataset evidence"])


@router.post("/studies/{study_id}/datasets/register", status_code=201)
async def register_dataset(study_id: int, file: UploadFile = File(...), dataset_name: str | None = Form(None), version_notes: str | None = Form(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    registration = await DatasetWorkflowService(db).register(study, user.id, file, dataset_name, version_notes)
    return registration_payload(registration)


@router.get("/studies/{study_id}/datasets")
def study_datasets(study_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    StudyService(db).get_owned(study_id, user.id)
    return [dataset_payload(dataset, db) for dataset in DatasetRepository(db).list_for_study(study_id)]


@router.get("/registrations/{registration_id}")
def registration_detail(registration_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registration = db.query(DatasetRegistration).join(Dataset).join(Dataset.study).filter(DatasetRegistration.id == registration_id, Dataset.study.has(owner_id=user.id)).first()
    if not registration:
        raise ValueError("Registration not found")
    return registration_payload(registration)


@router.get("/registrations/{registration_id}/explanation-report")
def registration_explanation_report(registration_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registration = db.query(DatasetRegistration).join(Dataset).filter(
        DatasetRegistration.id == registration_id,
        Dataset.study.has(owner_id=user.id),
    ).first()
    if not registration:
        raise ValueError("Registration not found")
    report = _latest_report(db, "dataset.registration_report", "registration", registration_id)
    if not report or not _has_registration_column_inventory(report.details_json):
        dataset = db.get(Dataset, registration.dataset_id)
        study = StudyService(db).get_owned(dataset.study_id, user.id)
        payload = DatasetExplanationReportService.registration_report(study, dataset, registration)
        db.add(ActivityLog(study_id=study.id, actor_id=user.id, action="dataset.registration_report", entity_type="registration", entity_id=registration.id, details_json=payload))
        db.commit()
        return payload
    return report.details_json


@router.post("/registrations/{registration_id}/configure", status_code=201)
def configure_dataset(registration_id: int, payload: ConfigurationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registration = db.query(DatasetRegistration).join(Dataset).filter(DatasetRegistration.id == registration_id).first()
    if not registration:
        raise ValueError("Registration not found")
    dataset = db.get(Dataset, registration.dataset_id)
    study = StudyService(db).get_owned(dataset.study_id, user.id)
    version = DatasetWorkflowService(db).configure_and_analyze(study, user.id, registration_id, payload)
    return version_bundle(db, version)


@router.get("/versions/{version_id}/explanation-report")
def version_explanation_report(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).options(selectinload(DatasetVersion.fingerprint)).first()
    if not version:
        raise ValueError("Dataset version not found")
    report = _latest_report(db, "dataset.version_llm_report", "dataset_version", version_id) or _latest_report(db, "dataset.version_report", "dataset_version", version_id)
    if not report:
        dataset = db.get(Dataset, version.dataset_id)
        study = StudyService(db).get_owned(dataset.study_id, user.id)
        registration = db.get(DatasetRegistration, version.registration_id)
        configuration = db.get(DatasetConfiguration, version.configuration_id)
        profile_row = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
        diagnosis_row = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
        semantic_row = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
        payload = DatasetExplanationReportService.version_report(study, dataset, registration, version, configuration, version.fingerprint, profile_row, diagnosis_row, semantic_row)
        db.add(ActivityLog(study_id=study.id, actor_id=user.id, action="dataset.version_report", entity_type="dataset_version", entity_id=version.id, details_json=payload))
        db.commit()
        return payload
    return report.details_json


@router.post("/versions/{version_id}/explanation-report/generate", status_code=201)
def generate_version_explanation_report(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).first()
    if not version:
        raise ValueError("Dataset version not found")
    study = StudyService(db).get_owned(version.dataset.study_id, user.id)
    evidence = resolve_evidence(db, study, "dataset_explanation_report", version_id)
    record = AIExplanationService(db).explain(study, "dataset_explanation_report", version_id, evidence)
    payload = {
        "report_type": "llm_dataset_explanation_report",
        "report_version": AIExplanationService.prompt_version,
        "generated_at": record.created_at.isoformat() if record.created_at else None,
        "title": f"Dataset explanation report for V{version.version_number}",
        "summary": record.content,
        "ai": {
            "id": record.id,
            "model": record.model,
            "prompt_version": record.prompt_version,
            "source_evidence_hash": record.source_evidence_hash,
        },
        "version": {
            "id": version.id,
            "version_number": version.version_number,
            "dataset_name": version.dataset.name,
        },
    }
    db.add(ActivityLog(study_id=study.id, actor_id=user.id, action="dataset.version_llm_report", entity_type="dataset_version", entity_id=version.id, details_json=payload))
    db.commit()
    return payload


@router.get("/versions/{version_id}")
def version_detail(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).join(Dataset).filter(DatasetVersion.id == version_id, Dataset.study.has(owner_id=user.id)).options(selectinload(DatasetVersion.fingerprint)).first()
    if not version:
        raise ValueError("Dataset version not found")
    return version_bundle(db, version)


@router.get("/versions/{version_id}/analysis")
def version_analysis(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    selected = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).options(selectinload(DatasetVersion.fingerprint)).first()
    if not selected:
        raise ValueError("Dataset version not found")

    versions = db.query(DatasetVersion).filter(
        DatasetVersion.dataset_id == selected.dataset_id,
        DatasetVersion.version_number <= selected.version_number,
    ).order_by(DatasetVersion.version_number).all()
    version_ids = [item.id for item in versions]
    diff_rows = db.query(SemanticDiffReport).filter(
        SemanticDiffReport.current_version_id.in_(version_ids)
    ).all()
    workflow = DatasetWorkflowService(db)
    refreshed = [workflow.refresh_semantic_report(item) for item in diff_rows]
    if any(refreshed):
        db.commit()
    diffs = {item.current_version_id: semantic_payload(item) for item in diff_rows}
    profile_row = db.query(DatasetProfileReport).filter(
        DatasetProfileReport.version_id == selected.id
    ).first()
    diagnosis_row = db.query(DiagnosisReport).filter(
        DiagnosisReport.version_id == selected.id
    ).first()
    return {
        "version": version_bundle(db, selected),
        "profile": None if not profile_row else {
            "id": profile_row.id,
            "version_id": selected.id,
            "profiler_version": profile_row.profiler_version,
            "report": profile_row.report_json,
            "created_at": profile_row.created_at,
        },
        "diagnosis": None if not diagnosis_row else {
            "id": diagnosis_row.id,
            "version_id": selected.id,
            "findings": diagnosis_row.findings_json,
            "mlrs_score": diagnosis_row.mlrs_score,
            "lrs_score": diagnosis_row.lrs_score,
            "score_breakdown": _latest_score_breakdown(db, diagnosis_row.id),
            "ruleset_version": diagnosis_row.ruleset_version,
            "created_at": diagnosis_row.created_at,
        },
        "timeline": [{
            "id": item.id,
            "version_number": item.version_number,
            "row_count": item.row_count,
            "column_count": item.column_count,
            "created_at": item.created_at,
            "semantic_diff": diffs.get(item.id),
        } for item in versions],
    }


@router.post("/versions/{version_id}/diagnosis/run", status_code=201)
def run_diagnosis(version_id: int, recompute: bool = Query(False), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).first()
    if not version:
        raise ValueError("Dataset version not found")
    study = StudyService(db).get_owned(version.dataset.study_id, user.id)
    DatasetWorkflowService(db).run_diagnosis(study, user.id, version_id, recompute=recompute)
    return version_analysis(version_id, db, user)


@router.delete("/versions/{version_id}", status_code=204)
def delete_version(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).first()
    if not version:
        raise ValueError("Dataset version not found")
    study = StudyService(db).get_owned(version.dataset.study_id, user.id)
    DatasetWorkflowService(db).delete_version(study, user.id, version_id)
    return Response(status_code=204)


@router.get("/versions/{version_id}/semantic-diff")
def semantic_diff(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version_detail(version_id, db, user)
    report = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version_id).first()
    if report and DatasetWorkflowService(db).refresh_semantic_report(report):
        db.commit()
    return None if not report else semantic_payload(report)


@router.get("/versions/{version_id}/compare")
def compare_versions(version_id: int, against_version_id: int = Query(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    current = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).first()
    against = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == against_version_id,
        Dataset.study.has(owner_id=user.id),
    ).first()
    if not current or not against or current.dataset_id != against.dataset_id:
        raise ValueError("Comparable dataset versions were not found")
    configuration = db.get(DatasetConfiguration, current.configuration_id)
    diff = SemanticDiffService().compare(pd.read_csv(against.immutable_file_path), pd.read_csv(current.immutable_file_path), configuration.target_column)
    return {
        "previous_version_id": against.id,
        "current_version_id": current.id,
        "previous_version_number": against.version_number,
        "current_version_number": current.version_number,
        "scm_score": diff["scm_score"],
        "dsi_score": diff["dsi_score"],
        "ruleset_version": diff["ruleset_version"],
        "report": diff["report"],
    }


@router.get("/versions/{version_id}/recreation-bundle")
def recreation_bundle(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.query(DatasetVersion).join(Dataset).filter(
        DatasetVersion.id == version_id,
        Dataset.study.has(owner_id=user.id),
    ).options(selectinload(DatasetVersion.fingerprint)).first()
    if not version:
        raise ValueError("Dataset version not found")
    dataset = db.get(Dataset, version.dataset_id)
    configuration = db.get(DatasetConfiguration, version.configuration_id)
    profile_row = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
    diagnosis_row = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
    return {
        "bundle_type": "fedrepro.dataset_version.recreation",
        "bundle_version": "1.0",
        "study_id": dataset.study_id,
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "version_id": version.id,
        "version_number": version.version_number,
        "parent_version_id": version.parent_version_id,
        "version_notes": version.version_notes,
        "dataset_shape": {"rows": version.row_count, "columns": version.column_count},
        "fingerprint_algorithm": version.fingerprint.algorithm_version,
        "expected_hashes": {
            "file_hash": version.fingerprint.file_hash,
            "schema_hash": version.fingerprint.schema_hash,
            "metadata_hash": version.fingerprint.metadata_hash,
            "configuration_hash": configuration.configuration_hash,
            "combined_fingerprint": version.fingerprint.combined_fingerprint,
        },
        "configuration": {
            "id": configuration.id,
            "task_type": configuration.task_type,
            "target_column": configuration.target_column,
            "primary_metric": configuration.primary_metric,
            "validation_strategy": configuration.validation_strategy,
            "feature_selection_mode": configuration.feature_selection_mode,
            "selected_features": configuration.selected_features_json,
            "scaling_strategy": configuration.scaling_strategy,
        },
        "evidence": {
            "profile_report_id": profile_row.id if profile_row else None,
            "diagnosis_report_id": diagnosis_row.id if diagnosis_row else None,
            "created_at": version.created_at,
        },
    }


@router.post("/versions/recreate/verify")
async def verify_recreation(file: UploadFile = File(...), bundle_json: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        bundle = json.loads(bundle_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Recreation bundle is not valid JSON") from exc
    version_id = bundle.get("version_id")
    if version_id:
        version_detail(int(version_id), db, user)
    expected = bundle.get("expected_hashes") or {}
    configuration = bundle.get("configuration") or {}
    normalized_config = {key: configuration.get(key) for key in ("target_column", "primary_metric", "validation_strategy", "feature_selection_mode", "selected_features", "scaling_strategy")}
    actual_config_hash = canonical_hash({"task_type": configuration.get("task_type"), **normalized_config}) if configuration.get("task_type") else None
    if file.filename and Path(file.filename).suffix.lower() != ".csv":
        raise ValueError("Only CSV files can be verified")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as handle:
        path = Path(handle.name)
        while chunk := await file.read(1024 * 1024):
            handle.write(chunk)
    try:
        frame = pd.read_csv(path)
        metadata = DatasetWorkflowService.metadata(frame)
        fingerprint = FingerprintService().generate(str(path), frame, metadata, actual_config_hash or expected.get("configuration_hash", ""))
        checks = [
            _recreation_check("file_hash", fingerprint["file_hash"], expected.get("file_hash")),
            _recreation_check("schema_hash", fingerprint["schema_hash"], expected.get("schema_hash")),
            _recreation_check("metadata_hash", fingerprint["metadata_hash"], expected.get("metadata_hash")),
            _recreation_check("configuration_hash", actual_config_hash, expected.get("configuration_hash")),
            _recreation_check("combined_fingerprint", fingerprint["combined_fingerprint"], expected.get("combined_fingerprint")),
            _recreation_check("fingerprint_algorithm", fingerprint["algorithm_version"], bundle.get("fingerprint_algorithm")),
        ]
        expected_checks = [item for item in checks if item["expected"]]
        passed_checks = sum(1 for item in expected_checks if item["matched"])
        expected_shape = bundle.get("dataset_shape") or {}
        row_delta = int(len(frame)) - int(expected_shape.get("rows") or len(frame))
        column_delta = int(len(frame.columns)) - int(expected_shape.get("columns") or len(frame.columns))
        shape_match = row_delta == 0 and column_delta == 0
        matched = bool(expected_checks) and all(item["matched"] for item in expected_checks)
        similarity_rate = round((passed_checks / len(expected_checks)) * 100, 2) if expected_checks else 0
        return {
            "matched": matched,
            "status": "match" if matched else "mismatch",
            "similarity_rate": similarity_rate,
            "metrics": {
                "passed_checks": passed_checks,
                "total_checks": len(expected_checks),
                "shape_match": shape_match,
                "row_delta": row_delta,
                "column_delta": column_delta,
            },
            "checks": checks,
            "candidate": {
                "filename": file.filename,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "column_names": list(frame.columns),
                "metadata": metadata,
                "fingerprint": fingerprint,
            },
            "bundle": {
                "version_id": version_id,
                "version_number": bundle.get("version_number"),
                "dataset_name": bundle.get("dataset_name"),
                "configuration": configuration,
                "expected_shape": bundle.get("dataset_shape"),
            },
        }
    finally:
        path.unlink(missing_ok=True)


@router.get("/versions/{version_id}/profile")
def profile(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version_detail(version_id, db, user)
    report = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version_id).first()
    if not report:
        raise ValueError("Profile report not found")
    return {"id": report.id, "version_id": version_id, "profiler_version": report.profiler_version, "report": report.report_json, "created_at": report.created_at}


@router.get("/versions/{version_id}/diagnosis")
def diagnosis(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version_detail(version_id, db, user)
    report = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version_id).first()
    if not report:
        raise ValueError("Diagnosis report not found")
    score_breakdown = _latest_score_breakdown(db, report.id)
    return {"id": report.id, "version_id": version_id, "findings": report.findings_json, "mlrs_score": report.mlrs_score, "lrs_score": report.lrs_score, "score_breakdown": score_breakdown, "mlrs_components": (score_breakdown or {}).get("mlrs_components"), "lrs_components": (score_breakdown or {}).get("lrs_components"), "ruleset_version": report.ruleset_version, "created_at": report.created_at}


@router.get("/versions/{version_id}/diagnosis-contract")
def diagnosis_contract(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.get(DatasetVersion, version_id)
    if not version:
        raise ValueError("Version not found")
    study = StudyService(db).get_owned(version.dataset.study_id, user.id)
    report = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version_id).first()
    profile = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version_id).first()
    if not report:
        raise ValueError("Diagnosis report not found")
    return DiagnosisContractService().build(study, version, profile, report)


@router.get("/versions/{version_id}/diagnosis-report")
def diagnosis_report(version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    version = db.get(DatasetVersion, version_id)
    if not version:
        raise ValueError("Version not found")
    study = StudyService(db).get_owned(version.dataset.study_id, user.id)
    path = DiagnosisReportExportService(db).build(study, version)
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", filename=path.name)


def _recreation_check(name: str, actual, expected):
    return {"name": name, "actual": actual, "expected": expected, "matched": bool(expected) and actual == expected}


def _latest_report(db: Session, action: str, entity_type: str, entity_id: int):
    return db.query(ActivityLog).filter(
        ActivityLog.action == action,
        ActivityLog.entity_type == entity_type,
        ActivityLog.entity_id == entity_id,
    ).order_by(ActivityLog.created_at.desc()).first()


def _has_registration_column_inventory(payload):
    if not isinstance(payload, dict):
        return False
    columns = payload.get("columns")
    if isinstance(columns, list) and columns:
        return True
    return any(section.get("title") == "Column Evidence" for section in payload.get("sections") or [] if isinstance(section, dict))


def _latest_score_breakdown(db: Session, diagnosis_report_id: int):
    report = _latest_report(db, "diagnosis.score_breakdown", "diagnosis_report", diagnosis_report_id)
    return report.details_json if report else None


def _diagnosis_status(version, profile_row, diagnosis_row, semantic_row=None):
    if not diagnosis_row:
        return "Not Diagnosed"
    if not profile_row:
        return "Recompute Available"
    if profile_row.profiler_version != ProfilingService.profiler_version:
        return "Recompute Available"
    if diagnosis_row.ruleset_version != DiagnosisService.ruleset_version:
        return "Recompute Available"
    if version.parent_version_id and not semantic_row:
        return "Recompute Available"
    if semantic_row and semantic_row.ruleset_version != SemanticDiffService.ruleset_version:
        return "Recompute Available"
    return "Diagnosed"


def registration_payload(item):
    return {"id": item.id, "dataset_id": item.dataset_id, "original_filename": item.original_filename, "file_size": item.file_size, "version_notes": item.version_notes, "metadata": item.metadata_json, "validation": item.validation_json, "status": item.status, "created_at": item.created_at}


def dataset_payload(item, db: Session | None = None):
    versions = []
    for row in item.versions:
        configuration = db.get(DatasetConfiguration, row.configuration_id) if db else None
        profile_row = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == row.id).first() if db else None
        diagnosis_row = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == row.id).first() if db else None
        semantic_row = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == row.id).first() if db else None
        diagnosis_status = _diagnosis_status(row, profile_row, diagnosis_row, semantic_row)
        versions.append({
            "id": row.id,
            "registration_id": row.registration_id,
            "parent_version_id": row.parent_version_id,
            "version_number": row.version_number,
            "row_count": row.row_count,
            "column_count": row.column_count,
            "file_hash": row.file_hash,
            "version_notes": row.version_notes,
            "generation_method": row.generation_method,
            "diagnosis_status": diagnosis_status,
            "diagnosis": None if not diagnosis_row else {"id": diagnosis_row.id, "mlrs_score": diagnosis_row.mlrs_score, "lrs_score": diagnosis_row.lrs_score, "finding_count": len(diagnosis_row.findings_json)},
            "configuration": None if not configuration else {
                "id": configuration.id,
                "task_type": configuration.task_type,
                "target_column": configuration.target_column,
                "primary_metric": configuration.primary_metric,
                "validation_strategy": configuration.validation_strategy,
                "feature_selection_mode": configuration.feature_selection_mode,
                "selected_features": configuration.selected_features_json,
                "scaling_strategy": configuration.scaling_strategy,
                "configuration_hash": configuration.configuration_hash,
            },
            "fingerprint": None if not row.fingerprint else {"file_hash": row.fingerprint.file_hash, "schema_hash": row.fingerprint.schema_hash, "metadata_hash": row.fingerprint.metadata_hash, "combined_fingerprint": row.fingerprint.combined_fingerprint, "algorithm_version": row.fingerprint.algorithm_version},
            "created_at": row.created_at,
        })
    return {"id": item.id, "study_id": item.study_id, "name": item.name, "created_at": item.created_at, "registrations": [registration_payload(row) for row in item.registrations], "versions": versions}


def semantic_payload(item):
    return {"id": item.id, "previous_version_id": item.previous_version_id, "current_version_id": item.current_version_id, "scm_score": item.scm_score, "dsi_score": item.dsi_score, "ruleset_version": item.ruleset_version, "report": item.report_json, "created_at": item.created_at}


def version_bundle(db, version):
    configuration = db.get(DatasetConfiguration, version.configuration_id)
    diff = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
    profile_row = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
    diagnosis_row = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
    score_breakdown = _latest_score_breakdown(db, diagnosis_row.id) if diagnosis_row else None
    variant_record = db.query(VariantGenerationRecord).filter(VariantGenerationRecord.variant_version_id == version.id).order_by(VariantGenerationRecord.created_at.desc()).first()
    diagnosis_status = _diagnosis_status(version, profile_row, diagnosis_row, diff)
    return {"id": version.id, "dataset_id": version.dataset_id, "version_number": version.version_number, "parent_version_id": version.parent_version_id, "version_notes": version.version_notes, "file_hash": version.file_hash, "row_count": version.row_count, "column_count": version.column_count, "generation_method": version.generation_method, "diagnosis_status": diagnosis_status, "configuration": {"id": configuration.id, "task_type": configuration.task_type, "target_column": configuration.target_column, "primary_metric": configuration.primary_metric, "validation_strategy": configuration.validation_strategy, "feature_selection_mode": configuration.feature_selection_mode, "selected_features": configuration.selected_features_json, "scaling_strategy": configuration.scaling_strategy, "configuration_hash": configuration.configuration_hash}, "fingerprint": {"file_hash": version.fingerprint.file_hash, "schema_hash": version.fingerprint.schema_hash, "metadata_hash": version.fingerprint.metadata_hash, "combined_fingerprint": version.fingerprint.combined_fingerprint, "algorithm_version": version.fingerprint.algorithm_version}, "semantic_diff": None if not diff else semantic_payload(diff), "profile_report_id": profile_row.id if profile_row else None, "variant_record": None if not variant_record else {"id": variant_record.id, "job_id": variant_record.job_id, "pipeline_id": variant_record.pipeline_id, "vrs_score": variant_record.vrs_score, "vrs_rank": variant_record.vrs_rank, "goal_satisfaction": variant_record.goal_satisfaction, "mlrs_before": variant_record.mlrs_before, "mlrs_after": variant_record.mlrs_after, "lrs_after": variant_record.lrs_after, "steps": variant_record.pipeline_steps_json or [], "explanation": variant_record.explanation_json or {}}, "diagnosis": None if not diagnosis_row else {"id": diagnosis_row.id, "mlrs_score": diagnosis_row.mlrs_score, "lrs_score": diagnosis_row.lrs_score, "finding_count": len(diagnosis_row.findings_json), "score_breakdown": score_breakdown, "mlrs_components": (score_breakdown or {}).get("mlrs_components"), "lrs_components": (score_breakdown or {}).get("lrs_components")}, "created_at": version.created_at}
