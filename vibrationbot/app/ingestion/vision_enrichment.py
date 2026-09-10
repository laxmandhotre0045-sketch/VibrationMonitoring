"""
Vision enrichment: use OpenAI's vision model to extract and caption the visual
elements of a document — figures, charts, diagrams, and tables — into the
knowledge base. Body text is left to the fast local extractor; only visual
content is routed through the LLM.

For each element the model produces search-oriented text that replaces the
placeholder ("Figure on page 12") or augments a rough local table extraction,
so these elements become findable by semantic search.

Robustness rules
----------------
* The OpenAI client is created with ``max_retries=0`` so it never blocks the
  pipeline with exponential-backoff sleeps. Transient errors are retried once
  manually; quota/auth errors abort enrichment immediately so the rest of the
  pipeline (FAISS indexing) still completes.
* A shared quota flag short-circuits all remaining calls the moment we hit a
  429 "insufficient_quota" error — sleeping cannot recover a depleted billing
  quota within a single run.
* Source pages are rendered in the main thread before the worker pool starts:
  PyMuPDF documents are not safe for concurrent access, so only the network
  calls run in parallel.
"""

from __future__ import annotations

import base64
import json
import logging
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from app.config import (
    ENABLE_VISION_ENRICHMENT,
    MIN_IMAGE_PX,
    OPENAI_API_KEY,
    VISION_CAPTION_WORKERS,
    VISION_ENRICH_FIGURES,
    VISION_ENRICH_TABLES,
    VISION_IMAGE_TOKEN_EST,
    VISION_MAX_ELEMENTS,
    VISION_MAX_RETRIES,
    VISION_MAX_TOKENS,
    VISION_IMAGE_DETAIL,
    VISION_MODEL,
    VISION_PAGE_RENDER_DPI,
    VISION_TABLE_ANCHOR_CHARS,
    VISION_TPM_HEADROOM,
    VISION_TPM_LIMIT,
)

logger = logging.getLogger(__name__)


class _TokenBucket:
    """Thread-safe token bucket that paces calls to a tokens-per-minute budget.

    Vision workers ``acquire`` their estimated token cost before each request;
    the bucket refills continuously at ``budget/60`` per second, so once a
    minute's worth of tokens is spent, further calls block until it refills.
    This keeps the aggregate request rate under the account's TPM limit, which
    is what stops the 429 storms — retries alone cannot, because the ceiling is
    a sustained-rate limit, not a transient one.
    """

    def __init__(self, tokens_per_min: float) -> None:
        self.capacity = max(1.0, tokens_per_min)
        # Start EMPTY, not full. A full bucket would release a burst of ~a
        # minute's worth of calls instantly before pacing engaged, and that
        # burst is exactly what clips the TPM ceiling. Starting empty makes
        # calls pace smoothly from the very first one.
        self.tokens = 0.0
        self.rate = self.capacity / 60.0
        self._lock = threading.Lock()
        self._last = time.monotonic()

    def acquire(self, cost: float) -> None:
        cost = min(max(1.0, cost), self.capacity)
        while True:
            with self._lock:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity, self.tokens + (now - self._last) * self.rate
                )
                self._last = now
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                wait = (cost - self.tokens) / self.rate
            time.sleep(min(max(wait, 0.05), 5.0))


def _make_token_bucket() -> _TokenBucket | None:
    if VISION_TPM_LIMIT <= 0:
        return None
    return _TokenBucket(VISION_TPM_LIMIT * VISION_TPM_HEADROOM)

FIGURE_PROMPT = """Describe this figure, chart, graph, or diagram from a technical document.
Include: chart/diagram type, axes labels, units, trends, key values, legends, and any visible text or numbers.
Be specific and factual. Output 3-6 sentences suitable for search retrieval."""

TABLE_PROMPT = """This image is a page from a technical document that contains a table.
A rough automatic extraction of the target table is provided below to help you locate it.

Reconstruct THAT table accurately as a clean GitHub-flavored Markdown table, then add a
short plain-language summary (2-3 sentences) of what the table contains, including the
quantities, units, and any thresholds or limits. Output the Markdown table first, then the
summary. Use only what is visible in the image.

Rough extraction of the target table:
---
{local_text}
---"""

