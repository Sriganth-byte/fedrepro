"""ExplanationEngineService — template-based (no AI) explanation passport
generator.  Every transformation_id in the knowledge base has a corresponding
explanation template; this service fills in the params and goal context.
"""
from __future__ import annotations

from app.services.transformation_knowledge_base import TRANSFORMATIONS

GOAL_DESCRIPTIONS: dict[str, str] = {
    "maximize_accuracy":   "maximise overall predictive accuracy",
    "faster_training":     "reduce training and preprocessing time",
    "lightweight_dataset": "minimise dataset size and memory footprint",
    "improve_recall":      "improve recall for the minority class",
    "fairness":            "balance class representation for fair modelling",
    "explainable_model":   "produce an interpretable, low-complexity feature set",
}

GOAL_SATISFACTION_DESCRIPTIONS: dict[str, str] = {
    "excellent": "This pipeline is strongly aligned with the stated goal.",
    "good":      "This pipeline is well-aligned with the stated goal.",
    "fair":      "This pipeline partially addresses the stated goal.",
    "poor":      "This pipeline has limited alignment with the stated goal.",
}


class ExplanationEngineService:
    """Generates a structured explanation passport for a pipeline.

    All text is deterministic and template-driven — no Ollama calls.
    """

    def explain_pipeline(
        self,
        pipeline: dict,
        requirements: dict,
        goal: str,
        evaluation_summary: dict | None = None,
    ) -> dict:
        steps: list[dict] = pipeline.get("steps", [])
        goal_desc = GOAL_DESCRIPTIONS.get(goal, goal)
        study_type = requirements.get("study_type", "classification")
        row_count = requirements.get("row_count", 0)

        step_explanations = []
        for step in steps:
            tid = step.get("transformation_id", "")
            t_def = TRANSFORMATIONS.get(tid, {})
            explanation = t_def.get("explanation", step.get("explanation", ""))
            # Fill in params into template placeholders where possible
            params = step.get("params", {})
            try:
                explanation = explanation.format(**params)
            except (KeyError, ValueError):
                pass  # template may reference params not set — leave as-is

            step_explanations.append({
                "category": step.get("category"),
                "transformation_id": tid,
                "label": step.get("label", t_def.get("label", tid)),
                "params": params,
                "explanation": explanation,
            })

        # Rationale paragraph
        step_labels = [s["label"] for s in step_explanations]
        rationale_parts = []
        if step_labels:
            rationale_parts.append(
                f"This pipeline applies {len(step_labels)} preprocessing stage(s) "
                f"({', '.join(step_labels)}) selected to {goal_desc}."
            )
        if row_count:
            rationale_parts.append(
                f"The source dataset contains {row_count:,} rows "
                f"({study_type} task)."
            )
        if evaluation_summary:
            satisfaction = evaluation_summary.get("goal_satisfaction", "fair")
            rationale_parts.append(GOAL_SATISFACTION_DESCRIPTIONS.get(satisfaction, ""))
            vrs = evaluation_summary.get("vrs_score")
            if vrs is not None:
                rationale_parts.append(f"Variant Readiness Score: {vrs:.1f}/100.")

        # SCM context tag — prevents variant SCM from being confused with research-change SCM
        return {
            "pipeline_id": pipeline.get("pipeline_id"),
            "goal": goal,
            "goal_description": goal_desc,
            "rationale": " ".join(filter(None, rationale_parts)),
            "steps": step_explanations,
            "scm_variant_context": True,
            "lrs_caveat": evaluation_summary.get("lrs_caveat") if evaluation_summary else None,
            "vrs_components": evaluation_summary.get("vrs_components") if evaluation_summary else None,
        }

    @staticmethod
    def all_transformation_ids_have_templates() -> bool:
        """Utility for test coverage: verify every known transformation_id has a non-empty explanation."""
        return all(bool(t.get("explanation")) for t in TRANSFORMATIONS.values())
