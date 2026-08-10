from collections import Counter

import numpy as np
import pandas as pd


SCM_COMPONENT_WEIGHTS = {
    "schema": 0.30,
    "rows": 0.35,
    "missingness": 0.20,
    "categorical_structure": 0.15,
}

DSI_COMPONENT_WEIGHTS = {
    "mean_feature_shift": 0.65,
    "max_feature_shift": 0.20,
    "drifted_feature_ratio": 0.15,
}

SCHEMA_SEVERITY = {
    "target_removed": 0.65,
    "target_added": 0.30,
    "target_dtype_changed": 0.35,
    "feature_dtype_changed": 0.10,
    "feature_removed": 0.08,
    "feature_added": 0.05,
    "target_role_changed": 0.20,
}

DRIFTED_FEATURE_THRESHOLD = 20.0
LOW_CARDINALITY_LIMIT = 100
IDENTIFIER_NAME_HINTS = ("id", "uuid", "guid", "key")


class SemanticDiffService:
    ruleset_version = "semantic-2.0"

    def compare(self, previous: pd.DataFrame, current: pd.DataFrame, target_column: str | None) -> dict:
        old_columns, new_columns = set(previous.columns), set(current.columns)
        common = sorted(old_columns & new_columns)
        added, removed = sorted(new_columns - old_columns), sorted(old_columns - new_columns)
        dtype_changes = {
            column: {"previous": str(previous[column].dtype), "current": str(current[column].dtype)}
            for column in common
            if str(previous[column].dtype) != str(current[column].dtype)
        }
        added_details = {column: self._column_identity(current[column]) for column in added}
        removed_details = {column: self._column_identity(previous[column]) for column in removed}

        old_missing = float(previous.isna().mean().mean()) if len(previous.columns) else 0.0
        new_missing = float(current.isna().mean().mean()) if len(current.columns) else 0.0
        duplicate_previous, duplicate_current = int(previous.duplicated().sum()), int(current.duplicated().sum())

        missingness_changes, missingness_score = self._missingness_change(previous, current, common)
        schema_details, schema_score = self._schema_change(added, removed, dtype_changes, target_column)
        row_content_change = self._row_content_change(previous, current, common)
        row_change_score = (row_content_change or {}).get("artifact_change_ratio", 0.0)

        numeric_changes: dict[str, dict] = {}
        categorical_changes: dict[str, list[dict]] = {}
        feature_shift_scores: dict[str, float] = {}
        feature_shift_details: list[dict] = []
        target_shift, target_distribution = 0.0, {}

        for column in common:
            if self._is_numeric_pair(previous[column], current[column]):
                old = pd.to_numeric(previous[column], errors="coerce").dropna()
                new = pd.to_numeric(current[column], errors="coerce").dropna()
                shift = self._numeric_distribution_shift(old, new)
                shift_score = round(shift * 100, 3)
                previous_stats = self._numeric_summary(old)
                current_stats = self._numeric_summary(new)
                numeric_changes[column] = {
                    "previous": previous_stats,
                    "current": current_stats,
                    "delta": {
                        key: self._rounded((current_stats[key] or 0) - (previous_stats[key] or 0))
                        for key in ("mean", "median", "std", "min", "max")
                    },
                    "distribution_shift_score": shift_score,
                    "normalized_shift_score": shift_score,
                    "change_level": self._change_level(shift_score),
                    "method": "quantile_wasserstein_normalized",
                }
                if column == target_column:
                    target_shift = shift
                    target_distribution = {
                        "mode": "continuous",
                        "shift_score": shift_score,
                        "previous": previous_stats,
                        "current": current_stats,
                        "delta": numeric_changes[column]["delta"],
                    }
                else:
                    feature_shift_scores[column] = shift_score
                    feature_shift_details.append({"column": column, "type": "numeric", "shift_score": shift_score, "method": "quantile_wasserstein_normalized"})
                continue

            changes = self._distribution_changes(previous[column], current[column])
            structure = self._categorical_structure_shift(changes)
            shift_score = round(structure["distribution_shift"] * 100, 3)
            material = sorted(changes, key=lambda item: abs(item["ratio_delta"]), reverse=True)
            if structure["added_categories"] or structure["removed_categories"] or shift_score > 0:
                categorical_changes[column] = material[:20 if column == target_column else 10]
            if column == target_column:
                target_shift = structure["distribution_shift"]
                target_distribution = {
                    "mode": "categorical",
                    "shift_score": shift_score,
                    "added_categories": structure["added_categories"],
                    "removed_categories": structure["removed_categories"],
                    "changes": material[:20],
                }
            else:
                feature_shift_scores[column] = shift_score
                feature_shift_details.append({
                    "column": column,
                    "type": "categorical",
                    "shift_score": shift_score,
                    "method": "jensen_shannon",
                    "added_categories": structure["added_categories"],
                    "removed_categories": structure["removed_categories"],
                })

        categorical_structure_score = self._categorical_structure_score(previous, current, common, target_column)
        dsi_components = self._dsi_components(feature_shift_scores)
        dsi = 100 * sum(DSI_COMPONENT_WEIGHTS[key] * value for key, value in dsi_components.items())
        scm_components = {
            "schema": schema_score,
            "rows": row_change_score,
            "missingness": missingness_score,
            "categorical_structure": categorical_structure_score,
        }
        scm = 100 * sum(SCM_COMPONENT_WEIGHTS[key] * value for key, value in scm_components.items())

        top_shifted = sorted(feature_shift_details, key=lambda item: item["shift_score"], reverse=True)[:10]
        return {
            "report": {
                "metric_algorithm_versions": {"scm": "2.0", "dsi": "2.0"},
                "score_meaning": {
                    "scm": "Dataset artifact change between versions; it does not indicate whether the change is beneficial.",
                    "dsi": "Statistical distribution movement across common features; row-count change is not a direct drift component.",
                },
                "columns_added": added,
                "columns_added_details": added_details,
                "columns_removed": removed,
                "columns_removed_details": removed_details,
                "data_type_changes": dtype_changes,
                "schema_change_evidence": schema_details,
                "row_count_previous": len(previous),
                "row_count_current": len(current),
                "row_count_change": len(current) - len(previous),
                "column_count_change": len(current.columns) - len(previous.columns),
                "row_content_change": row_content_change,
                "duplicate_rows": {
                    "previous": duplicate_previous,
                    "current": duplicate_current,
                    "delta": duplicate_current - duplicate_previous,
                },
                "missing_ratio_previous": round(old_missing, 6),
                "missing_ratio_current": round(new_missing, 6),
                "missing_ratio_change": round(new_missing - old_missing, 6),
                "missingness_changes_by_column": missingness_changes,
                "numeric_distribution_changes": numeric_changes,
                "categorical_distribution_changes": categorical_changes,
                "target_distribution_change": target_distribution,
                "target_shift_score": round(target_shift * 100, 3),
                "feature_shift_scores": feature_shift_scores,
                "top_shifted_features": top_shifted,
                "drifted_feature_ratio": round(dsi_components["drifted_feature_ratio"], 6),
                "max_feature_shift": round(dsi_components["max_feature_shift"] * 100, 3),
                "scm_components": {key: round(value * 100, 3) for key, value in scm_components.items()},
                "dsi_components": {key: round(value * 100, 3) for key, value in dsi_components.items()},
            },
            "scm_score": round(self._bounded(scm), 3),
            "dsi_score": round(self._bounded(dsi), 3),
            "ruleset_version": self.ruleset_version,
        }

    @classmethod
    def _numeric_summary(cls, values: pd.Series) -> dict:
        if not len(values):
            return {key: None for key in ("mean", "median", "std", "min", "max")}
        return {
            "mean": cls._rounded(values.mean()),
            "median": cls._rounded(values.median()),
            "std": cls._rounded(values.std()),
            "min": cls._rounded(values.min()),
            "max": cls._rounded(values.max()),
        }

    @staticmethod
    def _column_identity(values: pd.Series) -> dict:
        return {
            "data_type": str(values.dtype),
            "missing_count": int(values.isna().sum()),
            "missing_ratio": round(float(values.isna().mean()), 6),
            "unique_count": int(values.nunique(dropna=True)),
        }

    @staticmethod
    def _is_numeric_pair(previous: pd.Series, current: pd.Series) -> bool:
        return pd.api.types.is_numeric_dtype(previous) and pd.api.types.is_numeric_dtype(current)

    @staticmethod
    def _change_level(score: float) -> str:
        if score < 1:
            return "negligible"
        if score < 10:
            return "minor"
        if score < 30:
            return "moderate"
        return "major"

    @staticmethod
    def _rounded(value: float) -> float | None:
        return None if pd.isna(value) else round(float(value), 6)

    @staticmethod
    def _bounded(value: float) -> float:
        return max(0.0, min(100.0, float(value or 0)))

    def _schema_change(self, added: list[str], removed: list[str], dtype_changes: dict, target_column: str | None) -> tuple[dict, float]:
        evidence = []
        severity = 0.0
        if target_column in removed:
            severity += SCHEMA_SEVERITY["target_removed"]
            evidence.append({"change": "target_removed", "column": target_column, "severity": SCHEMA_SEVERITY["target_removed"]})
        if target_column in added:
            severity += SCHEMA_SEVERITY["target_added"]
            evidence.append({"change": "target_added", "column": target_column, "severity": SCHEMA_SEVERITY["target_added"]})
        for column in removed:
            if column == target_column:
                continue
            severity += SCHEMA_SEVERITY["feature_removed"]
            evidence.append({"change": "feature_removed", "column": column, "severity": SCHEMA_SEVERITY["feature_removed"]})
        for column in added:
            if column == target_column:
                continue
            severity += SCHEMA_SEVERITY["feature_added"]
            evidence.append({"change": "feature_added", "column": column, "severity": SCHEMA_SEVERITY["feature_added"]})
        for column, change in dtype_changes.items():
            key = "target_dtype_changed" if column == target_column else "feature_dtype_changed"
            severity += SCHEMA_SEVERITY[key]
            evidence.append({"change": key, "column": column, "previous": change["previous"], "current": change["current"], "severity": SCHEMA_SEVERITY[key]})
        return {"events": evidence, "raw_severity": round(severity, 6)}, min(severity, 1.0)

    def _missingness_change(self, previous: pd.DataFrame, current: pd.DataFrame, common: list[str]) -> tuple[dict, float]:
        changes = {}
        deltas = []
        for column in common:
            old_count, new_count = int(previous[column].isna().sum()), int(current[column].isna().sum())
            old_ratio, new_ratio = float(previous[column].isna().mean()), float(current[column].isna().mean())
            delta = new_ratio - old_ratio
            deltas.append(abs(delta))
            if old_count != new_count or not np.isclose(old_ratio, new_ratio):
                changes[column] = {
                    "previous_count": old_count,
                    "current_count": new_count,
                    "count_delta": new_count - old_count,
                    "previous_ratio": round(old_ratio, 6),
                    "current_ratio": round(new_ratio, 6),
                    "ratio_delta": round(delta, 6),
                }
        if not deltas:
            return changes, 0.0
        return changes, min(1.0, 0.65 * float(np.mean(deltas)) + 0.35 * max(deltas))

    def _categorical_structure_score(self, previous: pd.DataFrame, current: pd.DataFrame, common: list[str], target_column: str | None) -> float:
        scores = []
        for column in common:
            if self._is_numeric_pair(previous[column], current[column]) and column != target_column:
                continue
            changes = self._distribution_changes(previous[column], current[column])
            structure = self._categorical_structure_shift(changes)
            changed_categories = len(structure["added_categories"]) + len(structure["removed_categories"])
            total_categories = max(len(changes), 1)
            scores.append(min(1.0, 0.6 * structure["distribution_shift"] + 0.4 * (changed_categories / total_categories)))
        return float(np.mean(scores)) if scores else 0.0

    @staticmethod
    def _numeric_distribution_shift(previous: pd.Series, current: pd.Series) -> float:
        if not len(previous) or not len(current):
            return 0.0
        combined = pd.concat([previous, current]).astype(float)
        old_dist = previous.astype(float).value_counts(normalize=True).sort_index()
        new_dist = current.astype(float).value_counts(normalize=True).sort_index()
        if old_dist.equals(new_dist):
            return 0.0
        scale = float(np.nanpercentile(combined, 75) - np.nanpercentile(combined, 25))
        if scale <= 1e-12:
            scale = float(combined.std() or 0)
        if scale <= 1e-12:
            scale = max(abs(float(combined.max() - combined.min())), 1.0)
        support = np.array(sorted(set(old_dist.index) | set(new_dist.index)), dtype=float)
        if len(support) <= 1:
            return 0.0
        old_probs = np.array([old_dist.get(value, 0.0) for value in support], dtype=float)
        new_probs = np.array([new_dist.get(value, 0.0) for value in support], dtype=float)
        old_cdf = np.cumsum(old_probs)
        new_cdf = np.cumsum(new_probs)
        gaps = np.diff(support)
        distance = float(np.sum(np.abs(old_cdf[:-1] - new_cdf[:-1]) * gaps))
        return min(1.0, distance / max(scale, 1e-9))

    @staticmethod
    def _distribution_changes(previous: pd.Series, current: pd.Series) -> list[dict]:
        old_values = previous.fillna("<MISSING>").astype(str)
        new_values = current.fillna("<MISSING>").astype(str)
        old_counts, new_counts = old_values.value_counts(), new_values.value_counts()
        old_total, new_total = max(len(old_values), 1), max(len(new_values), 1)
        labels = sorted(set(old_counts.index) | set(new_counts.index))
        return [{
            "value": label,
            "previous_count": int(old_counts.get(label, 0)),
            "current_count": int(new_counts.get(label, 0)),
            "count_delta": int(new_counts.get(label, 0) - old_counts.get(label, 0)),
            "previous_ratio": round(float(old_counts.get(label, 0) / old_total), 6),
            "current_ratio": round(float(new_counts.get(label, 0) / new_total), 6),
            "ratio_delta": round(float(new_counts.get(label, 0) / new_total - old_counts.get(label, 0) / old_total), 6),
        } for label in labels]

    @staticmethod
    def _categorical_structure_shift(changes: list[dict]) -> dict:
        old_probs = np.array([item["previous_ratio"] for item in changes], dtype=float)
        new_probs = np.array([item["current_ratio"] for item in changes], dtype=float)
        midpoint = (old_probs + new_probs) / 2

        def kl_divergence(values: np.ndarray, base: np.ndarray) -> float:
            mask = values > 0
            return float(np.sum(values[mask] * np.log2(values[mask] / np.maximum(base[mask], 1e-12))))

        jsd = 0.5 * kl_divergence(old_probs, midpoint) + 0.5 * kl_divergence(new_probs, midpoint)
        added_categories = [item["value"] for item in changes if item["previous_count"] == 0 and item["current_count"] > 0]
        removed_categories = [item["value"] for item in changes if item["previous_count"] > 0 and item["current_count"] == 0]
        return {
            "distribution_shift": min(1.0, float(np.sqrt(max(jsd, 0.0)))),
            "added_categories": added_categories,
            "removed_categories": removed_categories,
        }

    @staticmethod
    def _dsi_components(feature_shift_scores: dict[str, float]) -> dict[str, float]:
        if not feature_shift_scores:
            return {"mean_feature_shift": 0.0, "max_feature_shift": 0.0, "drifted_feature_ratio": 0.0}
        values = [score / 100 for score in feature_shift_scores.values()]
        return {
            "mean_feature_shift": float(np.mean(values)),
            "max_feature_shift": max(values),
            "drifted_feature_ratio": sum(score >= DRIFTED_FEATURE_THRESHOLD for score in feature_shift_scores.values()) / len(feature_shift_scores),
        }

    def _row_content_change(self, previous: pd.DataFrame, current: pd.DataFrame, common: list[str]) -> dict | None:
        if not common:
            return None
        key_columns = self._stable_key_columns(previous, current, common)
        if key_columns:
            old_keys = self._row_key_hashes(previous, key_columns)
            new_keys = self._row_key_hashes(current, key_columns)
            old_by_key = dict(zip(old_keys, self._row_hashes(previous, common), strict=False))
            new_by_key = dict(zip(new_keys, self._row_hashes(current, common), strict=False))
            old_key_set, new_key_set = set(old_by_key), set(new_by_key)
            unchanged = sum(1 for key in old_key_set & new_key_set if old_by_key[key] == new_by_key[key])
            modified = sum(1 for key in old_key_set & new_key_set if old_by_key[key] != new_by_key[key])
            added = len(new_key_set - old_key_set)
            removed = len(old_key_set - new_key_set)
            denominator = max(len(old_key_set | new_key_set), 1)
            return {
                "method": "stable_identifier_hash",
                "stable_key_columns": key_columns,
                "row_instances_added": added,
                "row_instances_removed": removed,
                "modified_row_instances": modified,
                "unchanged_row_instances": unchanged,
                "artifact_change_ratio": round((added + removed + modified) / denominator, 6),
                "turnover_ratio": round((added + removed) / max(len(previous) + len(current), 1), 6),
            }

        old_hashes = Counter(self._row_hashes(previous, common))
        new_hashes = Counter(self._row_hashes(current, common))
        hashes = set(old_hashes) | set(new_hashes)
        added = sum(max(new_hashes.get(value, 0) - old_hashes.get(value, 0), 0) for value in hashes)
        removed = sum(max(old_hashes.get(value, 0) - new_hashes.get(value, 0), 0) for value in hashes)
        unchanged = sum(min(old_hashes.get(value, 0), new_hashes.get(value, 0)) for value in hashes)
        denominator = max(len(previous) + len(current), 1)
        return {
            "method": "row_hash_multiset",
            "stable_key_columns": [],
            "row_instances_added": added,
            "row_instances_removed": removed,
            "modified_row_instances": 0,
            "unchanged_row_instances": unchanged,
            "artifact_change_ratio": round((added + removed) / denominator, 6),
            "turnover_ratio": round((added + removed) / denominator, 6),
        }

    @staticmethod
    def _stable_key_columns(previous: pd.DataFrame, current: pd.DataFrame, common: list[str]) -> list[str]:
        candidates = []
        for column in common:
            lower = str(column).lower()
            id_like = lower in IDENTIFIER_NAME_HINTS or lower.endswith("_id") or lower.endswith("id") or any(hint in lower for hint in ("uuid", "guid"))
            if not id_like:
                continue
            old_non_null = previous[column].notna().all()
            new_non_null = current[column].notna().all()
            old_unique = previous[column].nunique(dropna=True) == len(previous[column])
            new_unique = current[column].nunique(dropna=True) == len(current[column])
            if old_non_null and new_non_null and old_unique and new_unique:
                candidates.append(column)
        return sorted(candidates)[:2]

    def _row_hashes(self, frame: pd.DataFrame, columns: list[str]) -> list[int]:
        normalized = pd.DataFrame()
        for column in columns:
            normalized[column] = self._normalized_series(frame[column])
        return pd.util.hash_pandas_object(normalized, index=False).astype("uint64").tolist()

    def _row_key_hashes(self, frame: pd.DataFrame, columns: list[str]) -> list[int]:
        return self._row_hashes(frame, columns)

    @staticmethod
    def _normalized_series(values: pd.Series) -> pd.Series:
        if pd.api.types.is_numeric_dtype(values):
            return values.map(lambda value: "<MISSING>" if pd.isna(value) else format(float(value), ".15g"))
        return values.fillna("<MISSING>").astype(str)
