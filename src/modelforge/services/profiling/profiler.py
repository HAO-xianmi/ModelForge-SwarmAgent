"""Deterministic data profiler (spec 19.1).

Critical rule (19.2): the profiler DETECTS and RECOMMENDS — it never deletes.
Outliers are counted and flagged; no row is removed. The profile is a pure
function of the input bytes, so it is reproducible.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from modelforge.schemas.data import ColumnProfile, DataProfile

# Heuristic thresholds.
_ID_CARDINALITY_RATIO = 0.95  # near-unique column => likely identifier
_HIGH_MISSING_FRACTION = 0.4
_LEAKAGE_KEYWORDS = ("target", "label", "outcome", "y_true", "ground_truth", "result")


class DataProfiler:
    def profile_csv_bytes(self, file_id: str, filename: str, data: bytes) -> DataProfile:
        df = pd.read_csv(io.BytesIO(data))
        return self._profile_frame(file_id, filename, df)

    def profile_xlsx_bytes(self, file_id: str, filename: str, data: bytes) -> DataProfile:
        df = pd.read_excel(io.BytesIO(data))
        return self._profile_frame(file_id, filename, df)

    # ------------------------------------------------------------------ #
    def _profile_frame(self, file_id: str, filename: str, df: pd.DataFrame) -> DataProfile:
        row_count = len(df)
        columns: list[ColumnProfile] = []
        date_columns: list[str] = []
        identifier_columns: list[str] = []
        quality_warnings: list[str] = []

        for name in df.columns:
            series = df[name]
            col = self._profile_column(str(name), series, row_count)
            if col.is_datetime:
                date_columns.append(col.name)
            if col.is_potential_identifier:
                identifier_columns.append(col.name)
            if col.missing_fraction >= _HIGH_MISSING_FRACTION:
                quality_warnings.append(
                    f"column '{col.name}' is {col.missing_fraction:.0%} missing"
                )
            columns.append(col)

        leakage = self._leakage_heuristics(df)
        correlations = self._correlation_summary(df)
        duplicate_count = int(df.duplicated().sum())
        if duplicate_count:
            quality_warnings.append(f"{duplicate_count} duplicate rows detected")

        return DataProfile(
            file_id=file_id,
            filename=filename,
            row_count=row_count,
            column_count=int(df.shape[1]),
            duplicate_row_count=duplicate_count,
            columns=columns,
            date_columns=date_columns,
            potential_identifier_columns=identifier_columns,
            potential_leakage_warnings=leakage,
            correlation_summary=correlations,
            data_quality_warnings=quality_warnings,
        )

    def _profile_column(
        self, name: str, series: pd.Series, row_count: int
    ) -> ColumnProfile:
        missing = int(series.isna().sum())
        non_null = series.dropna()
        unique = int(non_null.nunique())
        cardinality_ratio = (unique / row_count) if row_count else 0.0
        inferred = _infer_type(series)
        is_datetime = inferred == "datetime"
        is_id = (
            cardinality_ratio >= _ID_CARDINALITY_RATIO
            and inferred in ("integer", "text", "categorical")
            and row_count > 1
        )

        col = ColumnProfile(
            name=name,
            inferred_type=inferred,
            missing_count=missing,
            missing_fraction=(missing / row_count) if row_count else 0.0,
            unique_count=unique,
            cardinality_ratio=round(cardinality_ratio, 4),
            is_potential_identifier=is_id,
            is_datetime=is_datetime,
            sample_values=[str(v) for v in non_null.unique()[:5]],
        )

        if inferred in ("numeric", "integer", "float") and len(non_null):
            numeric = pd.to_numeric(non_null, errors="coerce").dropna()
            if len(numeric):
                col.min = float(numeric.min())
                col.max = float(numeric.max())
                col.mean = float(numeric.mean())
                col.std = float(numeric.std(ddof=0))
                col.median = float(numeric.median())
                col.candidate_outlier_count = _count_outliers_iqr(numeric)
        return col

    def _leakage_heuristics(self, df: pd.DataFrame) -> list[str]:
        """Flag columns whose names suggest the target (potential leakage)."""
        warnings: list[str] = []
        cols = [str(c) for c in df.columns]
        target_like = [c for c in cols if any(k in c.lower() for k in _LEAKAGE_KEYWORDS)]
        if len(target_like) > 1:
            warnings.append(
                "multiple target-like columns: " + ", ".join(target_like)
            )
        # Near-perfect correlation between a feature and a target-like column.
        if target_like:
            numeric = df.select_dtypes(include=[np.number])
            for t in target_like:
                if t in numeric.columns:
                    corr = numeric.corr(numeric_only=True)[t].drop(labels=[t], errors="ignore")
                    for other, value in corr.items():
                        if abs(value) >= 0.999:
                            warnings.append(
                                f"'{other}' nearly identical to target '{t}' (corr={value:.3f})"
                            )
        return warnings

    def _correlation_summary(self, df: pd.DataFrame) -> dict[str, float]:
        numeric = df.select_dtypes(include=[np.number])
        if numeric.shape[1] < 2:
            return {}
        corr = numeric.corr(numeric_only=True)
        out: dict[str, float] = {}
        cols = list(corr.columns)
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                value = corr.iloc[i, j]
                if pd.notna(value) and abs(value) >= 0.5:
                    out[f"{cols[i]}~{cols[j]}"] = round(float(value), 4)
        return out


def _infer_type(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    # Try parsing object columns as datetime (common in CSVs).
    non_null = series.dropna()
    if len(non_null) and series.dtype == object:
        parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
        if parsed.notna().mean() >= 0.9:
            return "datetime"
        # Low-cardinality strings => categorical.
        if non_null.nunique() <= max(1, int(0.5 * len(non_null))):
            return "categorical"
        return "text"
    return "text"


def _count_outliers_iqr(numeric: pd.Series) -> int:
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return 0
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    return int(((numeric < low) | (numeric > high)).sum())
