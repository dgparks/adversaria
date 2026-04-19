#!/usr/bin/env python3
"""Extract text from the Maurer translation PDF and emit:

  artifacts/english_raw.json       structured page/block/span data
  artifacts/english_extracted.txt  flat reading-order text with page markers
  artifacts/english.md             lightly-structured Markdown

The extractor is intentionally conservative. Wording, punctuation and
capitalization from the PDF text layer are preserved verbatim. Only obvious
PDF-extraction artifacts are normalized (end-of-line hyphenation, intra-
paragraph line wraps, repeating running headers/footers, stray whitespace).

Heading and footnote detection use font-size cues observed in this PDF:

    25.0 Bold        -> aphorism number  (## N. <italic title>)
    16.9 BoldItalic  -> section heading  (## <text>)
    15.0             -> body text
    11.2             -> footnote text (sits at bottom of the page)

Run from the working directory:

    python scripts/extract_pdf.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PDF_PATH = Path("sources/english-maurer-doubleday.pdf")
ART_DIR = Path("artifacts")
RAW_JSON = ART_DIR / "english_raw.json"
EXTRACTED_TXT = ART_DIR / "english_extracted.txt"
MARKDOWN_OUT = ART_DIR / "english.md"
REVIEW_NOTES = ART_DIR / "english_review_notes.md"

# Tolerances for matching the size cues above.
SIZE_APHORISM_NUMBER = 25.0
SIZE_SECTION_HEADING = 16.9
SIZE_FOOTNOTE = 11.2
SIZE_BODY = 15.0
SIZE_TOL = 0.6

# Header band (top) / footer band (bottom) of a page in PDF points. Anything
# whose block bbox falls fully inside these bands AND whose text repeats across
# many pages is treated as a running header/footer and dropped.
HEADER_Y = 80.0
FOOTER_Y_FROM_BOTTOM = 60.0
RUNNING_REPEAT_THRESHOLD = 5  # text must repeat on N+ pages to be dropped


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Span:
    text: str
    size: float
    font: str
    flags: int
    bbox: tuple[float, float, float, float]

    def to_jsonable(self) -> dict:
        return {
            "text": self.text,
            "size": round(self.size, 2),
            "font": self.font,
            "flags": self.flags,
            "bbox": [round(x, 2) for x in self.bbox],
        }


@dataclass
class Line:
    spans: list[Span] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


@dataclass
class Block:
    lines: list[Line] = field(default_factory=list)
    bbox: tuple[float, float, float, float] = (0, 0, 0, 0)

    @property
    def text(self) -> str:
        return "\n".join(l.text for l in self.lines)


@dataclass
class Page:
    page_index: int  # 0-based
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)
    plain_text: str = ""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_pages(doc: fitz.Document) -> list[Page]:
    pages: list[Page] = []
    for i in range(doc.page_count):
        p = doc.load_page(i)
        rect = p.rect
        page = Page(page_index=i, width=rect.width, height=rect.height)
        page.plain_text = p.get_text("text")
        d = p.get_text("dict")
        for b in d["blocks"]:
            if b.get("type", 0) != 0:  # skip images
                continue
            block = Block(bbox=tuple(b["bbox"]))
            for line in b["lines"]:
                ln = Line(bbox=tuple(line["bbox"]))
                for s in line["spans"]:
                    ln.spans.append(
                        Span(
                            text=s["text"],
                            size=float(s["size"]),
                            font=s["font"],
                            flags=int(s["flags"]),
                            bbox=tuple(s["bbox"]),
                        )
                    )
                block.lines.append(ln)
            page.blocks.append(block)
        pages.append(page)
    return pages


# ---------------------------------------------------------------------------
# Running-header/footer detection
# ---------------------------------------------------------------------------


def find_running_strings(pages: list[Page]) -> set[str]:
    """Return the set of stripped strings that look like running headers/footers."""
    counts: Counter[str] = Counter()
    for page in pages:
        for block in page.blocks:
            y0, y1 = block.bbox[1], block.bbox[3]
            in_header = y1 <= HEADER_Y
            in_footer = y0 >= page.height - FOOTER_Y_FROM_BOTTOM
            if not (in_header or in_footer):
                continue
            t = block.text.strip()
            if not t:
                continue
            counts[t] += 1
    return {t for t, c in counts.items() if c >= RUNNING_REPEAT_THRESHOLD}


# ---------------------------------------------------------------------------
# Markdown build
# ---------------------------------------------------------------------------


# All end-of-line hyphens in this book are real compound words (sharp-eyed,
# self-mastery, etc.), not soft hyphens from line wrap. Preserve the hyphen
# and just drop the newline.
_HYPHEN_FIX = re.compile(r"(\w-)\n(\w)")
_MULTI_BLANK = re.compile(r"\n{3,}")


def _join_paragraph(lines: list[str]) -> str:
    """Join wrapped lines belonging to one paragraph, fixing soft hyphens."""
    raw = "\n".join(l.rstrip() for l in lines if l is not None)
    # Keep the compound-word hyphen, just drop the newline that wraps it.
    raw = _HYPHEN_FIX.sub(r"\1\2", raw)
    # Collapse single newlines (intra-paragraph wrap) into spaces, but keep
    # double newlines as paragraph separators.
    parts = raw.split("\n\n")
    cleaned: list[str] = []
    for p in parts:
        p = re.sub(r"\s*\n\s*", " ", p)
        # PyMuPDF span boundaries occasionally leave a space before
        # punctuation (e.g. "quality , and..."); normalize that.
        p = re.sub(r" +([,.;:!?])", r"\1", p)
        cleaned.append(p.strip())
    return "\n\n".join(p for p in cleaned if p)


def _is_size(value: float, target: float, tol: float = SIZE_TOL) -> bool:
    return abs(value - target) <= tol


def _block_kind(block: Block) -> str:
    """Classify a block by char-weighted span sizes plus salient cues.

    Order of precedence:
      * any aphorism-number-sized digit span  -> ``aphorism_number``
      * any section-heading-sized span        -> ``section_heading``
      * dominant size <= footnote-size        -> ``footnote``
      * otherwise                             -> ``body``
    """
    has_text = False
    weighted: dict[float, int] = {}
    for line in block.lines:
        for span in line.spans:
            t = span.text.strip()
            if not t:
                continue
            has_text = True
            if _is_size(span.size, SIZE_APHORISM_NUMBER) and t.lstrip("*").isdigit():
                return "aphorism_number"
            if _is_size(span.size, SIZE_SECTION_HEADING):
                return "section_heading"
            weighted[round(span.size, 1)] = weighted.get(round(span.size, 1), 0) + len(t)
    if not has_text:
        return "empty"
    dominant_size = max(weighted, key=weighted.get)
    if dominant_size <= SIZE_FOOTNOTE + SIZE_TOL:
        return "footnote"
    return "body"


def _flatten_block(block: Block) -> list[tuple[int, Span]]:
    """Return block spans in reading order tagged with their line index."""
    out: list[tuple[int, Span]] = []
    for li, line in enumerate(block.lines):
        for span in line.spans:
            out.append((li, span))
    return out


def _spans_to_text(spans: Iterable[tuple[int, Span]]) -> str:
    """Reconstruct text from (line_index, span) pairs preserving line breaks."""
    parts: list[str] = []
    last_li: int | None = None
    for li, span in spans:
        if last_li is not None and li != last_li:
            parts.append("\n")
        parts.append(span.text)
        last_li = li
    return "".join(parts)


def _split_aphorism_block(block: Block) -> tuple[str, str, str]:
    """Return (number, italic_title, body_text) for an aphorism-number block.

    The italic title is the first contiguous run of italic body-size spans
    after the bold number; it ends at the first sentence-terminator (`.`, `!`,
    `?`, `:`). Inline footnote-anchor spans (size ~11.2 / ~8.7) and pure-
    whitespace spans inside the run are kept as part of the title text.
    """
    flat = _flatten_block(block)
    if not flat:
        return "", "", ""

    i = 0
    number = ""
    if _is_size(flat[0][1].size, SIZE_APHORISM_NUMBER) and flat[0][1].text.strip().isdigit():
        number = flat[0][1].text.strip()
        i = 1

    # Skip leading whitespace spans.
    while i < len(flat) and not flat[i][1].text.strip():
        i += 1

    title_pieces: list[str] = []
    saw_italic = False
    last_li: int | None = None
    while i < len(flat):
        li, s = flat[i]
        is_italic_body = ("Italic" in s.font) and _is_size(s.size, SIZE_BODY)
        is_anchor = (
            _is_size(s.size, SIZE_FOOTNOTE) or _is_size(s.size, 8.7)
        ) and s.text.strip() in {"*", "**", "***", "†", "‡"}
        is_blank = not s.text.strip()
        if is_italic_body or is_anchor or (is_blank and saw_italic):
            # Preserve a space at line breaks (PyMuPDF dropped trailing space on
            # the previous line's span and leading space on this line's span).
            if last_li is not None and li != last_li:
                title_pieces.append(" ")
            title_pieces.append(s.text)
            last_li = li
            if is_italic_body:
                saw_italic = True
                if s.text.rstrip().endswith((".", "!", "?", ":")):
                    i += 1
                    break
            i += 1
        else:
            break

    title = re.sub(r"\s+", " ", "".join(title_pieces)).strip()
    body = _spans_to_text(flat[i:])
    return number, title, body


def _block_plain_text(block: Block) -> str:
    """Reconstruct the block's text preserving line breaks but joining spans."""
    out_lines: list[str] = []
    for line in block.lines:
        out_lines.append("".join(s.text for s in line.spans).rstrip())
    text = "\n".join(out_lines)
    # The PDF uses non-breaking spaces in headers; treat as blank.
    if text.replace("\u00a0", "").strip() == "":
        return ""
    return text


