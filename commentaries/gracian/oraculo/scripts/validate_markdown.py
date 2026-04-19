#!/usr/bin/env python3
"""Compare ``artifacts/english.md`` against ``artifacts/english_extracted.txt``.

The validator strips Markdown syntax, normalizes whitespace and punctuation,
and looks for content-level damage rather than visual divergence. It reports:

  * counts of normalized tokens on each side;
  * the number / identity of any aphorism numbers (1..300) missing or
    duplicated in the Markdown;
  * the number of footnote-style lines (``> ...``) preserved in the Markdown
    versus footnote-sized text observed in the extracted plain text;
  * a difflib summary of the first few differing token chunks (truncated).

The validator does NOT require byte-exact equality: front-matter title lines
and a few normalization edits (line-wrap, hyphenation, dropped headers/
footers) are expected to differ. It exits 0 on "no obvious damage" and 1 on
issues serious enough to investigate.
"""
from __future__ import annotations

import difflib
import re
import sys
from collections import Counter
from pathlib import Path

ART_DIR = Path("artifacts")
MD_PATH = ART_DIR / "english.md"
TXT_PATH = ART_DIR / "english_extracted.txt"
NOTES_PATH = ART_DIR / "english_review_notes.md"


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


_MD_HEADING = re.compile(r"^\s{0,3}#+\s*")
_MD_QUOTE = re.compile(r"^\s{0,3}>\s?")
_MD_RULE = re.compile(r"^\s*-{3,}\s*$|^\s*\*{3,}\s*$")
_MD_INLINE_EMPH = re.compile(r"(\*+|_+)((?:\\.|(?!\1)[^\n])+?)\1")
_MD_ESCAPE = re.compile(r"\\([\\*_`#>\-\[\]()])")
_PAGE_MARK = re.compile(r"^\s*=== Page \d+ ===\s*$")
_WS = re.compile(r"\s+")


def strip_markdown(md: str) -> str:
    out_lines: list[str] = []
    for raw in md.splitlines():
        if _MD_RULE.match(raw):
            continue
        line = _MD_HEADING.sub("", raw)
        line = _MD_QUOTE.sub("", line)
        # Repeatedly strip emphasis so nested or adjacent runs all collapse.
        for _ in range(3):
            new = _MD_INLINE_EMPH.sub(r"\2", line)
            if new == line:
                break
            line = new
        line = _MD_ESCAPE.sub(r"\1", line)
        out_lines.append(line)
    return "\n".join(out_lines)


def strip_extracted(txt: str) -> str:
    return "\n".join(l for l in txt.splitlines() if not _PAGE_MARK.match(l))


def normalize_for_compare(s: str) -> str:
    """Aggressive whitespace/punctuation collapse for fuzzy compare."""
    s = s.replace("\u00a0", " ")
    s = _WS.sub(" ", s)
    return s.strip()


def tokens(s: str) -> list[str]:
    """Lowercase alphanumeric tokens; punctuation/quotes ignored."""
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+", s.lower())


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_aphorism_numbers(md_text: str) -> tuple[list[int], list[int], list[int]]:
    # Accept both the old ``## N. <title>`` style and the bare-numeral
    # ``## N`` style produced by ``restyle_english.py``.
    seen = [int(m.group(1)) for m in re.finditer(r"^##\s+(\d+)\b", md_text, re.MULTILINE)]
    expected = list(range(1, 301))
    missing = sorted(set(expected) - set(seen))
    counts = Counter(seen)
    dups = sorted(n for n, c in counts.items() if c > 1)
    return seen, missing, dups


def check_token_drift(md_text: str, txt_text: str) -> tuple[int, int, list[str]]:
    md_tokens = tokens(strip_markdown(md_text))
    tx_tokens = tokens(strip_extracted(txt_text))
    md_counter = Counter(md_tokens)
    tx_counter = Counter(tx_tokens)
    sample: list[str] = []
    # Tokens dropped from Markdown but present in extracted text.
    for tok, c in tx_counter.most_common():
        delta = c - md_counter.get(tok, 0)
        if delta >= 5 and tok.isalpha() and len(tok) > 3:
            sample.append(f"  -{delta:>4d} '{tok}' (extracted={c}, markdown={md_counter.get(tok, 0)})")
        if len(sample) >= 15:
            break
    return len(md_tokens), len(tx_tokens), sample


def check_diff_sample(md_text: str, txt_text: str, max_blocks: int = 5) -> list[str]:
    md_norm = normalize_for_compare(strip_markdown(md_text)).split(" ")
    tx_norm = normalize_for_compare(strip_extracted(txt_text)).split(" ")
    sm = difflib.SequenceMatcher(a=tx_norm, b=md_norm, autojunk=False)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if len(out) >= max_blocks:
            break
        a_chunk = " ".join(tx_norm[i1:i2])[:200]
        b_chunk = " ".join(md_norm[j1:j2])[:200]
        out.append(
            f"  [{tag}] @ extracted[{i1}:{i2}] vs md[{j1}:{j2}]\n"
            f"      extracted: {a_chunk!r}\n"
            f"      markdown : {b_chunk!r}"
        )
    return out


def check_footnotes(md_text: str) -> int:
    return sum(1 for line in md_text.splitlines() if line.startswith(">"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    if not MD_PATH.exists() or not TXT_PATH.exists():
        print("Run scripts/extract_pdf.py first.", file=sys.stderr)
        return 2

    md_text = MD_PATH.read_text()
    txt_text = TXT_PATH.read_text()

    seen, missing, dups = check_aphorism_numbers(md_text)
    md_n, tx_n, drift_sample = check_token_drift(md_text, txt_text)
    diff_sample = check_diff_sample(md_text, txt_text)
    fn_lines = check_footnotes(md_text)

    print(f"markdown tokens : {md_n:,}")
    print(f"extracted tokens: {tx_n:,}")
    drift_pct = (md_n - tx_n) / tx_n * 100 if tx_n else 0.0
    print(f"token delta     : {md_n - tx_n:+,} ({drift_pct:+.2f}%)")
    print(f"aphorism #s seen: {len(seen)} (expected 300)")
    if missing:
        print(f"  MISSING: {missing}")
    if dups:
        print(f"  DUPLICATED: {dups}")
    print(f"footnote lines  : {fn_lines}")

    if drift_sample:
        print("\nTokens that appear noticeably more often in extracted text "
              "than in markdown (top 15):")
        for line in drift_sample:
            print(line)

    if diff_sample:
        print("\nFirst few differing chunks (sample):")
        for chunk in diff_sample:
            print(chunk)

    serious = bool(missing) or bool(dups) or abs(drift_pct) > 5.0
    if serious:
        print("\nVALIDATION: issues detected.")
        return 1
    print("\nVALIDATION: no obvious damage detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
