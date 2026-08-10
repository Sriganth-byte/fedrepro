from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.api.routes.ai import resolve_evidence
from app.core.database import SessionLocal
from app.models.entities import (
    AIGeneratedExplanation,
    ActivityLog,
    Dataset,
    DatasetConfiguration,
    DatasetFingerprint,
    DatasetProfileReport,
    DatasetRegistration,
    DatasetVersion,
    DiagnosisReport,
    SemanticDiffReport,
)
from app.services.ai_explanation_service import AIExplanationService
from app.services.dataset_explanation_report_service import DatasetExplanationReportService
from app.services.dataset_workflow_service import DatasetWorkflowService
from app.services.diagnosis_service import DiagnosisService
from app.services.fingerprint_service import FingerprintService
from app.services.profiling_service import ProfilingService


AI_TYPES_BY_VERSION = (
    "version_analysis",
    "dataset_executive_summary",
    "dataset_explanation_report",
    "diagnosis_report_interpretation",
)
AI_TYPES_BY_DIFF = ("semantic_metrics", "semantic_diff_interpretation")


def config_payload(configuration: DatasetConfiguration) -> dict:
    return {
        "task_type": configuration.task_type,
        "target_column": configuration.target_column,
        "primary_metric": configuration.primary_metric,
        "validation_strategy": configuration.validation_strategy,
        "feature_selection_mode": configuration.feature_selection_mode,
        "selected_features": configuration.selected_features_json or [],
        "scaling_strategy": configuration.scaling_strategy,
    }


def upsert_fingerprint(db, version: DatasetVersion, frame, metadata, configuration: DatasetConfiguration):
    fingerprint_data = FingerprintService().generate(
        version.immutable_file_path,
        frame,
        metadata,
        configuration.configuration_hash,
    )
    row = db.query(DatasetFingerprint).filter(DatasetFingerprint.version_id == version.id).first()
    if not row:
        row = DatasetFingerprint(version_id=version.id, **fingerprint_data)
        db.add(row)
    else:
        for key, value in fingerprint_data.items():
            setattr(row, key, value)
    version.file_hash = fingerprint_data["file_hash"]
    version.row_count = int(len(frame))
    version.column_count = int(len(frame.columns))
    return row


def upsert_semantic(db, version: DatasetVersion, frame, configuration: DatasetConfiguration):
    if not version.parent_version_id:
        return None, None
    parent = db.get(DatasetVersion, version.parent_version_id)
    if not parent:
        return None, None
    parent_frame = pd.read_csv(parent.immutable_file_path)
    payload = ProfilingSafeSemantic.compare(parent_frame, frame, configuration.target_column)
    row = db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
    if not row:
        row = SemanticDiffReport(
            previous_version_id=parent.id,
            current_version_id=version.id,
            report_json=payload["report"],
            scm_score=payload["scm_score"],
            dsi_score=payload["dsi_score"],
            ruleset_version=payload["ruleset_version"],
        )
        db.add(row)
    else:
        row.previous_version_id = parent.id
        row.report_json = payload["report"]
        row.scm_score = payload["scm_score"]
        row.dsi_score = payload["dsi_score"]
        row.ruleset_version = payload["ruleset_version"]
    return row, payload


class ProfilingSafeSemantic:
    @staticmethod
    def compare(previous, current, target_column):
        from app.services.semantic_diff_service import SemanticDiffService

        return SemanticDiffService().compare(previous, current, target_column)


def upsert_profile(db, version: DatasetVersion, frame, configuration: DatasetConfiguration, study):
    payload = ProfilingService().profile(frame, study.ml_task, config_payload(configuration))
    row = db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
    if not row:
        row = DatasetProfileReport(
            version_id=version.id,
            configuration_id=configuration.id,
            report_json=payload,
            profiler_version=ProfilingService.profiler_version,
        )
        db.add(row)
        db.flush()
    else:
        row.configuration_id = configuration.id
        row.report_json = payload
        row.profiler_version = ProfilingService.profiler_version
    return row, payload


def upsert_diagnosis(db, version, profile_row, profile_payload, semantic_payload, configuration, study):
    payload = DiagnosisService().diagnose(
        profile_payload,
        semantic_payload,
        {
            "source_version_id": version.parent_version_id,
            "version_number": version.version_number,
            "version_notes": version.version_notes,
        },
        config_payload(configuration),
    )
    row = db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
    if not row:
        row = DiagnosisReport(
            version_id=version.id,
            profile_report_id=profile_row.id,
            findings_json=payload["findings"],
            mlrs_score=payload["mlrs_score"],
            lrs_score=payload["lrs_score"],
            ruleset_version=payload["ruleset_version"],
        )
        db.add(row)
        db.flush()
    else:
        row.profile_report_id = profile_row.id
        row.findings_json = payload["findings"]
        row.mlrs_score = payload["mlrs_score"]
        row.lrs_score = payload["lrs_score"]
        row.ruleset_version = payload["ruleset_version"]
    db.add(ActivityLog(
        study_id=study.id,
        actor_id=None,
        action="diagnosis.score_breakdown",
        entity_type="diagnosis_report",
        entity_id=row.id,
        details_json=payload["score_breakdown"],
    ))
    return row


def write_deterministic_reports(db, study, dataset, registration, version, configuration, fingerprint, profile, diagnosis, semantic):
    db.add(ActivityLog(
        study_id=study.id,
        actor_id=None,
        action="dataset.version_report",
        entity_type="dataset_version",
        entity_id=version.id,
        details_json=DatasetExplanationReportService.version_report(
            study,
            dataset,
            registration,
            version,
            configuration,
            fingerprint,
            profile,
            diagnosis,
            semantic,
        ),
    ))
    if registration:
        db.add(ActivityLog(
            study_id=study.id,
            actor_id=None,
            action="dataset.registration_report",
            entity_type="registration",
            entity_id=registration.id,
            details_json=DatasetExplanationReportService.registration_report(study, dataset, registration),
        ))


