from typing import Any

import numpy as np
import pandas as pd

from app.utilities.dataframe import iqr_outlier_mask, json_value


class ProfilingService:
    profiler_version = "profile-1.0"

    def profile(self, frame: pd.DataFrame, task_type: str, configuration: dict) -> dict[str, Any]:
        target = configuration.get("target_column")
        columns = []
        for name in frame.columns:
            series = frame[name]
            numeric = pd.api.types.is_numeric_dtype(series)
            row = {"name": name, "data_type": str(series.dtype), "role": "target" if name == target else "feature", "missing_count": int(series.isna().sum()), "missing_ratio": round(float(series.isna().mean()), 6), "unique_count": int(series.nunique(dropna=True)), "unique_ratio": round(float(series.nunique(dropna=True) / max(len(series), 1)), 6)}
            if numeric:
                clean = pd.to_numeric(series, errors="coerce").dropna()
                row["statistics"] = {key: json_value(value) for key, value in {"min": clean.min() if len(clean) else None, "q25": clean.quantile(.25) if len(clean) else None, "median": clean.median() if len(clean) else None, "q75": clean.quantile(.75) if len(clean) else None, "max": clean.max() if len(clean) else None, "mean": clean.mean() if len(clean) else None, "std": clean.std() if len(clean) else None, "skewness": clean.skew() if len(clean) else None}.items()}
                row["outlier_count"] = int(iqr_outlier_mask(series).sum())
                row["outlier_ratio"] = round(row["outlier_count"] / max(len(frame), 1), 6)
            else:
                row["top_values"] = [{"value": str(key), "count": int(value)} for key, value in series.dropna().value_counts().head(10).items()]
            columns.append(row)
        numeric = frame.select_dtypes(include="number")
        correlations = []
        if 1 < len(numeric.columns) <= 200:
            matrix = numeric.corr()
            for index, left in enumerate(matrix.columns):
                for right in matrix.columns[index + 1:]:
                    value = matrix.loc[left, right]
                    if pd.notna(value) and abs(value) >= .8:
                        correlations.append({"left": left, "right": right, "correlation": round(float(value), 6)})
        report = {"summary": {"row_count": int(len(frame)), "column_count": int(len(frame.columns)), "missing_cells": int(frame.isna().sum().sum()), "missing_ratio": round(float(frame.isna().sum().sum() / max(frame.size, 1)), 6), "duplicate_rows": int(frame.duplicated().sum()), "duplicate_ratio": round(float(frame.duplicated().mean()), 6), "numeric_columns": int(len(numeric.columns)), "categorical_columns": int(len(frame.columns) - len(numeric.columns))}, "columns": columns, "high_correlations": correlations, "task_type": task_type, "task_profile": {}}
        if task_type == "classification" and target in frame.columns:
            counts = frame[target].dropna().astype(str).value_counts()
            total = max(int(counts.sum()), 1)
            report["task_profile"] = {"target_column": target, "class_distribution": {key: int(value) for key, value in counts.items()}, "class_ratios": {key: round(int(value) / total, 6) for key, value in counts.items()}, "minority_class": str(counts.idxmin()) if len(counts) else None, "imbalance_ratio": round(float(counts.max() / max(counts.min(), 1)), 4) if len(counts) else None}
        elif task_type == "regression" and target in frame.columns:
            values = pd.to_numeric(frame[target], errors="coerce")
            clean = values.dropna()
            report["task_profile"] = {"target_column": target, "target_skewness": json_value(clean.skew() if len(clean) else None), "target_outlier_count": int(iqr_outlier_mask(values).sum()), "target_missing_ratio": round(float(values.isna().mean()), 6), "target_statistics": {key: json_value(value) for key, value in (clean.describe().to_dict() if len(clean) else {}).items()}}
        elif task_type == "clustering":
            selected = configuration.get("selected_features") or list(numeric.columns)
            selected_numeric = [column for column in selected if column in numeric.columns]
            spreads = {column: json_value(numeric[column].std()) for column in selected_numeric}
            nonzero = [value for value in spreads.values() if value not in (None, 0)]
            spread_ratio = max(nonzero) / min(nonzero) if nonzero else 1
            report["task_profile"] = {"selected_features": selected_numeric, "feature_spread": spreads, "scaling_required": bool(spread_ratio > 10), "spread_ratio": round(float(spread_ratio), 4), "dimensionality_ratio": round(len(selected_numeric) / max(len(frame), 1), 6), "high_dimensional": len(selected_numeric) > max(20, len(frame) / 10)}
        return report
