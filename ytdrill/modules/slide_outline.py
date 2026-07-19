"""SlideOutline — a second Sonar pass over the TRANSCRIPT that produces a
frame-sized slide outline for the Beamer deck (independent of the prose summary,
so it distils from source rather than re-bulleting the summary).

Writes ``<bibkey>.deck.md`` + ``deck.md``, sets ``ctx.deck_md``, and attaches a
``deck-md`` tiddler field. The series aggregator normalises this markdown to
textscan-optimal plain text; here we keep it as markdown (the prompt asks for
`##` frame headings + `-` bullets) so a single video's deck is human-readable.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .base import BaseModule, Context, bibkey_of
from ..perplexity import NO_SEARCH, chat, resolve_key

log = logging.getLogger("ytdrill")

SYSTEM_MSG = ("You are an expert at distilling a talk into presentation slides. "
              + NO_SEARCH + " Turn the transcript into a terse, well-structured "
              "slide outline — headings and bullet points only, no prose.")


class SlideOutline(BaseModule):
    name = "slide_outline"

    def run(self, ctx: Context) -> None:
        if not ctx.transcript:
            log.warning("    empty transcript — skipping slide outline")
            return
        key = resolve_key(self.cfg.get("secret_cmd", ""))
        model = self.cfg.get("model", "sonar")
        howto = self._load_howto()
        user = (
            "IMPORTANT INSTRUCTION: Do not search the web. Use only the "
            "transcript and description text provided below.\n\n"
            f"## VIDEO TITLE\n{ctx.title}\n\n"
            f"## TRANSCRIPT\n{ctx.transcript}\n\n"
            f"## VIDEO DESCRIPTION\n{ctx.description}\n\n"
            f"## SLIDE INSTRUCTIONS\n{howto}"
        )
        out = chat(key, model, SYSTEM_MSG, user,
                   max_tokens=int(self.cfg.get("max_tokens", 2048)),
                   temperature=float(self.cfg.get("temperature", 0.2)))
        ctx.deck_md = out
        (ctx.workdir / "deck.md").write_text(out, encoding="utf-8")
        (ctx.workdir / f"{bibkey_of(ctx)}.deck.md").write_text(out, encoding="utf-8")
        extra = getattr(ctx, "extra_fields", None) or {}
        extra["deck-md"] = out
        ctx.extra_fields = extra  # type: ignore[attr-defined]
        log.info("    slide outline: %d chars (model=%s)", len(out), model)

    def _load_howto(self) -> str:
        p = Path(self.cfg.get("howto",
                              Path(__file__).parents[2] / "prompts" / "slides.md"))
        if p.is_file():
            return p.read_text(encoding="utf-8")
        log.warning("    slides template %s not found — using minimal default", p)
        return ("Produce a talk title, then frames: each a short Title-Case "
                "heading (`##`) with 2-6 terse `-` bullets. Keep key terms and "
                "equations. End with a `## References` frame of `[n]` sources. "
                "No prose, no BibTeX.")
