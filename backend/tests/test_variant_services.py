"""Unit tests for Variant Generator services.

Run with:
    cd backend && .venv\\Scripts\\python.exe -m pytest tests/test_variant_services.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

from app.services.issue_interpreter_service import IssueInterpreterService
from app.services.pipeline_planner_service import PipelinePlannerService
from app.services.variant_evaluator_service import VariantEvaluatorService
from app.services.explanation_engine_service import ExplanationEngineService
from app.services.transformation_knowledge_base import (
    CANONICAL_CATEGORY_ORDER,
    TRANSFORMATIONS,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _mock_diagnosis(findings: list[dict], mlrs: float = 45.0, lrs: float = 5.0):
    report = MagicMock()
    report.findings_json = findings
    report.mlrs_score = mlrs
    report.lrs_score = lrs
    return report


def _mock_profile(
    task_type: str = "classification",
    target_col: str = "Attrition",
    row_count: int = 1470,
    col_count: int = 35,
    numeric_cols: int = 28,
    cat_cols: int = 7,
    missing_ratio: float = 0.05,
    class_dist: dict | None = None,
):
    report = MagicMock()
    report.report_json = {
        "summary": {
            "row_count": row_count,
            "column_count": col_count,
            "numeric_columns": numeric_cols,
            "categorical_columns": cat_cols,
            "missing_ratio": missing_ratio,
            "duplicate_ratio": 0.0,
        },
        "task_type": task_type,
        "task_profile": {
            "target_column": target_col,
            "class_distribution": class_dist or {"Yes": 100, "No": 1000},
            "imbalance_ratio": 10.0,
        },
        "columns": [{"name": target_col, "role": "target"}],
        "high_correlations": [],
    }
    return report


# ── IssueInterpreterService ───────────────────────────────────────────────────

class TestIssueInterpreterService:

    def test_interpret_all_issues(self):
        findings = [
            {"code": "MISSINGNESS",     "severity": "high",   "evidence": {"missing_ratio": 0.15}},
            {"code": "CLASS_IMBALANCE", "severity": "high",   "evidence": {}},
            {"code": "OUTLIERS",        "severity": "medium", "evidence": {}},
            {"code": "CORRELATION",     "severity": "high",   "evidence": {}},
            {"code": "DUPLICATES",      "severity": "medium", "evidence": {}},
        ]
        result = IssueInterpreterService().interpret(
            _mock_diagnosis(findings), _mock_profile()
        )
        assert result["needs_missing_value_handling"] is True
        assert result["needs_class_balancing"] is True
        assert result["needs_outlier_treatment"] is True
        assert result["needs_feature_reduction"] is True
        assert result["has_duplicates"] is True
        assert result["missing_values_pct"] == pytest.approx(15.0, abs=0.1)
        assert result["class_imbalance_severity"] == "severe"
        assert result["outlier_severity"] == "moderate"

    def test_interpret_regression_no_class_balancing(self):
        findings = [{"code": "CLASS_IMBALANCE", "severity": "high", "evidence": {}}]
        result = IssueInterpreterService().interpret(
            _mock_diagnosis(findings),
            _mock_profile(task_type="regression", target_col="Price"),
        )
        assert result["needs_class_balancing"] is False, "Regression datasets must never need class balancing"
        assert result["class_imbalance_severity"] == "none"

    def test_interpret_clustering_no_leakage_fix(self):
        findings = [{"code": "TARGET_LEAKAGE", "severity": "critical", "evidence": {}}]
        result = IssueInterpreterService().interpret(
            _mock_diagnosis(findings),
            _mock_profile(task_type="clustering", target_col=None),
        )
        assert result["needs_leakage_fix"] is False, "Clustering has no target — leakage fix must be excluded"

    def test_minority_class_count(self):
        result = IssueInterpreterService().interpret(
            _mock_diagnosis([]),
            _mock_profile(class_dist={"Yes": 50, "No": 500}),
        )
        assert result["minority_class_count"] == 50

    def test_encoding_detected_from_profile(self):
        result = IssueInterpreterService().interpret(
            _mock_diagnosis([]),
            _mock_profile(cat_cols=3, target_col="label"),
        )
        # categorical_column_count should be at most cat_cols (minus target if categorical)
        assert isinstance(result["categorical_column_count"], int)


# ── PipelinePlannerService ────────────────────────────────────────────────────

def _base_requirements(study_type: str = "classification") -> dict:
    return {
        "needs_missing_value_handling": True,
        "needs_class_balancing": study_type == "classification",
        "needs_outlier_treatment": True,
        "needs_feature_reduction": True,
        "needs_scaling": False,
        "needs_encoding": False,
        "has_duplicates": True,
        "has_target_skew": False,
        "missing_values_pct": 10.0,
        "class_imbalance_severity": "severe",
        "outlier_severity": "moderate",
        "high_correlation_detected": True,
        "study_type": study_type,
        "target_column": "Attrition" if study_type != "clustering" else None,
        "row_count": 1470,
        "column_count": 35,
        "categorical_column_count": 0,
        "numeric_column_count": 28,
        "minority_class_count": 100,
        "variant_generator_hints": {},
    }


class TestPipelinePlannerService:

    def test_returns_n_pipelines(self):
        pipelines = PipelinePlannerService().plan(_base_requirements(), "maximize_accuracy", {}, n_pipelines=4)
        assert len(pipelines) == 4

    def test_step_order_canonical(self):
        requirements = _base_requirements()
        for pipeline in PipelinePlannerService().plan(requirements, "maximize_accuracy", {}, n_pipelines=2):
            categories = [s["category"] for s in pipeline["steps"]]
            # Must be a subsequence of canonical order
            order_idx = [CANONICAL_CATEGORY_ORDER.index(c) for c in categories if c in CANONICAL_CATEGORY_ORDER]
            assert order_idx == sorted(order_idx), (
                f"Steps are not in canonical order: {categories}"
            )

    def test_avoid_synthetic_data_excludes_smote_adasyn(self):
        requirements = _base_requirements()
        constraints = {"avoid_synthetic_data": True}
        for pipeline in PipelinePlannerService().plan(requirements, "maximize_accuracy", constraints, n_pipelines=4):
            ids = [s["transformation_id"] for s in pipeline["steps"]]
            assert "smote" not in ids
            assert "adasyn" not in ids

    def test_regression_no_class_balancing(self):
        requirements = _base_requirements(study_type="regression")
        requirements["needs_class_balancing"] = False
        for pipeline in PipelinePlannerService().plan(requirements, "maximize_accuracy", {}, n_pipelines=2):
            for step in pipeline["steps"]:
                assert step["category"] != "class_balancing", (
                    f"Regression pipeline must not include class_balancing, got: {step}"
                )

    def test_clustering_no_class_balancing(self):
        requirements = _base_requirements(study_type="clustering")
        requirements["needs_class_balancing"] = False
        requirements["target_column"] = None
        for pipeline in PipelinePlannerService().plan(requirements, "maximize_accuracy", {}, n_pipelines=2):
            for step in pipeline["steps"]:
                assert step["category"] != "class_balancing"

    def test_no_conflict_pairs(self):
        from app.services.pipeline_planner_service import CONFLICT_PAIRS
        requirements = _base_requirements()
        for pipeline in PipelinePlannerService().plan(requirements, "maximize_accuracy", {}, n_pipelines=4):
            ids = [s["transformation_id"] for s in pipeline["steps"]]
            for a, b in CONFLICT_PAIRS:
                assert not (a in ids and b in ids), (
                    f"Conflict pair ({a}, {b}) found in pipeline {pipeline['pipeline_id']}"
                )

    def test_pipeline_hash_present(self):
        pipelines = PipelinePlannerService().plan(_base_requirements(), "maximize_accuracy", {})
        for p in pipelines:
            assert "pipeline_hash" in p
            assert len(p["pipeline_hash"]) == 64  # SHA-256 hex

    def test_estimated_time_positive(self):
        pipelines = PipelinePlannerService().plan(_base_requirements(), "maximize_accuracy", {})
        for p in pipelines:
            assert p["estimated_time_seconds"] >= 0


# ── VariantEvaluatorService VRS formula ──────────────────────────────────────

class TestVrsFormula:
    """Test the corrected VRS formula: MLRS is a risk score, lower = better."""

    def _compute(self, source_mlrs, mlrs_after, miss_before=10.0, miss_after=0.0,
                 balance_before=0.5, balance_after=0.8, feat_before=35, feat_after=20,
                 goal="maximize_accuracy", cost="low"):
        from app.services.variant_evaluator_service import GOAL_WEIGHTS, COST_SCORE_MAP, FEATURE_REDUCTION_GOALS
        mlrs_risk_reduction = max(0.0, min(1.0, (source_mlrs - mlrs_after) / max(source_mlrs, 1.0)))
        if miss_before > 0:
            missing_reduction = max(0.0, min(1.0, (miss_before - miss_after) / max(miss_before, 0.01)))
        else:
            missing_reduction = 1.0
        class_balance = balance_after
        feat_ratio = feat_after / max(feat_before, 1)
        if goal in FEATURE_REDUCTION_GOALS:
            feature_score = max(0.0, min(1.0, 1.0 - feat_ratio))
        else:
            feature_score = max(0.0, min(1.0, feat_ratio))
        cost_score = COST_SCORE_MAP.get(cost, 0.5)
        w = GOAL_WEIGHTS[goal]
        vrs = (w["mlrs"] * mlrs_risk_reduction + w["miss"] * missing_reduction +
               w["bal"] * class_balance + w["feat"] * feature_score + w["cost"] * cost_score) * 100.0
        return max(0.0, min(100.0, vrs)), mlrs_risk_reduction

    def test_mlrs_risk_reduction_sign(self):
        """Lower MLRS after = positive risk reduction = good."""
        vrs, reduction = self._compute(source_mlrs=40, mlrs_after=20)
        assert reduction == pytest.approx(0.5), "Risk reduction should be 0.5 when MLRS drops from 40 to 20"
        assert reduction > 0

    def test_mlrs_increase_is_zero_contribution(self):
        """If MLRS increases (more risk), contribution must be clamped to 0."""
        vrs, reduction = self._compute(source_mlrs=20, mlrs_after=40)
        assert reduction == pytest.approx(0.0), "When MLRS increases, risk reduction must be 0 (not negative)"

    def test_vrs_always_between_0_and_100(self):
        """VRS must be within [0, 100] for any valid inputs."""
        test_cases = [
            (0, 0), (100, 0), (0, 100), (50, 50), (1, 99), (99, 1),
        ]
        for src, after in test_cases:
            vrs, _ = self._compute(source_mlrs=src, mlrs_after=after)
            assert 0.0 <= vrs <= 100.0, f"VRS={vrs} out of bounds for mlrs_before={src}, mlrs_after={after}"

    def test_perfect_improvement_approaches_100(self):
        """Near-perfect improvement across all components should give VRS close to 100."""
        vrs, _ = self._compute(
            source_mlrs=100, mlrs_after=0,
            miss_before=50.0, miss_after=0.0,
            balance_after=1.0,
            feat_before=35, feat_after=35,  # preservation goal
            goal="maximize_accuracy", cost="very_low"
        )
        assert vrs > 70, f"Perfect improvement should yield high VRS, got {vrs}"

    def test_weights_sum_to_one(self):
        from app.services.variant_evaluator_service import GOAL_WEIGHTS
        for goal, w in GOAL_WEIGHTS.items():
            total = sum(w.values())
            assert abs(total - 1.0) < 1e-9, f"Weights for goal '{goal}' sum to {total}, not 1.0"


# ── ExplanationEngineService ──────────────────────────────────────────────────

class TestExplanationEngineService:

    def test_all_transformation_ids_have_templates(self):
        assert ExplanationEngineService.all_transformation_ids_have_templates(), (
            "Every transformation in the knowledge base must have a non-empty explanation template"
        )

    def test_explain_pipeline_returns_required_keys(self):
        pipeline = {
            "pipeline_id": "V1-Pipeline-A",
            "steps": [
                {
                    "category": "missing_value_handling",
                    "transformation_id": "median_imputation",
                    "label": "Median Imputation",
                    "params": {"strategy": "median"},
                    "explanation": "Test explanation",
                    "cost": "very_low",
                }
            ],
            "estimated_cost": "very_low",
        }
        requirements = _base_requirements()
        result = ExplanationEngineService().explain_pipeline(pipeline, requirements, "maximize_accuracy")
        assert "pipeline_id" in result
        assert "steps" in result
        assert "rationale" in result
        assert result["scm_variant_context"] is True

    def test_lrs_caveat_passthrough(self):
        pipeline = {"pipeline_id": "V1-Pipeline-A", "steps": []}
        eval_summary = {"goal_satisfaction": "good", "vrs_score": 65.0, "lrs_caveat": "mi_selection_expected", "vrs_components": {}}
        result = ExplanationEngineService().explain_pipeline(pipeline, _base_requirements(), "maximize_accuracy", eval_summary)
        assert result["lrs_caveat"] == "mi_selection_expected"


# ── TransformationKnowledgeBase ───────────────────────────────────────────────

class TestTransformationKnowledgeBase:

    def test_all_have_category_and_cost(self):
        for tid, t in TRANSFORMATIONS.items():
            assert "category" in t, f"{tid} missing 'category'"
            assert "cost" in t, f"{tid} missing 'cost'"
            assert t["cost"] in ("very_low", "low", "medium", "high"), f"{tid} has invalid cost '{t['cost']}'"

    def test_classification_only_filtered_for_regression(self):
        from app.services.transformation_knowledge_base import TransformationKnowledgeBase
        reqs = _base_requirements(study_type="regression")
        available = TransformationKnowledgeBase().get_for_issues(reqs)
        assert "class_balancing" not in available

    def test_canonical_category_order_covers_all_categories(self):
        categories_in_registry = {t["category"] for t in TRANSFORMATIONS.values()}
        for cat in categories_in_registry:
            assert cat in CANONICAL_CATEGORY_ORDER, f"Category '{cat}' not in CANONICAL_CATEGORY_ORDER"
