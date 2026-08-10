import json

import pandas as pd

from app.services.ai_explanation_service import AIExplanationService
from app.services.diagnosis_service import DiagnosisService
from app.services.profiling_service import ProfilingService
from app.services.semantic_diff_service import SemanticDiffService


def test_deterministic_analysis_contracts():
    previous = pd.DataFrame({"age": [20, 21, 22, 23], "score": [40, 50, 60, 70], "placed": ["no", "no", "yes", "yes"]})
    current = pd.DataFrame({"age": [20, 21, 22, 80, 80], "score": [40, 50, None, 95, 95], "placed": ["no", "no", "no", "yes", "yes"]})
    config = {"target_column": "placed"}
    semantic = SemanticDiffService().compare(previous, current, "placed")
    profile = ProfilingService().profile(current, "classification", config)
    diagnosis = DiagnosisService().diagnose(profile, semantic, {"source_version_id": 1, "version_number": 2, "version_notes": "collection update"}, config)
    assert 0 <= semantic["scm_score"] <= 100
    assert 0 <= semantic["dsi_score"] <= 100
    assert semantic["ruleset_version"] == "semantic-1.2"
    assert semantic["report"]["row_content_change"]["row_instances_added"] == 3
    assert semantic["report"]["row_content_change"]["row_instances_removed"] == 2
    assert semantic["report"]["row_content_change"]["unchanged_row_instances"] == 2
    assert semantic["report"]["missingness_changes_by_column"]["score"]["count_delta"] == 1
    assert semantic["report"]["numeric_distribution_changes"]["age"]["current"]["max"] == 80
    assert semantic["report"]["numeric_distribution_changes"]["age"]["change_level"] in {"moderate", "major"}
    assert semantic["report"]["categorical_distribution_changes"]["placed"]
    assert "placed" not in semantic["report"]["numeric_distribution_changes"]
    assert profile["task_profile"]["minority_class"] == "yes"
    assert 0 <= diagnosis["mlrs_score"] <= 100
    assert 0 <= diagnosis["lrs_score"] <= 100
    assert diagnosis["ruleset_version"] == "diagnosis-2.0"
    assert diagnosis["score_breakdown"]["mlrs_components"]
    assert diagnosis["score_breakdown"]["lrs_components"]
    assert diagnosis["score_breakdown"]["variant_generator_hints"]
    for finding in diagnosis["findings"]:
        assert {"issue", "severity", "evidence", "risk", "recommendation"} <= finding.keys()


def test_version_analysis_response_contract():
    payload = {
        "executive_summary": "Summary",
        "selected_version_profile": ["Profile evidence"],
        "version_evolution": [{"transition": "V1 to V2", "changes": ["Five rows added"], "interpretation": "The evidence population changed."}],
        "research_cautions": ["Treat the versions as distinct evidence conditions."],
        "conclusion": "Conclusion",
    }
    assert AIExplanationService._validate_version_analysis(json.dumps(payload)) == payload


def test_version_analysis_has_complete_fallback():
    evidence = {
        "ml_study": {"name": "Placement Study", "ml_task": "classification", "problem_objective": "assess placement evidence"},
        "dataset": {"name": "Placement"},
        "selected_version": {"version_number": 2, "row_count": 105, "column_count": 11, "target_column": "placed", "primary_metric": "f1_weighted", "validation_strategy": "holdout"},
        "dataset_profile": {"summary": {"row_count": 105, "column_count": 11, "missing_cells": 2, "missing_ratio": .0017, "duplicate_rows": 0}, "task_profile": {"class_distribution": {"no": 60, "yes": 45}, "imbalance_ratio": 1.33}, "columns": []},
        "version_history": [{"version_number": 1, "row_count": 100, "column_count": 11, "version_notes": "baseline", "semantic_diff_from_previous": None}],
    }
    fallback = AIExplanationService._fallback_version_analysis(evidence, TimeoutError())
    assert fallback["executive_summary"]
    assert fallback["selected_version_profile"]
    assert fallback["version_evolution"]
    assert fallback["research_cautions"]
    assert fallback["conclusion"]
    assert fallback["generation_note"].startswith("Ollama could not")


def test_non_structured_ai_fallback_hides_internal_error_text():
    evidence = {
        "scm_score": 12.5,
        "dsi_score": 4.25,
        "report": {
            "columns_added": ["new_feature"],
            "columns_removed": [],
        },
    }
    fallback = AIExplanationService._fallback_interpretation("semantic_metrics", evidence)
    assert "Interpretation temporarily unavailable" in fallback
    assert "SCM: 12.5" in fallback
    assert "new_feature" in fallback
    assert "Ollama" not in fallback
    assert "timed out" not in fallback.lower()
