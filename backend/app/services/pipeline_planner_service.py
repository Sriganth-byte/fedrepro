"""PipelinePlannerService — builds N candidate preprocessing pipelines
deterministically from a requirements dict and a goal string.

Rules:
  • Step ordering is always: duplicate_removal → missing_value_handling →
    encoding → outlier_treatment → class_balancing → feature_reduction → scaling
  • No AI selection — goal weight tables and conflict rules are hard-coded
  • pipeline_hash computed from sorted steps for deduplication
"""
from __future__ import annotations

import hashlib
import json

from app.services.transformation_knowledge_base import (
    CANONICAL_CATEGORY_ORDER,
    COST_BASE_SECONDS,
    TRANSFORMATIONS,
    TransformationKnowledgeBase,
)

VALID_GOALS = {
    "maximize_accuracy",
    "faster_training",
    "lightweight_dataset",
    "improve_recall",
    "fairness",
    "explainable_model",
}

# Weight tables — each row sums to 1.0
GOAL_WEIGHTS: dict[str, dict[str, float]] = {
    "maximize_accuracy":   {"mlrs": 0.40, "miss": 0.25, "bal": 0.20, "feat": 0.10, "cost": 0.05},
    "faster_training":     {"mlrs": 0.25, "miss": 0.20, "bal": 0.15, "feat": 0.15, "cost": 0.25},
    "lightweight_dataset": {"mlrs": 0.25, "miss": 0.20, "bal": 0.10, "feat": 0.20, "cost": 0.25},
    "improve_recall":      {"mlrs": 0.30, "miss": 0.20, "bal": 0.35, "feat": 0.10, "cost": 0.05},
    "fairness":            {"mlrs": 0.25, "miss": 0.20, "bal": 0.40, "feat": 0.10, "cost": 0.05},
    "explainable_model":   {"mlrs": 0.30, "miss": 0.20, "bal": 0.15, "feat": 0.25, "cost": 0.10},
}

# Conflict pairs — never put both in the same pipeline
CONFLICT_PAIRS: list[tuple[str, str]] = [
    ("iqr_filtering", "isolation_forest"),
    ("correlation_filter", "mutual_information"),
]

# Preferred transformation per category for each goal
GOAL_PREFERENCES: dict[str, dict[str, list[str]]] = {
    "maximize_accuracy": {
        "missing_value_handling": ["median_imputation", "mean_imputation"],
        "outlier_treatment":      ["isolation_forest", "iqr_filtering"],
        "class_balancing":        ["smote", "adasyn", "random_oversampling"],
        "feature_reduction":      ["mutual_information", "correlation_filter"],
        "scaling":                ["standard_scaler", "robust_scaler"],
        "encoding":               ["onehot_encoding", "label_encoding"],
    },
    "faster_training": {
        "missing_value_handling": ["median_imputation", "drop_missing_rows"],
        "outlier_treatment":      ["iqr_filtering", "clip_outliers"],
        "class_balancing":        ["random_undersampling", "random_oversampling"],
        "feature_reduction":      ["variance_threshold", "correlation_filter"],
        "scaling":                ["standard_scaler", "minmax_scaler"],
        "encoding":               ["label_encoding", "onehot_encoding"],
    },
    "lightweight_dataset": {
        "missing_value_handling": ["drop_missing_rows", "median_imputation"],
        "outlier_treatment":      ["iqr_filtering", "clip_outliers"],
        "class_balancing":        ["random_undersampling"],
        "feature_reduction":      ["variance_threshold", "correlation_filter"],
        "scaling":                ["minmax_scaler", "standard_scaler"],
        "encoding":               ["label_encoding"],
    },
    "improve_recall": {
        "missing_value_handling": ["median_imputation", "mean_imputation"],
        "outlier_treatment":      ["clip_outliers", "iqr_filtering"],
        "class_balancing":        ["adasyn", "smote", "random_oversampling"],
        "feature_reduction":      ["mutual_information", "correlation_filter"],
        "scaling":                ["robust_scaler", "standard_scaler"],
        "encoding":               ["onehot_encoding", "label_encoding"],
    },
    "fairness": {
        "missing_value_handling": ["median_imputation", "mean_imputation"],
        "outlier_treatment":      ["clip_outliers"],
        "class_balancing":        ["adasyn", "smote", "random_oversampling"],
        "feature_reduction":      ["correlation_filter", "variance_threshold"],
        "scaling":                ["standard_scaler", "robust_scaler"],
        "encoding":               ["onehot_encoding", "label_encoding"],
    },
    "explainable_model": {
        "missing_value_handling": ["median_imputation"],
        "outlier_treatment":      ["iqr_filtering", "clip_outliers"],
        "class_balancing":        ["random_oversampling", "random_undersampling"],
        "feature_reduction":      ["variance_threshold", "correlation_filter"],
        "scaling":                ["standard_scaler", "minmax_scaler"],
        "encoding":               ["label_encoding", "onehot_encoding"],
    },
}


