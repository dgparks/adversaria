# adversaria

A workspace for converting source texts (PDFs, HTML, etc.) into clean,
high-fidelity Markdown for reading and downstream commentary.

The repository is organized as a collection of per-work projects under
`commentaries/`, each with its own `sources/`, `scripts/`, and `artifacts/`.

```
adversaria/
├── .tools/                       # workspace-local toolchain (uv + venv)
│   ├── bin/                      # uv, uvx
│   ├── uv-cache/                 # uv download cache
│   └── venv/                     # Python 3.12 virtualenv with deps
└── commentaries/
    └── gracian/
        └── oraculo/
            ├── sources/          # original inputs (PDF, HTML, …)
            ├── scripts/          # extraction / conversion / scaffold / build
            ├── artifacts/        # generated outputs (.md, .json, .txt, site/)
            ├── maxims/           # editorial source of truth (one .md per maxim)
            └── templates/        # Jinja2 + CSS for the local preview
```

## `.tools` — workspace-local Python toolchain

To stay sandbox-friendly (no `sudo`, no `~/.local` writes, no global
`pip install`), all Python dependencies live inside `.tools/`:

- `.tools/bin/uv` — the [uv](https://docs.astral.sh/uv/) package manager.
- `.tools/venv/` — a Python 3.12 virtualenv created with `uv venv`.
- `.tools/uv-cache/` — `UV_CACHE_DIR` so downloads stay in-tree.

### Running scripts

Always invoke the venv's interpreter directly so you don't depend on
shell activation:

```bash
.tools/venv/bin/python <path/to/script.py>
```

### Adding a new dependency

```bash
UV_CACHE_DIR=.tools/uv-cache \
  .tools/bin/uv pip install --python .tools/venv/bin/python <package>
```

Currently installed: `pymupdf` (PDF text + layout extraction),
`beautifulsoup4` (HTML parsing), `pyyaml` (frontmatter), `jinja2`
(templates), `markdown-it-py` (Markdown → HTML for the local preview).

### Bootstrapping `.tools` from scratch

If `.tools/` is missing (fresh clone, since it's gitignored):

```bash
mkdir -p .tools/bin .tools/uv-cache
curl -LsSf https://astral.sh/uv/install.sh \
  | env UV_INSTALL_DIR=.tools/bin INSTALLER_NO_MODIFY_PATH=1 sh
UV_CACHE_DIR=.tools/uv-cache .tools/bin/uv venv .tools/venv --python 3.12
UV_CACHE_DIR=.tools/uv-cache \
  .tools/bin/uv pip install --python .tools/venv/bin/python \
  pymupdf beautifulsoup4 pyyaml jinja2 markdown-it-py
```

## Conversion pattern

Each project follows the same general shape:

1. **Extract** — a deterministic Python script reads a file in `sources/`
   and writes structured intermediates to `artifacts/` (e.g. raw JSON
   plus a plain-text dump preserving reading order).
2. **Convert** — the same (or a sibling) script emits a Markdown file in
   `artifacts/` with only light, well-justified structural markup.
3. **Restyle** *(optional)* — a small script applies project-specific
   formatting conventions (e.g. heading style).
4. **Validate** — a script strips Markdown and compares against the
   plain-text extraction to catch dropped lines, altered wording,
   missing numbered entries, etc.
5. **Review notes** — `artifacts/review_notes.md` records ambiguities
   and decisions for human follow-up.

Hard rules for any conversion:

- **No paraphrasing, modernizing, or summarizing.** Preserve wording,
  punctuation, and capitalization exactly.
- **No OCR** unless the text layer demonstrably fails.
- **Normalize only obvious extraction artifacts** (line wraps,
  soft-hyphen joins, repeated headers/footers, stray whitespace).
- **Flag ambiguities** in `review_notes.md` instead of guessing.

## Worked example: `commentaries/gracian/oraculo`

Two parallel editions of Baltasar Gracián's *Oráculo manual y arte de
prudencia*:

- English: Maurer translation, born-digital PDF in
  `sources/english-maurer-doubleday.pdf`.
- Spanish: Cátedra edition, HTML in
  `sources/spanish-blanco-catedra.html`.

Sources are named `<language>-<editor/translator>-<imprint>.<ext>` and
artifacts are named after the language: `english.md`, `spanish.md`,
plus `english_<role>.<ext>` for intermediates
(`english_raw.json`, `english_extracted.txt`,
`english_review_notes.md`).

Both editions end up with the same heading convention: aphorisms are
headed by the bare numeral (`## 70`) with the original italicized title
embedded inline at the start of the body paragraph.

### Scripts

The pipeline has two stages: **extraction** (PDF/HTML → canonical
Markdown in `artifacts/`) and **editorial** (canonical Markdown →
per-maxim files in `maxims/` → optional local HTML preview).

**Extraction stage**

| Script | Input → Output | Purpose |
| --- | --- | --- |
| `scripts/extract_pdf.py` | `sources/english-maurer-doubleday.pdf` → `artifacts/{english_raw.json, english_extracted.txt, english.md, english_review_notes.md}` | PyMuPDF extraction; classifies blocks (heading / aphorism number / italic title / footnote / body) by font size and weight; merges multi-page footnotes; reformats the back-matter index. |
| `scripts/restyle_english.py` | `artifacts/english.md` (in-place) | Converts `## N. Title` → `## N` with the title moved to the start of the body as `*Title*`. Escapes literal `*`/`_` in titles. |
| `scripts/extract_html.py` | `sources/spanish-blanco-catedra.html` → `artifacts/spanish.md` | BeautifulSoup parse; emits the bare-numeral style natively. |
| `scripts/validate_markdown.py` | `artifacts/{english.md, english_extracted.txt}` | Strips Markdown, normalizes whitespace, diffs against extracted text; verifies the expected count of numbered aphorisms. |

**Editorial stage**

| Script | Input → Output | Purpose |
| --- | --- | --- |
| `scripts/scaffold_maxims.py` | `artifacts/{english.md, spanish.md}` → `maxims/NNN.md` (300 files) | Splits each canonical extraction at `## N` headings and writes one editorial file per maxim with YAML frontmatter and three named H2 sections (`## English`, `## Spanish`, `## Commentary`). Idempotent: never overwrites. Pass `--resync-text` to refresh only the language sections + title frontmatter from the canonical extractions, preserving commentary and other custom fields. |
| `scripts/check_maxims.py` | `maxims/*.md` (+ `artifacts/{english,spanish}.md`) | Lints the editorial corpus: 300 files present, frontmatter parseable, required keys present, all three sections present, status from a known set, and content-drift comparison vs. the canonical extractions. Pass `--strict` to make drift warnings fail the run. |
| `scripts/build_site.py` | `maxims/*.md` + `templates/` → `artifacts/site/{index.html, NNN.html, style.css}` | Renders a local HTML preview using Jinja2 + markdown-it-py: side-by-side English/Spanish on top, commentary below, prev/next nav, and an index page. **Disposable preview only**, not a publishing pipeline (see below). |

### `maxims/` is the editorial source of truth

After scaffolding, `maxims/NNN.md` is what you edit. Each file looks
like:

```markdown
---
number: 1
slug: all-has-reached-perfection-and-becoming-a-true-person-is
title_en: All has reached perfection, and becoming a true person is the greatest perfection of all
title_es: Todo está ya en su punto, y el ser persona en el mayor
status: draft           # draft | review | ready | published
themes: []
sources:
  english: english-maurer-doubleday
  spanish: spanish-blanco-catedra
---

## English

*All has reached perfection, …* It takes more to make one sage today …

## Spanish

*Todo está ya en su punto, y el ser persona en el mayor*. Más se requiere …

## Commentary

…your prose here…
```

The English/Spanish sections start as the canonical text from
`artifacts/english.md` / `artifacts/spanish.md`; you can edit them if
you want (e.g. to fix a stray PDF artifact in context), and
`check_maxims.py` will flag the divergence as a drift warning. If the
upstream extraction ever changes, `scaffold_maxims.py --resync-text`
pulls fresh language text in without touching your commentary.

### `artifacts/site/` is a disposable preview

`build_site.py` is **not** the publishing pipeline. The canonical
deliverables of this project are the Markdown files in `maxims/`.
When the site goes live, the target is a real engine — most likely
[VitePress](https://vitepress.dev/) — that consumes those Markdown
files directly via a small build-time transform that turns the three
named H2 sections into a Vue side-by-side layout.

Until that day, `artifacts/site/*.html` is a local sanity check: open
`artifacts/site/index.html` in a browser to see exactly what each
maxim will look like in the eventual layout. Treat it like
`artifacts/english_extracted.txt`: regenerable, gitignored, and free
to delete.

To keep the Markdown portable to whatever engine you eventually pick
(VitePress, Astro, Hugo, Ghost, …) stick to plain CommonMark + YAML
frontmatter. Avoid MDX, Vue components in MD, VitePress containers
(`::: tip`), Liquid/Jinja tags, and engine-specific footnote
extensions while drafting.

### Run the full pipeline

```bash
cd commentaries/gracian/oraculo

# 1. Extraction (re-run whenever sources/ changes)
../../../.tools/venv/bin/python scripts/extract_pdf.py
../../../.tools/venv/bin/python scripts/restyle_english.py
../../../.tools/venv/bin/python scripts/extract_html.py
../../../.tools/venv/bin/python scripts/validate_markdown.py

# 2. Editorial scaffold (one-shot; rerun is a no-op)
../../../.tools/venv/bin/python scripts/scaffold_maxims.py
# ...or refresh language text after a re-extraction:
# ../../../.tools/venv/bin/python scripts/scaffold_maxims.py --resync-text

# 3. Check + preview (run as often as you like while drafting)
../../../.tools/venv/bin/python scripts/check_maxims.py
../../../.tools/venv/bin/python scripts/build_site.py
# Then open artifacts/site/index.html in a browser.
```

A clean validation prints the aphorism count (300) and exits 0; a
clean check prints `CHECK: OK.` and exits 0. Any drift is reported as
a unified diff against `artifacts/english_extracted.txt` (extraction
validator) or as per-file warnings (editorial check).

## Conventions for new projects

When adding a new work under `commentaries/`:

1. Create `sources/`, `scripts/`, `artifacts/` siblings.
2. Drop original inputs into `sources/` named
   `<language>-<editor>-<imprint>.<ext>` (e.g.
   `english-maurer-doubleday.pdf`). Sources are kept in git; they are
   the provenance of every artifact.
3. Name artifacts after the language: `<language>.md` for the canonical
   Markdown and `<language>_<role>.<ext>` for intermediates
   (`<language>_raw.json`, `<language>_extracted.txt`,
   `<language>_review_notes.md`).
4. Make scripts idempotent and runnable from the project directory with
   no arguments.
5. Use the workspace `.tools/venv/bin/python` — do **not** introduce a
   per-project venv unless dependencies genuinely conflict.
6. Always pair an `extract` script with a `validate` script.
7. Write any human-relevant ambiguities to
   `artifacts/<language>_review_notes.md`.
8. If the work has commentary or other per-unit editorial content,
   adopt the `maxims/`-style pattern: a `scaffold_*.py` that generates
   one Markdown file per editorial unit with frontmatter and named
   sections, a `check_*.py` that lints the corpus and reports drift
   against the canonical extraction, and (optionally) a disposable
   `build_site.py` for local preview. Keep all engine-specific
   rendering out of the source Markdown.
