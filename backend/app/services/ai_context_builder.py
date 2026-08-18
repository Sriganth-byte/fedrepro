from sqlalchemy.orm import Session

from app.models.entities import ActivityLog, Dataset, DatasetConfiguration, DatasetProfileReport, DatasetVersion, DiagnosisReport, SemanticDiffReport, Study, VariantGenerationRecord


class AIContextBuilder:
    """Builds compact, evidence-only context for Ollama version analysis."""

    def __init__(self, db: Session):
        self.db = db

    def version_analysis(self, study: Study, version: DatasetVersion) -> dict:
        dataset = self.db.get(Dataset, version.dataset_id)
        configuration = self.db.get(DatasetConfiguration, version.configuration_id)
        profile = self.db.query(DatasetProfileReport).filter(DatasetProfileReport.version_id == version.id).first()
        diagnosis = self.db.query(DiagnosisReport).filter(DiagnosisReport.version_id == version.id).first()
        semantic = self.db.query(SemanticDiffReport).filter(SemanticDiffReport.current_version_id == version.id).first()
        variant = self.db.query(VariantGenerationRecord).filter(VariantGenerationRecord.variant_version_id == version.id).order_by(VariantGenerationRecord.created_at.desc()).first()
        score_breakdown = None
        if diagnosis:
            row = self.db.query(ActivityLog).filter(
                ActivityLog.action == "diagnosis.score_breakdown",
                ActivityLog.entity_type == "diagnosis_report",
                ActivityLog.entity_id == diagnosis.id,
            ).order_by(ActivityLog.created_at.desc()).first()
            score_breakdown = row.details_json if row else None
        return {
            "study": {
                "id": study.id,
                "name": study.name,
                "ml_task": study.ml_task,
                "objective": study.problem_objective,
                "intended_use": study.intended_use_case,
            },
            "dataset": {"id": dataset.id if dataset else None, "name": dataset.name if dataset else None},
            "version": {
                "id": version.id,
                "version_number": version.version_number,
                "parent_version_id": version.parent_version_id,
                "generation_method": version.generation_method,
                "rows": version.row_count,
                "columns": version.column_count,
                "file_hash": version.file_hash,
                "target_column": configuration.target_column if configuration else None,
                "primary_metric": configuration.primary_metric if configuration else None,
                "validation_strategy": configuration.validation_strategy if configuration else None,
                "feature_selection_mode": configuration.feature_selection_mode if configuration else None,
                "selected_feature_count": len(configuration.selected_features_json or []) if configuration else 0,
                "scaling_strategy": configuration.scaling_strategy if configuration else None,
            },
            "profile": self._compact_profile(profile.report_json if profile else {}),
            "diagnosis": None if not diagnosis else {
                "id": diagnosis.id,
                "mlrs_score": diagnosis.mlrs_score,
                "lrs_score": diagnosis.lrs_score,
                "ruleset_version": diagnosis.ruleset_version,
                "finding_count": len(diagnosis.findings_json or []),
                "findings": self._compact_findings(diagnosis.findings_json or []),
                "score_components": self._compact_score_breakdown(score_breakdown or {}),
            },
            "semantic_change": None if not semantic else {
                "scm_score": semantic.scm_score,
                "dsi_score": semantic.dsi_score,
                "ruleset_version": semantic.ruleset_version,
                "schema_added": (semantic.report_json or {}).get("columns_added", [])[:10],
                "schema_removed": (semantic.report_json or {}).get("columns_removed", [])[:10],
                "row_count_change": (semantic.report_json or {}).get("row_count_change"),
                "missing_ratio_change": (semantic.report_json or {}).get("missing_ratio_change"),
                "duplicate_delta": ((semantic.report_json or {}).get("duplicate_rows") or {}).get("delta"),
                "top_shifted_features": ((semantic.report_json or {}).get("dsi_components") or {}).get("top_shifted_features", [])[:5],
            },
            "variant": None if not variant else {
                "pipeline_id": variant.pipeline_id,
                "vrs_score": variant.vrs_score,
                "vrs_rank": variant.vrs_rank,
                "goal_satisfaction": variant.goal_satisfaction,
                "mlrs_before": variant.mlrs_before,
                "mlrs_after": variant.mlrs_after,
                "lrs_after": variant.lrs_after,
                "steps": [step.get("label") or step.get("transformation_id") for step in (variant.pipeline_steps_json or [])[:8]],
            },
        }

    @staticmethod
    def _compact_profile(report: dict) -> dict:
        summary = report.get("summary") or {}
        task = report.get("task_profile") or {}
        columns = report.get("columns") or []
        missing = sorted(
            [item for item in columns if (item.get("missing_count") or 0) > 0],
            key=lambda item: item.get("missing_ratio") or 0,
            reverse=True,
        )[:8]
        outliers = sorted(
            [item for item in columns if (item.get("outlier_count") or 0) > 0],
            key=lambda item: item.get("outlier_count") or 0,
            reverse=True,
        )[:8]
        return {
            "summary": {
                "rows": summary.get("row_count"),
                "columns": summary.get("column_count"),
                "missing_cells": summary.get("missing_cells"),
                "missing_ratio": summary.get("missing_ratio"),
                "duplicate_rows": summary.get("duplicate_rows"),
                "duplicate_ratio": summary.get("duplicate_ratio"),
                "numeric_columns": summary.get("numeric_columns"),
                "categorical_columns": summary.get("categorical_columns"),
            },
            "task": {
                "target_column": task.get("target_column"),
                "minority_class": task.get("minority_class"),
                "imbalance_ratio": task.get("imbalance_ratio"),
                "class_distribution": task.get("class_distribution"),
            },
            "top_missing_columns": [{"name": item.get("name"), "missing_ratio": item.get("missing_ratio")} for item in missing],
            "top_outlier_columns": [{"name": item.get("name"), "outlier_count": item.get("outlier_count")} for item in outliers],
            "high_correlation_count": len(report.get("high_correlations") or []),
        }

    @staticmethod
    def _compact_findings(findings: list[dict]) -> list[dict]:
        return [{
            "code": item.get("code"),
            "severity": item.get("severity"),
            "issue": item.get("issue"),
            "risk": item.get("risk"),
            "recommendation": item.get("recommendation"),
        } for item in findings[:12]]

    @staticmethod
    def _compact_score_breakdown(breakdown: dict) -> dict:
        return {
            "mlrs_components": {key: value for key, value in (breakdown.get("mlrs_components") or {}).items() if value},
            "lrs_components": {key: value for key, value in (breakdown.get("lrs_components") or {}).items() if value},
        }
