#!/usr/bin/env python3
"""Scaffold per-maxim editorial files from the canonical extractions.

Reads:
  artifacts/english.md     canonical English extraction
  artifacts/spanish.md     canonical Spanish extraction

Writes (one file per maxim, 1..300):
  maxims/001.md  ...
  maxims/300.md

Each file has YAML frontmatter (number, slug, title_en, title_es, status,
themes, sources) and three named H2 sections that the rest of the
pipeline parses:

    ## English
    ## Spanish
    ## Commentary

This script is idempotent: by default it never overwrites an existing
maxim file. Pass ``--resync-text`` to refresh the ``## English`` and
``## Spanish`` sections (and the ``title_en``/``title_es`` frontmatter)
from the current canonical extractions while preserving everything you
have authored under ``## Commentary`` and any other frontmatter you have
added (``status``, ``themes``, etc.).

Run from the working directory:

    python scripts/scaffold_maxims.py
    python scripts/scaffold_maxims.py --resync-text
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml


ENGLISH_PATH = Path("artifacts/english.md")
SPANISH_PATH = Path("artifacts/spanish.md")
MAXIMS_DIR = Path("maxims")

SECTION_NAMES = ("English", "Spanish", "Commentary")
COMMENTARY_STUB = "*Draft your commentary here.*\n"

_MAXIM_HEADING = re.compile(r"^##\s+(\d{1,3})\s*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^##\s", re.MULTILINE)
_SECTION_HEADING = re.compile(
    r"^##\s+(" + "|".join(SECTION_NAMES) + r")\s*$",
    re.MULTILINE,
)
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---[ \t]*\n?", re.DOTALL)
# Leading italic title: ``*...*``, allowing escaped chars (e.g. ``\*``).
_TITLE = re.compile(r"\*((?:\\.|[^*])+?)\*", re.DOTALL)


# ---------------------------------------------------------------------------
# Maxim file model — shared with check_maxims.py and build_site.py
# ---------------------------------------------------------------------------


@dataclass
class MaximFile:
    frontmatter: dict = field(default_factory=dict)
    sections: dict[str, str] = field(default_factory=dict)


def parse_maxim_file(text: str) -> MaximFile:
    """Parse a `maxims/NNN.md` file into frontmatter + named sections."""
    m = _FRONTMATTER.match(text)
    if m:
        fm = yaml.safe_load(m.group(1)) or {}
        body = text[m.end():]
    else:
        fm = {}
        body = text
    sections: dict[str, str] = {}
    matches = list(_SECTION_HEADING.finditer(body))
    for i, mh in enumerate(matches):
        name = mh.group(1)
        start = mh.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[name] = body[start:end].strip()
    return MaximFile(frontmatter=fm if isinstance(fm, dict) else {}, sections=sections)


def render_maxim_file(mf: MaximFile) -> str:
    fm_text = yaml.safe_dump(
        mf.frontmatter, allow_unicode=True, sort_keys=False, default_flow_style=False
    ).strip()
    parts = [f"---\n{fm_text}\n---", ""]
    for name in SECTION_NAMES:
        body = mf.sections.get(name, "").strip()
        parts.append(f"## {name}")
        parts.append("")
        parts.append(body if body else "")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Extraction from canonical artifacts
# ---------------------------------------------------------------------------


def split_maxims(md: str) -> dict[int, str]:
    """Return ``{maxim_number: body_text}`` for ``## N`` headings, 1..300."""
    out: dict[int, str] = {}
    for m in _MAXIM_HEADING.finditer(md):
        n = int(m.group(1))
        if not (1 <= n <= 300):
            continue
        start = m.end()
        nxt = _NEXT_H2.search(md, start)
        end = nxt.start() if nxt else len(md)
        out[n] = md[start:end].strip()
    return out


def extract_title(body: str) -> str:
    """Return the maxim title (leading italic span) with markup stripped.

    Inline footnote anchors that the PDF renders as literal asterisks
    inside the title (e.g. ``person*``) are stripped so the title field
    is plain prose. The asterisk is preserved in the body text.
    """
    m = _TITLE.search(body)
    if not m:
        return ""
    title = m.group(1)
    title = re.sub(r"\\(.)", r"\1", title)
    title = title.replace("*", "")
    title = re.sub(r"\s+", " ", title).strip()
    title = title.rstrip(".!?:;,")
    return title


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    if len(text) > 60:
        head = text[:60].rsplit("-", 1)[0]
        text = head or text[:60]
    return text