TABLE_PROMPT_TEXT_ONLY = """Below is a roughly-extracted table from a technical document.
Reconstruct it as a clean GitHub-flavored Markdown table, then add a short plain-language
summary (2-3 sentences) of what it contains, including quantities, units, and any thresholds
or limits. Output the Markdown table first, then the summary.

Rough extraction:
---
{local_text}
---"""


# --------------------------------------------------------------------------
# Image helpers
# --------------------------------------------------------------------------


def _asset_to_data_url(image_path: Path) -> str | None:
    try:
        import io

        from PIL import Image

        with Image.open(image_path) as img:
            if img.width < MIN_IMAGE_PX or img.height < MIN_IMAGE_PX:
                return None
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
    except Exception as exc:
        logger.warning("Could not read image %s: %s", image_path, exc)
        return None


def _render_page_data_url(doc: Any, page_num: int, dpi: int) -> str | None:
    """Render a 1-indexed PDF page to a PNG data URL (main thread only)."""
    try:
        if page_num < 1 or page_num > doc.page_count:
            return None
        pix = doc[page_num - 1].get_pixmap(dpi=dpi)
        b64 = base64.standard_b64encode(pix.tobytes("png")).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception as exc:
        logger.warning("Could not render page %s: %s", page_num, exc)
        return None


def _vision_call(client: OpenAI, prompt: str, data_url: str | None) -> str:
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    if data_url:
        content.append(
            {
                "type": "image_url",
                # "low" keeps image tokens flat (~85) so image-heavy docs fit
                # under the account's tokens-per-minute limit.
                "image_url": {"url": data_url, "detail": VISION_IMAGE_DETAIL},
            }
        )
    response = client.chat.completions.create(
        model=VISION_MODEL,
        messages=[{"role": "user", "content": content}],
        max_tokens=VISION_MAX_TOKENS,
        temperature=0.1,
    )
    return (response.choices[0].message.content or "").strip()


# --------------------------------------------------------------------------
# Error classification (unchanged behaviour)
# --------------------------------------------------------------------------


def _error_code(exc: Exception) -> str:
    """Best-effort extraction of OpenAI's error 'code' across SDK shapes."""
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


def _is_quota_error(exc: Exception) -> bool:
    """Return True when the error is a billing/auth failure that won't recover."""
    import openai

    if isinstance(exc, openai.AuthenticationError):
        return True
    if isinstance(exc, (openai.RateLimitError, openai.APIStatusError)):
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            return True
        if status == 429:
            code = _error_code(exc)
            if code == "insufficient_quota":
                return True
            return "insufficient_quota" in str(exc)
    return False


_RETRY_AFTER_RE = re.compile(r"try again in ([0-9.]+)\s*(ms|s)", re.IGNORECASE)


def _retry_after_seconds(exc: Exception) -> float | None:
    """Extract a suggested wait from a 429, from header or message text."""
    resp = getattr(exc, "response", None)
    headers = getattr(resp, "headers", None)
    if headers:
        for key in ("retry-after-ms", "retry-after"):
            val = headers.get(key)
            if val:
                try:
                    seconds = float(val)
                    return seconds / 1000.0 if key.endswith("ms") else seconds
                except ValueError:
                    pass
    m = _RETRY_AFTER_RE.search(str(exc))
    if m:
        value = float(m.group(1))
        return value / 1000.0 if m.group(2).lower() == "ms" else value
    return None


