"""Vision captioning: what gets described, and the pacing that keeps it under quota."""

import os as _os

MIN_IMAGE_PX = int(_os.getenv("MIN_IMAGE_PX", "80"))

ENABLE_VISION_ENRICHMENT = _os.getenv("ENABLE_VISION_ENRICHMENT", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Which visual element types OpenAI extracts/describes into the knowledge base.
# Body text stays with the fast local extractor; these go through the vision
# model (VISION_MODEL).
VISION_ENRICH_FIGURES = _os.getenv("VISION_ENRICH_FIGURES", "true").lower() in (
    "1",
    "true",
    "yes",
)
VISION_ENRICH_TABLES = _os.getenv("VISION_ENRICH_TABLES", "true").lower() in (
    "1",
    "true",
    "yes",
)
# DPI for rendering a table's source page to an image before sending to vision.
VISION_PAGE_RENDER_DPI = int(_os.getenv("VISION_PAGE_RENDER_DPI", "150"))
# Image detail sent to the vision model. "low" charges a flat ~85 tokens per
# image (vs thousands for a full-res page), which is what lets an image-heavy
# doc's vision calls fit under a 200K tokens/min account. Tables still carry
# their local text extraction as an anchor, so low detail is a fine tradeoff.
# Set "high" on a higher usage tier for maximum table/figure fidelity.
VISION_IMAGE_DETAIL = _os.getenv("VISION_IMAGE_DETAIL", "low").lower()
# Concurrent vision requests during ingest. Each is an independent OpenAI call.
# Kept modest by default: low-tier accounts have a small concurrent-request cap
# and reject bursts with 503 "Too many concurrent requests". Raise it once the
# account tier allows more.
VISION_CAPTION_WORKERS = int(_os.getenv("VISION_CAPTION_WORKERS", "4"))
# Attempts per vision call before giving up (exponential backoff between them,
# honouring any retry-after the API returns). Covers transient 429/500/503s.
VISION_MAX_RETRIES = int(_os.getenv("VISION_MAX_RETRIES", "6"))
# Safety cap on vision calls per document (0 = unlimited). A large catalog can
# contain thousands of figures; captioning them all would blow the token/min
# limit and cost. When a document exceeds the cap, tables are prioritised over
# figures and the remainder is skipped (with a warning — never silently).
VISION_MAX_ELEMENTS = int(_os.getenv("VISION_MAX_ELEMENTS", "150"))
# Response token ceiling per vision call, and how much of the rough local table
# extraction to include as an anchor. Both bound per-call token usage so more
# calls fit under the tokens-per-minute limit.
VISION_MAX_TOKENS = int(_os.getenv("VISION_MAX_TOKENS", "550"))
VISION_TABLE_ANCHOR_CHARS = int(_os.getenv("VISION_TABLE_ANCHOR_CHARS", "1500"))
# Client-side pacing to the account's tokens-per-minute limit. Vision calls are
# throttled to stay under VISION_TPM_LIMIT * headroom so requests don't pile up
# against the ceiling and 429. Set VISION_TPM_LIMIT=0 to disable pacing.
VISION_TPM_LIMIT = int(_os.getenv("VISION_TPM_LIMIT", "200000"))
VISION_TPM_HEADROOM = float(_os.getenv("VISION_TPM_HEADROOM", "0.8"))
# Rough per-image token cost used for pacing (actual is model-dependent).
VISION_IMAGE_TOKEN_EST = int(_os.getenv("VISION_IMAGE_TOKEN_EST", "1100"))