def delete_ai_cache(db, study_id, version_id, diagnosis_id, semantic_id):
    db.query(AIGeneratedExplanation).filter(
        AIGeneratedExplanation.study_id == study_id,
        AIGeneratedExplanation.source_entity_id == version_id,
        AIGeneratedExplanation.explanation_type.in_((
            "version_analysis",
            "dataset_executive_summary",
            "dataset_explanation_report",
        )),
    ).delete(synchronize_session=False)
    if diagnosis_id:
        db.query(AIGeneratedExplanation).filter(
            AIGeneratedExplanation.study_id == study_id,
            AIGeneratedExplanation.source_entity_id == diagnosis_id,
            AIGeneratedExplanation.explanation_type == "diagnosis_report_interpretation",
        ).delete(synchronize_session=False)
    if semantic_id:
        db.query(AIGeneratedExplanation).filter(
            AIGeneratedExplanation.study_id == study_id,
            AIGeneratedExplanation.source_entity_id == semantic_id,
            AIGeneratedExplanation.explanation_type.in_(AI_TYPES_BY_DIFF),
        ).delete(synchronize_session=False)


def generate_ai_for_version(db, study, version, semantic, diagnosis):
    service = AIExplanationService(db)
    generated = []
    for kind in ("version_analysis", "dataset_executive_summary", "dataset_explanation_report"):
        evidence = resolve_evidence(db, study, kind, version.id)
        service.explain(study, kind, version.id, evidence)
        generated.append(kind)
    if diagnosis:
        evidence = resolve_evidence(db, study, "diagnosis_report_interpretation", version.id)
        service.explain(study, "diagnosis_report_interpretation", diagnosis.id, evidence)
        generated.append("diagnosis_report_interpretation")
    if semantic:
        for kind in AI_TYPES_BY_DIFF:
            evidence = resolve_evidence(db, study, kind, semantic.id)
            service.explain(study, kind, semantic.id, evidence)
            generated.append(kind)
    return generated


def generate_llm_report_log(db, study, version):
    evidence = resolve_evidence(db, study, "dataset_explanation_report", version.id)
    record = AIExplanationService(db).explain(study, "dataset_explanation_report", version.id, evidence)
    db.add(ActivityLog(
        study_id=study.id,
        actor_id=None,
        action="dataset.version_llm_report",
        entity_type="dataset_version",
        entity_id=version.id,
        details_json={
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
        },
    ))


def main():
    parser = argparse.ArgumentParser(description="Recompute FedRepro dataset evidence for every version.")
    parser.add_argument("--skip-ai", action="store_true", help="Only recompute deterministic metrics and reports.")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of versions for a smoke run.")
    parser.add_argument("--keep-ai-cache", action="store_true", help="Do not delete matching AI rows before generation.")
    args = parser.parse_args()

    db = SessionLocal()
    summary = {"versions": 0, "semantic": 0, "profiles": 0, "diagnoses": 0, "ai_records": 0, "errors": []}
    try:
        versions = db.query(DatasetVersion).join(Dataset).order_by(Dataset.study_id, DatasetVersion.dataset_id, DatasetVersion.version_number).all()
        if args.limit:
            versions = versions[: args.limit]
        print(f"Found {len(versions)} dataset version(s).")
        for version in versions:
            dataset = db.get(Dataset, version.dataset_id)
            study = dataset.study
            registration = db.get(DatasetRegistration, version.registration_id)
            configuration = db.get(DatasetConfiguration, version.configuration_id)
            try:
                frame = pd.read_csv(version.immutable_file_path)
                metadata = DatasetWorkflowService.metadata(frame)
                if registration:
                    registration.metadata_json = metadata
                    registration.file_size = Path(version.immutable_file_path).stat().st_size
                fingerprint = upsert_fingerprint(db, version, frame, metadata, configuration)
                semantic, semantic_payload = upsert_semantic(db, version, frame, configuration)
                profile, profile_payload = upsert_profile(db, version, frame, configuration, study)
                diagnosis = upsert_diagnosis(db, version, profile, profile_payload, semantic_payload, configuration, study)
                write_deterministic_reports(db, study, dataset, registration, version, configuration, fingerprint, profile, diagnosis, semantic)
                db.commit()
                summary["versions"] += 1
                summary["profiles"] += 1
                summary["diagnoses"] += 1
                if semantic:
                    summary["semantic"] += 1
                print(f"Recomputed deterministic evidence for study {study.id}, dataset {dataset.id}, V{version.version_number} (version_id={version.id}).")

                if not args.skip_ai:
                    if not args.keep_ai_cache:
                        delete_ai_cache(db, study.id, version.id, diagnosis.id if diagnosis else None, semantic.id if semantic else None)
                        db.commit()
                    generated = generate_ai_for_version(db, study, version, semantic, diagnosis)
                    generate_llm_report_log(db, study, version)
                    db.commit()
                    summary["ai_records"] += len(generated)
                    print(f"Generated AI artifacts for version_id={version.id}: {', '.join(generated)}.")
            except Exception as exc:
                db.rollback()
                message = f"version_id={version.id}: {type(exc).__name__}: {exc}"
                summary["errors"].append(message)
                print(f"ERROR {message}")
        print("Summary:", summary)
        if summary["errors"]:
            raise SystemExit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