def _call_with_retry(
    make_call: Callable[[], str], label: str, quota_flag: threading.Event
) -> str:
    """Run one vision call with backoff on transient errors.

    Quota/auth failures set ``quota_flag`` (shared across workers) and abort
    immediately — sleeping cannot recover a depleted billing quota. Everything
    else (rate-limit 429s, 500/503 server errors, timeouts) is retried. When the
    API returns a retry-after (tokens-per-minute limits do), that wait is
    honoured — plus jitter so retrying workers don't hit the limit in lockstep.
    """
    if quota_flag.is_set():
        return ""
    attempts = max(1, VISION_MAX_RETRIES)
    delay = 1.0
    for attempt in range(attempts):
        try:
            return make_call()
        except Exception as exc:
            if _is_quota_error(exc):
                if not quota_flag.is_set():
                    logger.warning(
                        "Vision enrichment stopped: OpenAI quota/auth error (%s). "
                        "Remaining elements will be skipped. "
                        "Check your billing at https://platform.openai.com/",
                        exc,
                    )
                quota_flag.set()
                return ""
            if attempt == attempts - 1:
                logger.warning(
                    "Vision call failed for %s after %d attempts: %s",
                    label,
                    attempts,
                    exc,
                )
                return ""
            # Honour the API's suggested wait when present (TPM limits give one),
            # else exponential backoff. Jitter avoids a synchronized retry storm.
            suggested = _retry_after_seconds(exc)
            base = max(delay, suggested) if suggested is not None else delay
            time.sleep(base + random.uniform(0, min(base, 2.0)))
            delay = min(delay * 2, 30.0)
            if quota_flag.is_set():
                return ""
    return ""


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------


def _source_pdf(doc_dir: Path) -> Path | None:
    src = doc_dir / "source.pdf"
    return src if src.exists() else None


