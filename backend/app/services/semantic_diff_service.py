import numpy as np
import pandas as pd


class SemanticDiffService:
    ruleset_version = "semantic-1.2"

    def compare(self, previous: pd.DataFrame, current: pd.DataFrame, target_column: str | None) -> dict:
        old_columns, new_columns = set(previous.columns), set(current.columns)
        common = sorted(old_columns & new_columns)
        added, removed = sorted(new_columns - old_columns), sorted(old_columns - new_columns)
        dtype_changes = {column: {"previous": str(previous[column].dtype), "current": str(current[column].dtype)} for column in common if str(previous[column].dtype) != str(current[column].dtype)}
        added_details = {column: self._column_identity(current[column]) for column in added}
        removed_details = {column: self._column_identity(previous[column]) for column in removed}
        old_missing = float(previous.isna().mean().mean())
        new_missing = float(current.isna().mean().mean())
        row_change = abs(len(current) - len(previous)) / max(len(previous), 1)
        schema_change = (len(added) + len(removed) + len(dtype_changes)) / max(len(old_columns | new_columns), 1)
        numeric_shifts, feature_shifts, numeric_changes = [], {}, {}
        target_is_categorical = bool(
            target_column
            and target_column in common
            and len(set(previous[target_column].dropna().astype(str)) | set(current[target_column].dropna().astype(str))) <= 50
        )
        for column in common:
            if pd.api.types.is_numeric_dtype(previous[column]) and pd.api.types.is_numeric_dtype(current[column]):
                old = pd.to_numeric(previous[column], errors="coerce").dropna()
                new = pd.to_numeric(current[column], errors="coerce").dropna()
                pooled = max(float(pd.concat([old, new]).std() or 0), 1e-9)
                shift = min(abs(float(new.mean() if len(new) else 0) - float(old.mean() if len(old) else 0)) / pooled, 3) / 3
                shift_score = round(shift * 100, 3)
                if column != target_column:
                    numeric_shifts.append(shift)
                    feature_shifts[column] = shift_score
                if column == target_column and target_is_categorical:
                    continue
                previous_stats = self._numeric_summary(old)
                current_stats = self._numeric_summary(new)
                numeric_changes[column] = {
                    "previous": previous_stats,
                    "current": current_stats,
                    "delta": {
                        key: self._rounded((current_stats[key] or 0) - (previous_stats[key] or 0))
                        for key in ("mean", "median", "std", "min", "max")
                    },
                    "normalized_shift_score": shift_score,
                    "change_level": self._change_level(shift_score),
                }

        missingness_changes = {}
        for column in common:
            old_count, new_count = int(previous[column].isna().sum()), int(current[column].isna().sum())
            old_ratio, new_ratio = float(previous[column].isna().mean()), float(current[column].isna().mean())
            if old_count != new_count or not np.isclose(old_ratio, new_ratio):
                missingness_changes[column] = {
                    "previous_count": old_count,
                    "current_count": new_count,
                    "count_delta": new_count - old_count,
                    "previous_ratio": round(old_ratio, 6),
                    "current_ratio": round(new_ratio, 6),
                    "ratio_delta": round(new_ratio - old_ratio, 6),
                }

        categorical_changes = {}
        for column in common:
            if column == target_column and target_is_categorical:
                categorical_changes[column] = self._distribution_changes(previous[column], current[column])
                continue
            if pd.api.types.is_numeric_dtype(previous[column]) and pd.api.types.is_numeric_dtype(current[column]):
                continue
            combined_unique = len(set(previous[column].dropna().astype(str)) | set(current[column].dropna().astype(str)))
            if column != target_column and combined_unique > 50:
                continue
            changes = self._distribution_changes(previous[column], current[column])
            material = sorted(changes, key=lambda item: abs(item["ratio_delta"]), reverse=True)
            if any(item["previous_count"] != item["current_count"] for item in material):
                categorical_changes[column] = material[:20 if column == target_column else 10]

        target_shift, target_distribution = 0.0, {}
        if target_column and target_column in common:
            if target_is_categorical:
                old_dist = previous[target_column].fillna("<MISSING>").astype(str).value_counts(normalize=True)
                new_dist = current[target_column].fillna("<MISSING>").astype(str).value_counts(normalize=True)
                labels = sorted(set(old_dist.index) | set(new_dist.index))
                changes = {label: float(new_dist.get(label, 0) - old_dist.get(label, 0)) for label in labels}
                target_shift = min(sum(abs(value) for value in changes.values()) / 2, 1)
                target_distribution = {key: round(value, 6) for key, value in changes.items()}
            elif target_column in numeric_changes:
                target_shift = numeric_changes[target_column]["normalized_shift_score"] / 100
                target_distribution = {
                    "mode": "continuous",
                    "previous": numeric_changes[target_column]["previous"],
                    "current": numeric_changes[target_column]["current"],
                    "delta": numeric_changes[target_column]["delta"],
                }

        duplicate_previous, duplicate_current = int(previous.duplicated().sum()), int(current.duplicated().sum())
        row_content_change = self._row_content_change(previous, current)
        distribution_shift = float(np.mean(numeric_shifts)) if numeric_shifts else 0.0
        scm = min(100.0, 100 * (0.55 * schema_change + 0.25 * row_change + 0.20 * abs(new_missing - old_missing)))
        dsi = min(100.0, 100 * (0.45 * distribution_shift + 0.35 * target_shift + 0.20 * row_change))
        return {
            "report": {
                "columns_added": added,
                "columns_added_details": added_details,
                "columns_removed": removed,
                "columns_removed_details": removed_details,
                "data_type_changes": dtype_changes,
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
                "feature_shift_scores": feature_shifts,
            },
            "scm_score": round(scm, 3), "dsi_score": round(dsi, 3), "ruleset_version": self.ruleset_version,
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
    def _change_level(score: float) -> str:
        if score < 0.1:
            return "negligible"
        if score < 1:
            return "minor"
        if score < 5:
            return "moderate"
        return "major"

    @staticmethod
    def _rounded(value: float) -> float | None:
        return None if pd.isna(value) else round(float(value), 6)

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
    def _row_content_change(previous: pd.DataFrame, current: pd.DataFrame) -> dict | None:
        if set(previous.columns) != set(current.columns):
            return None
        ordered_current = current[list(previous.columns)]
        old_normalized, new_normalized = pd.DataFrame(), pd.DataFrame()
        for column in previous.columns:
            if pd.api.types.is_numeric_dtype(previous[column]) and pd.api.types.is_numeric_dtype(ordered_current[column]):
                normalize = lambda value: "<MISSING>" if pd.isna(value) else format(float(value), ".15g")
                old_normalized[column] = previous[column].map(normalize)
                new_normalized[column] = ordered_current[column].map(normalize)
            else:
                old_normalized[column] = previous[column].fillna("<MISSING>").astype(str)
                new_normalized[column] = ordered_current[column].fillna("<MISSING>").astype(str)
        old_hashes = pd.util.hash_pandas_object(old_normalized, index=False).value_counts()
        new_hashes = pd.util.hash_pandas_object(new_normalized, index=False).value_counts()
        hashes = set(old_hashes.index) | set(new_hashes.index)
        added = sum(max(int(new_hashes.get(value, 0) - old_hashes.get(value, 0)), 0) for value in hashes)
        removed = sum(max(int(old_hashes.get(value, 0) - new_hashes.get(value, 0)), 0) for value in hashes)
        unchanged = sum(min(int(old_hashes.get(value, 0)), int(new_hashes.get(value, 0))) for value in hashes)
        return {
            "row_instances_added": added,
            "row_instances_removed": removed,
            "unchanged_row_instances": unchanged,
            "turnover_ratio": round((added + removed) / max(len(previous) + len(current), 1), 6),
        }
