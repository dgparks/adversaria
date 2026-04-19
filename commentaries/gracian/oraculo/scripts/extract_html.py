#!/usr/bin/env python3
"""Convert the Cervantes Virtual HTML edition of the Oráculo to Markdown.

Input  : sources/spanish-blanco-catedra.html
Output : artifacts/spanish.md

The HTML is very clean — only ``<h1>``, ``<h2>``, ``<p>``, ``<em>``,
``<strong>`` and layout ``<div>``s carry meaning. Every aphorism is two
adjacent paragraphs:

    <p class="justificado "><strong>N</strong></p>
    <p class="justificado texto-indentado"><em>Title</em>. body...</p>

We preserve that structure verbatim by emitting ``## N`` for the bare
numeral and rendering the body paragraph with the italic title kept inline
as ``*Title*``. Layout-only classes (``centrado``, ``derecha``,
``texto-indentado``) are dropped; ``<em>`` becomes ``*…*`` and
``<strong>`` becomes ``**…**``.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

SRC = Path("sources/spanish-blanco-catedra.html")
OUT = Path("artifacts/spanish.md")

# Inline tags we render specially. Everything else is treated as transparent
# (children rendered, tag itself dropped).
_EMPH_OPEN = {"em": "*", "i": "*", "strong": "**", "b": "**"}


def render_inline(node: Tag | NavigableString) -> str:
    """Render an HTML node's text content, preserving italics and bolds.

    Whitespace is normalized: any run of whitespace inside an element becomes
    a single space, but leading/trailing whitespace at element boundaries is
    preserved so adjacent inline tags stay correctly spaced.
    """
    if isinstance(node, NavigableString):
        return re.sub(r"\s+", " ", str(node))
    pieces = [render_inline(c) for c in node.children]
    inner = "".join(pieces)
    # Avoid emphasizing whitespace-only content; that produces invalid Markdown
    # like ``** **`` that swallows the marker.
    if node.name in _EMPH_OPEN and inner.strip():
        delim = _EMPH_OPEN[node.name]
        # Split off leading/trailing whitespace so the markers hug real chars.
        m = re.match(r"^(\s*)(.*?)(\s*)$", inner, re.DOTALL)
        if m:
            lead, core, trail = m.group(1), m.group(2), m.group(3)
            return f"{lead}{delim}{core}{delim}{trail}"
    return inner


def is_aphorism_number_paragraph(p: Tag) -> str | None:
    """Return the bare number if ``p`` is a ``<p><strong>N</strong></p>`` block."""
    text = p.get_text(strip=True)
    if not text.isdigit():
        return None
    # Must contain exactly one <strong> with that text and nothing else.
    strongs = p.find_all("strong")
    if len(strongs) == 1 and strongs[0].get_text(strip=True) == text:
        return text
    return None


def normalize_paragraph(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", " ", text)
    return text.strip()


def walk(container: Tag) -> list[str]:
    out: list[str] = []
    aphorism_count = 0
    for child in container.children:
        if isinstance(child, NavigableString):
            if child.strip():
                out.append(normalize_paragraph(str(child)))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        if name in {"div", "section", "main"}:
            out.extend(walk(child))
            continue
        if name in {"h1", "h2", "h3", "h4"}:
            text = normalize_paragraph(render_inline(child))
            # Heading text is already prominent; if the whole heading was
            # wrapped in <strong>/<em>, drop the redundant emphasis markers.
            text = re.sub(r"^\*{1,3}(.+?)\*{1,3}$", r"\1", text)
            if text:
                hashes = "#" * int(name[1])
                out.append(f"{hashes} {text}")
            continue
        if name == "p":
            num = is_aphorism_number_paragraph(child)
            if num is not None:
                aphorism_count += 1
                out.append(f"## {num}")
                continue
            text = normalize_paragraph(render_inline(child))
            if text:
                out.append(text)
            continue
        # Unknown tag: render its inline content, fall back to recursion.
        out.extend(walk(child))
    return out


def main() -> int:
    if not SRC.exists():
        print(f"missing source: {SRC}", file=sys.stderr)
        return 2
    OUT.parent.mkdir(parents=True, exist_ok=True)

    soup = BeautifulSoup(SRC.read_text(encoding="utf-8"), "html.parser")
    obra = soup.find("div", id="obra") or soup.body
    if obra is None:
        print("could not find <div id='obra'> or <body>", file=sys.stderr)
        return 2

    blocks = walk(obra)
    md = "\n\n".join(b for b in blocks if b.strip()) + "\n"
    md = re.sub(r"\n{3,}", "\n\n", md)
    OUT.write_text(md, encoding="utf-8")

    aphorism_headings = re.findall(r"^##\s+(\d+)\s*$", md, re.MULTILINE)
    print(f"wrote           : {OUT}")
    print(f"blocks          : {len(blocks)}")
    print(f"aphorism #s     : {len(aphorism_headings)} "
          f"(min={min(map(int, aphorism_headings), default=0)}, "
          f"max={max(map(int, aphorism_headings), default=0)})")
    expected = set(range(1, 301))
    seen = set(map(int, aphorism_headings))
    missing = sorted(expected - seen)
    if missing:
        print(f"  missing       : {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
