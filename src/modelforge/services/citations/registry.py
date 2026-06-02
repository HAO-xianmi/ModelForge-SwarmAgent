"""Citation registry (spec 23).

The system MUST NOT invent citations (spec 23.1). This registry only normalizes
and verifies citations that already exist (e.g. references attached to method
library entries, or human-provided). Local verification checks structural
completeness; an optional remote resolver (Crossref) verifies DOIs when network
is available and fails gracefully otherwise.
"""

from __future__ import annotations

import re

from modelforge.common.ids import new_citation_id
from modelforge.common.timeutil import utcnow
from modelforge.schemas.enums import CitationStatus
from modelforge.schemas.evidence import CitationRecord

_DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


class CitationRegistry:
    def __init__(self, remote_resolver: RemoteResolver | None = None) -> None:
        self.remote = remote_resolver

    # ------------------------------------------------------------------ #
    def normalize(self, citation: CitationRecord) -> CitationRecord:
        """Normalize whitespace, lowercase DOI, strip URL fragments."""
        return citation.model_copy(
            update={
                "title": " ".join(citation.title.split()).strip(),
                "authors": [a.strip() for a in citation.authors if a.strip()],
                "doi": citation.doi.strip().lower().removeprefix("https://doi.org/"),
                "url": citation.url.strip(),
            }
        )

    def register_from_reference(self, reference: str) -> CitationRecord:
        """Build a citation record from a free-text reference string.

        Conservative parsing: pulls a trailing 4-digit year if present, treats
        the leading clause as authors and the rest as title. The record starts
        UNRESOLVED — it is never auto-marked verified without a check.
        """
        year = None
        m = re.search(r"\b(19|20)\d{2}\b", reference)
        if m:
            year = int(m.group(0))
        parts = [p.strip() for p in reference.split(",") if p.strip()]
        authors = [parts[0]] if parts else []
        title = reference.strip()
        return CitationRecord(
            citation_id=new_citation_id(),
            title=title,
            authors=authors,
            year=year,
            source_provider="local_reference",
            verification_status=CitationStatus.UNRESOLVED,
        )

    def deduplicate(self, citations: list[CitationRecord]) -> list[CitationRecord]:
        """Drop duplicates by (normalized title, year) or shared DOI."""
        seen_titles: set[tuple[str, int | None]] = set()
        seen_dois: set[str] = set()
        out: list[CitationRecord] = []
        for c in citations:
            key = (c.title.lower(), c.year)
            doi = c.doi.lower()
            if key in seen_titles or (doi and doi in seen_dois):
                continue
            seen_titles.add(key)
            if doi:
                seen_dois.add(doi)
            out.append(c)
        return out

    # ------------------------------------------------------------------ #
    def verify(self, citation: CitationRecord) -> CitationRecord:
        """Verify a citation: structural local check, then optional remote DOI."""
        c = self.normalize(citation)
        notes: list[str] = []

        has_title = bool(c.title)
        has_year = c.year is not None
        has_author = bool(c.authors)
        valid_doi = bool(c.doi) and bool(_DOI_RE.match(c.doi))

        # Remote DOI check (graceful failure).
        if valid_doi and self.remote is not None:
            try:
                resolved = self.remote.resolve_doi(c.doi)
            except RemoteUnavailable as exc:
                notes.append(f"remote DOI check unavailable: {exc}")
                resolved = None
            if resolved is True:
                notes.append("DOI resolved remotely")
                return c.model_copy(
                    update={
                        "verification_status": CitationStatus.VERIFIED,
                        "verification_notes": "; ".join(notes),
                        "retrieved_at": utcnow(),
                        "source_provider": self.remote.provider_name,
                    }
                )
            if resolved is False:
                return c.model_copy(
                    update={
                        "verification_status": CitationStatus.REJECTED,
                        "verification_notes": "DOI did not resolve remotely",
                        "retrieved_at": utcnow(),
                    }
                )

        # Local structural verdict.
        complete = sum([has_title, has_year, has_author])
        if has_title and complete >= 3:
            status = CitationStatus.VERIFIED if valid_doi else CitationStatus.PARTIALLY_VERIFIED
            notes.append("verified locally (structural)")
        elif has_title and complete == 2:
            status = CitationStatus.PARTIALLY_VERIFIED
            notes.append("partial metadata")
        elif has_title:
            status = CitationStatus.NEEDS_HUMAN_REVIEW
            notes.append("incomplete metadata")
        else:
            status = CitationStatus.UNRESOLVED
            notes.append("missing title")

        return c.model_copy(
            update={
                "verification_status": status,
                "verification_notes": "; ".join(notes),
                "retrieved_at": utcnow(),
            }
        )

    def verify_all(self, citations: list[CitationRecord]) -> list[CitationRecord]:
        return [self.verify(c) for c in self.deduplicate(citations)]


# --------------------------------------------------------------------------- #
# Remote resolver interface (implemented but network-dependent)
# --------------------------------------------------------------------------- #
class RemoteUnavailable(Exception):
    """Raised when a remote citation service cannot be reached."""


class RemoteResolver:
    """Interface for a remote DOI/metadata resolver."""

    provider_name = "remote"

    def resolve_doi(self, doi: str) -> bool | None:  # pragma: no cover - network
        """Return True if resolved, False if confirmed-missing, None if unknown.

        Raises ``RemoteUnavailable`` if the service is unreachable.
        """
        raise NotImplementedError


class CrossrefResolver(RemoteResolver):
    """Crossref DOI resolver. Requires network access (spec: graceful fallback).

    Not exercised in offline CI; the registry catches ``RemoteUnavailable`` and
    falls back to local structural verification.
    """

    provider_name = "crossref"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    def resolve_doi(self, doi: str) -> bool | None:  # pragma: no cover - network
        import httpx

        url = f"https://api.crossref.org/works/{doi}"
        try:
            resp = httpx.get(url, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise RemoteUnavailable(str(exc)) from exc
        if resp.status_code == 200:
            return True
        if resp.status_code == 404:
            return False
        return None
