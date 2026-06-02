"""Data profiling schemas (spec 19.1).

Key rule (19.2): the profiler DETECTS and RECOMMENDS but never silently deletes.
Outliers are flagged in ``candidate_outliers``; no destructive action is encoded
in the profile.
"""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel


class ColumnProfile(MFBaseModel):
    name: str
    inferred_type: str  # numeric | integer | float | categorical | datetime | text | boolean
    missing_count: int = 0
    missing_fraction: float = 0.0
    unique_count: int = 0
    cardinality_ratio: float = 0.0
    is_potential_identifier: bool = False
    is_datetime: bool = False
    # numeric summary (None for non-numeric)
    min: float | None = None
    max: float | None = None
    mean: float | None = None
    std: float | None = None
    median: float | None = None
    candidate_outlier_count: int = 0
    sample_values: list[str] = Field(default_factory=list)


class DataProfile(MFBaseModel):
    """Profile of one dataset file (spec 19.1)."""

    file_id: str
    filename: str
    row_count: int = 0
    column_count: int = 0
    duplicate_row_count: int = 0
    columns: list[ColumnProfile] = Field(default_factory=list)
    date_columns: list[str] = Field(default_factory=list)
    potential_identifier_columns: list[str] = Field(default_factory=list)
    potential_leakage_warnings: list[str] = Field(default_factory=list)
    correlation_summary: dict[str, float] = Field(default_factory=dict)
    data_quality_warnings: list[str] = Field(default_factory=list)
    unit_metadata: dict[str, str] = Field(default_factory=dict)
    artifact_id: str | None = None

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]
