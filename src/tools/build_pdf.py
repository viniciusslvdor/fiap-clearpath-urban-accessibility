"""Builds the submission PDF (in Portuguese) from document/relatorio.md.

    uv run python src/tools/build_pdf.py

What it does:
1. Replaces the code markers with the REAL code from the files (the PDF never gets out
   of sync with the repository, and the code comes out as text, not as a screenshot):
     [[code path name]]      function, class or variable from a .py file
     [[lines path a b]]      lines a..b of any file
     [[text path]]           whole text file
2. Converts the Markdown into HTML (tables, images and Mermaid diagrams).
3. Prints it to PDF with Chrome or Edge in headless mode.
"""
from __future__ import annotations

import ast
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "document"
LANGUAGE = {".py": "python", ".ino": "cpp", ".js": "javascript", ".jsx": "jsx", ".json": "json"}

BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser", "microsoft-edge",
]


def python_snippet(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = []
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            targets = [node.name]
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            ts = node.targets if isinstance(node, ast.Assign) else [node.target]
            targets = [t.id for t in ts if isinstance(t, ast.Name)]
        if name in targets:
            lines = source.splitlines()
            start = (node.decorator_list[0].lineno if getattr(node, "decorator_list", None) else node.lineno) - 1
            return "\n".join(lines[start:node.end_lineno])
    raise ValueError(f"'{name}' not found in {path}")


def block(code: str, language: str, caption: str) -> str:
    return f'<p class="code-caption">{html.escape(caption)}</p>\n\n```{language}\n{code}\n```'


def expand_markers(md: str) -> str:
    def replace(m: re.Match) -> str:
        kind, args = m.group(1), m.group(2).split()
        path = REPO_ROOT / args[0]
        if kind == "code":
            return block(python_snippet(path, args[1]), "python", f"{args[0]} · {args[1]}")
        if kind == "lines":
            a, b = int(args[1]), int(args[2])
            text = "\n".join(path.read_text(encoding="utf-8").splitlines()[a - 1:b])
            return block(text, LANGUAGE.get(path.suffix, "text"), f"{args[0]} · linhas {a} a {b}")
        if kind == "text":
            return block(path.read_text(encoding="utf-8").strip(), "text", args[0])
        raise ValueError(kind)

    return re.sub(r"\[\[(code|lines|text) ([^\]]+)\]\]", replace, md)


CSS = """
@page { size: A4; margin: 20mm 18mm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 11pt; line-height: 1.45; color: #000; }
h1, h2, h3 { line-height: 1.2; }
h2 { font-size: 15pt; margin-top: 22px; }
h3 { font-size: 12pt; margin-top: 14px; }
h2, h3, .code-caption { page-break-after: avoid; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 10pt; page-break-inside: avoid; }
th, td { border: 1px solid #999; padding: 4px 6px; text-align: left; vertical-align: top; }
th { background: #eee; }
pre { border: 1px solid #ccc; padding: 8px 10px; font-size: 8pt; line-height: 1.35;
      white-space: pre-wrap; word-break: break-word; }
code { font-family: Consolas, "Courier New", monospace; font-size: 0.92em; }
.code-caption { font-size: 8.5pt; color: #444; margin: 10px 0 -6px; font-family: Consolas, monospace; }
img { max-width: 100%; max-height: 90mm; display: block; margin: 8px auto 2px; border: 1px solid #ccc; page-break-inside: avoid; }
pre.mermaid { border: none; text-align: center; }
.page-break { page-break-after: always; }
.pending { border: 2px dashed #c00; padding: 10px; color: #c00; font-weight: bold; }
.cover { text-align: center; padding-top: 25mm; }
.cover p { margin: 2px 0; }
.cover .title { font-size: 36pt; margin: 45mm 0 4mm; }
.cover .subtitle { font-size: 13pt; margin-bottom: 30mm; }
.cover table { width: 75%; margin: 0 auto; }
.cover th { width: 30%; }
.cover .date { margin-top: 30mm; }
"""


def build_html(md_text: str) -> str:
    body = markdown.markdown(expand_markers(md_text), extensions=["tables", "fenced_code", "md_in_html"])
    body = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>',
                  lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', body, flags=re.S)
    # Mermaid is only loaded when the document has a diagram
    mermaid = ('<script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>'
               '<script>mermaid.initialize({ startOnLoad: true, theme: "neutral" });</script>') if 'class="mermaid"' in body else ""
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>ClearPath - Relatório Global Solution 2026.2</title><style>{CSS}</style>{mermaid}
</head><body>{body}</body></html>"""


def find_browser() -> str:
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    sys.exit("Chrome/Edge not found. Open relatorio.html in a browser and use Print > Save as PDF.")


def main():
    html_file = DOC_DIR / "other" / "relatorio.html"
    pdf_file = DOC_DIR / "ClearPath_GS2026-2_relatorio.pdf"
    html = build_html((DOC_DIR / "relatorio.md").read_text(encoding="utf-8"))
    # the HTML lives in document/other/, so image paths relative to document/ need one more level
    html_file.write_text(html.replace('src="../assets/', 'src="../../assets/'), encoding="utf-8")
    subprocess.run([
        find_browser(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--virtual-time-budget=20000", "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_file}", html_file.as_uri(),
    ], check=True, capture_output=True)
    print(f"HTML: {html_file}\nPDF:  {pdf_file}")


if __name__ == "__main__":
    main()
