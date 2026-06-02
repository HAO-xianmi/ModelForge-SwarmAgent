"""Ingestion: validate, store, hash, extract text/tables, build a manifest.

Security posture (spec 30.2): filenames are sanitized, extensions allowlisted,
sizes capped, and ZIP archives are validated against path traversal and
zip-bombs before extraction. Document *content* is treated as untrusted data;
the parser (Phase E) separates it from instructions (spec 30.3).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from modelforge.common.config import get_settings
from modelforge.common.errors import InputError
from modelforge.common.hashing import hash_bytes
from modelforge.common.ids import new_id, slugify
from modelforge.schemas.enums import ArtifactType
from modelforge.schemas.problem import FileManifest, InputManifest
from modelforge.storage.repositories.artifact_registry import ArtifactRegistry

# Allowed upload extensions (spec 9.1 MVP formats).
ALLOWED_EXTENSIONS: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".zip": "application/zip",
    ".json": "application/json",
}

# Inferred file role from name/extension (drives parsing + baselines).
_ROLE_HINTS = {
    "problem": "problem",
    "rules": "rules",
    "notes": "notes",
    "constraints": "constraints",
}

_MAX_ZIP_MEMBERS = 200
_MAX_ZIP_UNCOMPRESSED = 200 * 1024 * 1024  # 200 MiB total expanded


@dataclass
class UploadedFile:
    """An in-memory uploaded file before ingestion."""

    filename: str
    data: bytes


class IngestionService:
    def __init__(self, registry: ArtifactRegistry) -> None:
        self.registry = registry

    def ingest(self, run_id: str, uploads: list[UploadedFile]) -> InputManifest:
        manifest = InputManifest(run_id=run_id)
        problem_text_parts: list[str] = []
        max_total = get_settings().max_upload_bytes
        total = 0

        for up in uploads:
            total += len(up.data)
            if total > max_total:
                raise InputError(
                    "upload bundle exceeds size limit",
                    context={"limit_bytes": max_total},
                )
            expanded = self._maybe_unzip(up)
            for filename, data in expanded:
                manifest.files.append(
                    self._ingest_one(run_id, filename, data, problem_text_parts)
                )

        manifest.total_size_bytes = total
        manifest.problem_text = "\n\n".join(problem_text_parts).strip()
        return manifest

    # ------------------------------------------------------------------ #
    def _ingest_one(
        self, run_id: str, filename: str, data: bytes, problem_text_parts: list[str]
    ) -> FileManifest:
        safe = _sanitize_filename(filename)
        ext = Path(safe).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise InputError(
                f"unsupported file type: {ext}", context={"filename": safe}
            )
        if len(data) > get_settings().max_upload_bytes:
            raise InputError("file exceeds size limit", context={"filename": safe})

        role = _infer_role(safe, ext)
        artifact = self.registry.register_bytes(
            run_id, ArtifactType.INPUT_FILE, safe, data, metadata={"role": role}
        )

        text_available = False
        tables_available = False
        text = ""
        if ext in (".txt", ".md", ".json"):
            text = data.decode("utf-8", errors="replace")
            text_available = True
        elif ext == ".pdf":
            text = _extract_pdf_text(data)
            text_available = bool(text)
        elif ext == ".csv":
            tables_available = True
            text = _csv_preview(data)
            text_available = True
        elif ext == ".xlsx":
            tables_available = True

        if text and role in ("problem", "rules", "notes"):
            problem_text_parts.append(f"[{role}:{safe}]\n{text}")
        if text_available and text:
            self.registry.register_text(
                run_id, ArtifactType.PARSED_TEXT, f"{safe}.txt", text
            )

        return FileManifest(
            file_id=new_id("file"),
            original_name=filename,
            normalized_name=safe,
            content_hash=hash_bytes(data),
            mime_type=ALLOWED_EXTENSIONS[ext],
            size_bytes=len(data),
            extracted_text_available=text_available,
            extracted_tables_available=tables_available,
            ingestion_status="INGESTED",
            source_reference=safe,
            artifact_id=artifact.artifact_id,
            role=role,
        )

    def _maybe_unzip(self, up: UploadedFile) -> list[tuple[str, bytes]]:
        if Path(up.filename).suffix.lower() != ".zip":
            return [(up.filename, up.data)]
        return _safe_unzip(up.data)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _sanitize_filename(name: str) -> str:
    """Drop directory components and dangerous characters (spec 30.2)."""
    base = Path(name).name
    cleaned = "".join(c for c in base if c.isalnum() or c in "._- ").strip()
    cleaned = cleaned.replace(" ", "_")
    if not cleaned or cleaned in (".", ".."):
        cleaned = f"file_{slugify(name)}"
    return cleaned[:200]


def _infer_role(filename: str, ext: str) -> str:
    low = filename.lower()
    for hint, role in _ROLE_HINTS.items():
        if hint in low:
            return role
    if ext in (".csv", ".xlsx"):
        return "data"
    if ext in (".txt", ".md") and "problem" not in low:
        # A lone text/markdown file is most likely the problem statement.
        return "problem"
    return "data"


def _safe_unzip(data: bytes) -> list[tuple[str, bytes]]:
    """Validate and extract a ZIP against traversal and bomb risks (spec 30.2)."""
    out: list[tuple[str, bytes]] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InputError("invalid zip archive", context={"error": str(exc)}) from exc

    members = [m for m in zf.infolist() if not m.is_dir()]
    if len(members) > _MAX_ZIP_MEMBERS:
        raise InputError("zip has too many members", context={"count": len(members)})

    total_uncompressed = sum(m.file_size for m in members)
    if total_uncompressed > _MAX_ZIP_UNCOMPRESSED:
        raise InputError("zip expands too large (possible zip bomb)")

    for member in members:
        name = member.filename
        # Reject absolute paths and traversal.
        if name.startswith(("/", "\\")) or ".." in Path(name).parts:
            raise InputError("zip member path traversal", context={"member": name})
        ext = Path(name).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS or ext == ".zip":  # no nested zips
            continue
        out.append((Path(name).name, zf.read(member)))
    if not out:
        raise InputError("zip contained no supported files")
    return out


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages).strip()
    except Exception:
        return ""


def _csv_preview(data: bytes, max_rows: int = 20) -> str:
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    lines = []
    for i, row in enumerate(reader):
        if i >= max_rows:
            lines.append("...")
            break
        lines.append(", ".join(row))
    return "\n".join(lines)
