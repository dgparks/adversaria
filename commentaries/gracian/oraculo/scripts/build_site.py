#!/usr/bin/env python3
"""Local-preview HTML renderer for ``maxims/*.md``.

NOTE
----
This is **scaffolding**, not a publishing pipeline. The canonical
deliverables of this project are the Markdown files under ``maxims/``.
When the time comes to ship to a real engine (VitePress, Astro, Ghost,
Hugo, …), those Markdown files are the input — this script's HTML
output is throwaway. Treat ``artifacts/site/`` the way you treat
``artifacts/english_extracted.txt``: a regenerable artifact for sanity
checks and live preview, not a deliverable.

Reads:
  maxims/NNN.md            (frontmatter + ## English / ## Spanish / ## Commentary)
  templates/maxim.html.j2  (per-maxim layout)
  templates/index.html.j2  (list of all 300)
  templates/style.css      (page CSS, copied verbatim)

Writes:
  artifacts/site/index.html
  artifacts/site/NNN.html  (one per maxim found)
  artifacts/site/style.css

Run from the working directory:

    python scripts/build_site.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt

from scaffold_maxims import MAXIMS_DIR, parse_maxim_file

TEMPLATE_DIR = Path("templates")
SITE_DIR = Path("artifacts/site")


def _render_md(parser: MarkdownIt, body: str) -> str:
    return parser.render(body) if body.strip() else ""


def main() -> int:
    if not MAXIMS_DIR.is_dir():
        print(f"missing {MAXIMS_DIR}; run scripts/scaffold_maxims.py first.",
              file=sys.stderr)
        return 2
    if not TEMPLATE_DIR.is_dir():
        print(f"missing {TEMPLATE_DIR}", file=sys.stderr)
        return 2

    md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    md.enable("table")
    md.enable("strikethrough")

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "j2"]),
        keep_trailing_newline=True,
    )
    maxim_tpl = env.get_template("maxim.html.j2")
    index_tpl = env.get_template("index.html.j2")

    SITE_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(MAXIMS_DIR.glob("*.md"))
    parsed: list[tuple[int, dict, dict[str, str]]] = []
    skipped: list[str] = []
    for f in files:
        try:
            mf = parse_maxim_file(f.read_text(encoding="utf-8"))
        except Exception as exc:
            skipped.append(f"{f.name}: parse error: {exc}")
            continue
        n = mf.frontmatter.get("number")
        if not isinstance(n, int):
            skipped.append(f"{f.name}: non-integer 'number' frontmatter")
            continue
        parsed.append((n, mf.frontmatter, mf.sections))
    parsed.sort(key=lambda t: t[0])

    numbers = [n for n, _, _ in parsed]
    written = 0
    for i, (n, fm, sections) in enumerate(parsed):
        prev_n = numbers[i - 1] if i > 0 else None
        next_n = numbers[i + 1] if i + 1 < len(numbers) else None
        html = maxim_tpl.render(
            number=n,
            title_en=fm.get("title_en", ""),
            title_es=fm.get("title_es", ""),
            sources=fm.get("sources", {}) or {},
            status=fm.get("status", ""),
            english_html=_render_md(md, sections.get("English", "")),
            spanish_html=_render_md(md, sections.get("Spanish", "")),
            commentary_html=_render_md(md, sections.get("Commentary", "")),
            prev_number=prev_n,
            next_number=next_n,
        )
        (SITE_DIR / f"{n:03d}.html").write_text(html, encoding="utf-8")
        written += 1

    status_tally: dict[str, int] = {}
    for _, fm, _ in parsed:
        s = str(fm.get("status", "draft"))
        status_tally[s] = status_tally.get(s, 0) + 1
    status_counts = sorted(status_tally.items(), key=lambda kv: kv[0])

    index_html = index_tpl.render(
        maxims=[
            {
                "number": n,
                "title_en": fm.get("title_en", ""),
                "status": fm.get("status", "draft"),
            }
            for n, fm, _ in parsed
        ],
        status_counts=status_counts,
    )
    (SITE_DIR / "index.html").write_text(index_html, encoding="utf-8")

    css_src = TEMPLATE_DIR / "style.css"
    if css_src.exists():
        shutil.copy(css_src, SITE_DIR / "style.css")

    print(f"maxim pages     : {written}")
    print(f"index page      : {SITE_DIR / 'index.html'}")
    if skipped:
        print(f"skipped         : {len(skipped)}")
        for s in skipped[:10]:
            print(f"  {s}")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more")
    print(f"output dir      : {SITE_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
