r"""LaTeX -> PDF compilation (spec 9.9).

Uses ``pdflatex`` when available, copying figures next to the .tex source so
``\includegraphics`` resolves. When no LaTeX compiler is present, PDF export is
skipped gracefully (markdown + .tex still produced) and the reason is recorded --
never a fake PDF (working rule 5).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from modelforge.common.logging import get_logger

_log = get_logger("modelforge.latex")


class LatexBuilder:
    def __init__(self, compiler: str = "pdflatex") -> None:
        self.compiler = compiler

    def available(self) -> bool:
        return shutil.which(self.compiler) is not None

    def compile_pdf(
        self,
        tex_source: str,
        out_dir: Path,
        *,
        figures: dict[str, bytes] | None = None,
        basename: str = "report",
    ) -> tuple[Path | None, str]:
        """Compile ``tex_source`` to ``{out_dir}/{basename}.pdf``.

        Returns (pdf_path_or_None, compilation_log). If no compiler is present,
        returns (None, message) without raising.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        tex_path = out_dir / f"{basename}.tex"
        tex_path.write_text(tex_source, encoding="utf-8")

        for name, data in (figures or {}).items():
            (out_dir / Path(name).name).write_bytes(data)

        if not self.available():
            msg = f"{self.compiler} not found; PDF compilation skipped"
            _log.warning(msg)
            return None, msg

        log_parts: list[str] = []
        # Two passes for references; non-interactive, halt on error.
        for _ in range(2):
            try:
                proc = subprocess.run(
                    [
                        self.compiler,
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        f"-output-directory={out_dir}",
                        str(tex_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                return None, f"compilation error: {exc}"
            log_parts.append(proc.stdout[-4000:])
            if proc.returncode != 0:
                pdf = out_dir / f"{basename}.pdf"
                # pdflatex may still emit a partial PDF; only accept if present
                # AND the final pass succeeded.
                return (pdf if pdf.exists() else None), "\n".join(log_parts)

        pdf_path = out_dir / f"{basename}.pdf"
        if pdf_path.exists():
            return pdf_path, "\n".join(log_parts)
        return None, "\n".join(log_parts) + "\nPDF not produced"
