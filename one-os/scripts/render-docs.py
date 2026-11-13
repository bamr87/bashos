#!/usr/bin/env python3
"""render-docs.py OUTDIR — the repository's Markdown as a small offline website.

Every *.md (README, PLAN, CLAUDE, docs/…) becomes .html at the same relative path,
links between pages are rewritten from .md to .html, links to folders go to their
README or a generated index, and docs/images/ is copied. OUTDIR/index.html opens the
documentation home. Needs python3-markdown (in the builder image).
Mermaid diagrams are shown as their source here; they render on GitHub.
"""
from __future__ import annotations

import html
import re
import shutil
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
SKIP = {"build", "cache", ".git", "node_modules", ".pytest_cache", ".ruff_cache", "local-isos"}

CSS = """
:root { --bg:#fbfbfa; --fg:#1d1d1b; --muted:#6b6b66; --line:#e3e2dd; --code:#f1f0ec; --link:#2f5bd3; }
@media (prefers-color-scheme: dark) { :root { --bg:#171716; --fg:#ecebe6; --muted:#a09f98; --line:#33332f;
  --code:#242422; --link:#8fb0ff; } }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system, "Segoe UI", sans-serif; }
nav { border-bottom:1px solid var(--line); padding:10px 16px; font-size:14px; }
nav a { margin-right:14px; }
main { max-width:900px; margin:0 auto; padding:16px 16px 64px; }
a { color:var(--link); } img { max-width:100%; border:1px solid var(--line); border-radius:6px; }
pre { background:var(--code); padding:12px; border-radius:6px; overflow:auto; }
code { background:var(--code); padding:1px 4px; border-radius:4px; font-size:90%; }
pre code { padding:0; background:none; }
table { border-collapse:collapse; display:block; overflow:auto; } th, td { border:1px solid var(--line); padding:4px 8px; }
.note { color:var(--muted); font-size:13px; }
"""


def md_files() -> list[Path]:
    def wanted(p: Path) -> bool:
        parts = p.relative_to(ROOT).parts
        # .claude/worktrees/ holds other sessions' checkouts, not this project's docs
        return not (SKIP & set(parts)) and parts[:2] != (".claude", "worktrees")
    return sorted(p for p in ROOT.rglob("*.md") if wanted(p))


def rewrite_links(body: str, src: Path, out_root: Path, dir_pages: set[Path]) -> str:
    def fix(m: re.Match) -> str:
        attr, url = m.group(1), m.group(2)
        if re.match(r"^(https?:|mailto:|#)", url):
            return m.group(0)
        path, _, anchor = url.partition("#")
        target = (src.parent / path).resolve()
        if path.endswith(".md"):
            path = path[:-3] + ".html"
        elif target.is_dir():
            readme = target / "README.md"
            if readme.exists():
                path = path.rstrip("/") + "/README.html"
            else:
                dir_pages.add(target)
                path = path.rstrip("/") + "/index.html"
        return f'{attr}="{path}{"#" + anchor if anchor else ""}"'
    return re.sub(r'(href|src)="([^"]+)"', fix, body)


def page(title: str, body: str, depth: int) -> str:
    up = "../" * depth
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)} — one-os</title><style>{CSS}</style></head><body>"
            f"<nav><a href='{up}docs/README.html'>Documentation</a><a href='{up}README.html'>README</a>"
            f"<a href='{up}docs/user-guide/quick-reference.html'>Quick reference</a>"
            f"<a href='{up}docs/troubleshooting.html'>Troubleshooting</a></nav><main>{body}</main></body></html>")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(sys.argv[1])
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    dir_pages: set[Path] = set()
    for src in md_files():
        rel = src.relative_to(ROOT)
        text = src.read_text(encoding="utf-8")
        body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
        body = re.sub(r'<pre><code class="language-mermaid">',
                      '<p class="note">Diagram (Mermaid source; rendered on GitHub):</p><pre><code>', body)
        body = rewrite_links(body, src, out, dir_pages)
        m = re.search(r"^#\s+(.+)$", text, re.M)
        dest = out / rel.with_suffix(".html")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page(m.group(1) if m else rel.stem, body, len(rel.parts) - 1), encoding="utf-8")
    for d in sorted(dir_pages):
        rel = d.relative_to(ROOT)
        items = "".join(f"<li><a href='{p.stem}.html'>{html.escape(p.stem)}</a></li>" for p in sorted(d.glob("*.md")))
        dest = out / rel / "index.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(page(str(rel), f"<h1>{html.escape(str(rel))}</h1><ul>{items}</ul>", len(rel.parts)))
    shutil.copytree(ROOT / "docs" / "images", out / "docs" / "images")
    (out / "index.html").write_text("<!doctype html><meta http-equiv=refresh content='0; url=docs/README.html'>"
                                    "<a href='docs/README.html'>one-os documentation</a>\n")
    print(f"render-docs: {len(md_files())} pages → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
