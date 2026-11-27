#!/usr/bin/env python3
"""Build ARCHITECTURE_NOTE.pdf from ARCHITECTURE_NOTE.md (Mermaid → PNG → HTML → PDF)."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ARCHITECTURE_NOTE.md"
OUT_PDF = ROOT / "ARCHITECTURE_NOTE.pdf"
BUILD = ROOT / "build" / "architecture-pdf"
DIAGRAMS = BUILD / "diagrams"
CHROME = Path(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)


def _run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True, **kwargs)


def extract_mermaid_blocks(text: str) -> list[str]:
    pattern = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
    return [m.group(1).strip() for m in pattern.finditer(text)]


def markdown_with_images(text: str, names: list[str]) -> str:
    idx = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal idx
        name = names[idx]
        idx += 1
        return f"![Diagram {idx}](diagrams/{name})"

    return re.sub(r"```mermaid\n.*?```", repl, text, flags=re.DOTALL)


def sanitize_mermaid_for_render(source: str) -> str:
    """Kroki's Mermaid build is strict: no <br/>, reserved id `graph`, or / in edge labels."""
    text = source.replace("<br/>", " — ").replace("<br>", " — ")
    text = re.sub(r"^(\s*)graph(\[)", r"\1langgraph\2", text, flags=re.MULTILINE)
    text = text.replace(" --> graph", " --> langgraph")
    text = text.replace("graph -->", "langgraph -->")
    text = re.sub(
        r"\|([^|]+)\|",
        lambda m: "|" + m.group(1).replace("/", " ") + "|",
        text,
    )
    return text


def render_mermaid_png(source: str, dest: Path) -> None:
    payload = sanitize_mermaid_for_render(source)
    req = urllib.request.Request(
        "https://kroki.io/mermaid/png",
        data=payload.encode("utf-8"),
        headers={
            "Content-Type": "text/plain",
            "User-Agent": "Project-Sankalp-architecture-pdf/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        dest.write_bytes(resp.read())


def write_html(md_path: Path, html_path: Path) -> None:
    css = BUILD / "print.css"
    css.write_text(
        """
@page { size: A4; margin: 14mm 16mm; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.4;
  color: #111;
  max-width: 100%;
}
h1 { font-size: 17pt; margin: 0 0 6pt; }
h2 { font-size: 12pt; margin: 14pt 0 6pt; page-break-after: avoid; }
p, li { margin: 0 0 6pt; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 8pt 0; }
th, td { border: 1px solid #ccc; padding: 4pt 6pt; text-align: left; vertical-align: top; }
th { background: #f4f4f4; }
img { display: block; max-width: 100%; height: auto; margin: 8pt auto; page-break-inside: avoid; }
hr { border: none; border-top: 1px solid #ddd; margin: 12pt 0; }
code { font-size: 9pt; }
em.footer { font-size: 9pt; color: #444; }
""",
        encoding="utf-8",
    )
    _run(
        [
            "pandoc",
            str(md_path),
            "-o",
            str(html_path),
            "--standalone",
            "--metadata",
            "title=Technical architecture note — Project Sankalp pilot",
            "--css",
            str(css),
        ],
        cwd=str(BUILD),
    )


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    if not CHROME.is_file():
        raise SystemExit(
            "Google Chrome not found; install Chrome or print the HTML file manually."
        )
    url = html_path.resolve().as_uri()
    _run(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path.resolve()}",
            url,
        ]
    )


def main() -> int:
    if not SOURCE.is_file():
        print(f"Missing {SOURCE}", file=sys.stderr)
        return 1
    if shutil.which("pandoc") is None:
        print("pandoc is required (brew install pandoc).", file=sys.stderr)
        return 1

    text = SOURCE.read_text(encoding="utf-8")
    blocks = extract_mermaid_blocks(text)
    if not blocks:
        print("No mermaid blocks found.", file=sys.stderr)
        return 1

    if BUILD.exists():
        shutil.rmtree(BUILD)
    DIAGRAMS.mkdir(parents=True)

    png_names: list[str] = []
    for i, block in enumerate(blocks, start=1):
        mmd = DIAGRAMS / f"diagram-{i}.mmd"
        png = DIAGRAMS / f"diagram-{i}.png"
        mmd.write_text(block + "\n", encoding="utf-8")
        try:
            render_mermaid_png(block, png)
        except (urllib.error.URLError, urllib.error.HTTPError) as err:
            raise SystemExit(f"Kroki render failed for {mmd.name}: {err}") from err
        png_names.append(png.name)

    md_out = BUILD / "ARCHITECTURE_NOTE.rendered.md"
    md_out.write_text(markdown_with_images(text, png_names), encoding="utf-8")
    html_out = BUILD / "ARCHITECTURE_NOTE.html"
    write_html(md_out, html_out)
    html_to_pdf(html_out, OUT_PDF)
    print(f"Wrote {OUT_PDF}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())