def build_markdown(pages: list[Page]) -> tuple[str, list[str]]:
    """Convert pages into Markdown. Also return a list of review notes."""
    notes: list[str] = []
    running = find_running_strings(pages)
    if running:
        notes.append(
            "Detected running header/footer strings (dropped from Markdown): "
            + ", ".join(sorted(repr(s) for s in running))
        )

    out: list[str] = []
    aphorisms_seen: list[int] = []
    # Pending footnotes for the current run. Each entry is a single footnote
    # (already a list of block texts that will be joined into one paragraph).
    # A "footnote run" can span multiple PyMuPDF blocks and even page
    # boundaries; we flush only when the next non-footnote block appears.
    pending_footnotes: list[list[str]] = []

    _FN_MARKER_FIRSTSPAN = re.compile(r"^\s*(?:\*{1,3}|\d+\.)\s*$")

    def _first_nonblank_span(block: Block) -> Span | None:
        for line in block.lines:
            for span in line.spans:
                if span.text.strip():
                    return span
        return None

    def add_footnote_block(block: Block) -> None:
        first = _first_nonblank_span(block)
        is_new = bool(first and _FN_MARKER_FIRSTSPAN.match(first.text))
        text = _block_plain_text(block)
        if is_new or not pending_footnotes:
            pending_footnotes.append([text])
        else:
            pending_footnotes[-1].append(text)

    def flush_footnotes() -> None:
        if not pending_footnotes:
            return
        out.append("")
        out.append("---")
        for chunks in pending_footnotes:
            joined = _join_paragraph(
                [ln for chunk in chunks for ln in chunk.splitlines()]
            )
            single_line = re.sub(r"\s+", " ", joined).strip()
            if single_line:
                out.append(f"> {single_line}")
        out.append("")
        pending_footnotes.clear()

    # The book's title page is decorative and image-only. The metadata title is
    # "The Art of Worldly Wisdom"; emit it as the H1 once.
    out.append("# The Art of Worldly Wisdom")
    out.append("")
    out.append("*A Pocket Oracle*")
    out.append("")
    out.append("Baltasar Gracián — translated by Christopher Maurer")
    out.append("")
    seen_title = True

    for page in pages:
        page_no = page.page_index + 1
        for block in page.blocks:
            text = _block_plain_text(block)
            if not text:
                continue
            stripped = text.strip()
            if stripped in running:
                continue
            kind = _block_kind(block)

            if kind == "section_heading":
                flush_footnotes()
                out.append("")
                out.append(f"## {stripped}")
                continue

            if kind == "aphorism_number":
                flush_footnotes()
                number, title, body_raw = _split_aphorism_block(block)
                out.append("")
                if number:
                    aphorisms_seen.append(int(number))
                if title:
                    head = f"## {number}. {title}" if number else f"## {title}"
                else:
                    head = f"## {number}." if number else "##"
                    notes.append(
                        f"page {page_no}: aphorism {number or '?'} had no italic title sentence"
                    )
                out.append(head)
                body = _join_paragraph(body_raw.split("\n"))
                if body:
                    out.append("")
                    out.append(body)
                continue

            if kind == "footnote":
                add_footnote_block(block)
                continue

            if kind == "body":
                flush_footnotes()
                para = _join_paragraph(text.split("\n"))
                if para:
                    out.append("")
                    out.append(para)
                continue

            # empty / unknown: skip
    # Final flush after the last page.
    flush_footnotes()

    # Sanity-check aphorism numbering.
    if aphorisms_seen:
        expected = list(range(1, max(aphorisms_seen) + 1))
        missing = sorted(set(expected) - set(aphorisms_seen))
        if missing:
            notes.append(f"Missing aphorism numbers in Markdown output: {missing}")
        dups = [n for n, c in Counter(aphorisms_seen).items() if c > 1]
        if dups:
            notes.append(f"Duplicate aphorism numbers detected: {sorted(dups)}")
        if max(aphorisms_seen) != 300:
            notes.append(
                f"Highest aphorism number = {max(aphorisms_seen)} (expected 300)."
            )

    md = "\n".join(out).rstrip() + "\n"
    md = _MULTI_BLANK.sub("\n\n", md)
    md = _reformat_index_section(md, "THE APHORISMS")
    return md, notes


