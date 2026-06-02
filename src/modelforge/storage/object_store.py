"""Object storage abstraction with a local-filesystem implementation.

The interface is deliberately narrow so an S3/MinIO backend can be dropped in
later (spec 3.2 / 34.2) without touching callers. URIs are ``file://`` for the
local store.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from modelforge.common.hashing import hash_bytes
from modelforge.storage.run_directory import RunDirectory


class ObjectStore(Protocol):
    """Minimal blob store contract."""

    def put_bytes(self, run_id: str, relative_path: str, data: bytes) -> str:
        """Store bytes; return a storage URI."""
        ...

    def put_text(self, run_id: str, relative_path: str, text: str) -> str: ...

    def get_bytes(self, uri: str) -> bytes: ...

    def exists(self, uri: str) -> bool: ...


class LocalObjectStore:
    """Stores objects inside each run's directory on the local filesystem."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def _run_dir(self, run_id: str) -> RunDirectory:
        return RunDirectory(run_id, root=self._root)

    def put_bytes(self, run_id: str, relative_path: str, data: bytes) -> str:
        rd = self._run_dir(run_id)
        target = rd.resolve_within(*Path(relative_path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target.as_uri()

    def put_text(self, run_id: str, relative_path: str, text: str) -> str:
        return self.put_bytes(run_id, relative_path, text.encode("utf-8"))

    def get_bytes(self, uri: str) -> bytes:
        return Path(_uri_to_path(uri)).read_bytes()

    def get_text(self, uri: str) -> str:
        return self.get_bytes(uri).decode("utf-8")

    def exists(self, uri: str) -> bool:
        return Path(_uri_to_path(uri)).exists()

    @staticmethod
    def content_hash(data: bytes) -> str:
        return hash_bytes(data)


def _uri_to_path(uri: str) -> str:
    if uri.startswith("file:///"):
        # file:///C:/... on Windows -> strip the leading slash before the drive
        from urllib.parse import unquote, urlparse

        parsed = urlparse(uri)
        path = unquote(parsed.path)
        if len(path) >= 3 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return path
    if uri.startswith("file://"):
        return uri[len("file://") :]
    return uri
