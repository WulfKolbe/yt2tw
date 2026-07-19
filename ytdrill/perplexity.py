"""Shared Perplexity Sonar client (stdlib urllib) — used by summarize and
slide_outline so the key resolution and HTTP shape live in one place.

Secret order (NEVER hardcode — the repo is public): env PERPLEXITY_API_KEY,
then a configured ``secret_cmd`` whose stdout is the key.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import urllib.request

API_URL = "https://api.perplexity.ai/chat/completions"

NO_SEARCH = ("IMPORTANT: Do NOT search the web. Do NOT search the internet. "
             "Do NOT retrieve any external sources or URLs. "
             "Use ONLY the transcript and description provided in the user message.")


def resolve_key(secret_cmd: str = "") -> str:
    key = os.environ.get("PERPLEXITY_API_KEY", "").strip()
    if key:
        return key
    if secret_cmd:
        out = subprocess.run(shlex.split(secret_cmd), capture_output=True,
                             text=True, check=True).stdout.strip()
        if out:
            return out
    raise SystemExit(
        "No Perplexity key: set PERPLEXITY_API_KEY or configure the module's "
        "secret_cmd (e.g. 'apivault get perplexity').")


def chat(key: str, model: str, system: str, user: str, *,
         max_tokens: int = 2048, temperature: float = 0.2,
         timeout: int = 300) -> str:
    """One Sonar chat completion; returns the assistant message content."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]
