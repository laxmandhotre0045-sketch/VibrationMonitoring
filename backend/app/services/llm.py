"""A minimal OpenAI chat client.

Written against urllib rather than adding httpx or the openai package, because
this makes one POST to one endpoint and a new runtime dependency is a poor
trade for that.

The important property is that **absence of a key is a supported state**, not
an error. Everything that calls this must work without a language model: the
platform's findings are produced by rule, and narration is a presentation
nicety. A deployment with no key, or with the API down, still gets its
analysis — it just gets it in the platform's own words.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from app.config import settings

log = logging.getLogger(__name__)

_ENDPOINT = "https://api.openai.com/v1/chat/completions"

#: Long enough for a paragraph from a small model, short enough that a hung
#: API cannot hold a dashboard request open. A summary is optional; a slow one
#: is worse than none.
_TIMEOUT_S = 30


def is_configured() -> bool:
    return bool(getattr(settings, "openai_api_key", ""))


def model_name() -> str:
    return getattr(settings, "openai_model", "") or "gpt-4o-mini"


def complete(system: str, user: str, *, max_tokens: int = 600,
             temperature: float = 0.0) -> Optional[str]:
    """One completion, or None if it could not be produced.

    None on every failure path — no key, network error, API error, malformed
    response — and never an exception. A caller deciding whether to show a
    generated paragraph should not have to catch four exception types to find
    out that it cannot.

    temperature defaults to 0: this narrates measurements, and a model that
    phrases the same findings differently on each refresh reads as instability
    in the data rather than in the prose.
    """
    if not is_configured():
        return None

    payload = json.dumps({
        "model": model_name(),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode("utf-8")

    request = urllib.request.Request(
        _ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.openai_api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:
            body: dict[str, Any] = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # The body carries the reason — a bad key, a rate limit, a model that
        # does not exist — and a bare status code would send someone hunting.
        detail = ""
        try:
            detail = exc.read().decode()[:300]
        except Exception:  # noqa: BLE001
            pass
        log.warning("LLM call failed: HTTP %s %s", exc.code, detail)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("LLM call failed: %s: %s", type(exc).__name__, exc)
        return None

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        log.warning("LLM response had no content: %s", str(body)[:200])
        return None
    return (text or "").strip() or None
