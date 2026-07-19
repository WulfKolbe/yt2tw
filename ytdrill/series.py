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

import re

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
