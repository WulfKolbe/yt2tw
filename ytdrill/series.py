"""Series aggregation — turn per-video results into textscan-optimal plain text.

YTDRILL's job ends at plain text; the downstream chain is
``PYTHONPATH=$HOME/TEXTDRILL/src python3 -m textscan <file> --emit docmodel``
→ a PDFDRILL docmodel → a LaTeX projector (article / Beamer).

The whole point of this module is ``to_textscan_text``: textscan scores headings
from PLAIN-TEXT features, so a leading ``#`` and ``-``/``*`` bullets actively hurt
it (measured: 9/12 sections + 0 citations for raw markdown vs 12/12 + 3 for
plain text). We therefore normalise the Sonar markdown into bare title-case
heading lines, ``•`` bullets, kept inline ``[n]`` citations, and drop the BibTeX
block (not prose — it survives in the tiddler ``bibtex`` field for pdfdrill).

Pure/stdlib only — unit-tested, and the output is verified by running it back
through textscan in the test suite.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Callable

from .modules.base import Context

log = logging.getLogger("ytdrill")

_HEADING = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*#*\s*$")   # '## H' / '### H ###'
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")             # '- x' / '* x' / '+ x'
_BIBTEX_HEAD = re.compile(r"^\s*#{0,6}\s*bibtex\b", re.IGNORECASE)
_ANY_HEAD = re.compile(r"^\s*#{1,6}\s+")
_AT_ENTRY = re.compile(r"^\s*@[A-Za-z]+\s*\{")           # '@article{...'


def to_textscan_text(md: str) -> str:
    """Markdown summary/deck → textscan-optimal plain text.

    * heading ``#{1,6} X`` → bare ``X`` (title case, blank-surrounded → Section)
    * ``-``/``*``/``+`` bullet → ``• `` (dot bullet; textscan keeps these as
      ListItems without shredding citations)
    * inline numeric ``[n]`` citations preserved as-is
    * a ``BibTeX`` heading and everything under it (to the next heading / EOF),
      plus any stray ``@type{...}`` entry lines, are removed — not prose.
    """
    out: list[str] = []
    skip_bibtex = False
    for line in md.splitlines():
        if _BIBTEX_HEAD.match(line):            # enter a BibTeX section → drop it
            skip_bibtex = True
            continue
        if skip_bibtex:
            if _ANY_HEAD.match(line):           # a new heading ends the bibtex block
                skip_bibtex = False
            else:
                continue
        if _AT_ENTRY.match(line):               # stray '@article{' entry line
            continue
        h = _HEADING.match(line)
        if h:
            out.append(h.group(1).strip())
            continue
        b = _BULLET.match(line)
        if b:
            out.append(f"• {b.group(2).strip()}")
            continue
        out.append(line)
    # collapse 3+ blank lines to one blank (paragraph separation)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def _combine(series_title: str, videos: list[dict], field: str) -> str:
    """series title, then per video: the bare video title + normalised `field`,
    in the given order."""
    parts: list[str] = [series_title.strip(), ""]
    for v in videos:
        body = to_textscan_text(v.get(field, "") or "")
        parts.append(v.get("title", "").strip())
        parts.append("")
        parts.append(body)
        parts.append("")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(parts)).strip() + "\n"


def build_article_txt(series_title: str, videos: list[dict]) -> str:
    """The written-text source: title + each video's normalised summary, in order."""
    return _combine(series_title, videos, "summary")


def build_deck_txt(series_title: str, videos: list[dict]) -> str:
    """The Beamer source: title + each video's normalised slide outline, in order."""
    return _combine(series_title, videos, "deck")


# -- input & runner ---------------------------------------------------------
def expand_series_input(arg: str) -> tuple[list[str], str]:
    """Resolve ``--series ARG`` to ``(ordered watch URLs, default series name)``.

    A path to an existing file → its non-blank, non-``#`` lines (order kept),
    name = file stem. Otherwise ``arg`` is a playlist/URL → expanded via yt-dlp
    (flat, no download), name = the playlist title.
    """
    p = Path(arg).expanduser()
    if p.is_file():
        urls = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.lstrip().startswith("#")]
        return urls, p.stem

    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
            "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(arg, download=False)
    entries = info.get("entries") or [info]
    urls = [e.get("url") or e.get("webpage_url") or
            f"https://www.youtube.com/watch?v={e.get('id')}"
            for e in entries if e]
    name = info.get("title") or "series"
    return urls, name


def run_series(urls: list[str], *, series_name: str, workdir: Path,
               config: dict, registry: dict[str, type], want_asr: bool = False,
               run: Callable = None,
               log_fn: Callable[[str], None] | None = None) -> list[dict]:
    """Process each URL through ``run`` (default ``planner.run_plan``) into its
    own numbered sub-workdir, collecting ``{url,title,summary,deck}`` per video
    in order. Re-runnable: a video whose ``result.json`` cache exists is loaded,
    not re-run. A failing video is logged and skipped, not fatal.
    """
    if run is None:                       # late import avoids a planner import cycle
        from .planner import run_plan as run
    say = log_fn or (lambda m: log.info("%s", m))
    results: list[dict] = []
    for i, url in enumerate(urls, start=1):
        sub = Path(workdir) / f"{i:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        cache = sub / "result.json"
        if cache.is_file():
            say(f"SKIP [{i}/{len(urls)}] cached {url}")
            results.append(json.loads(cache.read_text(encoding="utf-8")))
            continue
        ctx = Context(url=url, workdir=sub, config=dict(config))
        try:
            run(ctx, registry, is_local=False, want_summary=True,
                want_slide_outline=True, want_asr=want_asr)
        except Exception as e:            # noqa: BLE001 — isolate one bad video
            say(f"FAIL [{i}/{len(urls)}] {url}: {e}")
            continue
        rec = {"url": url, "title": ctx.title,
               "summary": ctx.summary, "deck": ctx.deck_md}
        cache.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        say(f"OK   [{i}/{len(urls)}] {ctx.title}")
        results.append(rec)
    return results


def write_series_outputs(series_name: str, videos: list[dict],
                         outdir: Path) -> tuple[Path, Path]:
    """Write ``<name>.article.txt`` and ``<name>.deck.txt`` into ``outdir``;
    return their paths."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w.-]+", "_", series_name).strip("_") or "series"
    art = outdir / f"{slug}.article.txt"
    deck = outdir / f"{slug}.deck.txt"
    art.write_text(build_article_txt(series_name, videos), encoding="utf-8")
    deck.write_text(build_deck_txt(series_name, videos), encoding="utf-8")
    return art, deck
