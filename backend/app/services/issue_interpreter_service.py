"""IssueInterpreterService — reads DiagnosisReport + DatasetProfileReport
and produces a structured requirements dict for PipelinePlannerService.
"""
from __future__ import annotations

from app.models.entities import DatasetProfileReport, DiagnosisReport


# Exact mapping from diagnosis-2.0 finding codes to requirements keys.
# Tuple: (requirements_bool_key, optional_severity_or_detail_key)
FINDING_CODE_MAP: dict[str, tuple[str, str | None]] = {
    "MISSINGNESS":     ("needs_missing_value_handling", "missing_values_pct"),
    "DUPLICATES":      ("has_duplicates", None),
    "OUTLIERS":        ("needs_outlier_treatment", "outlier_severity"),
    "CORRELATION":     ("needs_feature_reduction", "high_correlation_detected"),
    "CLASS_IMBALANCE": ("needs_class_balancing", "class_imbalance_severity"),
    "TARGET_LEAKAGE":  ("needs_leakage_fix", None),
    "TARGET_SKEW":     ("has_target_skew", None),
    "SCALING":         ("needs_scaling", None),
}

SEVERITY_MAP: dict[str, str] = {
    "low":      "mild",
    "medium":   "moderate",
    "high":     "severe",
    "critical": "severe",
}


class IssueInterpreterService:
    """Deterministic translation layer: diagnosis findings → pipeline requirements."""

    def interpret(
        self,
        diagnosis_report: DiagnosisReport,
        profile_report: DatasetProfileReport,
    ) -> dict:
        profile: dict = profile_report.report_json or {}
        summary: dict = profile.get("summary", {})
        task_profile: dict = profile.get("task_profile", {})
        task_type: str = profile.get("task_type", "classification")
        columns: list[dict] = profile.get("columns", [])

        # ── bootstrap result with safe defaults ──────────────────────────────
        result: dict = {
            "needs_missing_value_handling": False,
            "needs_class_balancing": False,
            "needs_outlier_treatment": False,
            "needs_feature_reduction": False,
            "needs_leakage_fix": False,
            "needs_scaling": False,
            "needs_encoding": False,
            "has_duplicates": False,
            "has_target_skew": False,
            "missing_values_pct": 0.0,
            "class_imbalance_severity": "none",
            "outlier_severity": "none",
            "high_correlation_detected": False,
            "study_type": task_type,
            "target_column": task_profile.get("target_column"),
            "row_count": summary.get("row_count", 0),
            "column_count": summary.get("column_count", 0),
            "categorical_column_count": summary.get("categorical_columns", 0),
            "numeric_column_count": summary.get("numeric_columns", 0),
            "minority_class_count": None,
            "variant_generator_hints": {},
        }

        # ── read variant_generator_hints from score_breakdown if available ───
        # findings_json is a list; the hints live in score_breakdown stored in
        # activity_logs (diagnosis.score_breakdown). We don't want to re-query
        # activity logs here, so we check if the DiagnosisReport has embedded hints.
        # The diagnosis service writes findings_json as a list of finding dicts.
        findings_list: list[dict] = diagnosis_report.findings_json or []

        # ── apply FINDING_CODE_MAP ────────────────────────────────────────────
        for finding in findings_list:
            code: str = finding.get("code", "")
            severity: str = finding.get("severity", "low")
            evidence: dict = finding.get("evidence", {})
            if code not in FINDING_CODE_MAP:
                continue
            bool_key, detail_key = FINDING_CODE_MAP[code]
            result[bool_key] = True

            if code == "MISSINGNESS":
                result["missing_values_pct"] = float(evidence.get("missing_ratio", 0) * 100)
            elif code == "OUTLIERS":
                result["outlier_severity"] = SEVERITY_MAP.get(severity, "none")
            elif code == "CORRELATION":
                result["high_correlation_detected"] = True
            elif code == "CLASS_IMBALANCE":
                result["class_imbalance_severity"] = SEVERITY_MAP.get(severity, "none")

        # ── regression/clustering cannot do class balancing ──────────────────
        if task_type != "classification":
            result["needs_class_balancing"] = False
            result["class_imbalance_severity"] = "none"

        # ── clustering has no target → disable target-dependent transforms ───
        if task_type == "clustering" or result["target_column"] is None:
            result["needs_leakage_fix"] = False

        # ── encoding needed when categorical columns present ─────────────────
        cat_count = summary.get("categorical_columns", 0)
        target_col = result["target_column"]
        # subtract 1 if target is categorical (it won't be encoded as a feature)
        if target_col:
            target_row = next(
                (c for c in columns if c.get("name") == target_col), None
            )
            if target_row and not target_row.get("statistics"):  # non-numeric
                cat_count = max(0, cat_count - 1)
        result["needs_encoding"] = cat_count > 0
        result["categorical_column_count"] = cat_count

        # ── minority class count (for SMOTE k_neighbors guard) ───────────────
        if task_type == "classification":
            class_dist: dict = task_profile.get("class_distribution", {})
            if class_dist:
                result["minority_class_count"] = int(min(class_dist.values()))

        return result