def enrich_chunks(chunks_path: Path, doc_dir: Path) -> int:
    """Extract/caption figures, charts, diagrams, and tables via OpenAI.

    Returns the number of chunks enriched. Vision calls run concurrently
    (``VISION_CAPTION_WORKERS``); chunk order on disk is preserved. If the
    OpenAI key has no quota, emits one warning and finishes so the rest of the
    pipeline (sanitize + FAISS index) still completes.
    """
    if not ENABLE_VISION_ENRICHMENT:
        return 0
    if not OPENAI_API_KEY:
        logger.warning("Vision enrichment skipped: OPENAI_API_KEY not set")
        return 0
    if not chunks_path.exists():
        return 0

    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    # Pass 1 — collect job descriptors (no rendering yet, so tables dropped by
    # the cap below don't pay the page-render cost).
    figure_jobs: list[dict[str, Any]] = []
    table_jobs: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks):
        ctype = chunk.get("chunk_type", "")
        meta = chunk.get("meta") or {}
        if VISION_ENRICH_FIGURES and ctype in ("image", "diagram"):
            asset_rel = meta.get("asset_path", "")
            if asset_rel and (doc_dir / asset_rel).exists():
                figure_jobs.append(
                    {"idx": idx, "mode": "figure", "asset": doc_dir / asset_rel}
                )
        elif VISION_ENRICH_TABLES and ctype == "table":
            table_jobs.append(
                {
                    "idx": idx,
                    "mode": "table",
                    "page": int(chunk.get("page_start", 0) or 0),
                    "local_text": (chunk.get("text") or "").strip(),
                }
            )

    # Per-document cap: tables are prioritised over figures — a table is
    # structured data worth a call, whereas a catalog's thousands of incidental
    # figures are not. Skips are logged, never silent.
    total = len(table_jobs) + len(figure_jobs)
    if VISION_MAX_ELEMENTS > 0 and total > VISION_MAX_ELEMENTS:
        table_jobs = table_jobs[:VISION_MAX_ELEMENTS]
        figure_jobs = figure_jobs[: max(0, VISION_MAX_ELEMENTS - len(table_jobs))]
        kept = len(table_jobs) + len(figure_jobs)
        logger.warning(
            "Vision cap: %d visual element(s) exceed VISION_MAX_ELEMENTS=%d. "
            "Processing %d table(s) + %d figure(s); skipping %d. "
            "Raise VISION_MAX_ELEMENTS (or disable VISION_ENRICH_FIGURES for "
            "image-heavy catalogs) to cover more.",
            total,
            VISION_MAX_ELEMENTS,
            len(table_jobs),
            len(figure_jobs),
            total - kept,
        )

    # Pass 1b — render pages for the surviving table jobs (main thread only;
    # PyMuPDF documents are not safe for concurrent access).
    pdf_doc = None
    page_cache: dict[int, str | None] = {}

    def page_url(page_num: int) -> str | None:
        nonlocal pdf_doc
        if page_num in page_cache:
            return page_cache[page_num]
        if pdf_doc is None:
            src = _source_pdf(doc_dir)
            if not src:
                page_cache[page_num] = None
                return None
            import fitz

            pdf_doc = fitz.open(src)
        url = _render_page_data_url(pdf_doc, page_num, VISION_PAGE_RENDER_DPI)
        page_cache[page_num] = url
        return url

    try:
        for job in table_jobs:
            job["data_url"] = page_url(job["page"])
    finally:
        if pdf_doc is not None:
            pdf_doc.close()

    jobs = table_jobs + figure_jobs
    if not jobs:
        return 0

    quota_flag = threading.Event()
    bucket = _make_token_bucket()
    # max_retries=0 prevents the SDK from sleeping on 429s; retries are managed
    # above so the pipeline is never blocked by backoff waits.
    client = OpenAI(api_key=OPENAI_API_KEY, max_retries=0)

    def _estimate_tokens(prompt: str, has_image: bool) -> int:
        # Prompt chars/4 + reserved response + a flat per-image cost. Deliberately
        # generous so pacing errs under the TPM ceiling rather than over it.
        return (
            len(prompt) // 4
            + VISION_MAX_TOKENS
            + (VISION_IMAGE_TOKEN_EST if has_image else 0)
        )

    def _paced_call(prompt: str, data_url: str | None) -> str:
        if bucket is not None:
            bucket.acquire(_estimate_tokens(prompt, data_url is not None))
        return _vision_call(client, prompt, data_url)

    def run(job: dict[str, Any]) -> str:
        if job["mode"] == "figure":
            asset: Path = job["asset"]
            data_url = _asset_to_data_url(asset)
            if not data_url:  # unreadable image — never send a text-only figure
                return ""
            return _call_with_retry(
                lambda: _paced_call(FIGURE_PROMPT, data_url), asset.name, quota_flag
            )
        # table
        data_url = job["data_url"]
        local_text = job["local_text"] or "(no local extraction available)"
        template = TABLE_PROMPT if data_url else TABLE_PROMPT_TEXT_ONLY
        prompt = template.format(local_text=local_text[:VISION_TABLE_ANCHOR_CHARS])
        return _call_with_retry(
            lambda: _paced_call(prompt, data_url), f"table@idx{job['idx']}", quota_flag
        )

    workers = max(1, min(VISION_CAPTION_WORKERS, len(jobs)))
    logger.info(
        "Vision enrichment: processing %d element(s) (%d figure, %d table) with %d worker(s)",
        len(jobs),
        sum(1 for j in jobs if j["mode"] == "figure"),
        sum(1 for j in jobs if j["mode"] == "table"),
        workers,
    )
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run, jobs))

    # Pass 3 — merge back by original position.
    enriched = 0
    for job, result in zip(jobs, results):
        if not result:
            continue
        idx = job["idx"]
        chunk = chunks[idx]
        meta = chunk.get("meta") or {}
        if job["mode"] == "figure":
            existing = (chunk.get("text") or "").strip()
            chunk["text"] = f"{result}\n\n{existing}" if existing else result
            meta["vision_caption"] = result
        else:  # table
            # The vision transcription becomes the knowledge-base text; the
            # rough local extraction is kept in meta as a fallback/reference.
            local = (chunk.get("text") or "").strip()
            if local:
                meta.setdefault("local_table_text", local)
            chunk["text"] = result
            meta["vision_table"] = result
            meta.setdefault("table_markdown", result)
        chunk["meta"] = meta
        enriched += 1

    payload = "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks)
    chunks_path.write_text(payload + ("\n" if chunks else ""), encoding="utf-8")

    if quota_flag.is_set():
        logger.info(
            "Vision enrichment: %d element(s) processed before quota exhausted "
            "(set ENABLE_VISION_ENRICHMENT=false to skip entirely)",
            enriched,
        )
    else:
        logger.info("Vision enrichment: %d visual element(s) enriched", enriched)
    return enriched