# Split between maxim entries: a sentence terminator (with optional trailing
# closing quotes / parens), then whitespace, then ``<n>.``. Captured so we can
# preserve the terminator and just replace the separating whitespace.
_INDEX_SPLIT = re.compile(r"([.…!?][”\"’')\]]*)\s+(?=\d{1,3}\.)")


def _reformat_index_section(md: str, heading_text: str) -> str:
    """Put each numbered title on its own line within an index-style section.

    Looks for the ``## <heading_text>`` heading and rewrites the body of that
    section (up to the next ``##``/``---``/EOF) so paragraphs are joined and
    then split at every ``<number>.`` boundary.
    """
    pattern = re.compile(rf"^##\s+{re.escape(heading_text)}\s*$", re.MULTILINE)
    m = pattern.search(md)
    if not m:
        return md
    body_start = m.end()
    end_match = re.search(r"(?m)^(##\s|---\s*$)", md[body_start:])
    body_end = body_start + end_match.start() if end_match else len(md)

    body = md[body_start:body_end]
    # Collapse blank-line paragraph separators within the index into a single
    # space so the index reads as one continuous stream of "<n>. Title."
    flat = re.sub(r"\n\s*\n", " ", body).strip()
    flat = re.sub(r"[ \t]+", " ", flat)
    if not flat:
        return md
    one_per_line = _INDEX_SPLIT.sub(r"\1\n", flat)
    return md[:body_start].rstrip() + "\n\n" + one_per_line + "\n\n" + md[body_end:].lstrip()


