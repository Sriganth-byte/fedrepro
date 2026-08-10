"""VariantEvaluatorService — evaluates a built variant CSV using the
existing deterministic scoring infrastructure (ProfilingService →
DiagnosisService) and computes the corrected VRS score.

MLRS is a risk score: higher = worse.  VRS rewards MLRS *reduction*.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app.services.diagnosis_service import DiagnosisService
from app.services.profiling_service import ProfilingService
from app.services.variant_builder_service import BuildResult

GOAL_WEIGHTS: dict[str, dict[str, float]] = {
    "maximize_accuracy":   {"mlrs": 0.40, "miss": 0.25, "bal": 0.20, "feat": 0.10, "cost": 0.05},
    "faster_training":     {"mlrs": 0.25, "miss": 0.20, "bal": 0.15, "feat": 0.15, "cost": 0.25},
    "lightweight_dataset": {"mlrs": 0.25, "miss": 0.20, "bal": 0.10, "feat": 0.20, "cost": 0.25},
    "improve_recall":      {"mlrs": 0.30, "miss": 0.20, "bal": 0.35, "feat": 0.10, "cost": 0.05},
    "fairness":            {"mlrs": 0.25, "miss": 0.20, "bal": 0.40, "feat": 0.10, "cost": 0.05},
    "explainable_model":   {"mlrs": 0.30, "miss": 0.20, "bal": 0.15, "feat": 0.25, "cost": 0.10},
}

COST_SCORE_MAP: dict[str, float] = {
    "very_low": 1.0,
    "low":      0.75,
    "medium":   0.50,
    "high":     0.25,
}

FEATURE_REDUCTION_GOALS = {"lightweight_dataset", "faster_training", "explainable_model"}


@dataclass
class EvaluationResult:
    mlrs_after: float
    lrs_after: float
    lrs_caveat: str | None
    vrs_score: float         # 0–100
    goal_satisfaction: str   # excellent | good | fair | poor
    # Component breakdown for transparency
    mlrs_risk_reduction: float
    missing_reduction: float
    class_balance_score: float
    feature_score: float
    cost_score: float


class VariantEvaluatorService:
    """Runs ProfilingService → DiagnosisService on the variant CSV,
    then computes the corrected VRS formula."""

    def evaluate(
        self,
        build_result: BuildResult,
        source_mlrs: float,
        goal: str,
        pipeline: dict,
        dataset_config: dict,
    ) -> EvaluationResult:
        """
        dataset_config: dict with at least {"task_type": str, "target_column": str|None}
        """
        task_type = dataset_config.get("task_type", "classification")
        target_col = dataset_config.get("target_column")

        # ── 1. profile the variant CSV ────────────────────────────────────────
        try:
            variant_df = pd.read_csv(build_result.output_csv_path)
        except Exception:
            # If CSV unreadable, return zero VRS
            return EvaluationResult(
                mlrs_after=source_mlrs,
                lrs_after=0.0,
                lrs_caveat=None,
                vrs_score=0.0,
                goal_satisfaction="poor",
                mlrs_risk_reduction=0.0,
                missing_reduction=0.0,
                class_balance_score=0.0,
                feature_score=0.0,
                cost_score=0.0,
            )

        profile_data = ProfilingService().profile(variant_df, task_type, dataset_config)

        # ── 2. diagnose (semantic_diff=None for variants — by design) ─────────
        lineage = {"source_version_id": None, "version_number": 1, "version_notes": "variant"}
        diagnosis = DiagnosisService().diagnose(profile_data, None, lineage, dataset_config)
        mlrs_after = float(diagnosis["mlrs_score"])
        lrs_after = float(diagnosis["lrs_score"])

        # ── 3. LRS caveat (mutual_information artificially elevates LRS) ──────
        lrs_caveat: str | None = None
        step_ids = [s.get("transformation_id", "") for s in pipeline.get("steps", [])]
        if "mutual_information" in step_ids:
            lrs_caveat = "mi_selection_expected"

        # ── 4. VRS components ─────────────────────────────────────────────────
        # MLRS risk REDUCTION (positive = improvement because MLRS is a risk score)
        mlrs_risk_reduction = max(0.0, min(1.0,
            (source_mlrs - mlrs_after) / max(source_mlrs, 1.0)
        ))

        # Missing value reduction
        miss_before = build_result.missing_values_pct_before
        miss_after = build_result.missing_values_pct_after
        if miss_before > 0:
            missing_reduction = max(0.0, min(1.0,
                (miss_before - miss_after) / max(miss_before, 0.01)
            ))
        else:
            missing_reduction = 1.0  # already clean = full score

        # Class balance (0–1, higher = better)
        class_balance = float(build_result.class_balance_score_after)

        # Feature score — goal-dependent direction
        feat_before = max(build_result.column_count_before, 1)
        feat_after = build_result.column_count_after
        feat_ratio = feat_after / feat_before
        if goal in FEATURE_REDUCTION_GOALS:
            feature_score = max(0.0, min(1.0, 1.0 - feat_ratio))
        else:
            feature_score = max(0.0, min(1.0, feat_ratio))

        # Cost efficiency
        cost_score = COST_SCORE_MAP.get(pipeline.get("estimated_cost", "medium"), 0.5)

        # ── 5. Weighted sum ───────────────────────────────────────────────────
        w = GOAL_WEIGHTS.get(goal, GOAL_WEIGHTS["maximize_accuracy"])
        vrs = (
            w["mlrs"] * mlrs_risk_reduction
            + w["miss"] * missing_reduction
            + w["bal"] * class_balance
            + w["feat"] * feature_score
            + w["cost"] * cost_score
        ) * 100.0
        vrs = max(0.0, min(100.0, round(vrs, 2)))

        goal_satisfaction = (
            "excellent" if vrs >= 80 else
            "good"      if vrs >= 60 else
            "fair"      if vrs >= 40 else
            "poor"
        )

        return EvaluationResult(
            mlrs_after=round(mlrs_after, 2),
            lrs_after=round(lrs_after, 2),
            lrs_caveat=lrs_caveat,
            vrs_score=vrs,
            goal_satisfaction=goal_satisfaction,
            mlrs_risk_reduction=round(mlrs_risk_reduction, 4),
            missing_reduction=round(missing_reduction, 4),
            class_balance_score=round(class_balance, 4),
            feature_score=round(feature_score, 4),
            cost_score=round(cost_score, 4),
        )
