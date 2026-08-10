"""TransformationKnowledgeBase — static registry of all preprocessing
transformations available to the Variant Generator.

AI never reads or modifies this file at runtime.  It is a pure data
registry consumed by PipelinePlannerService.
"""
from __future__ import annotations

# Each transformation entry schema:
# {
#   "transformation_id": str   — stable identifier
#   "category":          str   — canonical ordering category
#   "label":             str   — human-readable name
#   "cost":              str   — very_low | low | medium | high
#   "requires_target":   bool  — True if needs a target column
#   "classification_only": bool
#   "default_params":    dict
#   "explanation":       str   — template text used by ExplanationEngineService
# }

TRANSFORMATIONS: dict[str, dict] = {
    # ── duplicate_removal ────────────────────────────────────────────────────
    "drop_duplicates": {
        "transformation_id": "drop_duplicates",
        "category": "duplicate_removal",
        "label": "Remove Duplicate Rows",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"keep": "first"},
        "explanation": (
            "Exact duplicate rows are identified and removed, keeping the first "
            "occurrence. This prevents data leakage across train/validation splits "
            "and removes artificial observation weighting."
        ),
    },

    # ── missing_value_handling ───────────────────────────────────────────────
    "median_imputation": {
        "transformation_id": "median_imputation",
        "category": "missing_value_handling",
        "label": "Median Imputation",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"strategy": "median"},
        "explanation": (
            "Missing numeric values are replaced with the column median. "
            "Median is robust to outliers and preserves the central tendency "
            "without making distributional assumptions."
        ),
    },
    "mean_imputation": {
        "transformation_id": "mean_imputation",
        "category": "missing_value_handling",
        "label": "Mean Imputation",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"strategy": "mean"},
        "explanation": (
            "Missing numeric values are replaced with the column mean. "
            "Efficient and appropriate when the distribution is approximately normal."
        ),
    },
    "drop_missing_rows": {
        "transformation_id": "drop_missing_rows",
        "category": "missing_value_handling",
        "label": "Drop Rows with Missing Values",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"threshold": 0.5},
        "explanation": (
            "Rows where more than {threshold*100:.0f}% of feature values are "
            "missing are removed. This preserves data quality at the cost of "
            "reduced sample size."
        ),
    },

    # ── encoding ─────────────────────────────────────────────────────────────
    "label_encoding": {
        "transformation_id": "label_encoding",
        "category": "encoding",
        "label": "Label Encoding",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {},
        "explanation": (
            "Categorical feature columns are encoded as integer labels. "
            "Ordinal relationships are preserved where they exist."
        ),
    },
    "onehot_encoding": {
        "transformation_id": "onehot_encoding",
        "category": "encoding",
        "label": "One-Hot Encoding",
        "cost": "low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"max_categories": 20, "handle_unknown": "ignore"},
        "explanation": (
            "Categorical feature columns with up to {max_categories} unique values "
            "are one-hot encoded into binary indicator columns. This avoids imposing "
            "false ordinal relationships."
        ),
    },

    # ── outlier_treatment ────────────────────────────────────────────────────
    "iqr_filtering": {
        "transformation_id": "iqr_filtering",
        "category": "outlier_treatment",
        "label": "IQR Outlier Removal",
        "cost": "low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"factor": 1.5},
        "explanation": (
            "Rows with any numeric feature value outside the IQR×{factor} fence "
            "are removed. This is a transparent, deterministic filter appropriate "
            "for datasets with well-defined value ranges."
        ),
    },
    "isolation_forest": {
        "transformation_id": "isolation_forest",
        "category": "outlier_treatment",
        "label": "Isolation Forest Outlier Detection",
        "cost": "medium",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"contamination": "auto", "random_state": 42},
        "explanation": (
            "An Isolation Forest model detects anomalous rows by measuring how "
            "quickly each observation is isolated in a random tree partition. "
            "Contamination='auto' adapts to the actual outlier prevalence rather "
            "than assuming a fixed rate."
        ),
    },
    "clip_outliers": {
        "transformation_id": "clip_outliers",
        "category": "outlier_treatment",
        "label": "Winsorize / Clip Outliers",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"lower": 0.01, "upper": 0.99},
        "explanation": (
            "Extreme numeric values below the {lower*100:.0f}th and above the "
            "{upper*100:.0f}th percentile are clipped to those boundary values. "
            "Outlier information is retained in bounded form."
        ),
    },

    # ── class_balancing ──────────────────────────────────────────────────────
    "smote": {
        "transformation_id": "smote",
        "category": "class_balancing",
        "label": "SMOTE Oversampling",
        "cost": "medium",
        "requires_target": True,
        "classification_only": True,
        "default_params": {"k_neighbors": 5, "random_state": 42},
        "explanation": (
            "Synthetic Minority Over-sampling Technique generates synthetic minority-"
            "class observations by interpolating between existing minority samples. "
            "The k_neighbors parameter controls neighbourhood size."
        ),
    },
    "adasyn": {
        "transformation_id": "adasyn",
        "category": "class_balancing",
        "label": "ADASYN Oversampling",
        "cost": "medium",
        "requires_target": True,
        "classification_only": True,
        "default_params": {"n_neighbors": 5, "random_state": 42},
        "explanation": (
            "Adaptive Synthetic Sampling generates more synthetic examples near the "
            "decision boundary (harder-to-learn minority regions), focusing the model "
            "on the most informative minority samples."
        ),
    },
    "random_oversampling": {
        "transformation_id": "random_oversampling",
        "category": "class_balancing",
        "label": "Random Oversampling",
        "cost": "low",
        "requires_target": True,
        "classification_only": True,
        "default_params": {"random_state": 42},
        "explanation": (
            "Minority class rows are randomly duplicated until class sizes are "
            "balanced. This is the safest option for very small minority classes "
            "where synthetic generation may be unreliable."
        ),
    },
    "random_undersampling": {
        "transformation_id": "random_undersampling",
        "category": "class_balancing",
        "label": "Random Undersampling",
        "cost": "very_low",
        "requires_target": True,
        "classification_only": True,
        "default_params": {"random_state": 42},
        "explanation": (
            "Majority class rows are randomly removed until class sizes are balanced. "
            "This reduces dataset size but eliminates no information from minority classes."
        ),
    },

    # ── feature_reduction ────────────────────────────────────────────────────
    "correlation_filter": {
        "transformation_id": "correlation_filter",
        "category": "feature_reduction",
        "label": "High-Correlation Filter",
        "cost": "low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"threshold": 0.9},
        "explanation": (
            "Feature pairs with absolute Pearson correlation ≥ {threshold} are "
            "identified and the lower-variance member is dropped. This removes "
            "redundant signals while preserving independent information."
        ),
    },
    "mutual_information": {
        "transformation_id": "mutual_information",
        "category": "feature_reduction",
        "label": "Mutual Information Feature Selection",
        "cost": "medium",
        "requires_target": True,
        "classification_only": False,
        "default_params": {"k": 20, "random_state": 42},
        "explanation": (
            "The top {k} features ranked by mutual information with the target column "
            "are selected. Features with low statistical dependence on the target are "
            "removed to reduce noise and improve model signal-to-noise ratio."
        ),
    },
    "variance_threshold": {
        "transformation_id": "variance_threshold",
        "category": "feature_reduction",
        "label": "Low-Variance Feature Removal",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {"threshold": 0.01},
        "explanation": (
            "Features with variance below {threshold} (near-constant columns) are "
            "removed. Such columns carry minimal information and can destabilise "
            "distance-based or regularised models."
        ),
    },

    # ── scaling ──────────────────────────────────────────────────────────────
    "standard_scaler": {
        "transformation_id": "standard_scaler",
        "category": "scaling",
        "label": "Standard Scaler (Z-Score)",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {},
        "explanation": (
            "Numeric feature columns are standardised to zero mean and unit variance. "
            "This makes gradient-based models and regularisation penalties scale-invariant."
        ),
    },
    "robust_scaler": {
        "transformation_id": "robust_scaler",
        "category": "scaling",
        "label": "Robust Scaler (IQR-based)",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {},
        "explanation": (
            "Numeric features are scaled using the interquartile range rather than "
            "mean and std. This is robust to outliers that would inflate the standard "
            "deviation and distort standard scaling."
        ),
    },
    "minmax_scaler": {
        "transformation_id": "minmax_scaler",
        "category": "scaling",
        "label": "Min-Max Scaler [0, 1]",
        "cost": "very_low",
        "requires_target": False,
        "classification_only": False,
        "default_params": {},
        "explanation": (
            "Numeric features are scaled to the [0, 1] range. Appropriate when the "
            "downstream model requires bounded inputs (e.g., neural networks) or when "
            "the data has no significant outliers."
        ),
    },
}