def _pipeline_hash(steps: list[dict]) -> str:
    payload = json.dumps(
        [{"transformation_id": s["transformation_id"], "params": s["params"]} for s in steps],
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _has_conflict(step_ids: list[str]) -> bool:
    for a, b in CONFLICT_PAIRS:
        if a in step_ids and b in step_ids:
            return True
    return False


def _estimate_cost(steps: list[dict], row_count: int) -> tuple[str, float]:
    """Return (overall_cost_label, estimated_seconds)."""
    if not steps:
        return "very_low", 0.0
    total_sec = sum(COST_BASE_SECONDS[s["cost"]] for s in steps) * max(1.0, row_count / 1000.0)
    costs = [s["cost"] for s in steps]
    if "high" in costs:
        label = "high"
    elif "medium" in costs:
        label = "medium"
    elif "low" in costs:
        label = "low"
    else:
        label = "very_low"
    return label, round(total_sec, 1)


class PipelinePlannerService:
    """Builds candidate pipelines deterministically from requirements + goal."""

    def plan(
        self,
        requirements: dict,
        goal: str,
        constraints: dict,
        n_pipelines: int = 4,
    ) -> list[dict]:
        if goal not in VALID_GOALS:
            goal = "maximize_accuracy"

        n_pipelines = max(2, min(8, n_pipelines))
        avoid_synthetic = constraints.get("avoid_synthetic_data", False)
        max_features = constraints.get("max_features")
        row_count = requirements.get("row_count", 1000)
        study_type = requirements.get("study_type", "classification")
        target_col = requirements.get("target_column")
        preferences = GOAL_PREFERENCES.get(goal, GOAL_PREFERENCES["maximize_accuracy"])
        letters = "ABCDEFGH"

        # Build candidate pool per category
        # Each pipeline picks different candidates from each category
        pipelines: list[dict] = []
        candidate_sets = self._build_candidate_sets(
            requirements, constraints, preferences, study_type, target_col, avoid_synthetic, max_features, n_pipelines
        )

        for i in range(n_pipelines):
            steps = []
            used_ids: list[str] = []

            for category in CANONICAL_CATEGORY_ORDER:
                cat_candidates = candidate_sets.get(category, [])
                if not cat_candidates:
                    continue
                # Rotate through candidates across pipelines
                t = cat_candidates[i % len(cat_candidates)]
                tid = t["transformation_id"]
                # Check conflicts
                if _has_conflict(used_ids + [tid]):
                    # Try alternate candidate
                    for alt in cat_candidates:
                        if not _has_conflict(used_ids + [alt["transformation_id"]]):
                            t = alt
                            tid = alt["transformation_id"]
                            break
                    else:
                        continue  # No valid alternative — skip this category
                params = dict(t["default_params"])
                used_ids.append(tid)
                steps.append({
                    "category": t["category"],
                    "transformation_id": tid,
                    "label": t["label"],
                    "cost": t["cost"],
                    "params": params,
                    "explanation": t["explanation"],
                })

            cost_label, est_seconds = _estimate_cost(steps, row_count)
            letter = letters[i]
            pipelines.append({
                "pipeline_id": f"Pipeline-{letter}",
                "pipeline_hash": _pipeline_hash(steps),
                "steps": steps,
                "estimated_cost": cost_label,
                "estimated_time_seconds": est_seconds,
            })

        return pipelines

    def _build_candidate_sets(
        self,
        requirements: dict,
        constraints: dict,
        preferences: dict,
        study_type: str,
        target_col: str | None,
        avoid_synthetic: bool,
        max_features: int | None,
        n_pipelines: int,
    ) -> dict[str, list[dict]]:
        """Build per-category candidate lists based on requirements."""
        tkb = TransformationKnowledgeBase()
        available = tkb.get_for_issues(requirements)
        result: dict[str, list[dict]] = {}

        for category, candidates in available.items():
            if not self._category_needed(category, requirements, max_features):
                continue
            # Filter by preference order for this goal
            preferred_ids = preferences.get(category, [])
            # Sort by preference, then alphabetical for stability
            ordered = sorted(
                candidates,
                key=lambda t: (
                    preferred_ids.index(t["transformation_id"])
                    if t["transformation_id"] in preferred_ids
                    else len(preferred_ids),
                    t["transformation_id"],
                ),
            )
            # Apply avoid_synthetic constraint
            if avoid_synthetic:
                ordered = [t for t in ordered if t["transformation_id"] not in ("smote", "adasyn")]
            if ordered:
                result[category] = ordered

        # Always include scaling (apply after feature reduction)
        if "scaling" not in result:
            preferred_scaling = preferences.get("scaling", ["standard_scaler"])
            scaling_options = [TRANSFORMATIONS[s] for s in preferred_scaling if s in TRANSFORMATIONS]
            if scaling_options:
                result["scaling"] = scaling_options

        return result

    @staticmethod
    def _category_needed(category: str, requirements: dict, max_features: int | None) -> bool:
        mapping = {
            "duplicate_removal":      "has_duplicates",
            "missing_value_handling": "needs_missing_value_handling",
            "encoding":               "needs_encoding",
            "outlier_treatment":      "needs_outlier_treatment",
            "class_balancing":        "needs_class_balancing",
            "feature_reduction":      "needs_feature_reduction",
            "scaling":                True,  # always
        }
        val = mapping.get(category, False)
        if val is True:
            return True
        if val is False:
            return False
        # feature_reduction also triggered by max_features constraint
        if category == "feature_reduction" and max_features:
            return True
        return bool(requirements.get(val, False))
