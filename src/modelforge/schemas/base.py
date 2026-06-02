"""Shared base model and timestamp mixin for all schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from modelforge.common.timeutil import utcnow


class MFBaseModel(BaseModel):
    """Base for every ModelForge schema.

    Config choices:
      * ``use_enum_values=False`` — keep enum members typed (we serialize via
        ``model_dump(mode="json")`` which renders StrEnum as its value anyway).
      * ``extra="forbid"`` — reject unknown fields so malformed LLM output is
        caught early (spec 37.2 output validation).
      * ``validate_assignment=True`` — keep instances valid after mutation.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
        ser_json_timedelta="float",
    )


class TimestampedModel(MFBaseModel):
    """Adds created/updated timestamps in UTC."""

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def touch(self) -> None:
        self.updated_at = utcnow()
