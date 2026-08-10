"""VariantBuilderService — applies a planned pipeline to a source CSV and
produces a transformed variant CSV.

All transformations are deterministic given the same random_seed.
No AI involvement. Returns a BuildResult dataclass.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import LabelEncoder, MinMaxScaler, RobustScaler, StandardScaler

# imbalanced-learn — optional; imported lazily to keep the service loadable
# even without the package installed (tests can mock it)
try:
    from imblearn.over_sampling import ADASYN, SMOTE, RandomOverSampler
    from imblearn.under_sampling import RandomUnderSampler
    _IMBLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _IMBLEARN_AVAILABLE = False


@dataclass
class BuildResult:
    output_csv_path: str
    row_count_before: int
    row_count_after: int
    column_count_before: int
    column_count_after: int
    missing_values_pct_before: float
    missing_values_pct_after: float
    class_balance_score_before: float   # 0–1; 1 = perfectly balanced
    class_balance_score_after: float
    execution_time_seconds: float
    library_versions: dict
    applied_steps: list[str]            # transformation_ids that succeeded
    error: str | None = None


def _class_balance_score(df: pd.DataFrame, target_col: str | None) -> float:
    """Compute class balance score 0–1 (1 = perfectly balanced). 0 if no target."""
    if not target_col or target_col not in df.columns:
        return 1.0  # non-classification → no imbalance concept
    counts = df[target_col].value_counts()
    if len(counts) < 2:
        return 1.0
    min_ratio = counts.min() / counts.sum()
    max_ratio = counts.max() / counts.sum()
    perfect = 1.0 / len(counts)
    # Score: how close to perfect balance (each class = 1/n)
    imbalance = abs(max_ratio - perfect) / (1.0 - perfect) if (1.0 - perfect) > 0 else 0.0
    return round(max(0.0, 1.0 - imbalance), 6)


def _missing_pct(df: pd.DataFrame) -> float:
    total = df.size
    if total == 0:
        return 0.0
    return round(float(df.isna().sum().sum() / total * 100), 6)


class VariantBuilderService:
    """Applies a planned pipeline list to source CSV. Returns BuildResult."""

    def build(
        self,
        source_csv_path: str,
        pipeline: dict,
        requirements: dict,
        job_id: int,
        random_seed: int = 42,
    ) -> BuildResult:
        start_time = time.time()
        steps: list[dict] = pipeline.get("steps", [])
        pipeline_id: str = pipeline.get("pipeline_id", "Pipeline-A")
        target_col: str | None = requirements.get("target_column")
        study_type: str = requirements.get("study_type", "classification")
        minority_count: int | None = requirements.get("minority_class_count")

        applied_steps: list[str] = []

        # ── output path ──────────────────────────────────────────────────────
        safe_id = pipeline_id.lower().replace("-", "_")
        out_dir = Path("uploads") / "variants" / str(job_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(out_dir / f"{safe_id}.csv")

        # ── library versions ─────────────────────────────────────────────────
        lib_versions: dict = {
            "pandas": pd.__version__,
            "scikit-learn": sklearn.__version__,
            "numpy": np.__version__,
        }
        if _IMBLEARN_AVAILABLE:
            try:
                import imblearn
                lib_versions["imbalanced-learn"] = imblearn.__version__
            except Exception:
                pass

        try:
            df = pd.read_csv(source_csv_path)
        except Exception as exc:
            return BuildResult(
                output_csv_path=output_path,
                row_count_before=0, row_count_after=0,
                column_count_before=0, column_count_after=0,
                missing_values_pct_before=0.0, missing_values_pct_after=0.0,
                class_balance_score_before=0.0, class_balance_score_after=0.0,
                execution_time_seconds=0.0, library_versions=lib_versions,
                applied_steps=[], error=f"Could not read source CSV: {exc}",
            )

        # ── baseline metrics ─────────────────────────────────────────────────
        row_count_before = len(df)
        column_count_before = len(df.columns)
        missing_pct_before = _missing_pct(df)
        balance_before = _class_balance_score(df, target_col)
        original_columns = list(df.columns)

        # ── separate column types (never transform target column as feature) ─
        feature_cols = [c for c in df.columns if c != target_col]
        numeric_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
        categorical_cols = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(df[c])]

        try:
            for step in steps:
                tid = step["transformation_id"]
                params = step.get("params", {})
                try:
                    df, numeric_cols, categorical_cols = self._apply_step(
                        df, tid, params, target_col, study_type,
                        numeric_cols, categorical_cols,
                        minority_count, random_seed,
                    )
                    applied_steps.append(tid)
                    # Refresh column lists after each step
                    feature_cols = [c for c in df.columns if c != target_col]
                    numeric_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
                    categorical_cols = [c for c in feature_cols if not pd.api.types.is_numeric_dtype(df[c])]
                except Exception as step_exc:
                    # Log step failure but continue with remaining steps
                    import logging
                    logging.getLogger(__name__).warning(
                        "Step %s failed (continuing): %s", tid, step_exc
                    )

            # ── restore original column order (minus removed columns) ────────
            remaining = [c for c in original_columns if c in df.columns]
            df = df[remaining]

            df.to_csv(output_path, index=False)

            exec_time = round(time.time() - start_time, 3)
            return BuildResult(
                output_csv_path=output_path,
                row_count_before=row_count_before,
                row_count_after=len(df),
                column_count_before=column_count_before,
                column_count_after=len(df.columns),
                missing_values_pct_before=missing_pct_before,
                missing_values_pct_after=_missing_pct(df),
                class_balance_score_before=balance_before,
                class_balance_score_after=_class_balance_score(df, target_col),
                execution_time_seconds=exec_time,
                library_versions=lib_versions,
                applied_steps=applied_steps,
            )

        except Exception as exc:
            return BuildResult(
                output_csv_path=output_path,
                row_count_before=row_count_before,
                row_count_after=row_count_before,
                column_count_before=column_count_before,
                column_count_after=column_count_before,
                missing_values_pct_before=missing_pct_before,
                missing_values_pct_after=missing_pct_before,
                class_balance_score_before=balance_before,
                class_balance_score_after=balance_before,
                execution_time_seconds=round(time.time() - start_time, 3),
                library_versions=lib_versions,
                applied_steps=applied_steps,
                error=traceback.format_exc(limit=5),
            )

    def _apply_step(
        self,
        df: pd.DataFrame,
        tid: str,
        params: dict,
        target_col: str | None,
        study_type: str,
        numeric_cols: list[str],
        categorical_cols: list[str],
        minority_count: int | None,
        random_seed: int,
    ) -> tuple[pd.DataFrame, list[str], list[str]]:
        """Apply a single transformation. Returns updated (df, numeric_cols, categorical_cols)."""

        # ── duplicate_removal ────────────────────────────────────────────────
        if tid == "drop_duplicates":
            df = df.drop_duplicates(keep=params.get("keep", "first")).reset_index(drop=True)

        # ── missing_value_handling ───────────────────────────────────────────
        elif tid == "median_imputation":
            if numeric_cols:
                imp = SimpleImputer(strategy="median")
                df[numeric_cols] = imp.fit_transform(df[numeric_cols])
            if categorical_cols:
                imp_cat = SimpleImputer(strategy="most_frequent")
                df[categorical_cols] = imp_cat.fit_transform(df[categorical_cols])

        elif tid == "mean_imputation":
            if numeric_cols:
                imp = SimpleImputer(strategy="mean")
                df[numeric_cols] = imp.fit_transform(df[numeric_cols])
            if categorical_cols:
                imp_cat = SimpleImputer(strategy="most_frequent")
                df[categorical_cols] = imp_cat.fit_transform(df[categorical_cols])

        elif tid == "drop_missing_rows":
            threshold = params.get("threshold", 0.5)
            n_cols = len(df.columns)
            min_valid = int((1.0 - threshold) * n_cols)
            df = df.dropna(thresh=min_valid).reset_index(drop=True)

        # ── encoding ─────────────────────────────────────────────────────────
        elif tid == "label_encoding":
            for col in categorical_cols:
                le = LabelEncoder()
                not_null_mask = df[col].notna()
                df.loc[not_null_mask, col] = le.fit_transform(
                    df.loc[not_null_mask, col].astype(str)
                )
                df[col] = pd.to_numeric(df[col], errors="coerce")
            # After encoding, these columns become numeric
            numeric_cols = numeric_cols + [c for c in categorical_cols if c in df.columns]
            categorical_cols = []

        elif tid == "onehot_encoding":
            max_cat = params.get("max_categories", 20)
            cols_to_encode = [
                c for c in categorical_cols
                if df[c].nunique(dropna=True) <= max_cat
            ]
            if cols_to_encode:
                df = pd.get_dummies(df, columns=cols_to_encode, drop_first=False, dummy_na=False)
                # Update column lists
                new_numeric = [c for c in df.columns if c not in (categorical_cols + [target_col or ""])]
                numeric_cols = new_numeric if new_numeric else numeric_cols
                categorical_cols = [c for c in categorical_cols if c not in cols_to_encode and c in df.columns]

        # ── outlier_treatment ────────────────────────────────────────────────
        elif tid == "iqr_filtering":
            factor = params.get("factor", 1.5)
            if numeric_cols:
                q1 = df[numeric_cols].quantile(0.25)
                q3 = df[numeric_cols].quantile(0.75)
                iqr = q3 - q1
                mask = ~((df[numeric_cols] < (q1 - factor * iqr)) | (df[numeric_cols] > (q3 + factor * iqr))).any(axis=1)
                df = df[mask].reset_index(drop=True)

        elif tid == "isolation_forest":
            if numeric_cols and len(df) > 10:
                # Use "auto" contamination — adapts to actual outlier prevalence
                iso = IsolationForest(contamination="auto", random_state=random_seed)
                pred = iso.fit_predict(df[numeric_cols].fillna(df[numeric_cols].median()))
                df = df[pred == 1].reset_index(drop=True)

        elif tid == "clip_outliers":
            lower = params.get("lower", 0.01)
            upper = params.get("upper", 0.99)
            if numeric_cols:
                for col in numeric_cols:
                    lo = df[col].quantile(lower)
                    hi = df[col].quantile(upper)
                    df[col] = df[col].clip(lower=lo, upper=hi)

        # ── class_balancing (classification only) ────────────────────────────
        elif tid in ("smote", "adasyn", "random_oversampling", "random_undersampling"):
            if study_type == "classification" and target_col and target_col in df.columns and _IMBLEARN_AVAILABLE:
                # Only use numeric features for resampling (object cols already encoded or will be encoded)
                resample_feature_cols = [c for c in numeric_cols if c in df.columns]
                if resample_feature_cols:
                    X = df[resample_feature_cols].fillna(df[resample_feature_cols].median())
                    y = df[target_col].astype(str)

                    if tid == "smote":
                        mc = minority_count
                        k = max(1, min(5, mc - 1)) if mc and mc > 1 else None
                        if k:
                            sampler = SMOTE(k_neighbors=k, random_state=random_seed)
                        else:
                            sampler = RandomOverSampler(random_state=random_seed)
                    elif tid == "adasyn":
                        mc = minority_count
                        n = max(1, min(5, mc - 1)) if mc and mc > 1 else None
                        if n:
                            sampler = ADASYN(n_neighbors=n, random_state=random_seed)
                        else:
                            sampler = RandomOverSampler(random_state=random_seed)
                    elif tid == "random_oversampling":
                        sampler = RandomOverSampler(random_state=random_seed)
                    else:  # random_undersampling
                        sampler = RandomUnderSampler(random_state=random_seed)

                    X_res, y_res = sampler.fit_resample(X, y)
                    resampled_df = pd.DataFrame(X_res, columns=resample_feature_cols)
                    resampled_df[target_col] = y_res.values
                    # Retain non-numeric (still present) columns with NaN (they were not resampled)
                    for col in df.columns:
                        if col not in resampled_df.columns:
                            resampled_df[col] = np.nan
                    df = resampled_df

        # ── feature_reduction ────────────────────────────────────────────────
        elif tid == "correlation_filter":
            threshold = params.get("threshold", 0.9)
            if len(numeric_cols) > 1:
                corr_matrix = df[numeric_cols].corr().abs()
                upper = corr_matrix.where(
                    np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
                )
                # Drop lower-variance column of each highly-correlated pair
                to_drop = set()
                for col in upper.columns:
                    correlated = upper.index[upper[col] >= threshold].tolist()
                    for other in correlated:
                        # drop whichever has lower variance
                        drop_col = col if df[col].var() < df[other].var() else other
                        to_drop.add(drop_col)
                if to_drop:
                    df = df.drop(columns=list(to_drop))
                    numeric_cols = [c for c in numeric_cols if c not in to_drop]

        elif tid == "mutual_information":
            if target_col and target_col in df.columns and numeric_cols:
                from sklearn.feature_selection import SelectKBest, mutual_info_classif, mutual_info_regression
                k = min(params.get("k", 20), len(numeric_cols))
                X_feats = df[numeric_cols].fillna(df[numeric_cols].median())
                y_feats = df[target_col]
                mi_func = mutual_info_classif if study_type == "classification" else mutual_info_regression
                selector = SelectKBest(mi_func, k=k)
                selector.fit(X_feats, y_feats)
                selected_mask = selector.get_support()
                selected_cols = [c for c, s in zip(numeric_cols, selected_mask) if s]
                removed = [c for c in numeric_cols if c not in selected_cols]
                if removed:
                    df = df.drop(columns=removed)
                    numeric_cols = selected_cols

        elif tid == "variance_threshold":
            threshold = params.get("threshold", 0.01)
            if numeric_cols:
                variances = df[numeric_cols].var()
                low_var = variances[variances < threshold].index.tolist()
                if low_var:
                    df = df.drop(columns=low_var)
                    numeric_cols = [c for c in numeric_cols if c not in low_var]

        # ── scaling ──────────────────────────────────────────────────────────
        elif tid == "standard_scaler":
            current_numeric = [c for c in numeric_cols if c in df.columns]
            if current_numeric:
                scaler = StandardScaler()
                df[current_numeric] = scaler.fit_transform(df[current_numeric].fillna(df[current_numeric].median()))

        elif tid == "robust_scaler":
            current_numeric = [c for c in numeric_cols if c in df.columns]
            if current_numeric:
                scaler = RobustScaler()
                df[current_numeric] = scaler.fit_transform(df[current_numeric].fillna(df[current_numeric].median()))

        elif tid == "minmax_scaler":
            current_numeric = [c for c in numeric_cols if c in df.columns]
            if current_numeric:
                scaler = MinMaxScaler()
                df[current_numeric] = scaler.fit_transform(df[current_numeric].fillna(df[current_numeric].median()))

        return df, numeric_cols, categorical_cols
