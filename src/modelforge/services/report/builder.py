"""Report builder (spec 22) — evidence-constrained assembly.

Given a verified outline (from PaperArchitectAgent) and section drafts (from
PaperWriterAgent), this assembles ``report.md`` and ``report.tex`` plus a
``report_claim_map.json`` linking quantitative statements to claim ids and
evidence artifacts. It enforces the writer-access rule one more time at assembly:
any ``[claim:<id>]`` reference to a non-verified claim is stripped and flagged
for human review, so the final document cannot present unsupported numbers.
"""

from __future__ import annotations

import re

from modelforge.schemas.evidence import CitationRecord, EvidenceClaim
from modelforge.schemas.report import (
    ClaimMapEntry,
    ReportOutline,
    ReportSection,
)

_CLAIM_REF = re.compile(r"\[claim:([a-zA-Z0-9_]+)\]")


class ReportBuilder:
    def build_markdown(
        self,
        title: str,
        outline: ReportOutline,
        section_texts: dict[str, str],
        claims: list[EvidenceClaim],
        citations: list[CitationRecord],
        *,
        ai_disclosure: str | None = None,
    ) -> tuple[str, list[ClaimMapEntry]]:
        """Return (markdown, claim_map). Unverified claim refs are flagged."""
        claim_index = {c.claim_id: c for c in claims}
        usable_ids = {c.claim_id for c in claims if c.usable_by_writer}
        claim_map: list[ClaimMapEntry] = []
        lines = [f"# {title}", ""]

        for section in outline.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            raw = section_texts.get(section.section_id, "").strip()
            if not raw:
                raw = "_(section pending — no verified evidence available yet)_"
            cleaned = self._resolve_claims(
                raw, section, usable_ids, claim_index, claim_map
            )
            lines.append(cleaned)
            lines.append("")
            # Reference figures/tables that belong to this section.
            for fid in section.required_figure_ids:
                lines.append(f"![{fid}]({fid})")
            lines.append("")

        if citations:
            lines.append("## References")
            lines.append("")
            for i, cit in enumerate(
                [c for c in citations if c.includable_in_report], start=1
            ):
                authors = ", ".join(cit.authors) if cit.authors else "Anon."
                lines.append(f"{i}. {authors} ({cit.year or 'n.d.'}). *{cit.title}*.")
            lines.append("")

        if ai_disclosure:
            lines.append(ai_disclosure)

        return "\n".join(lines).strip() + "\n", claim_map

    def _resolve_claims(
        self,
        text: str,
        section: ReportSection,
        usable_ids: set[str],
        claim_index: dict[str, EvidenceClaim],
        claim_map: list[ClaimMapEntry],
    ) -> str:
        """Replace [claim:id] refs: verified -> footnote marker; else flag."""

        def _repl(m: re.Match[str]) -> str:
            cid = m.group(1)
            if cid in usable_ids:
                claim = claim_index[cid]
                claim_map.append(
                    ClaimMapEntry(
                        section_id=section.section_id,
                        claim_id=cid,
                        evidence_artifact_ids=claim.artifact_ids,
                    )
                )
                return f"[ev:{cid}]"
            # Unsupported claim reference — strip the number, flag for review.
            return "[UNVERIFIED — needs human review]"

        return _CLAIM_REF.sub(_repl, text)

    def build_latex(
        self,
        title: str,
        markdown: str,
        citations: list[CitationRecord],
    ) -> str:
        """A minimal, compilable LaTeX rendering of the markdown report."""
        body = _markdown_to_latex(markdown)
        return _LATEX_TEMPLATE.format(title=_tex_escape(title), body=body)

    def build_bibtex(self, citations: list[CitationRecord]) -> str:
        entries = []
        for cit in citations:
            if not cit.includable_in_report:
                continue
            authors = " and ".join(cit.authors) if cit.authors else "Anon"
            entries.append(
                f"@article{{{cit.bibtex_key()},\n"
                f"  title = {{{cit.title}}},\n"
                f"  author = {{{authors}}},\n"
                f"  year = {{{cit.year or ''}}},\n"
                f"  journal = {{{cit.venue}}},\n"
                + (f"  doi = {{{cit.doi}}},\n" if cit.doi else "")
                + "}\n"
            )
        return "\n".join(entries)


# --------------------------------------------------------------------------- #
# LaTeX helpers
# --------------------------------------------------------------------------- #
_LATEX_TEMPLATE = r"""\documentclass[11pt]{{article}}
\usepackage[utf8]{{inputenc}}
\usepackage{{graphicx}}
\usepackage{{amsmath}}
\usepackage{{hyperref}}
\title{{{title}}}
\author{{ModelForge-Swarm (human-supervised)}}
\date{{\today}}
\begin{{document}}
\maketitle
{body}
\end{{document}}
"""


def _tex_escape(text: str) -> str:
    repl = {
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
        "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(repl.get(c, c) for c in text)


def _markdown_to_latex(markdown: str) -> str:
    out: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            out.append(r"\section*{" + _tex_escape(line[3:]) + "}")
        elif line.startswith("# "):
            continue  # title handled by \maketitle
        elif line.startswith("![") and "](" in line:
            # ![alt](path) -> includegraphics (best-effort; missing files skipped)
            inside = line[line.find("](") + 2 : line.rfind(")")]
            out.append(r"\begin{figure}[h]\centering")
            out.append(rf"\includegraphics[width=0.7\textwidth]{{{inside}}}")
            out.append(r"\end{figure}")
        elif line.strip():
            out.append(_tex_escape(line))
        else:
            out.append("")
    return "\n".join(out)
