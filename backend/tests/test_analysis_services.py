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
    assert semantic["ruleset_version"] == "semantic-2.0"
    assert semantic["report"]["metric_algorithm_versions"] == {"scm": "2.0", "dsi": "2.0"}
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


def test_identical_versions_have_zero_change_and_drift_deterministically():
    frame = pd.DataFrame({"id": [1, 2, 3], "age": [20, 21, 22], "placed": ["no", "yes", "yes"]})
    service = SemanticDiffService()
    first = service.compare(frame, frame.copy(), "placed")
    second = service.compare(frame, frame.copy(), "placed")
    assert first == second
    assert first["scm_score"] == 0
    assert first["dsi_score"] == 0
    assert first["report"]["row_content_change"]["unchanged_row_instances"] == 3


def test_dsi_ignores_size_when_distribution_is_stable():
    previous = pd.DataFrame({"score": [10, 20, 30, 40], "segment": ["a", "a", "b", "b"], "target": [0, 1, 0, 1]})
    current = pd.concat([previous, previous], ignore_index=True)
    semantic = SemanticDiffService().compare(previous, current, "target")
    assert semantic["report"]["row_count_change"] == 4
    assert semantic["dsi_score"] == 0
    assert semantic["scm_score"] > 0


def test_semantic_diff_detects_modified_rows_with_stable_identifier():
    previous = pd.DataFrame({"EmployeeID": [1, 2, 3], "salary": [10, 20, 30], "status": ["new", "new", "old"]})
    current = pd.DataFrame({"EmployeeID": [1, 2, 4], "salary": [10, 25, 40], "status": ["new", "new", "new"]})
    semantic = SemanticDiffService().compare(previous, current, "status")
    row_change = semantic["report"]["row_content_change"]
    assert row_change["method"] == "stable_identifier_hash"
    assert row_change["row_instances_added"] == 1
    assert row_change["row_instances_removed"] == 1
    assert row_change["modified_row_instances"] == 1


def test_mlrs_improves_when_readiness_improves_even_with_high_scm():
    bad = pd.DataFrame({"x": [1, None, None, 1000, 1000], "target": ["yes", "yes", "yes", "yes", "no"]})
    good = pd.DataFrame({"x": [1, 2, 3, 4, 5], "target": ["yes", "no", "yes", "no", "yes"], "new_feature": [9, 8, 7, 6, 5]})
    semantic = SemanticDiffService().compare(bad, good, "target")
    config = {"target_column": "target"}
    bad_profile = ProfilingService().profile(bad, "classification", config)
    good_profile = ProfilingService().profile(good, "classification", config)
    bad_diagnosis = DiagnosisService().diagnose(bad_profile, None, {"version_number": 1}, config)
    good_diagnosis = DiagnosisService().diagnose(good_profile, semantic, {"source_version_id": 1, "version_number": 2, "version_notes": "cleaned"}, config)
    assert semantic["scm_score"] > 0
    assert good_diagnosis["mlrs_score"] < bad_diagnosis["mlrs_score"]
    assert "drift" not in good_diagnosis["score_breakdown"]["mlrs_components"]


def test_lrs_identifier_alone_is_low_but_direct_target_copy_is_high():
    base_profile = {
        "summary": {"row_count": 4, "missing_ratio": 0, "missing_cells": 0, "duplicate_ratio": 0, "duplicate_rows": 0},
        "columns": [
            {"name": "EmployeeID", "role": "feature", "unique_ratio": 1, "missing_ratio": 0, "missing_count": 0},
            {"name": "placed", "role": "target", "unique_ratio": .5, "missing_ratio": 0, "missing_count": 0},
        ],
        "high_correlations": [],
        "task_type": "classification",
        "task_profile": {"class_distribution": {"yes": 2, "no": 2}, "imbalance_ratio": 1},
    }
    config = {"target_column": "placed"}
    identifier_only = DiagnosisService().diagnose(base_profile, None, {"version_number": 1}, config)
    assert identifier_only["lrs_score"] <= 8

    leaking_profile = {
        **base_profile,
        "columns": base_profile["columns"] + [{"name": "placed_label_copy", "role": "feature", "unique_ratio": .5, "missing_ratio": 0, "missing_count": 0}],
        "high_correlations": [{"left": "placed", "right": "placed_label_copy", "correlation": 1.0}],
    }
    leaking = DiagnosisService().diagnose(leaking_profile, None, {"version_number": 1}, config)
    assert leaking["lrs_score"] > identifier_only["lrs_score"] + 20
    assert leaking["score_breakdown"]["lrs_components"]["direct_target_leakage"] > 0


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