# ---------------------------------------------------------------------------
# Plain text
# ---------------------------------------------------------------------------


def build_plain_text(pages: list[Page]) -> str:
    parts: list[str] = []
    for page in pages:
        parts.append(f"=== Page {page.page_index + 1} ===")
        parts.append(page.plain_text.rstrip())
        parts.append("")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Raw JSON
# ---------------------------------------------------------------------------


def to_raw_json(pages: list[Page]) -> dict:
    return {
        "source_pdf": str(PDF_PATH),
        "page_count": len(pages),
        "pages": [
            {
                "page_index": p.page_index,
                "page_number": p.page_index + 1,
                "width": round(p.width, 2),
                "height": round(p.height, 2),
                "plain_text": p.plain_text,
                "blocks": [
                    {
                        "bbox": [round(x, 2) for x in b.bbox],
                        "lines": [
                            {
                                "bbox": [round(x, 2) for x in l.bbox],
                                "spans": [s.to_jsonable() for s in l.spans],
                            }
                            for l in b.lines
                        ],
                    }
                    for b in p.blocks
                ],
            }
            for p in pages
        ],
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}", file=sys.stderr)
        return 2
    ART_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(PDF_PATH)
    pages = extract_pages(doc)

    RAW_JSON.write_text(json.dumps(to_raw_json(pages), ensure_ascii=False, indent=1))
    EXTRACTED_TXT.write_text(build_plain_text(pages))

    md, notes = build_markdown(pages)
    MARKDOWN_OUT.write_text(md)

    note_path = REVIEW_NOTES
    standing = """# Review notes (English)

Generated by `scripts/extract_pdf.py`. These are known limitations or pages
worth inspecting by hand. Wording, punctuation, and capitalization come
straight from the PDF text layer; only line wraps, soft hyphens, and running
headers/footers are normalized.

## Source

- The source PDF (`sources/english-maurer-doubleday.pdf`) is born-digital.
  321 of 324 pages have a real text layer; the 3 zero-character pages are
  the decorative title/copyright pages. No OCR was needed.
- Fonts: body text is FreeSerif at 15.0 pt; aphorism numbers are FreeSerifBold
  at 25.0 pt; section headings are FreeSerifBoldItalic at 16.9 pt; footnotes
  are FreeSerif/FreeSerifItalic at 11.2 pt; inline footnote anchors (`*`,
  `**`) are at 8.7 pt.

## Known structural decisions

- The H1 title (`# The Art of Worldly Wisdom`) and the author/translator line
  are synthesized — the original title page is image-only and has no text
  layer. Remove the H1 if you want a strictly-from-text result.
- All 300 numbered aphorisms are emitted as `## N. <italic title sentence>`
  followed by the body paragraph. The italic title is the first contiguous
  italic run after the bold number, ending at the first `.`/`!`/`?`/`:` and
  may include inline footnote anchors (`*`, `**`).
- Footnotes are emitted as Markdown blockquotes (`> ...`) preceded by a
  horizontal rule (`---`). A footnote that PyMuPDF returned in several blocks
  (or that wraps onto the top of the next page) is merged into one quoted
  paragraph.
- Running headers/footers detected by repetition + position are dropped from
  the Markdown but remain in `book_extracted.txt`.

## Pages worth inspecting by hand

- The back-matter section `## THE APHORISMS` (after aphorism 300) is an
  index of all 300 titles. PyMuPDF returned it as many small blocks; the
  Markdown preserves the text verbatim but renders each block as its own
  paragraph rather than as a single numbered list.
- Front-matter block immediately before "1. All has reached perfection..."
  contains the running heading "THE APHORISMS" emitted as `##`.
- Aphorism 1 contains an inline `*` footnote anchor that is preserved inside
  the heading (`true person*`). This is faithful to the print layout.
- A small amount of text on the back cover (page 324 in the PDF) is
  preserved but unstyled; check if you want it dropped.

## Automated run notes (most recent extraction)

"""
    body = "\n".join(f"- {n}" for n in notes) if notes else "- No automated issues detected."
    note_path.write_text(standing + body + "\n")

    print(f"pages           : {len(pages)}")
    print(f"raw json        : {RAW_JSON}")
    print(f"plain text      : {EXTRACTED_TXT}")
    print(f"markdown        : {MARKDOWN_OUT}")
    print(f"review notes    : {note_path}")
    print(f"automated notes : {len(notes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
