#!/usr/bin/env python3
"""Restyle ``artifacts/english.md`` to match the Spanish edition's layout.

The Spanish edition prints each maxim as a bare numeral heading followed by a
body paragraph that opens with the maxim's italicized title sentence:

    ## 1

    *Todo está ya en su punto, y el ser persona en el mayor*. Más se requiere…

The English Markdown produced by ``extract_pdf.py`` originally folds the title
into the heading (``## 1. All has reached perfection…``). This script
rewrites every aphorism heading from ``## N. <title>`` to bare ``## N`` and
prepends ``*<title>*`` to the body paragraph that follows.

Inputs:  artifacts/english.md
Output:  artifacts/english.md (overwritten by default; pass --output PATH to
         write to a different file).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


HEADING_RE = re.compile(r"^##\s+(\d+)\.\s*(.+?)\s*$")


def restyle(text: str) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    converted = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        m = HEADING_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue

        number, title = m.group(1), m.group(2)

        # Find the next non-blank line — that's the body paragraph for this
        # maxim. Anything blank in between is preserved.
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1

        out.append(f"## {number}")
        out.append("")

        # Re-italicize the title; if the body line exists, prepend it. Otherwise
        # emit the italicized title on its own. Escape any literal ``*``/``_``
        # inside the title (e.g. inline footnote anchors like ``person*``)
        # so they don't terminate the surrounding italics.
        safe_title = title.replace("\\", "\\\\").replace("*", r"\*").replace("_", r"\_")
        title_md = f"*{safe_title}*" if safe_title else ""
        if j < len(lines):
            body = lines[j].lstrip()
            if title_md:
                # If the body starts with punctuation (comma, semicolon, period
                # — i.e. the original italic title in the PDF didn't include
                # the terminator), don't insert a separating space.
                sep = "" if body and body[0] in ",;.:!?)" else " "
                joined = f"{title_md}{sep}{body}".strip()
            else:
                joined = body
            out.append(joined)
            i = j + 1
        else:
            if title_md:
                out.append(title_md)
            i = j
        converted += 1
    return "\n".join(out) + ("\n" if text.endswith("\n") else ""), converted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", default="artifacts/english.md", type=Path)
    ap.add_argument("--output", default=None, type=Path,
                    help="Where to write (default: overwrite --input).")
    args = ap.parse_args(argv)

    src: Path = args.input
    dst: Path = args.output or src
    if not src.exists():
        print(f"missing input: {src}", file=sys.stderr)
        return 2

    text = src.read_text(encoding="utf-8")
    new_text, converted = restyle(text)
    dst.write_text(new_text, encoding="utf-8")
    print(f"converted {converted} aphorism headings -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
