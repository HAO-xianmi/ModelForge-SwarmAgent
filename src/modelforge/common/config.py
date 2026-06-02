"""Configuration loading and environment validation (spec section 36).

Precedence (low -> high): hard-coded safe defaults, then environment / ``.env``.
Competition-profile and run-level overrides are applied later by the control
plane, not here. Secrets are read from the environment and never written to
artifacts or logs.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class OperatingMode(StrEnum):
    PRACTICE = "practice"
    CONTEST_COMPLIANT = "contest_compliant"
    RESEARCH = "research"


class BudgetProfile(StrEnum):
    DEMO = "demo"
    STANDARD = "standard"
    HIGH_QUALITY = "high_quality"
    RESEARCH = "research"


class LLMBackend(StrEnum):
    MOCK = "mock"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class SandboxBackend(StrEnum):
    AUTO = "auto"
    DOCKER = "docker"
    SUBPROCESS = "subprocess"


class Settings(BaseSettings):
    """Process-wide settings, populated from environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="MODELFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Mode / budget
    mode: OperatingMode = OperatingMode.PRACTICE
    budget_profile: BudgetProfile = BudgetProfile.STANDARD

    # Storage
    runs_dir: Path = Path("./runs")
    database_url: str = Field(default="sqlite:///./modelforge.db", alias="DATABASE_URL")
    redis_url: str | None = Field(default=None, alias="REDIS_URL")

    # LLM (note: keys use their own env names, not the MODELFORGE_ prefix)
    llm: LLMBackend = LLMBackend.MOCK
    llm_model: str = ""
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")

    # Sandbox
    sandbox: SandboxBackend = SandboxBackend.AUTO
    sandbox_timeout: int = 120
    sandbox_memory_mb: int = 1024
    sandbox_cpu: float = 1.0
    sandbox_image: str = "modelforge-sandbox:latest"

    # Loop protection / budgets (spec 7.3, 14.4)
    max_debug_retries: int = 3
    max_model_revisions: int = 2
    max_report_revisions: int = 2
    max_citation_retries: int = 2
    max_total_loops: int = 12
    max_proposer_instances: int = 3
    max_debate_rounds: int = 2

    # Uploads
    max_upload_mb: int = 50

    @field_validator("runs_dir")
    @classmethod
    def _expand_runs_dir(cls, v: Path) -> Path:
        return Path(v).expanduser()

    @property
    def runs_path(self) -> Path:
        return self.runs_dir.resolve()

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton. Call ``get_settings.cache_clear()`` in tests."""
    return Settings()


class EnvCheck:
    """A single environment validation result (used by ``modelforge doctor``)."""

    def __init__(self, name: str, ok: bool, detail: str, required: bool) -> None:
        self.name = name
        self.ok = ok
        self.detail = detail
        self.required = required

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "required": self.required,
            "status": "OK" if self.ok else ("FAIL" if self.required else "WARN"),
        }


def validate_environment(settings: Settings | None = None) -> list[EnvCheck]:
    """Run lightweight, side-effect-free environment checks.

    Heavier checks (Docker daemon, LaTeX, DB connectivity) live in the doctor
    command; this function only validates configuration coherence so it is safe
    to call during startup.
    """
    s = settings or get_settings()
    checks: list[EnvCheck] = []

    checks.append(
        EnvCheck(
            "runs_dir_writable",
            _is_writable(s.runs_path),
            f"runs directory: {s.runs_path}",
            required=True,
        )
    )

    if s.llm is LLMBackend.OPENAI:
        checks.append(
            EnvCheck(
                "openai_api_key",
                bool(s.openai_api_key),
                "OPENAI_API_KEY present" if s.openai_api_key else "OPENAI_API_KEY missing",
                required=True,
            )
        )
    elif s.llm is LLMBackend.ANTHROPIC:
        checks.append(
            EnvCheck(
                "anthropic_api_key",
                bool(s.anthropic_api_key),
                "ANTHROPIC_API_KEY present"
                if s.anthropic_api_key
                else "ANTHROPIC_API_KEY missing",
                required=True,
            )
        )
    else:
        checks.append(
            EnvCheck("llm_backend", True, "mock provider (no key required)", required=False)
        )

    return checks


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