# ---------------------------------------------------------------------------
# Build / refresh
# ---------------------------------------------------------------------------


def _build_frontmatter(number: int, en_body: str, es_body: str) -> dict:
    title_en = extract_title(en_body)
    title_es = extract_title(es_body)
    slug = slugify(title_en) or f"maxim-{number:03d}"
    return {
        "number": number,
        "slug": slug,
        "title_en": title_en,
        "title_es": title_es,
        "status": "draft",
        "themes": [],
        "sources": {
            "english": "english-maurer-doubleday",
            "spanish": "spanish-blanco-catedra",
        },
    }


def scaffold_new(number: int, en_body: str, es_body: str) -> MaximFile:
    return MaximFile(
        frontmatter=_build_frontmatter(number, en_body, es_body),
        sections={
            "English": en_body,
            "Spanish": es_body,
            "Commentary": COMMENTARY_STUB.strip(),
        },
    )


def resync_text(existing: MaximFile, en_body: str, es_body: str) -> tuple[MaximFile, bool]:
    """Refresh English/Spanish text and titles; preserve commentary + custom fm.

    Returns ``(updated_file, changed)``.
    """
    changed = False
    fm = dict(existing.frontmatter)
    title_en = extract_title(en_body)
    title_es = extract_title(es_body)
    if fm.get("title_en") != title_en:
        fm["title_en"] = title_en
        changed = True
    if fm.get("title_es") != title_es:
        fm["title_es"] = title_es
        changed = True
    sections = dict(existing.sections)
    if sections.get("English", "").strip() != en_body.strip():
        sections["English"] = en_body
        changed = True
    if sections.get("Spanish", "").strip() != es_body.strip():
        sections["Spanish"] = es_body
        changed = True
    sections.setdefault("Commentary", COMMENTARY_STUB.strip())
    return MaximFile(frontmatter=fm, sections=sections), changed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--resync-text",
        action="store_true",
        help=(
            "Refresh English/Spanish sections of existing files from the canonical "
            "extractions. Preserves Commentary and custom frontmatter."
        ),
    )
    args = ap.parse_args(argv)

    if not ENGLISH_PATH.exists() or not SPANISH_PATH.exists():
        print("missing artifacts/english.md or artifacts/spanish.md; "
              "run extract_pdf.py / extract_html.py first.", file=sys.stderr)
        return 2

    en = split_maxims(ENGLISH_PATH.read_text(encoding="utf-8"))
    es = split_maxims(SPANISH_PATH.read_text(encoding="utf-8"))
    expected = set(range(1, 301))
    missing_en = sorted(expected - en.keys())
    missing_es = sorted(expected - es.keys())
    if missing_en or missing_es:
        print(f"missing English maxims: {missing_en or 'none'}", file=sys.stderr)
        print(f"missing Spanish maxims: {missing_es or 'none'}", file=sys.stderr)
        return 2

    MAXIMS_DIR.mkdir(parents=True, exist_ok=True)

    created = 0
    skipped = 0
    resynced = 0
    unchanged = 0
    for n in sorted(expected):
        path = MAXIMS_DIR / f"{n:03d}.md"
        en_body = en[n]
        es_body = es[n]
        if path.exists():
            if args.resync_text:
                existing = parse_maxim_file(path.read_text(encoding="utf-8"))
                updated, changed = resync_text(existing, en_body, es_body)
                if changed:
                    path.write_text(render_maxim_file(updated), encoding="utf-8")
                    resynced += 1
                else:
                    unchanged += 1
            else:
                skipped += 1
            continue
        new = scaffold_new(n, en_body, es_body)
        path.write_text(render_maxim_file(new), encoding="utf-8")
        created += 1

    print(f"target dir      : {MAXIMS_DIR}/")
    print(f"created         : {created}")
    print(f"skipped (exists): {skipped}")
    if args.resync_text:
        print(f"resynced        : {resynced}")
        print(f"unchanged       : {unchanged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
