"""Content hashing utilities for the Artifact Registry and reproducibility.

Hashes are SHA-256 hex digests. ``hash_bytes`` and ``hash_file`` give
content-addressed identity for artifacts; ``hash_json`` provides a canonical,
order-independent hash of structured data for manifests.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_CHUNK = 1 << 20  # 1 MiB


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: str | Path) -> str:
    """Stream a file through SHA-256 so large datasets do not load into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def hash_json(obj: Any) -> str:
    """Canonical hash of JSON-serializable data (sorted keys, compact separators)."""
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hash_text(canonical)


def short_hash(full_hash: str, length: int = 12) -> str:
    return full_hash[:length]
