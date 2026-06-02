"""Environment diagnostics for ``modelforge doctor`` (spec milestone 20).

Checks Python version, Docker, LaTeX, database connectivity, Redis (if
configured), writable storage, the active sandbox backend, and LLM provider
configuration. Returns structured results so the CLI can render them and exit
non-zero on a required failure.
"""

from __future__ import annotations

import shutil
import sys

from modelforge.common.config import LLMBackend, get_settings, validate_environment
from modelforge.services.sandbox.factory import docker_available


def run_checks() -> list[dict]:
    s = get_settings()
    checks: list[dict] = []

    # Python version (>=3.12 required).
    py_ok = sys.version_info >= (3, 12)
    checks.append(
        _check("python_version", py_ok, f"Python {sys.version.split()[0]}", required=True)
    )

    # Config coherence (runs dir writable, provider keys).
    for c in validate_environment(s):
        checks.append(c.to_dict())

    # Sandbox backend.
    has_docker = docker_available()
    backend = "docker" if (s.sandbox.value in ("auto", "docker") and has_docker) else "subprocess"
    checks.append(
        _check(
            "sandbox_backend",
            True,
            f"active backend: {backend}" + ("" if has_docker else " (Docker not available)"),
            required=False,
        )
    )

    # LaTeX compiler.
    latex = shutil.which("pdflatex")
    checks.append(
        _check(
            "latex",
            latex is not None,
            f"pdflatex at {latex}" if latex else "pdflatex not found (PDF export disabled)",
            required=False,
        )
    )

    # Database connectivity.
    db_ok, db_detail = _check_db(s.database_url)
    checks.append(_check("database", db_ok, db_detail, required=True))

    # Redis (only if configured).
    if s.redis_url:
        checks.append(
            _check("redis", _check_redis(s.redis_url), f"redis at {s.redis_url}", required=False)
        )

    # LLM provider.
    if s.llm is LLMBackend.MOCK:
        checks.append(_check("llm_provider", True, "mock (no key required)", required=False))
    else:
        key = s.openai_api_key if s.llm is LLMBackend.OPENAI else s.anthropic_api_key
        checks.append(
            _check("llm_provider", bool(key), f"{s.llm.value} ({'key set' if key else 'NO KEY'})",
                   required=True)
        )

    return checks


def _check(name: str, ok: bool, detail: str, *, required: bool) -> dict:
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "required": required,
        "status": "OK" if ok else ("FAIL" if required else "WARN"),
    }


def _check_db(url: str) -> tuple[bool, str]:
    try:
        from sqlalchemy import text

        from modelforge.storage.database import make_engine

        engine = make_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, f"connected: {url.split('://')[0]}"
    except Exception as exc:
        return False, f"connection failed: {exc}"


def _check_redis(url: str) -> bool:
    try:
        import redis  # type: ignore[import-untyped,import-not-found]

        client = redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        return True
    except Exception:
        return False


def all_required_pass(checks: list[dict]) -> bool:
    return all(c["ok"] for c in checks if c["required"])
