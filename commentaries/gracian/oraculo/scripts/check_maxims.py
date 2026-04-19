#!/usr/bin/env python3
"""Sanity-check ``maxims/*.md`` for completeness, parseability, and drift.

Reports, with non-zero exit on hard errors:

  * file count vs expected 1..300, plus any missing or unexpected files
  * per-file: frontmatter parses, required keys present, ``number`` field
    matches filename
  * per-file: ``## English`` / ``## Spanish`` / ``## Commentary`` sections
    present
  * drift: each file's ``## English`` / ``## Spanish`` body compared to
    the current canonical extractions in ``artifacts/english.md`` and
    ``artifacts/spanish.md`` (warnings only — manual edits are allowed)
  * a status histogram (``draft`` / ``review`` / ``ready`` / ``published``)

Drift warnings do not fail the check; rerun with ``--strict`` to make
them errors.

Run from the working directory:

    python scripts/check_maxims.py
"""
from __future__ import annotations

import argparse
import sys

from scaffold_maxims import (
    ENGLISH_PATH,
    MAXIMS_DIR,
    SECTION_NAMES,
    SPANISH_PATH,
    parse_maxim_file,
    split_maxims,
)


REQUIRED_FM = ("number", "slug", "title_en", "title_es", "status", "themes")
KNOWN_STATUSES = ("draft", "review", "ready", "published")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat drift warnings as errors (non-zero exit).",
    )
    args = ap.parse_args(argv)

    if not MAXIMS_DIR.is_dir():
        print(f"missing {MAXIMS_DIR}; run scripts/scaffold_maxims.py first.", file=sys.stderr)
        return 2

    en = split_maxims(ENGLISH_PATH.read_text(encoding="utf-8"))
    es = split_maxims(SPANISH_PATH.read_text(encoding="utf-8"))

    files = sorted(MAXIMS_DIR.glob("*.md"))
    expected = {f"{n:03d}" for n in range(1, 301)}
    actual = {f.stem for f in files}

    errors: list[str] = []
    drift: list[str] = []
    status_counts: dict[str, int] = {}

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"missing files: {missing}")
    if extra:
        errors.append(f"unexpected files: {extra}")

    for path in files:
        if path.stem not in expected:
            continue
        n = int(path.stem)
        try:
            mf = parse_maxim_file(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: parse error: {exc}")
            continue

        for key in REQUIRED_FM:
            if key not in mf.frontmatter:
                errors.append(f"{path.name}: missing frontmatter key '{key}'")

        fm_n = mf.frontmatter.get("number")
        if fm_n != n:
            errors.append(
                f"{path.name}: frontmatter number={fm_n!r} does not match filename {n}"
            )

        status = str(mf.frontmatter.get("status", "draft"))
        status_counts[status] = status_counts.get(status, 0) + 1
        if status not in KNOWN_STATUSES:
            errors.append(
                f"{path.name}: unknown status {status!r} "
                f"(expected one of {list(KNOWN_STATUSES)})"
            )

        for s in SECTION_NAMES:
            if s not in mf.sections:
                errors.append(f"{path.name}: missing '## {s}' section")

        for label, src in (("English", en), ("Spanish", es)):
            canonical = src.get(n, "").strip()
            current = mf.sections.get(label, "").strip()
            if canonical and current and canonical != current:
                drift.append(f"{path.name}: {label} differs from artifacts/")

    print(f"files           : {len(files)} (expected 300)")
    if missing:
        print(f"  MISSING       : {missing}")
    if extra:
        print(f"  EXTRA         : {extra}")
    print(f"errors          : {len(errors)}")
    for e in errors[:20]:
        print(f"  {e}")
    if len(errors) > 20:
        print(f"  ... and {len(errors) - 20} more")
    print(f"drift warnings  : {len(drift)}")
    for d in drift[:20]:
        print(f"  {d}")
    if len(drift) > 20:
        print(f"  ... and {len(drift) - 20} more")
    if status_counts:
        print("status counts   :")
        for k in KNOWN_STATUSES:
            if status_counts.get(k):
                print(f"  {k:<10s}: {status_counts[k]}")
        for k, v in status_counts.items():
            if k not in KNOWN_STATUSES:
                print(f"  {k:<10s}: {v}  (UNKNOWN)")

    if errors or (args.strict and drift):
        print("\nCHECK: issues detected.")
        return 1
    print("\nCHECK: OK." if not drift else "\nCHECK: OK (with drift warnings).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
