from datetime import datetime, timezone

from app.models.entities import Dataset, DatasetConfiguration, DatasetFingerprint, DatasetProfileReport, DatasetRegistration, DatasetVersion, DiagnosisReport, SemanticDiffReport, Study


def _value(value, fallback="Not Available"):
    return fallback if value is None or value == "" else value


def _metric(value):
    return None if value is None else round(float(value), 4)


class DatasetExplanationReportService:
    report_version = "dataset-explanation-1.0"

    @staticmethod
    def _registration_columns(metadata: dict) -> list[dict]:
        column_names = metadata.get("column_names") or []
        data_types = metadata.get("data_types") or {}
        missing_values = metadata.get("missing_values") or {}
        row_count = metadata.get("row_count") or 0
        columns = []
        for position, name in enumerate(column_names, start=1):
            missing_count = missing_values.get(name)
            missing_ratio = None
            if missing_count is not None and row_count:
                missing_ratio = round(float(missing_count) / float(row_count), 6)
            columns.append(
                {
                    "position": position,
                    "name": name,
                    "data_type": data_types.get(name),
                    "missing_count": missing_count,
                    "missing_ratio": missing_ratio,
                    "evidence_source": "registration_metadata",
                }
            )
        return columns

    @classmethod
    def registration_report(cls, study: Study, dataset: Dataset, registration: DatasetRegistration) -> dict:
        metadata = registration.metadata_json or {}
        columns = cls._registration_columns(metadata)
        return {
            "report_type": "dataset_registration_explanation",
            "report_version": cls.report_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "title": f"{dataset.name} dataset registration report",
            "summary": (
                f"{dataset.name} was registered for study {study.name}. "
                f"The uploaded artifact contains {_value(metadata.get('row_count'))} rows and "
                f"{_value(metadata.get('column_count'))} columns."
            ),
            "study": {
                "id": study.id,
                "name": study.name,
                "ml_task": study.ml_task,
                "objective": _value(study.problem_objective),
                "intended_use": _value(study.intended_use_case),
            },
            "dataset": {
                "id": dataset.id,
                "name": dataset.name,
                "registration_id": registration.id,
                "original_filename": registration.original_filename,
                "file_size": registration.file_size,
                "status": registration.status,
                "created_at": registration.created_at.isoformat() if registration.created_at else None,
            },
            "metrics": {
                "rows": metadata.get("row_count"),
                "columns": metadata.get("column_count"),
                "missing_cells": metadata.get("missing_total"),
                "duplicate_rows": metadata.get("duplicate_count"),
                "memory_usage_bytes": metadata.get("memory_usage_bytes"),
            },
            "columns": columns,
            "sections": [
                {
                    "title": "Dataset Identity",
                    "items": [
                        {"label": "Dataset", "value": dataset.name},
                        {"label": "Original file", "value": registration.original_filename},
                        {"label": "Registration status", "value": registration.status},
                    ],
                },
                {
                    "title": "Observed Structure",
                    "items": [
                        {"label": "Rows", "value": _value(metadata.get("row_count"))},
                        {"label": "Columns", "value": _value(metadata.get("column_count"))},
                        {"label": "Missing cells", "value": _value(metadata.get("missing_total"))},
                        {"label": "Duplicate rows", "value": _value(metadata.get("duplicate_count"))},
                    ],
                },
                {
                    "title": "Research Notes",
                    "items": [{"label": "Version notes", "value": _value(registration.version_notes)}],
                },
                {
                    "title": "Column Evidence",
                    "items": [
                        {"label": "Captured columns", "value": len(columns) if columns else "Not Available"},
                        {"label": "Data type evidence", "value": "Available" if any(item.get("data_type") for item in columns) else "Not Available"},
                        {"label": "Missingness evidence", "value": "Available" if any(item.get("missing_count") is not None for item in columns) else "Not Available"},
                    ],
                },
                {
                    "title": "Next Process",
                    "items": [
                        {"label": "Recommended action", "value": "Configure target and evaluation settings to create an immutable dataset version."},
                        {"label": "Evidence dependency", "value": "Versioning, fingerprinting, profiling, and diagnosis require configuration."},
                    ],
                },
            ],
        }

    @classmethod
    def version_report(
        cls,
        study: Study,
        dataset: Dataset,
        registration: DatasetRegistration,
        version: DatasetVersion,
        configuration: DatasetConfiguration,
        fingerprint: DatasetFingerprint | None,
        profile: DatasetProfileReport | None,
        diagnosis: DiagnosisReport | None,
        semantic: SemanticDiffReport | None,
    ) -> dict:
        semantic_report = semantic.report_json if semantic else {}
        profile_report = profile.report_json if profile else {}
        return {
            "report_type": "dataset_version_explanation",
            "report_version": cls.report_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "title": f"{dataset.name} V{version.version_number} evidence report",
            "summary": (
                f"Version V{version.version_number} is an immutable evidence artifact for {dataset.name}. "
                f"It contains {version.row_count} rows and {version.column_count} columns."
            ),
            "study": {
                "id": study.id,
                "name": study.name,
                "ml_task": study.ml_task,
                "objective": _value(study.problem_objective),
            },
            "version": {
                "id": version.id,
                "dataset_name": dataset.name,
                "version_number": version.version_number,
                "parent_version_id": version.parent_version_id,
                "version_notes": _value(version.version_notes),
                "rows": version.row_count,
                "columns": version.column_count,
                "created_at": version.created_at.isoformat() if version.created_at else None,
            },
            "configuration": {
                "id": configuration.id,
                "task_type": configuration.task_type,
                "target_column": _value(configuration.target_column),
                "primary_metric": _value(configuration.primary_metric),
                "validation_strategy": _value(configuration.validation_strategy),
                "feature_selection_mode": _value(configuration.feature_selection_mode),
                "scaling_strategy": _value(configuration.scaling_strategy),
                "configuration_hash": _value(configuration.configuration_hash),
            },
            "evidence": {
                "fingerprint_available": bool(fingerprint),
                "profile_report_id": profile.id if profile else None,
                "diagnosis_report_id": diagnosis.id if diagnosis else None,
                "semantic_diff_id": semantic.id if semantic else None,
                "recreation_bundle_available": bool(fingerprint and configuration.configuration_hash),
            },
            "metrics": {
                "scm_score": _metric(semantic.scm_score) if semantic else None,
                "dsi_score": _metric(semantic.dsi_score) if semantic else None,
                "mlrs_score": _metric(diagnosis.mlrs_score) if diagnosis else None,
                "lrs_score": _metric(diagnosis.lrs_score) if diagnosis else None,
                "finding_count": len(diagnosis.findings_json or []) if diagnosis else None,
                "row_count_change": semantic_report.get("row_count_change"),
                "column_count_change": semantic_report.get("column_count_change"),
                "missing_ratio_change": semantic_report.get("missing_ratio_change"),
                "duplicate_row_delta": (semantic_report.get("duplicate_rows") or {}).get("delta"),
                "profile_columns": len(profile_report.get("columns", {}) or {}) if isinstance(profile_report, dict) else None,
            },
            "sections": [
                {
                    "title": "Version Identity",
                    "items": [
                        {"label": "Dataset", "value": dataset.name},
                        {"label": "Version", "value": f"V{version.version_number}"},
                        {"label": "Parent version", "value": _value(version.parent_version_id, "Baseline")},
                        {"label": "Notes", "value": _value(version.version_notes)},
                    ],
                },
                {
                    "title": "Reproducibility Evidence",
                    "items": [
                        {"label": "Fingerprint", "value": "Available" if fingerprint else "Not Available"},
                        {"label": "Configuration hash", "value": _value(configuration.configuration_hash)},
                        {"label": "Recreation bundle", "value": "Available" if fingerprint and configuration.configuration_hash else "Not Available"},
                    ],
                },
                {
                    "title": "Research Metrics",
                    "items": [
                        {"label": "SCM", "value": _value(_metric(semantic.scm_score) if semantic else None)},
                        {"label": "DSI", "value": _value(_metric(semantic.dsi_score) if semantic else None)},
                        {"label": "MLRS", "value": _value(_metric(diagnosis.mlrs_score) if diagnosis else None)},
                        {"label": "LRS", "value": _value(_metric(diagnosis.lrs_score) if diagnosis else None)},
                    ],
                },
                {
                    "title": "Next Process",
                    "items": [
                        {"label": "Recommended action", "value": "Open diagnosis and create variant plans." if diagnosis else "Run dataset diagnosis."},
                        {"label": "Downstream use", "value": "Use this report with the recreation bundle when auditing or reproducing the dataset version."},
                    ],
                },
            ],
        }
