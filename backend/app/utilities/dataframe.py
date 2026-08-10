from typing import Any

import numpy as np
import pandas as pd


def json_value(value: Any) -> Any:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def iqr_outlier_mask(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    q1, q3 = numeric.quantile(0.25), numeric.quantile(0.75)
    iqr = q3 - q1
    if pd.isna(iqr) or iqr == 0:
        return pd.Series(False, index=series.index)
    return (numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)

