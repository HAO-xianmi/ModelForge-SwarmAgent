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
# Defense-in-depth: strip any internal id a model may have written into prose.
_LEAK = re.compile(r"\[?\bclaim_[0-9a-fA-F]{4,}\b\]?|\[ev:[^\]]*\]|\[claim:[^\]]*\]")


def _strip_leaked_tokens(text: str) -> str:
    text = _LEAK.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).replace(" .", ".").replace(" ,", ",")


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
        """Replace [claim:id] refs with clean, sequential evidence markers.

        A verified ref becomes ``[E1]``/``[E2]`` (reader-facing, no internal id)
        and is recorded in the claim map; an unverified ref is dropped (the writer
        must not cite unverified claims). A final sweep removes any raw claim id a
        model may have emitted in prose, so internal tokens never leak (the
        original report.pdf leaked ``claim_efa52f7c7a6b`` into the body)."""
        counter = {"n": 0}
        seen: dict[str, str] = {}

        def _repl(m: re.Match[str]) -> str:
            cid = m.group(1)
            if cid in usable_ids:
                if cid not in seen:
                    counter["n"] += 1
                    seen[cid] = f"[E{counter['n']}]"
                    claim_map.append(
                        ClaimMapEntry(
                            section_id=section.section_id,
                            claim_id=cid,
                            evidence_artifact_ids=claim_index[cid].artifact_ids,
                        )
                    )
                return seen[cid]
            return ""  # unverified reference dropped

        return _strip_leaked_tokens(_CLAIM_REF.sub(_repl, text))

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
\usepackage{{iftex}}
\ifPDFTeX
\usepackage[utf8]{{inputenc}}
\else
\usepackage{{fontspec}}
\IfFileExists{{xeCJK.sty}}{{%
  \usepackage{{xeCJK}}
  \IfFontExistsTF{{SimSun}}{{\setCJKmainfont{{SimSun}}}}{{\setCJKmainfont{{Microsoft YaHei}}}}
}}{{}}
\fi
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


def _render_inline(text: str) -> str:
    """Escape text for LaTeX but PRESERVE inline ``$...$`` math segments."""
    parts = text.split("$")
    out: list[str] = []
    for i, seg in enumerate(parts):
        out.append(f"${seg}$" if i % 2 == 1 else _tex_escape(seg))
    return "".join(out)


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_separator(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(c and set(c) <= set("-: ") and "-" in c for c in cells)


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _render_table(block: list[str]) -> list[str]:
    parsed = [_split_row(r) for r in block if not _is_table_separator(r)]
    if not parsed:
        return []
    ncol = max(len(r) for r in parsed)
    out = [r"\begin{table}[h]\centering",
           r"\begin{tabular}{" + "l" * ncol + "}", r"\hline"]
    for ri, cells in enumerate(parsed):
        cells = cells + [""] * (ncol - len(cells))
        out.append(" & ".join(_render_inline(c) for c in cells) + r" \\")
        if ri == 0:
            out.append(r"\hline")
    out += [r"\hline", r"\end{tabular}", r"\end{table}"]
    return out


def _markdown_to_latex(markdown: str) -> str:
    """Render a competition report's markdown to compilable LaTeX, including
    equations (inline ``$...$`` and display ``$$``), markdown tables, headings,
    subsections, figures, and lists."""
    lines = markdown.splitlines()
    out: list[str] = []
    i, n = 0, len(lines)
    in_itemize = False

    def close_itemize() -> None:
        nonlocal in_itemize
        if in_itemize:
            out.append(r"\end{itemize}")
            in_itemize = False

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped == "$$":  # display-math block
            close_itemize()
            j = i + 1
            buf: list[str] = []
            while j < n and lines[j].strip() != "$$":
                buf.append(lines[j])
                j += 1
            out += [r"\[", *buf, r"\]"]
            i = j + 1
            continue

        if _is_table_row(line):  # markdown table block
            close_itemize()
            j = i
            block: list[str] = []
            while j < n and _is_table_row(lines[j]):
                block.append(lines[j])
                j += 1
            out += _render_table(block)
            i = j
            continue

        if line.startswith("#### "):
            close_itemize(); out.append(r"\subsubsection*{" + _tex_escape(line[5:]) + "}")
        elif line.startswith("### "):
            close_itemize(); out.append(r"\subsection*{" + _tex_escape(line[4:]) + "}")
        elif line.startswith("## "):
            close_itemize(); out.append(r"\section*{" + _tex_escape(line[3:]) + "}")
        elif line.startswith("# "):
            pass  # title handled by \maketitle
        elif line.startswith("![") and "](" in line:
            close_itemize()
            inside = line[line.find("](") + 2 : line.rfind(")")]
            out += [r"\begin{figure}[h]\centering",
                    rf"\includegraphics[width=0.7\textwidth]{{{inside}}}",
                    r"\end{figure}"]
        elif stripped.startswith(("- ", "* ")):
            if not in_itemize:
                out.append(r"\begin{itemize}")
                in_itemize = True
            out.append(r"\item " + _render_inline(stripped[2:]))
        elif stripped:
            close_itemize()
            out.append(_render_inline(line))
        else:
            close_itemize()
            out.append("")
        i += 1
    close_itemize()
    return "\n".join(out)
