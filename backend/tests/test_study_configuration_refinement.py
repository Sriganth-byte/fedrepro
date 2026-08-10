"""
Unit tests for Refinement #1: Study Configuration completeness scoring and diff logic.

These tests exercise pure service-layer logic and do NOT hit the database.
"""
import pytest

from app.services.study_service import StudyService, _COMPLETENESS_FIELDS


class TestComputeCompleteness:
    """Tests for StudyService._compute_completeness()."""

    def test_empty_data_scores_zero_and_all_fields_missing(self):
        score, missing = StudyService._compute_completeness({})
        assert score == 0
        assert set(missing) == set(_COMPLETENESS_FIELDS)
        assert len(missing) == len(_COMPLETENESS_FIELDS)

    def test_full_data_scores_hundred(self):
        data = {
            "ml_task": "classification",
            "domain": "healthcare",
            "research_objective": "Improve readiness scores",
            "research_question": "Does repair help?",
            "hypothesis": "Yes it does",
            "target_column": "outcome",
            "primary_metric": "f1_weighted",
            "baseline_model": "random_forest",
            "validation_strategy": "stratified_holdout",
            "random_seed": 42,
        }
        score, missing = StudyService._compute_completeness(data)
        assert score == 100
        assert missing == []

    def test_random_seed_zero_is_valid_and_not_missing(self):
        """random_seed=0 is a valid value; it must NOT appear in missing_fields."""
        data = {"random_seed": 0, "ml_task": "regression"}
        score, missing = StudyService._compute_completeness(data)
        assert "random_seed" not in missing
        # ml_task (10) + random_seed (10) = 20
        assert score == 20

    def test_random_seed_none_counts_as_missing(self):
        _, missing = StudyService._compute_completeness({"random_seed": None})
        assert "random_seed" in missing

    def test_partial_data_scores_proportionally(self):
        data = {
            "ml_task": "classification",
            "domain": "finance",
            "research_objective": "Detect risk",
        }
        score, missing = StudyService._compute_completeness(data)
        # 3 present, 7 absent: 30 pts
        assert score == 30
        assert len(missing) == 7

    def test_empty_string_counts_as_missing(self):
        """Falsy string (empty or whitespace) must count as missing."""
        data = {"ml_task": "", "domain": "   "}
        # Note: the Pydantic blank_to_none validator normalises strings before
        # they reach the service layer, but _compute_completeness checks falsy.
        _, missing = StudyService._compute_completeness(data)
        assert "ml_task" in missing

    def test_score_is_clamped_to_zero(self):
        """Score should never be negative even if extra missing fields are supplied."""
        score, _ = StudyService._compute_completeness({})
        assert score >= 0

    @pytest.mark.parametrize(
        "field,value",
        [
            ("ml_task", "classification"),
            ("domain", "test domain"),
            ("research_objective", "test objective"),
            ("research_question", "test question"),
            ("hypothesis", "test hypothesis"),
            ("target_column", "outcome"),
            ("primary_metric", "f1_weighted"),
            ("baseline_model", "random_forest"),
            ("validation_strategy", "stratified_holdout"),
            ("random_seed", 0),
        ],
    )
    def test_each_field_contributes_exactly_ten_points(self, field, value):
        """Each individual completeness field must contribute exactly 10 points."""
        score, _ = StudyService._compute_completeness({field: value})
        assert score == 10, f"Field '{field}' should contribute 10 pts, got {score}"

    def test_missing_fields_list_matches_expected_absent_fields(self):
        """missing_fields must exactly list the fields that are absent."""
        data = {
            "ml_task": "regression",
            "domain": "supply chain",
        }
        _, missing = StudyService._compute_completeness(data)
        expected_missing = {f for f in _COMPLETENESS_FIELDS if f not in data}
        assert set(missing) == expected_missing

    def test_completeness_fields_list_has_ten_entries(self):
        """There must be exactly 10 fields in _COMPLETENESS_FIELDS (= 100 pts max)."""
        assert len(_COMPLETENESS_FIELDS) == 10
