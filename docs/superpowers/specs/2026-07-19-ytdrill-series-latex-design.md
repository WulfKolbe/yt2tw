# YTDRILL series → article + deck Markdown (for TEXTRILL)

**Status:** approved design (2026-07-19)

## Goal

Turn a whole YouTube **series/playlist** into two Markdown documents that
TEXTRILL (a separate Markdown→LaTeX tool the user is building) converts into:

- a **written-text** LaTeX article, and
- a **Beamer** presentation.

YTDRILL produces Markdown only. It never emits LaTeX. TEXTRILL owns
Markdown→LaTeX for both outputs. This keeps a clean tool boundary.

Both outputs are **generated from the summaries** — no slide images. (The
existing `--slides` OCR feature is orthogonal and unused here.)

## Boundary / division of labour

```
playlist URL ──► YTDRILL ──► <series>.article.md  ──► TEXTRILL ──► article.tex
                        └──► <series>.deck.md     ──► TEXTRILL ──► beamer.tex
```

## Components

### 1. `slide_outline` module (new, per video)

A **second Sonar pass over the TRANSCRIPT** (independent of the prose summary,
so it's a faithful distillation from source, not a lossy re-bulleting of the
summary). Prompt template `prompts/slides.md`: emit one `##` heading per frame,
≤6 terse bullets each, preserve key equations/terms, no prose paragraphs.

- input: `ctx.transcript` (must exist — captions or, on the CLI, ASR fallback)
- output: sets `ctx.deck_md`; writes `<bibkey>.deck.md`; adds a `deck-md`
  field to the tiddler via the additive `ctx.extra_fields` contract
- config: `modules.slide_outline` (`model`, `max_tokens`, `temperature`,
  `howto: prompts/slides.md`), mirroring `summarize`
- **Naming:** `.deck.md` (not `.slides.md`) to avoid confusion with the OCR
  `<bibkey>_slides.pdf` from `--slides`. "deck" = presentation deck outline.

### 2. Lazy-planner integration

`run_plan` gains `want_slide_outline: bool = False`. When set, `slide_outline`
runs right after `summarize`/`extract_references` (it needs the transcript,
which the source layer already produced; it does NOT trigger any download).
`emit_tiddler` still closes the plan.

### 3. Playlist expansion + series runner (`ytdrill/series.py`)

- **Input:** `--series <arg>` accepts EITHER
  - a YouTube **playlist URL** → expanded via
    `yt_dlp.extract_info(url, download=False, process=False)` with
    `extract_flat` → ordered list of watch URLs + the playlist title, or
  - a **file** of URLs (one per line) → used verbatim, order preserved.
- **Series name:** `--series-name` overrides; else the playlist title (slugged)
  when expanding a playlist, else the file stem.
- **Run:** each video → its own `NN-<videoid>/` sub-workdir under the series
  workdir, via `run_plan(is_local=False, want_summary=True,
  want_slide_outline=True, want_asr=<--asr flag>)`. Re-runnable: a sub-workdir
  that already holds a tiddler is skipped (like `batch-testdata.sh`).
- **Failure isolation:** one video failing logs and continues; the aggregate is
  built from whatever succeeded, and missing videos are reported.

### 4. Aggregation (pure, in `ytdrill/series.py`)

From the per-video results (each: title, summary markdown, deck markdown,
bibtex entries, order index):

- `<series>.article.md`: `# <series title>`, then per video `## <video title>`
  + its summary body, in playlist order; ALL BibTeX entries merged and
  **de-duped by citekey** into a single trailing `## References` section.
- `<series>.deck.md`: `# <series title>`, then per video `## <video title>`
  + that video's frame outline, concatenated in order — a Beamer-ready Markdown.

These two pure builders (`build_article_md`, `build_deck_md`) are the unit-test
surface: given fake per-video dicts → exact combined Markdown, order preserved,
references merged/de-duped.

### 5. CLI

`python -m ytdrill --series <playlist-url|file> [--series-name NAME]
[--workdir DIR] [--asr]`

- with `--series`: expand → iterate → aggregate → print the two output paths.
- without `--series`: single-video, exactly as today (unchanged).
- `--asr` (default off for series to avoid Whisper on 18 videos; the user can
  opt in) toggles `want_asr` for the per-video runs.

## Testing (TDD)

- `build_article_md` / `build_deck_md`: pure, fully unit-tested (order, section
  headings, ref merge+dedup, empty-summary handling).
- playlist-vs-file input detection: unit-tested (a URL string vs an existing
  file path) — the yt-dlp expansion itself is not unit-tested (network).
- `slide_outline` prompt assembly: unit-tested; the Sonar call is not (network),
  same policy as `summarize`.

## Explicitly NOT in scope

- TEXTRILL itself, or any LaTeX generation inside YTDRILL.
- Slide-image Beamer frames (the user chose generated-from-summary).
- An auto-invoke `--textrill <cmd>` hook — deferred (YAGNI).

## The concrete first target

The user's playlist `PLIljB45xT85B0aMG-G9oqj-NPIuBMnq8z` (18 videos). Running it
is a post-implementation step (18 videos × 2 Sonar passes) done only on the
user's explicit go-ahead — not part of building the feature.