# Canonical step ordering — steps must be applied in this order
CANONICAL_CATEGORY_ORDER = [
    "duplicate_removal",
    "missing_value_handling",
    "encoding",
    "outlier_treatment",
    "class_balancing",
    "feature_reduction",
    "scaling",
]

# Cost → base seconds for time estimation
COST_BASE_SECONDS: dict[str, int] = {
    "very_low": 1,
    "low": 5,
    "medium": 30,
    "high": 120,
}


class TransformationKnowledgeBase:
    """Read-only registry. Returns applicable transformation candidates."""

    @staticmethod
    def get_all() -> dict[str, dict]:
        return TRANSFORMATIONS

    @staticmethod
    def get(transformation_id: str) -> dict | None:
        return TRANSFORMATIONS.get(transformation_id)

    @staticmethod
    def get_for_issues(requirements: dict) -> dict[str, list[dict]]:
        """Return a dict of {category: [applicable_transformations]} filtered
        by the requirements dict produced by IssueInterpreterService."""
        study_type = requirements.get("study_type", "classification")
        target_col = requirements.get("target_column")
        result: dict[str, list[dict]] = {}

        for t_id, t in TRANSFORMATIONS.items():
            # Skip classification-only transforms for non-classification tasks
            if t["classification_only"] and study_type != "classification":
                continue
            # Skip transforms that need a target when there is none
            if t["requires_target"] and not target_col:
                continue
            cat = t["category"]
            result.setdefault(cat, [])
            result[cat].append(t)

        # Remove class_balancing entirely for non-classification
        if study_type != "classification":
            result.pop("class_balancing", None)

        # Only include encoding category when categorical columns exist
        if not requirements.get("needs_encoding"):
            result.pop("encoding", None)

        return result
