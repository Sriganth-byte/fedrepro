import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.entities import ActivityLog, AIGeneratedExplanation, Dataset, DatasetConfiguration, DatasetProfileReport, DatasetVersion, DiagnosisReport, SemanticDiffReport, User
from app.schemas.contracts import ExplanationRequest
from app.services.ai_explanation_service import AIExplanationService
from app.services.dataset_workflow_service import DatasetWorkflowService
from app.services.diagnosis_contract_service import DiagnosisContractService
from app.services.study_service import StudyService
from app.utilities.hashing import canonical_hash

router = APIRouter(prefix="/ai", tags=["optional AI explanations"])


def usable_cached_explanation(record: AIGeneratedExplanation | None) -> AIGeneratedExplanation | None:
    if record and not AIExplanationService.is_fallback_content(record.content):
        return record
    return None


@router.post("/studies/{study_id}/explain", status_code=201)
def explain(study_id: int, payload: ExplanationRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    evidence = resolve_evidence(db, study, payload.explanation_type, payload.source_entity_id)
    record = AIExplanationService(db).explain(study, payload.explanation_type, payload.source_entity_id, evidence)
    response = {"id": record.id, "type": record.explanation_type, "model": record.model, "prompt_version": record.prompt_version, "source_evidence_hash": record.source_evidence_hash, "content": record.content, "created_at": record.created_at}
    if payload.explanation_type == "version_analysis":
        try:
            response["structured_content"] = json.loads(record.content)
        except json.JSONDecodeError:
            response["structured_content"] = None
    return response


@router.post("/studies/{study_id}/semantic-diffs/{diff_id}/metrics-interpretation", status_code=201)
def semantic_metrics_interpretation(study_id: int, diff_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    evidence = resolve_evidence(db, study, "semantic_metrics", diff_id)
    evidence_hash = canonical_hash(evidence)
    cached = db.query(AIGeneratedExplanation).filter(
        AIGeneratedExplanation.study_id == study.id,
        AIGeneratedExplanation.explanation_type == "semantic_metrics",
        AIGeneratedExplanation.source_entity_id == diff_id,
        AIGeneratedExplanation.source_evidence_hash == evidence_hash,
        AIGeneratedExplanation.prompt_version == AIExplanationService.prompt_version,
    ).order_by(AIGeneratedExplanation.created_at.desc()).first()
    cached = usable_cached_explanation(cached)
    record = cached or AIExplanationService(db).explain(study, "semantic_metrics", diff_id, evidence)
    return {"id": record.id, "type": record.explanation_type, "model": record.model, "prompt_version": record.prompt_version, "source_evidence_hash": record.source_evidence_hash, "content": record.content, "created_at": record.created_at, "cached": bool(cached)}


@router.post("/studies/{study_id}/semantic-diffs/{diff_id}/interpretation", status_code=201)
def semantic_diff_interpretation(study_id: int, diff_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    evidence = resolve_evidence(db, study, "semantic_diff_interpretation", diff_id)
    evidence_hash = canonical_hash(evidence)
    cached = db.query(AIGeneratedExplanation).filter(
        AIGeneratedExplanation.study_id == study.id,
        AIGeneratedExplanation.explanation_type == "semantic_diff_interpretation",
        AIGeneratedExplanation.source_entity_id == diff_id,
        AIGeneratedExplanation.source_evidence_hash == evidence_hash,
        AIGeneratedExplanation.prompt_version == AIExplanationService.prompt_version,
    ).order_by(AIGeneratedExplanation.created_at.desc()).first()
    cached = usable_cached_explanation(cached)
    record = cached or AIExplanationService(db).explain(study, "semantic_diff_interpretation", diff_id, evidence)
    return {"id": record.id, "type": record.explanation_type, "model": record.model, "prompt_version": record.prompt_version, "source_evidence_hash": record.source_evidence_hash, "content": record.content, "created_at": record.created_at, "cached": bool(cached)}


@router.post("/studies/{study_id}/versions/{version_id}/executive-summary", status_code=201)
def version_executive_summary(study_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    evidence = resolve_evidence(db, study, "dataset_executive_summary", version_id)
    evidence_hash = canonical_hash(evidence)
    cached = db.query(AIGeneratedExplanation).filter(
        AIGeneratedExplanation.study_id == study.id,
        AIGeneratedExplanation.explanation_type == "dataset_executive_summary",
        AIGeneratedExplanation.source_entity_id == version_id,
        AIGeneratedExplanation.source_evidence_hash == evidence_hash,
        AIGeneratedExplanation.prompt_version == AIExplanationService.prompt_version,
    ).order_by(AIGeneratedExplanation.created_at.desc()).first()
    cached = usable_cached_explanation(cached)
    record = cached or AIExplanationService(db).explain(study, "dataset_executive_summary", version_id, evidence)
    return {"id": record.id, "type": record.explanation_type, "version_id": version_id, "model": record.model, "prompt_version": record.prompt_version, "source_evidence_hash": record.source_evidence_hash, "content": record.content, "created_at": record.created_at, "cached": bool(cached)}


@router.post("/studies/{study_id}/versions/{version_id}/executive-summary/stream")
def version_executive_summary_stream(study_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    evidence = resolve_evidence(db, study, "dataset_executive_summary", version_id)
    stream = AIExplanationService(db).explain_stream(study, "dataset_executive_summary", version_id, evidence)
    return StreamingResponse(
        stream,
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/studies/{study_id}/versions/{version_id}/diagnosis-interpretation", status_code=201)
def version_diagnosis_interpretation(study_id: int, version_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    study = StudyService(db).get_owned(study_id, user.id)
    evidence = resolve_evidence(db, study, "diagnosis_report_interpretation", version_id)
    diagnosis_id = evidence["diagnosis"]["id"]
    evidence_hash = canonical_hash(evidence)
    cached = db.query(AIGeneratedExplanation).filter(
        AIGeneratedExplanation.study_id == study.id,
        AIGeneratedExplanation.explanation_type == "diagnosis_report_interpretation",
        AIGeneratedExplanation.source_entity_id == diagnosis_id,
        AIGeneratedExplanation.source_evidence_hash == evidence_hash,
        AIGeneratedExplanation.prompt_version == AIExplanationService.prompt_version,
    ).order_by(AIGeneratedExplanation.created_at.desc()).first()
    cached = usable_cached_explanation(cached)
    record = cached or AIExplanationService(db).explain(study, "diagnosis_report_interpretation", diagnosis_id, evidence)
    return {"id": record.id, "type": record.explanation_type, "version_id": version_id, "model": record.model, "prompt_version": record.prompt_version, "source_evidence_hash": record.source_evidence_hash, "content": record.content, "created_at": record.created_at, "cached": bool(cached)}


def resolve_evidence(db: Session, study, kind: str, entity_id: int) -> dict:
    if kind == "study_description":
        return {"name": study.name, "ml_task": study.ml_task, "description": study.description, "problem_objective": study.problem_objective, "intended_use_case": study.intended_use_case}
    if kind in {"version_analysis", "dataset_executive_summary", "dataset_explanation_report"}:
        selected = db.query(DatasetVersion).join(Dataset).filter(
            DatasetVersion.id == entity_id,
            Dataset.study_id == study.id,
        ).first()
        if not selected:
            raise ValueError("Version analysis source does not belong to the study")
        dataset = db.get(Dataset, selected.dataset_id)
        configuration = db.get(DatasetConfiguration, selected.configuration_id)
        profile = db.query(DatasetProfileReport).filter(
            DatasetProfileReport.version_id == selected.id
        ).first()
        if not profile:
            raise ValueError("Dataset profile is unavailable for this version")
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
        diffs = {item.current_version_id: item for item in diff_rows}
        return {
            "ml_study": {
                "id": study.id,
                "name": study.name,
                "ml_task": study.ml_task,
                "description": study.description,
                "problem_objective": study.problem_objective,
                "intended_use_case": study.intended_use_case,
            },
            "dataset": {"id": dataset.id, "name": dataset.name},
            "selected_version": {
                "id": selected.id,
                "version_number": selected.version_number,
                "row_count": selected.row_count,
                "column_count": selected.column_count,
                "file_hash": selected.file_hash,
                "combined_fingerprint": selected.fingerprint.combined_fingerprint if selected.fingerprint else None,
                "fingerprint_algorithm_version": selected.fingerprint.algorithm_version if selected.fingerprint else None,
                "configuration_hash": configuration.configuration_hash,
                "target_column": configuration.target_column,
                "primary_metric": configuration.primary_metric,
                "validation_strategy": configuration.validation_strategy,
                "feature_selection_mode": configuration.feature_selection_mode,
                "selected_features": configuration.selected_features_json,
                "scaling_strategy": configuration.scaling_strategy,
            },
            "dataset_profile": compact_profile(profile.report_json),
            "version_history": [{
                "id": item.id,
                "version_number": item.version_number,
                "row_count": item.row_count,
                "column_count": item.column_count,
                "version_notes": item.version_notes,
                "semantic_diff_from_previous": None if item.id not in diffs else compact_semantic_diff(diffs[item.id]),
            } for item in versions],
        }
    if kind in {"semantic_metrics", "semantic_diff_interpretation"}:
        report = db.get(SemanticDiffReport, entity_id)
        if not report:
            raise ValueError("Semantic metric source report not found")
        current = db.query(DatasetVersion).join(Dataset).filter(DatasetVersion.id == report.current_version_id, Dataset.study_id == study.id).first()
        previous = db.get(DatasetVersion, report.previous_version_id)
        if not current:
            raise ValueError("Semantic metric source does not belong to the study")
        payload = {
            "scm_score": report.scm_score,
            "dsi_score": report.dsi_score,
            "ruleset_version": report.ruleset_version,
            "previous_version_id": report.previous_version_id,
            "current_version_id": report.current_version_id,
            "previous_version_number": previous.version_number if previous else None,
            "current_version_number": current.version_number,
        }
        if kind == "semantic_diff_interpretation":
            payload.update({
                "study": {
                    "name": study.name,
                    "ml_task": study.ml_task,
                    "objective": study.problem_objective,
                    "intended_use": study.intended_use_case,
                },
                "current_version": {
                    "version_number": current.version_number,
                    "rows": current.row_count,
                    "columns": current.column_count,
                    "notes": current.version_notes,
                },
                "semantic_diff": compact_semantic_diff(report),
            })
        return payload
    if kind == "diagnosis_report_interpretation":
        selected = db.query(DatasetVersion).join(Dataset).filter(
            DatasetVersion.id == entity_id,
            Dataset.study_id == study.id,
        ).first()
        if not selected:
            raise ValueError("Diagnosis interpretation source does not belong to the study")
        dataset = db.get(Dataset, selected.dataset_id)
        configuration = db.get(DatasetConfiguration, selected.configuration_id)
        profile = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == selected.id).first()
        diagnosis = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == selected.id).first()
        if not profile or not diagnosis:
            raise ValueError("Diagnosis evidence is unavailable for this version")
        semantic = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == selected.id).first()
        if semantic and DatasetWorkflowService(db).refresh_semantic_report(semantic):
            db.commit()
        contract = DiagnosisContractService().build(study, selected, profile, diagnosis)
        return {
            "ml_study": {
                "id": study.id,
                "name": study.name,
                "ml_task": study.ml_task,
                "description": study.description,
                "problem_objective": study.problem_objective,
                "intended_use_case": study.intended_use_case,
            },
            "dataset": {"id": dataset.id, "name": dataset.name},
            "selected_version": {
                "id": selected.id,
                "version_number": selected.version_number,
                "parent_version_id": selected.parent_version_id,
                "row_count": selected.row_count,
                "column_count": selected.column_count,
                "version_notes": selected.version_notes,
                "combined_fingerprint": selected.fingerprint.combined_fingerprint if selected.fingerprint else None,
                "configuration_hash": configuration.configuration_hash,
                "target_column": configuration.target_column,
                "primary_metric": configuration.primary_metric,
                "validation_strategy": configuration.validation_strategy,
                "feature_selection_mode": configuration.feature_selection_mode,
                "scaling_strategy": configuration.scaling_strategy,
            },
            "dataset_profile": compact_profile(profile.report_json),
            "diagnosis": {
                "id": diagnosis.id,
                "mlrs_score": diagnosis.mlrs_score,
                "lrs_score": diagnosis.lrs_score,
                "score_breakdown": latest_score_breakdown(db, diagnosis.id),
                "ruleset_version": diagnosis.ruleset_version,
                "findings": diagnosis.findings_json,
                "created_at": diagnosis.created_at,
            },
            "semantic_diff_from_previous": None if not semantic else compact_semantic_diff(semantic),
            "diagnosis_contract": contract,
        }
    model = {"semantic_diff": SemanticDiffReport, "profile": DatasetProfileReport, "diagnosis": DiagnosisReport}[kind]
    report = db.get(model, entity_id)
    if not report:
        raise ValueError("Explanation source report not found")
    version_id = report.current_version_id if kind == "semantic_diff" else report.version_id
    if not db.query(DatasetVersion).join(Dataset).filter(DatasetVersion.id == version_id, Dataset.study_id == study.id).first():
        raise ValueError("Explanation source does not belong to the study")
    if kind == "semantic_diff":
        return {"scm_score": report.scm_score, "dsi_score": report.dsi_score, "report": report.report_json}
    if kind == "profile":
        return report.report_json
    return {"mlrs_score": report.mlrs_score, "lrs_score": report.lrs_score, "score_breakdown": latest_score_breakdown(db, report.id), "findings": report.findings_json}


def latest_score_breakdown(db: Session, diagnosis_report_id: int):
    row = db.query(ActivityLog).filter(
        ActivityLog.action == "diagnosis.score_breakdown",
        ActivityLog.entity_type == "diagnosis_report",
        ActivityLog.entity_id == diagnosis_report_id,
    ).order_by(ActivityLog.created_at.desc()).first()
    return row.details_json if row else None


def compact_profile(report: dict) -> dict:
    columns = []
    for item in report.get("columns", []):
        column = {
            "name": item.get("name"),
            "role": item.get("role"),
            "data_type": item.get("data_type"),
            "missing_count": item.get("missing_count"),
            "missing_ratio": item.get("missing_ratio"),
            "unique_count": item.get("unique_count"),
            "outlier_count": item.get("outlier_count"),
        }
        if item.get("statistics"):
            column["statistics"] = item["statistics"]
        if item.get("top_values"):
            column["top_values"] = item["top_values"][:5]
        columns.append(column)
    return {
        "summary": report.get("summary", {}),
        "task_type": report.get("task_type"),
        "task_profile": report.get("task_profile", {}),
        "high_correlations": report.get("high_correlations", []),
        "columns": columns,
    }


def compact_semantic_diff(report) -> dict:
    details = report.report_json
    numeric_changes = {
        column: change
        for column, change in details.get("numeric_distribution_changes", {}).items()
        if change.get("normalized_shift_score", 0) > 0.001
        or any(abs(float(value or 0)) > 0.000001 for value in change.get("delta", {}).values())
    }
    return {
        "scm_score": report.scm_score,
        "dsi_score": report.dsi_score,
        "ruleset_version": report.ruleset_version,
        "schema": {
            "columns_added": details.get("columns_added", []),
            "columns_added_details": details.get("columns_added_details", {}),
            "columns_removed": details.get("columns_removed", []),
            "columns_removed_details": details.get("columns_removed_details", {}),
            "data_type_changes": details.get("data_type_changes", {}),
        },
        "rows": {
            "previous": details.get("row_count_previous"),
            "current": details.get("row_count_current"),
            "net_change": details.get("row_count_change"),
            "row_content_change": details.get("row_content_change"),
            "duplicate_rows": details.get("duplicate_rows"),
        },
        "missingness": {
            "overall_ratio_change": details.get("missing_ratio_change"),
            "changes_by_column": details.get("missingness_changes_by_column", {}),
        },
        "numeric_distribution_changes": numeric_changes,
        "categorical_distribution_changes": details.get("categorical_distribution_changes", {}),
        "target_distribution_change": details.get("target_distribution_change", {}),
    }
