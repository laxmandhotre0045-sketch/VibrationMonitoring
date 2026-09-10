"""Shared OpenAI client helpers — fast-fail on quota/auth errors."""

from __future__ import annotations

from openai import OpenAI

from app.config import OPENAI_API_KEY


def make_openai_client() -> OpenAI:
    """OpenAI client with no SDK retries (avoids blocking on 429 backoff)."""
    return OpenAI(api_key=OPENAI_API_KEY, max_retries=0)


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        if isinstance(body.get("code"), str):
            return body["code"]
        inner = body.get("error")
        if isinstance(inner, dict) and isinstance(inner.get("code"), str):
            return inner["code"]
    return ""


def openai_error_message(exc: Exception) -> str | None:
    """Return a user-facing message for fatal OpenAI errors, else None."""
    import openai

    if isinstance(exc, openai.AuthenticationError):
        return (
            "OpenAI API key is invalid. Update OPENAI_API_KEY in .env with a key "
            "from https://platform.openai.com/api-keys"
        )
    if isinstance(exc, (openai.RateLimitError, openai.APIStatusError)):
        status = getattr(exc, "status_code", None)
        code = _error_code(exc)
        if status == 429 and (
            code == "insufficient_quota" or "insufficient_quota" in str(exc)
        ):
            return (
                "OpenAI billing quota exceeded. Add credits at "
                "https://platform.openai.com/settings/organization/billing "
                "and ensure your API key belongs to the project with credit."
            )
        if status == 429:
            return "OpenAI rate limit hit. Wait a moment and try again."
        if status in (401, 403):
            return (
                "OpenAI API access denied. Check OPENAI_API_KEY in .env matches "
                "your project at https://platform.openai.com/api-keys"
            )
    return None


def raise_openai_error(exc: Exception) -> None:
    """Re-raise fatal OpenAI errors as RuntimeError with a clear message."""
    msg = openai_error_message(exc)
    if msg:
        raise RuntimeError(msg) from exc
    raise exc


def retrieval_only_answer(question: str, chunks: list[dict]) -> str:
    """Format top retrieved chunks when GPT is unavailable."""
    if not chunks:
        return (
            "OpenAI is currently unavailable and no matching excerpts were found.\n\n"
            "Add credits at https://platform.openai.com/settings/organization/billing "
            "and update OPENAI_API_KEY in .env."
        )
    lines = [
        "OpenAI is currently unavailable — here are the most relevant document excerpts:",
        "",
    ]
    for chunk in chunks:
        section = chunk.get("section_path", "Unknown section")
        page = chunk.get("page_start", "?")
        text = chunk.get("text", "").strip()
        if len(text) > 400:
            text = text[:400] + "..."
        lines.append(f"• {section} (p.{page}): {text}")
    lines.extend(
        [
            "",
            "To get AI-generated answers, add OpenAI credits and restart the server.",
        ]
    )
    return "\n".join(lines)
