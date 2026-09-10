# Vibration Analysis Assistant — Complete System Reference

Generated from the live codebase. Every value below was read from the running system,
not from memory.

**Status:** Phases 0, 1, 3 complete. Phase 2 (retrieval tuning + corpus expansion) and
Phase 4 (measurement intake) are **not built** — some configuration constants exist for
them but are not yet consumed. Those are marked **⚠ DECLARED, NOT WIRED** throughout.

---

## Table of contents

1. [What this system is](#1-what-this-system-is)
2. [Runtime stack and pinned versions](#2-runtime-stack-and-pinned-versions)
3. [Repository layout](#3-repository-layout)
4. [Complete configuration reference](#4-complete-configuration-reference)
5. [Domain layer — every hardcoded table](#5-domain-layer--every-hardcoded-table)
6. [RAG pipeline](#6-rag-pipeline)
7. [LangGraph orchestration](#7-langgraph-orchestration)
8. [API reference](#8-api-reference)
9. [Storage layout](#9-storage-layout)
10. [Test suite](#10-test-suite)
11. [Known limitations and not-built](#11-known-limitations-and-not-built)
12. [Operational runbook](#12-operational-runbook)

---

## 1. What this system is

A LangGraph chatbot for rotating-machinery vibration analysis, layered on a multimodal
document RAG over vibration standards and textbooks.

**Core design rule: an LLM never computes a number.** Bearing fault frequencies, ISO
severity zones, unit conversions, and fault ranking come from deterministic Python that
is unit-tested against published values. The model routes, retrieves, calls tools, and
explains. Every number in an answer carries the inputs and formula that produced it.

Three layers, deliberately separated:

| Layer | Package | Depends on |
|---|---|---|
| Deterministic vibration math | `app/domain/` | numpy only — **no LangChain, no OpenAI** |
| Orchestration | `app/chat/graph/` | LangGraph + the domain layer + retrieval |
| Document RAG | `app/ingestion/`, `app/retrieval/` | FAISS, sentence-transformers, OpenAI vision |

The domain layer is importable and testable with zero LLM plumbing. That is what makes
`scripts/vib_cli.py` possible and what keeps 185 of the 323 tests network-free by
construction rather than by mocking.

---

## 2. Runtime stack and pinned versions

Python 3.12, Windows, CPU-only, no Docker. Virtualenv at `.venv/`.

### Pinned in `requirements.txt`

```
fastapi==0.136.3                    uvicorn[standard]==0.49.0
python-multipart==0.0.32            python-dotenv==1.2.2
openai==2.41.0                      langchain-core==1.4.2
langchain-community==0.4.2          langchain-openai==1.2.2
langgraph==1.2.4                    langgraph-checkpoint-sqlite==3.1.0
sentence-transformers==5.5.1        faiss-cpu==1.14.2
pymupdf==1.27.2.3                   pdfplumber==0.11.9
docling==2.102.2                    python-docx==1.2.0
Pillow==12.2.0                      numpy==2.4.6
scipy==1.17.1                       pandas==3.0.3
matplotlib==3.11.0                  pydantic==2.13.4
pytest==9.1.0
```

Optional, commented out: `langchain-anthropic==1.4.0` (only for `LLM_PROVIDER=anthropic`).

### ⚠ Why the pins are load-bearing

`langchain-core==1.4.2` and `openai==2.41.0` **must not float**:

- `langgraph>=1.2.9` requires `langchain-core>=1.4.7`
- `langchain-openai>=1.3` requires `langchain-core>=1.4.9` **and `openai>=2.45.0`**
- `langchain-openai>=1.4` requires `langchain-core>=1.5.1`

An `openai` upgrade past 2.41 moves the SDK out from under the
`isinstance(exc, openai.AuthenticationError)` / `openai.RateLimitError` checks in
[app/llm/openai_utils.py](app/llm/openai_utils.py), which **silently disables
`ENABLE_RETRIEVAL_FALLBACK`** — quota errors would become 503s instead of degrading to
retrieval-only answers.

**After any change to `requirements.txt`:**
```bash
pip install --dry-run -r requirements.txt
```
Confirm `langchain-core` and `openai` do **not** appear in the "Would install" line.

Transitive pins installed alongside: `langgraph-checkpoint==4.1.1`,
`langgraph-prebuilt==1.1.0`, `langgraph-sdk==0.4.2`, `aiosqlite==0.22.1`,
`sqlite-vec==0.1.9`, `tiktoken==0.13.0`, `ormsgpack==1.12.2`, `websockets==15.0.1`
(downgraded from 16.0 by `langgraph-sdk`; compatible with uvicorn 0.49).

Also present as transitive deps: `torch==2.12.0`, `transformers==5.10.2`,
`huggingface-hub==1.18.0`, `rapidocr==3.8.4`, `opencv-python==4.13.0.92`.

---

## 3. Repository layout

```
vibrationbot/
├── .env                          LOCAL SECRETS — gitignored, never commit
├── .env.example                  template, 60+ documented variables
├── .gitignore                    protects .env, data/, logs/, *.pdf, *.sqlite
├── pytest.ini                    markers + "not live" default
├── requirements.txt              pinned, see §2
├── README.md                     user-facing quick start
├── SYSTEM.md                     this document
│
├── app/
│   ├── main.py                   FastAPI app factory, lifespan, /health
│   ├── api/
│   │   ├── routes_chat.py        POST /chat (graph|agent|simple)
│   │   └── routes_documents.py   upload / list / detail / chunks / assets
│   ├── config/                   54 env-backed constants, by topic — see §4
│   │   ├── paths.py              BASE_DIR + every data/log location
│   │   ├── llm.py, retrieval.py, vision.py, ingestion.py, chat.py
│   │   └── __init__.py           re-exports all of it flat
│   ├── schemas/
│   │   ├── documents.py          document / chunk / ingestion DTOs
│   │   └── chat.py               chat request + response DTOs
│   │
│   ├── domain/                   ★ DETERMINISTIC VIBRATION MATH (no LLM)
│   │   ├── bearing.py            BPFO/BPFI/BSF/FTF + geometry resolution
│   │   ├── iso10816.py           ISO 10816-3 / 20816-3 severity zones
│   │   ├── units.py              g / mm·s⁻¹ / µm / mil, rms / peak / pk-pk
│   │   ├── signatures.py         15-rule fault matcher + SpectralPeak
│   │   ├── machine.py            MachineProfile + derived forcing frequencies
│   │   ├── records.py            ComputationRecord audit trail
│   │   └── data/
│   │       ├── bearings.json     2 catalog entries + 59 boundary dimensions
│   │       ├── iso10816_3.json   4 groups × 2 foundations × 3 boundaries
│   │       └── fault_signatures.json   15 fault rules
│   │
│   ├── chat/                     ★ THE THREE CHAT MODES
│   │   ├── graph_rag_service.py  ★ graph_answer() — mode=graph entry
│   │   ├── agent_rag_service.py  legacy hand-rolled tool loop (unchanged)
│   │   ├── rag_service.py        legacy single-shot RAG (unchanged)
│   │   ├── sessions.py           in-memory LRU chat history
│   │   └── graph/                ★ LANGGRAPH ORCHESTRATION
│   │       ├── state.py          GraphState TypedDict + reducers
│   │       ├── prompts.py        all 8 prompt templates
│   │       ├── nodes.py          13 node functions + 6 routers
│   │       ├── build.py          StateGraph wiring, SqliteSaver, singletons
│   │       ├── tools_domain.py   5 domain tools (content_and_artifact)
│   │       └── tools_retrieval.py 3 retrieval tools + RetrievalContext
│   │
│   ├── ingestion/                DOCUMENT INGESTION
│   │   ├── ingest_service.py     upload + cross-process lock
│   │   ├── run_full_pipeline.py  6-step orchestrator
│   │   ├── docling_config.py     PDF classifier + Docling converter
│   │   ├── document_pdf_pipeline.py       PyMuPDF + pdfplumber (digital)
│   │   ├── document_multimodal_pipeline.py Docling (scanned/hybrid)
│   │   ├── vision_enrichment.py  VLM figure/table captioning
│   │   ├── filter_toc.py         TOC/noise chunk removal
│   │   ├── sanitize_section_path.py
│   │   └── progress.py           console step output for the CLIs
│   │
│   ├── retrieval/
│   │   ├── retrieval_service.py  hybrid scoring + cross-encoder rerank
│   │   ├── index_service.py      FAISS + chunk cache singleton
│   │   ├── faiss_index.py        FAISS build/load
│   │   └── embeddings.py         embedding model singleton
│   │
│   └── llm/
│       ├── provider.py           ★ get_chat_model(purpose) — the test seam
│       └── openai_utils.py       client factory + error classification
│
├── scripts/
│   ├── vib_cli.py                ★ domain tools from the command line
│   ├── rag_cli.py                ingest / ask / chat / list
│   ├── ingest_folder.py          batch ingest Input_Data/
│   ├── reindex_all.py            re-run pipeline over data/documents/*
│   ├── warmup.py
│   └── create_sample_pdf.py, create_sample_docx.py   (HR-template leftovers)
│
├── tests/                        323 tests, 14 files — see §10
│   ├── conftest.py               ingest-lock isolation
│   └── fake_llm.py               scriptable FakeChatModel
│
├── examples/P-101.json           sample machine profile
├── static/index.html             single-file UI, no build step
├── data/                         gitignored — see §9
└── logs/interactions.jsonl       one JSON line per chat turn
```

Roughly 7,900 lines of Python across `app/`, `scripts/`, `tests/`.

---

## 4. Complete configuration reference

All configuration lives in [app/config/](app/config/) and is read from
`.env` at import (`load_dotenv(override=True)` — `.env` beats stale shell variables).

**Legend:** ✅ active · ⚠ declared but not consumed by any code yet

### 4.1 Paths (derived, not env-configurable)

| Constant | Value | Status |
|---|---|---|
| `BASE_DIR` | repository root | ✅ |
| `DATA_DIR` | `<root>/data` | ✅ |
| `DOCUMENTS_DIR` | `<root>/data/documents` | ✅ |
| `LOGS_DIR` | `<root>/logs` | ✅ |
| `INTERACTION_LOG_PATH` | `<root>/logs/interactions.jsonl` | ✅ |
| `GRAPH_CHECKPOINT_PATH` | `<root>/data/graph_checkpoints.sqlite` | ✅ |
| `MACHINES_DIR` | `<root>/data/machines` | ✅ |

`MACHINES_DIR` is a **sibling** of `DOCUMENTS_DIR`, never a child. `index_service.list_ready_doc_ids()` and `ingest_service.list_documents()`
treat every subdirectory of `DOCUMENTS_DIR` as a document, so anything stored there
would surface as a failed document in the picker.

### 4.2 Models

| Variable | Default | Current `.env` | Status |
|---|---|---|---|
| `OPENAI_API_KEY` | `""` | *(set — REDACTED)* | ✅ |
| `OPENAI_MODEL` | `gpt-4o-mini` | `gpt-4o-mini` | ✅ |
| `VISION_MODEL` | `gpt-4o-mini` | `gpt-4o-mini` | ✅ |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | same | ✅ |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | same | ✅ |
| `LLM_PROVIDER` | `openai` | `openai` | ✅ graph mode only |
| `ANTHROPIC_API_KEY` | `""` | unset | ✅ |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | unset | ✅ |

`LLM_PROVIDER` affects **only** `mode=graph`. The legacy `agent` and `simple` modes
always use the raw OpenAI client in `openai_utils.py`.

### 4.3 Generation

| Variable | Default | Status | Notes |
|---|---|---|---|
| `DEFAULT_TOP_K` | `6` | ✅ | excerpts retrieved per query |
| `DEFAULT_TEMPERATURE` | `0.1` | ✅ | |
| `DEFAULT_MAX_TOKENS` | `1024` | ✅ | |
| `ENABLE_RETRIEVAL_FALLBACK` | `true` | ✅ | on quota/auth failure return excerpts, not 503 |

### 4.4 Per-purpose model settings

Hardcoded in [app/llm/provider.py](app/llm/provider.py) — **not
env-configurable**:

| Purpose | temperature | max_tokens | Used by |
|---|---|---|---|
| `classify` | 0.0 | 400 | `classify`, `rewrite` nodes |
| `grade` | 0.0 | 600 | `grade` node (excerpt relevance) |
| `verify` | 0.0 | 600 | `check_groundedness` node |
| `agent` | 0.1 | 1024 | `agent` node (tool calling) |
| `generate` | 0.1 | 1024 | `generate` node |
| `vision` | 0.1 | 1024 | `vision_answer` node |
| `chart` | 0.0 | 1200 | ⚠ Phase 4 chart reader |

`max_retries=0` is forced on every model. **This is not optional** — `ChatOpenAI`
defaults to 2, but `openai_utils.make_openai_client()` deliberately sets 0 so the
retrieval fallback fires immediately. With retries on, every quota error stalls ~30 s
before degrading.

`grade` and `verify` are separate purposes despite identical settings: they are
different jobs, may want different models later, and keeping them distinct is what lets
tests script one without accidentally answering the other.

### 4.5 Sessions

| Variable | Default | Status |
|---|---|---|
| `MAX_SESSION_TURNS` | `10` | ✅ turns retained per session |
| `MAX_SESSIONS` | `1000` | ✅ LRU cap, oldest evicted |

### 4.6 Retrieval

| Variable | Default | Status | Notes |
|---|---|---|---|
| `RETRIEVAL_CANDIDATE_K` | `30` | ✅ | candidates pulled **per document index** |
| `RERANK_POOL_K` | `48` | ✅ | **changed from 30** — candidates reaching the reranker |
| `RETRIEVAL_CANDIDATE_K_MULTI` | `15` | ⚠ Phase 2 | intended per-index K when >3 indexes |
| `RETRIEVAL_MULTI_DOC_THRESHOLD` | `3` | ⚠ Phase 2 | index count that triggers the above |

**Known scaling issue (Phase 2 work):** `_candidates_from_index` pulls
`max(RETRIEVAL_CANDIDATE_K, top_k*5)` candidates *per index*. At 2 documents that is 60,
comfortably under `RERANK_POOL_K=48`… at 8 documents it is 240, and everything past 48
is discarded ranked only by the crude hybrid score. Raising `RERANK_POOL_K` from 30 to
48 buys headroom; the proper fix is wiring `RETRIEVAL_CANDIDATE_K_MULTI`.

### 4.7 Chunking

| Variable | Default | Status |
|---|---|---|
| `MIN_CHUNK_CHARS` | `40` | ✅ TOC-filter minimum |
| `MIN_IMAGE_PX` | `80` | ✅ smallest extracted image edge |

The actual splitter is `_split_text(text, max_chars=900)` hardcoded in
[app/ingestion/document_pdf_pipeline.py:240](app/ingestion/document_pdf_pipeline.py#L240),
sentence-aware greedy packing with **zero overlap**, splitting on `(?<=[.!?])\s+`.

**Known issues, unfixed:** the regex splits after `Fig.`, `Eq.`, `Sec.`, `et al.`,
`0.5 in.`; zero overlap severs a derivation's premise from its conclusion; 900 chars
truncates worked examples. Changing this requires a full reindex, which re-pays every
vision call.

### 4.8 Vision enrichment

| Variable | Default | Current `.env` | Status |
|---|---|---|---|
| `ENABLE_VISION_ENRICHMENT` | `true` | `true` | ✅ |
| `VISION_ENRICH_FIGURES` | `true` | `true` | ✅ |
| `VISION_ENRICH_TABLES` | `true` | `true` | ✅ |
| `VISION_PAGE_RENDER_DPI` | `150` | **`120`** | ✅ |
| `VISION_IMAGE_DETAIL` | `low` | `low` | ✅ ~85 flat image tokens |
| `VISION_CAPTION_WORKERS` | `4` | `4` | ✅ |
| `VISION_MAX_RETRIES` | `6` | `6` | ✅ |
| `VISION_MAX_ELEMENTS` | `150` | `150` | ✅ **per-document cap** |
| `VISION_MAX_TOKENS` | `550` | — | ✅ |
| `VISION_TABLE_ANCHOR_CHARS` | `1500` | — | ✅ |
| `VISION_TPM_LIMIT` | `200000` | `200000` | ✅ |
| `VISION_TPM_HEADROOM` | `0.8` | **`0.7`** | ✅ |
| `VISION_IMAGE_TOKEN_EST` | `1100` | **`200`** | ✅ |

**⚠ `VISION_MAX_ELEMENTS=150` truncated the existing corpus.**
`data/documents/cat2/status.json` reports `enriched_figures: 150` against **1141
extracted assets** — roughly 1000 figures were never captioned, in a document whose
figures *are* the content. Tables are prioritised over figures when the cap is hit.
Real cost at `detail=low` is about **$0.15 per 400 elements**, so the cap is protecting
against a cost that does not exist. Raise it before ingesting image-heavy books.

Vision hardening (all in `vision_enrichment.py`): `_TokenBucket` paces to
`VISION_TPM_LIMIT × VISION_TPM_HEADROOM`, starting empty so a burst cannot fire;
`_call_with_retry` does exponential backoff with jitter honouring `retry-after`; a
shared `threading.Event` short-circuits all workers on `insufficient_quota`; pages are
rasterized on the main thread only, because PyMuPDF is not thread-safe.

### 4.9 Agent and graph bounds

| Variable | Default | Status | Bounds |
|---|---|---|---|
| `AGENT_MAX_ITERATIONS` | `4` | ✅ | tool-call loop, both agent and graph modes |
| `AGENT_SKIP_FINAL_CALL` | `true` | ✅ | legacy agent mode only |
| `GRAPH_MAX_REWRITES` | `1` | ✅ | retrieval-retry cycle |
| `GRAPH_MAX_REGENS` | `1` | ✅ | groundedness-retry cycle |

`RECURSION_LIMIT = 2 × AGENT_MAX_ITERATIONS + 16 = 24`, hardcoded in
[app/chat/graph/build.py](app/chat/graph/build.py).

### 4.10 Docling (scanned/hybrid PDFs only)

| Variable | Default | Purpose |
|---|---|---|
| `DOCLING_DO_OCR` | `false` | OCR is the main `std::bad_alloc` OOM source |
| `DOCLING_LIGHT_MODE` | `auto` | `auto` \| `true` \| `false` |
| `DOCLING_LARGE_PDF_MB` | `15.0` | light-mode trigger |
| `DOCLING_LARGE_PDF_PAGES` | `80` | light-mode trigger |
| `DOCLING_IMAGES_SCALE` | `1.0` | |
| `DOCLING_DOCUMENT_TIMEOUT` | `600.0` | seconds |
| `DOCLING_NUM_THREADS` | `2` | memory bounding |
| `DOCLING_PAGE_BATCH` | `10` | pages per conversion window |
| `DOCLING_QUEUE_MAX` | `4` | |
| `DOCLING_LAYOUT_BATCH` | `4` | |
| `DOCLING_TABLE_BATCH` | `4` | |
| `DOCLING_OCR_BATCH` | `2` | |
| `DOCLING_MIN_PAGE_COVERAGE` | `0.5` | below this, fall back to PyMuPDF |

### 4.11 PDF classification

| Variable | Default | Purpose |
|---|---|---|
| `PDF_CLASSIFY_SAMPLE` | `12` | pages sampled evenly across the document |
| `PDF_CLASSIFY_MIN_CHARS` | `100` | chars for a page to count as "has text" |
| `PDF_DIGITAL_THRESHOLD` | `0.8` | `text_ratio ≥` → digital (PyMuPDF, no OCR) |
| `PDF_SCANNED_THRESHOLD` | `0.15` | `text_ratio ≤` → scanned (Docling + OCR) |
| `PDF_TABLE_WORKERS` | `8` | pdfplumber process pool |
| `PDF_TABLE_PARALLEL_MIN_PAGES` | `40` | below this, process startup outweighs the saving |
| `DIGITAL_PDF_USE_DOCLING` | `false` | route digital PDFs through Docling instead |
| `SUPPORTED_EXTENSIONS` | `{.pdf, .docx}` | hardcoded |

Anything between the two thresholds is `hybrid` → Docling with OCR on image pages only.

**⚠ Margin risk:** the un-ingested `rolling-bearing-analysis` PDF measures
`text_ratio = 0.83` against a `0.80` threshold, sampled from 12 pages. One plate-heavy
page landing in the sample flips it to `hybrid` → Docling + OCR over 1105 pages → hours,
or an OOM. Mitigation (not built): a `--force-kind` flag on `run_full_pipeline`.

---

## 5. Domain layer — every hardcoded table

### 5.1 `bearing.py` — fault frequencies

**Formulas.** With `fr = RPM/60`, `n` elements, `d` element diameter, `D` pitch
diameter, `θ` contact angle, and `r = (d/D)·cos θ`:

| Output | Formula | Meaning |
|---|---|---|
| **BPFO** | `(n/2)(1 − r)·fr` | ball pass frequency, outer race |
| **BPFI** | `(n/2)(1 + r)·fr` | ball pass frequency, inner race |
| **BSF** | `(D/2d)(1 − r²)·fr` | ball spin frequency |
| **2×BSF** | `2 × BSF` | what actually appears in a spectrum |
| **FTF** | `(1/2)(1 − r)·fr` | fundamental train (cage) frequency |

**Invariant:** `BPFO + BPFI == n·fr` exactly, for any geometry. Property-tested over 25
random geometries; it catches sign and factor errors instantly.

All four are irrational multiples of running speed — **non-synchronous** — which is the
first thing distinguishing a bearing defect from unbalance or misalignment.

**Bundled catalog** (`app/domain/data/bearings.json`) — only bearings with published,
widely cross-checked internal geometry:

| Designation | n | ball dia (mm) | pitch dia (mm) | angle | Source |
|---|---|---|---|---|---|
| `6203` | 8 | 6.7462 | 28.4988 | 0° | SKF 6203-2RS JEM |
| `6205` | 9 | 7.94 | 39.04 | 0° | SKF 6205-2RS JEM |

**This is deliberately tiny.** Filling it with plausible-looking geometry for other
bearings would produce confidently wrong fault frequencies — a wrong ball count shifts
BPFO by ~11%. To add one properly, take `n_balls` / `ball_dia_mm` / `pitch_dia_mm` from
the manufacturer's drawing or an analyser's bearing database and cite it in `note`.

**Boundary dimensions** (ISO 15 standard, bore/OD/width in mm) — used by the estimator
only. Series `60` (13 sizes), `62` (20), `63` (20), `64` (6) = **59 entries**.

**Estimator constants** (hardcoded in `bearing.py`, deep-groove ball bearings only):

```
_BALL_DIA_FRACTION  = 0.30      ball_dia  ≈ 0.30 × (OD − bore)
_BALL_COUNT_DIVISOR = 1.65      n_balls   ≈ (π × D / d) / 1.65
                                pitch_dia ≈ (bore + OD) / 2
```

Calibrated against 6203 and 6205 (exact on both) and cross-checked against published
6308 (exact) and 6312 (off by one ball). Accuracy: ~3% on ball diameter, ~1.5% on pitch
diameter, ±1 on ball count.

**Geometry resolution — strict tier order, catalog first, RAG never first:**

| Tier | Source | `source` | `confidence` |
|---|---|---|---|
| 0 | Explicit user geometry (n, d, D) | `user` | 1.0 |
| 1 | Bundled catalog | `catalog` | 1.0 |
| 2 | Estimator from boundary dimensions | `estimated` | **0.6** + assumption string |
| 3 | *(designed, not built)* RAG over bearing catalogues | `retrieved` | 0.4 |
| 4 | Return `None` → the tool asks the user | — | — |

A rerank miss must never be able to change a fault frequency. Roller bearings
(`22312`, `NU312`, `32210`) return `None` rather than receiving ball-bearing geometry.

**Designation normalization.** Strips manufacturer prefixes
(`SKF|FAG|NSK|NTN|KOYO|TIMKEN|INA|NACHI|ZKL|SNR|MRC|RHP`) and repeatedly strips
seal/shield/clearance suffixes (`2RS|RS|2Z|ZZ|Z|2RSR|RSR|N|NR|M|E|EM|TN9|C0–C5|P0–P6|J|JEM`).
`"SKF 6205-2RS1/C3"` → `"6205"`.

**ISO 15 bore code → bore (mm):** `00→10`, `01→12`, `02→15`, `03→17`, then
`code × 5` for codes 04–96.

**Standing assumption on every result:** *"Pure rolling contact, no sliding or slip.
Real bearings slip by 1–2%, so measured defect frequencies sit slightly below these
values — match peaks within about ±1.5%, not exactly."*

### 5.2 `iso10816.py` — severity zones

**Complete velocity boundary table** (mm/s RMS, 10–1000 Hz, non-rotating parts):

| Group | Description | Foundation | A/B | B/C | C/D |
|---|---|---|---|---|---|
| **1** | Large machines, 300 kW–50 MW; electrical H ≥ 315 mm | rigid | 2.3 | 4.5 | 7.1 |
| **1** | | flexible | 3.5 | 7.1 | 11.0 |
| **2** | Medium, 15–300 kW; electrical 160 ≤ H < 315 mm | rigid | 1.4 | 2.8 | 4.5 |
| **2** | | flexible | 2.3 | 4.5 | 7.1 |
| **3** | Pumps, multivane impeller, **separate** driver, >15 kW | rigid | 2.3 | 4.5 | 7.1 |
| **3** | | flexible | 3.5 | 7.1 | 11.0 |
| **4** | Pumps, multivane impeller, **integrated** driver, >15 kW | rigid | 1.4 | 2.8 | 4.5 |
| **4** | | flexible | 2.3 | 4.5 | 7.1 |

Groups 1 and 3 share limits; Groups 2 and 4 share limits.

**Boundary convention:** a value exactly **on** a boundary belongs to the **lower** zone.
`2.80 → B`, `2.81 → C`. Tested from both sides on all 8 rows.

**Zone meanings and actions:**

| Zone | Meaning | Action | Urgency |
|---|---|---|---|
| **A** | Typical of newly commissioned machines | No action | `informational` |
| **B** | Acceptable for unrestricted long-term operation | Continue routine monitoring | `monitor` |
| **C** | Unsatisfactory for long-term continuous operation | Limited-period operation only; investigate, plan remedial action, increase monitoring frequency | `scheduled` |
| **D** | Severe enough to cause damage | Do not continue operating; shut down and correct | `immediate` |

**Standards mapping:** `10816-3` → `ISO 10816-3:2009`; `20816-3` → `ISO 20816-3:2022`.
Same velocity limits, different citation.

**Group inference** (`infer_machine_group`), in order:
1. `"pump"` in machine type → Group **4** if integrated driver, else **3**
2. `power_kw > 300` → **1**; `power_kw > 15` → **2**; `≤ 15` → `None` (outside scope)
3. `shaft_height_mm ≥ 315` → **1**; `≥ 160` → **2**
4. Otherwise `None` → the tool asks

**Why hardcoded, not retrieved:** these numbers are the maintenance decision. A
retrieval miss or a reranker reordering must never flip a Zone C verdict to Zone B. The
ingested standard supplies the prose the answer cites; this table supplies the verdict.

**`displacement_zone()` raises `NotImplementedError` on purpose.** ISO 10816-3 also
tabulates displacement limits in µm for Groups 1 and 2; those columns have not been
transcribed, and writing them from memory is exactly the failure this module exists to
prevent.

### 5.3 `units.py` — amplitude conversion

**Physical constants:**
```
G_TO_MM_S2 = 9806.65     standard gravity, mm/s²
UM_PER_MIL = 25.4        1 mil = 25.4 µm
peak       = √2 × rms
pk-pk      = 2 × peak
```

**Supported units and their quantities:**

| Unit | Quantity | To canonical |
|---|---|---|
| `g` | acceleration | × 9806.65 → mm/s² |
| `m/s2` | acceleration | × 1000 → mm/s² |
| `mm/s` | velocity | × 1 |
| `in/s` | velocity | × 25.4 → mm/s |
| `um` | displacement | × 1 |
| `mm` | displacement | × 1000 → µm |
| `mil` | displacement | × 25.4 → µm |

**Aliases accepted:** `gs`, `m/s^2`, `ms2`, `mms`, `ips`, `micron(s)`, `mils`;
measures `pk`, `0-pk`, `zero-peak`, `pkpk`, `p-p`, `pp`, `peak-peak`, `peaktopeak`.

**Conversion relations** (ω = 2πf): `a_pk = ω·v_pk = ω²·d_pk`

Cross-quantity conversion **requires** `frequency_hz > 0` and raises `ValueError`
without it. Same-quantity conversion (g → m/s², rms → peak) does not.

**Confidence:** 1.0 for same-quantity, **0.8** for cross-quantity, which always attaches
the warning that the relation is exact only for a single sinusoid at that frequency —
broadband integration must be done in the frequency domain.

**Verified reference values:** `1.0 g rms @ 100 Hz = 15.61 mm/s rms`;
`1.0 g peak @ 100 Hz = 11.04 mm/s rms`; `2 mil pk-pk = 50.8 µm pk-pk`.

### 5.4 `signatures.py` — fault matching

**Scoring constants** (hardcoded):

```
SYNCHRONOUS_TOLERANCE = 0.02    |order − round(order)| < this → synchronous
DOMINANCE_THRESHOLD   = 0.85    a "dominant" order must reach 85% of the largest peak
NO_AXIAL_PENALTY      = 0.55    multiplier for axial-signature faults with no axial data
```

**Scoring formula:**
```
score = (Σ matched weight − 0.5 × Σ contradicting weight × relative amplitude)
        / Σ available weight
```
clamped to [0, 1]. A missing **dominant** or **required** order **disqualifies** the
rule outright.

The contradicting term is scaled by the contradicting peak's amplitude relative to the
largest peak. Without that scaling, a normal weak 2× alongside a dominant 1× penalised
unbalance enough to rank it below rules that merely list fewer contradictions.

**Role semantics:**

| Role | Meaning |
|---|---|
| `dominant` | must be present AND ≥ 85% of the largest peak |
| `required` | must be present |
| `supporting` | adds evidence when present, costs nothing when absent |
| `contradicting` | subtracts evidence when present, scaled by relative amplitude |

**Confidence:** `score × min(confidence of all matched peaks)`. A hypothesis built on
VLM-read chart values can therefore never be reported as firmly as one from a computed
waveform.

**Dynamic order references**, resolved from machine context at match time. A rule whose
reference cannot be resolved is **skipped**, not guessed — a machine with no gearbox
never receives a gear-mesh hypothesis:

`@bpfo` `@bpfi` `@bsf` `@bsf2x` `@ftf` `@gmf` `@vane_pass` `@blade_pass`
`@line_2x` `@belt`, each optionally suffixed `*N` (e.g. `@bpfo*2`).

**All 15 rules:**

| Key | Name | Signature (orders) | Tolerance |
|---|---|---|---|
| `unbalance` | Unbalance | **1×** dominant; contra 0.5×, 1.5×, 2×, 3× | ±0.04 |
| `misalignment_parallel` | Parallel (offset) misalignment | **2×** dominant, 1× required, 3× supporting | ±0.04 |
| `misalignment_angular` | Angular misalignment | 1× + 2× required, **axial** | ±0.04 |
| `bent_shaft` | Bent shaft | **1×** dominant + 2×, **axial** | ±0.04 |
| `mechanical_looseness` | Mechanical looseness | **0.5×** required + 1×…5× series | ±0.04 |
| `structural_looseness` | Structural looseness / soft foot | **1×** dominant + 2×, 3×; contra 0.5×, 1.5×, 2.5× | ±0.04 |
| `bearing_outer_race` | Bearing — outer race defect | **@bpfo** dominant + 2×, 3× harmonics | ±1.5% |
| `bearing_inner_race` | Bearing — inner race defect | **@bpfi** dominant, 1× sidebands | ±1.5% |
| `bearing_ball_defect` | Bearing — rolling element defect | **@bsf2x** dominant, @ftf sidebands | ±1.5% |
| `bearing_cage` | Bearing — cage damage | **@ftf** dominant | ±2.0% |
| `gear_mesh` | Gear mesh / tooth defect | **@gmf** dominant + harmonics, 1× sidebands | ±1.0% |
| `blade_vane_pass` | Blade / vane pass | **@vane_pass** dominant + 2× | ±1.0% |
| `electrical` | Electrical fault | **@line_2x** dominant | ±0.5% |
| `oil_whirl` | Oil whirl (journal bearing) | **0.43×** dominant | ±0.06 |
| `belt_drive` | Belt drive fault | **@belt** dominant + 2×, 3× | ±2.0% |

Every rule carries a `mechanism` paragraph, 2–3 `confirming_checks`, and a `query_hint`
used to retrieve the textbook passage that explains it.

**Physical gating:** `oil_whirl` is excluded unless `has_journal_bearings`; all
`bearing_*` rules are excluded unless `has_rolling_bearings`.

**Bearing cross-check** (`cross_check_bearing_peaks`, ±1.5%): matches non-synchronous
peaks against computed BPFO/BPFI/BSF/FTF and labels them. This is the join between
computed geometry and observed data — it turns "an unexplained peak at 3.58×" into
"BPFO for the fitted bearing, within 0.4%". It is the single most diagnostic behaviour
in the system.

**`SpectralPeak` is the pivot of the whole design:**
```python
frequency_hz, amplitude, order, direction (H|V|A|""),
sidebands_hz, label, source (waveform|chart_vlm|user), confidence
```
Peaks computed from a waveform and peaks read off an analyser screenshot produce **the
same structure**, differing only in `source` and `confidence`. Every downstream
consumer therefore works identically whichever way the data arrived.

### 5.5 `machine.py` — asset profile and forcing frequencies

**Validation:** `MACHINE_ID_RE = ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$` — `machine_id`
becomes a directory name, so path traversal is rejected.

**Profile schema:**
```
MachineProfile
├── machine_id, name, type, foundation (rigid|flexible), iso_group, notes
├── Driver:   kind, power_kw, poles, line_freq_hz, rated_rpm, vfd, shaft_height_mm
├── Driven:   kind, rated_rpm, n_vanes, n_blades, integrated_driver
├── Coupling: kind (direct|belt|gear|fluid), ratio,
│             belt_length_mm, driver_sheave_dia_mm, driven_sheave_dia_mm
├── Gearbox:  stages[{teeth_in, teeth_out, name}]
├── bearings[]: position, designation, shaft (driver|driven),
│               n_balls, ball_dia_mm, pitch_dia_mm, contact_angle_deg,
│               kind (rolling|journal)
└── points[]:   point_id, location, direction (H|V|A), sensor, mount
```

**Every field is optional.** Each additional field switches on the frequencies that
depend on it; a profile with nothing but a speed still yields 1×/2×/3×, and an empty
profile returns `{}` rather than raising.

**Derived forcing frequencies** (`derived_frequencies`):

| Key | Formula |
|---|---|
| `1x` `2x` `3x` | `n × driver_rpm/60` |
| `driven_1x` | driven shaft rate, emitted only when it differs from the driver |
| `vane_pass` | `n_vanes × driven_hz` |
| `blade_pass` | `n_blades × driven_hz` |
| `gmf_stage{i}` | `teeth_in × that stage's input rate` |
| `line_2x` | `2 × line_freq_hz` — **pinned to the supply, not shaft speed** |
| `pole_pass` | `slip_hz × poles`, where `slip_hz = (120·f/poles − rpm)/60` |
| `belt` | `π × driver_sheave_dia × driver_hz / belt_length` |
| `bpfo` `bpfi` `bsf` `bsf2x` `ftf` | per bearing position, prefixed when several exist |

**Orders are always expressed against the driver shaft**, because that is what a
tachometer on the motor reports and what an analyser normalises to.

**Speed precedence:** measured `actual_rpm` > user-stated `shaft_rpm` > nameplate
`rated_rpm`. Fault frequencies scale with true running speed, and an induction motor
under load runs a few percent below rating — enough to miss a ±1.5% bearing match.

**Storage:** `data/machines/{machine_id}/profile.json`, written via write-to-temp then
`replace()` so a crash mid-write cannot leave an unparseable profile. Thread-locked.

### 5.6 `records.py` — the audit trail

```python
ComputationRecord:
  id                    "C1", "C2", ... assigned by the graph
  tool                  which tool produced this
  inputs                every input, so the arithmetic can be redone by hand
  outputs               the computed values
  formula               the formula in text
  formula_source        FormulaSource(kind, ref, query_hint)
  assumptions           surfaced in the answer's "Assumptions" line
  confidence            1.0 = exact given the inputs
  supporting_chunk_id   filled by the ground_computations node
  supporting_doc_id
```

`FormulaSource.query_hint` is a **retrieval query, not a citation**. The graph runs it
against the corpus to find the passage that explains the formula, so a computed value
cites two things: the tool that produced it, and the textbook that defines it.

---

## 6. RAG pipeline

### 6.1 Ingestion — 6 steps

`run_full_pipeline.py` orchestrates:

1. **Classify** (`docling_config.classify_pdf`) — sample 12 pages evenly, compute
   `text_ratio` → `digital` / `scanned` / `hybrid`. Includes garbled-ToUnicode detection
   and a "single raster image covering >85% of the page" scanned check.
2. **Extract** — routed by kind:

   | Kind | Extractor | OCR |
   |---|---|---|
   | `digital` | PyMuPDF + pdfplumber | none |
   | `digital` + `DIGITAL_PDF_USE_DOCLING=true` | Docling | `force_ocr=False` |
   | `scanned` / `hybrid` | Docling | `force_ocr=True` |
   | `.docx` | Docling, falling back to `python-docx` | — |

3. **Filter TOC** (`filter_toc.py`) — drops dot-leader lines (>40% of lines),
   "table of contents/index" chunks under 200 chars, and page-number-only chunks;
   minimum `MIN_CHUNK_CHARS=40`.
4. **Sanitize section paths** (`sanitize_section_path.py`) — collapse whitespace,
   dedupe consecutive segments, strip a leading `CHAPTER n >`.
5. **Vision enrichment** (`vision_enrichment.py`) — see §6.3.
6. **Index** (`faiss_index.py`) — build FAISS, save to disk.

Table extraction runs in a `ProcessPoolExecutor` (`PDF_TABLE_WORKERS=8`) because
pdfplumber is pure-Python and CPU-bound, so threads would serialize on the GIL.

Docling converts in bounded 10-page sub-PDF windows with a `DegenerateExtraction` guard
against mass OOM producing empty output.

### 6.2 Chunk types

`clause` · `section_summary` · `chapter_summary` · `table` · `image` · `diagram`

Live distribution:

| doc_id | total | clause | table | image | section | chapter |
|---|---|---|---|---|---|---|
| `cat2` | 1841 | 1664 | 66 | 84 | 26 | 1 |
| `condition_monitoring` | 1766 | 1689 | 19 | 52 | 5 | 1 |

### 6.3 What makes it "multimodal"

**VLM-captioning-to-text — there is no CLIP and no image embedding.** Figures and
tables are turned into English prose by the vision model and embedded in the *same*
text vector space as everything else. One unified index.

- **Figures** → the extracted asset PNG is sent; the caption is **prepended** to the
  existing text and stored in `meta.vision_caption`.
- **Tables** → the whole source page is rasterized at `VISION_PAGE_RENDER_DPI` and sent,
  anchored by the rough pdfplumber extraction. The caption **replaces** the text
  entirely; the original is preserved in `meta.local_table_text`, and
  `meta.vision_table` / `meta.table_markdown` are set.

A fourth mechanism operates at answer time: retrieved `image`/`diagram` chunks have
their actual PNG bytes base64-attached to the final synthesis call (`vision_answer`
node in graph mode, `_final_answer_with_vision` in agent mode).

### 6.4 Embeddings

- **`BAAI/bge-small-en-v1.5`**, 384 dimensions, HuggingFace sentence-transformers
- **CPU only**, normalized embeddings
- BGE query instruction prefix: `"Represent this sentence for searching relevant passages: "`
- Global singleton behind a `threading.Lock`, warm-loaded at FastAPI startup

### 6.5 Vector store

- **FAISS `IndexFlatL2`**, 384-dim, L2 metric, exhaustive brute force (no IVF/HNSW/PQ)
- **One index per document** at `data/documents/{doc_id}/faiss_index/`
  (`index.faiss` + `index.pkl`). There is no collection concept; `doc_id` is the unit.
- Live: `cat2` = 1841 vectors, `condition_monitoring` = 1766 vectors
- `IndexService` is a lock-guarded singleton caching FAISS objects and
  `{chunk_id: chunk}` maps, with a 5-second TTL on the ready-document listing

Metadata written per vector: `chunk_id, chunk_type, page_start, page_end, section_path,
node_id, doc_id, asset_path`, plus every remaining `meta` key.

**Why per-document rather than one unified index:** `retrieve_across_documents` already
merges and reranks once on the merged pool; per-document gives free incremental
re-ingest, per-document cache invalidation, and `doc_ids` filtering with no
metadata-filter machinery. At ~8 documents that is roughly 30k × 384 floats ≈ 46 MB and
~15 ms of serial search — a rounding error next to the ~900 ms rerank. Revisit past
~25 documents / ~200k vectors.

### 6.6 Retrieval scoring

**There is no LangChain retriever object.** No MMR, no `ParentDocumentRetriever`, no
`MultiVectorRetriever`, no BM25. Everything is explicit in `retrieval_service.py`.

Per index, candidates = `max(RETRIEVAL_CANDIDATE_K, top_k × 5)` = `max(30, 5·top_k)`:

```
vector_score = 1.0 / (1.0 + L2_distance)
kw_score     = |query keywords present in text| / |query keywords|
type_boost   = +0.12
combined     = 0.7 × vector_score + 0.3 × kw_score + type_boost
```

`type_boost` fires **+0.12** for:
- `table` chunks when the query contains any of:
  `table, row, column, value, values, data, cell, cells`
- `image` / `diagram` chunks when the query contains any of:
  `chart, graph, figure, diagram, plot, image, picture, visual, trend, axis, axes`

**⚠ Known gap (Phase 2):** these signal words are generic English. **No vibration term**
(`spectrum`, `waterfall`, `cascade`, `orbit`, `bode`, `nyquist`, `envelope`, `fft`,
`waveform`, `polar`) triggers the figure boost.

**⚠ Known gap (Phase 2):** `_extract_keywords` uses `re.findall(r"[a-zA-Z0-9]+", ...)`
and drops tokens of length ≤ 2. It therefore discards `1x`, `2x`, `Hz`, `mm`, `g`, `dB`,
and shreds `mm/s` → `{mm, s}`, `10816-3` → `{10816, 3}`, `4.5` → `{4, 5}`. The keyword
half of the hybrid score is effectively blind to this domain's vocabulary. 105 stopwords
are filtered.

**Full retrieval flow:**
```
embed query once (reused across indexes when >1)
  → per-index FAISS top-max(30, 5·top_k)
  → hybrid rescore + type boost
  → merge across documents
  → sort by hybrid_score
  → dedupe: identity (doc_id, chunk_id), then normalized text
  → CrossEncoder rerank the top RERANK_POOL_K=48
  → return top_k
```

The per-index loop is **intentionally serial**: FAISS search is ~7 ms across 24 indexes
while the rerank is ~900 ms — over 99% of retrieval time. Speed up by shrinking
`RERANK_POOL_K`, not by parallelising search.

**Two-level dedupe** exists because `chunk_id` restarts at `chunk_000001` in every
document, so the identity key must include `doc_id`; and the same passage often exists
in several indexed documents (re-uploads, overlapping editions), so equal normalized
text is collapsed keeping the best-scoring copy.

**Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2`, lazy singleton. Must run **once**
on the merged pool — reranking per document then merging would compare unbounded
cross-encoder logits against 0–1 hybrid scores. On any reranker failure the hybrid
ordering is preserved, so `score` stays on one scale either way.

**Follow-up handling:** 10 regex patterns (`explain in detail`, `tell me more`,
`elaborate`, `expand on`, `go deeper`, `clarify`, …). On a match the retrieval query
becomes `"{last_question} {question}"`.

---

## 7. LangGraph orchestration

### 7.1 State and reducers

```python
class GraphState(TypedDict, total=False):
    # accumulating
    messages:     Annotated[list[AnyMessage], add_messages]
    computations: Annotated[list[dict], operator.add]
    plots:        Annotated[list[dict], operator.add]
    trace:        Annotated[list[dict], operator.add]

    # request
    question, retrieval_query, session_id: str
    doc_ids: Optional[list[str]];  allowed_docs: list[str];  top_k: int

    # measurement context
    machine_id, point_id: Optional[str]
    machine: Optional[dict];  forcing_freqs: dict
    signal_ids, chart_ids: list[str];  peaks: list[dict];  stated_facts: dict

    # routing / retrieval — OVERWRITE
    route: Literal["theory","numeric","data","hybrid","chitchat"]
    retrieved, graded: list[dict]

    # output
    answer: str;  diagnosis: Optional[dict];  grounded: bool
    used_fallback: bool;  error: Optional[str]

    # bounded counters — PLAIN INTS, OVERWRITE
    rewrite_count, regen_count, tool_loops: int
```

**Reducer rationale — this is the classic LangGraph bug surface:**

| Channel | Reducer | Why |
|---|---|---|
| `messages` | `add_messages` | agent and tool nodes both append; handles id-based replacement |
| `computations`, `plots`, `trace` | `operator.add` | several nodes append across loop iterations |
| `retrieved`, `graded` | **overwrite** | a re-retrieval after a rewrite must *replace*; appending would re-admit exactly the passages the grader just rejected, so the loop could never converge |
| counters | **plain int, overwrite** | `operator.add` forces nodes to return deltas; one node returning the absolute value silently doubles the counter and breaks the bound |

Counters are incremented via `bump(state, key)` which always returns the **absolute**
new value. Locked by `test_bump_returns_absolute_value_not_a_delta`.

`retrieve` and the tool loop are kept sequential — LangGraph raises `InvalidUpdateError`
if two parallel branches write the same non-reduced key in one superstep.

### 7.2 Node graph

```
START → prepare → classify ─┬─ chitchat ────────────────────────────────► generate
                            ├─ theory ─► retrieve → grade ─┬─ ok ───────► agent
                            │                              └─ weak ─► rewrite (×1) ─┐
                            │                                    ▲                  │
                            │                                    └──────────────────┘
                            └─ numeric/data/hybrid ─► resolve_machine_context ─► retrieve

agent ⇄ execute_tools  (bounded by AGENT_MAX_ITERATIONS = 4)
      └─► ground_computations ─► generate

generate ─ figures or plots? ─► vision_answer ─┐
         └─────────────────────────────────────┴─► check_groundedness
                                                    ├─ ungrounded (×1) ─► generate
                                                    └─ ok ─► finalize → END
```

### 7.3 The 13 nodes

| Node | LLM purpose | What it does |
|---|---|---|
| `prepare` | — | session, ready docs, `_retrieval_query_for_turn`. Raises the same `FileNotFoundError`/`ValueError` the legacy services raise, so existing 404/400 handlers still work |
| `classify` | `classify` | **route + query rewrite + fact extraction in ONE call**. A separate rewrite node would double latency for no gain |
| `resolve_machine_context` | — | loads `MachineProfile`, computes forcing frequencies. User-stated facts beat the stored nameplate |
| `retrieve` | — | `retrieve_across_documents` verbatim — zero reimplementation |
| `grade` | `grade` | grades **all** excerpts in ONE batched call. Per-excerpt calls would cost top_k× for a binary decision |
| `rewrite` | `classify` | reformulates using the grader's rejection reasons |
| `agent` | `agent` | `bind_tools(domain + retrieval)` |
| `execute_tools` | — | runs tools, pulls `ToolMessage.artifact` into `computations` |
| `ground_computations` | — | one retrieval per **distinct** `query_hint` → `supporting_chunk_id` |
| `generate` | `generate` | two-block `<COMPUTED>` + `<EXCERPTS>` prompt |
| `vision_answer` | `vision` | refines the draft with figure images attached |
| `check_groundedness` | `verify` | `{grounded, unsupported_claims}` |
| `finalize` | — | writes the turn to `SessionService` |

**Failure isolation:** `classify` failure → defaults to `hybrid`; `grade` failure →
keeps all excerpts; `check_groundedness` failure → passes through; `vision_answer`
failure → keeps the draft; `generate` failure with a recognised OpenAI error →
`retrieval_only_answer`. No auxiliary node can fail the turn.

### 7.4 Loop bounds — all enforced and tested

| Loop | Bound | Constant |
|---|---|---|
| Tool calling | 4 | `AGENT_MAX_ITERATIONS` |
| Retrieval rewrite | 1 | `GRAPH_MAX_REWRITES` |
| Answer regeneration | 1 | `GRAPH_MAX_REGENS` |
| Graph recursion | 24 | `RECURSION_LIMIT = 2×4 + 16` |

Rewrite triggers when `len(graded) < max(1, len(retrieved)//3)`.

`GraphRecursionError` **subclasses `RecursionError`** (verified). `graph_answer` catches
it and degrades to a budget-exhausted answer with the retrieved excerpts;
`routes_chat.py` has an explicit `except RecursionError` before the generic handler so
it can never surface as an opaque 500.

### 7.5 Prompts

Eight templates in [app/chat/graph/prompts.py](app/chat/graph/prompts.py): `SYSTEM_PROMPT`,
`CLASSIFY_PROMPT`, `GRADE_PROMPT`, `REWRITE_PROMPT`, `GENERATE_PROMPT`,
`CHITCHAT_PROMPT`, `GROUNDEDNESS_PROMPT`, `REGENERATE_SUFFIX`.

**The critical one is `SYSTEM_PROMPT`'s tiered evidence policy.** The legacy modes
instruct the model to answer *only* from retrieved excerpts and otherwise reply
`"I do not know from the provided document excerpts."` Under that rule a model
**refuses to state a number a tool just computed**, because it appears in no excerpt.
Copying it into the graph is the single most likely way to ship a broken bot.

Graph mode instead uses:

1. `<COMPUTED>` — deterministic tool results from this turn. **Authoritative.** State
   exactly as given; never re-derive or round. Always show the inputs.
2. `<EXCERPTS>` — retrieved passages. Use for mechanism, interpretation, recommended
   action. Cite as (section, p.N).
3. Nothing else. Never invent thresholds, standard limits, bearing geometry, or fault
   frequencies — call the tool or say what input is needed.

Plus: trust `<COMPUTED>` on numeric disagreement and flag it; surface every
tool-declared assumption; always attach units; give frequencies as `Hz (order)`.

**`rag_service.py` and `agent_rag_service.py` keep their exact original strings**, so
their behaviour and tests are unaffected.

### 7.6 Tools

**5 domain tools**, all `response_format="content_and_artifact"` — the model sees a
short summary, the `ComputationRecord` travels as an artifact it never reads:

| Tool | Key arguments |
|---|---|
| `bearing_fault_frequencies` | `shaft_rpm`, `designation`, `n_balls`, `ball_dia_mm`, `pitch_dia_mm`, `contact_angle_deg` |
| `iso_severity_zone` | `velocity_rms_mm_s`, `machine_group`, `foundation`, `standard` |
| `convert_amplitude` | `value`, `from_unit`, `to_unit`, `frequency_hz`, `from_measure`, `to_measure` |
| `match_fault_signatures` | `peaks_orders`, `peaks_amplitudes`, `top_n` |
| `machine_forcing_frequencies` | `actual_rpm` |

**3 retrieval tools:** `semantic_search(query, top_k=6)`,
`table_search(query, top_k=4)` (filtered to `chunk_types=["table"]`, retrying unfiltered
with a `"table "` prefix if empty), `get_figure(chunk_id, doc_id)` (bypasses vectors,
injects at `score=1.0`).

### 7.7 ⚠ Input precedence — a real bug, fixed

**A live run had the model pass `machine_group=1` for a 55 kW pump. That is Group 3.**
It was harmless only because Groups 1 and 3 share identical limits; on a Group 2 machine
the same guess returns the wrong zone with full confidence.

**A tool argument supplied by the model is the least trustworthy input available.**
`iso_severity_zone` now resolves the group in this order:

1. User-stated `machine_group` (from `classify`'s extraction)
2. Machine profile's `resolved_iso_group()`
3. Inferred from stated `power_kw` + `machine_type`
4. **The model's own argument — last resort**, and only with a note plus
   `confidence = 0.7`
5. Otherwise: ask the user

When 1–3 produce a value that differs from the model's argument, the derived value wins
and the override is announced — at **full confidence**, since correcting a guess with a
derived value makes the result more trustworthy, not less.

`shaft_rpm` follows the same principle: measured > stated > nameplate.

Regression-tested in `tests/test_graph_tools.py::TestIsoGroupPrecedence`.

### 7.8 Checkpointer and memory

**`SqliteSaver` at `data/graph_checkpoints.sqlite`, `thread_id = session_id`.**

- `sqlite3.connect(..., check_same_thread=False)` — FastAPI runs the sync chat handler
  in a threadpool, so the connection is used from several threads.
- `SqliteSaver.from_conn_string` is **deliberately not used**: it is a context manager,
  and calling it bare closes the connection immediately.
- Falls back to `MemorySaver` with a warning if SQLite is unavailable.
- Compiled at app startup in `lifespan`, so the first request does not pay for it.

**`SessionService` is bridged, not replaced.** It still backs the legacy modes and
`_retrieval_query_for_turn`'s follow-up detection, and keeping both written means
switching mode mid-conversation does not lose history. `finalize` writes to both.

**⚠ Documented asymmetry:** graph-mode history lives in the SQLite checkpoint and
**survives a restart**; agent and simple mode history is in-process and does not.

### 7.9 Per-turn contexts

Tool closures hold mutable state that must not be serialised into a checkpoint, so
`RetrievalContext` and `DomainContext` live in a module-level dict keyed by session
(`_TURN_CONTEXTS`), set before `invoke` and cleared in a `finally` block.

---

## 8. API reference

Base: `/api/v1`

| Method | Path | Notes |
|---|---|---|
| `POST` | `/chat?mode=graph\|agent\|simple` | **default `graph`**; unknown mode → 400 |
| `POST` | `/chat/simple` | alias |
| `POST` | `/chat/agent` | alias |
| `POST` | `/documents/upload` | multipart; `?async_process=true` for background |
| `GET` | `/documents` | list |
| `GET` | `/documents/{doc_id}` | detail |
| `GET` | `/documents/{doc_id}/chunks?offset&limit` | paged |
| `GET` | `/documents/{doc_id}/assets/{filename}` | figure images |
| `GET` | `/health` | see below |
| `GET` | `/` | serves `static/index.html` |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | FastAPI built-ins |

### `ChatRequest`
```python
question: str
doc_ids: Optional[list[str]] = None
session_id: Optional[str] = None
top_k: int = 6
machine_id: Optional[str] = None      # graph mode
point_id: Optional[str] = None        # graph mode
signal_ids: list[str] = []            # ⚠ Phase 4
chart_ids: list[str] = []             # ⚠ Phase 4
```

### `ChatResponse`
```python
answer: str
sources: list[SourceCitation]
session_id: str
# added for graph mode — all defaulted, so existing clients are unaffected
route: Optional[str] = None
computations: list[ComputationRecordOut] = []
plots: list[PlotRef] = []
grounded: bool = True
trace: list[TraceStep] = []
```

**⚠ These fields must live on `ChatResponse` itself, never on a subclass.** FastAPI's
`response_model` filters out fields not declared on the model, so returning a subclass
would silently drop everything new.

**⚠ Computations must not go into `sources`.** `SourceCitation` requires integer
`page_start`/`page_end`, so a computation folded in there renders as "pp.0-0" in the UI.

### Error mapping (`routes_chat.py`)

| Exception | HTTP |
|---|---|
| `FileNotFoundError` | 404 |
| `ValueError` | 400 |
| `RuntimeError` | 503 |
| `RecursionError` (incl. `GraphRecursionError`) | 503, explicit handler |
| anything else | 500 |

### `/health` response
```json
{"status": "ok", "embedding_model_ready": true, "ready_documents": 3,
 "graph_ready": true, "llm_provider": "openai", "registered_machines": 1}
```

### Path-traversal hardening

`DOC_ID_RE = ^[A-Za-z0-9_-]{1,128}$` and `_safe_asset_path` using `Path.is_relative_to`
containment. Covered by 24 tests in `test_api_security.py`, including a canary file
outside `DOCUMENTS_DIR`.

---

## 9. Storage layout

Everything under `data/` and `logs/` is **gitignored** and reproducible from source
documents via `scripts/reindex_all.py`.

```
data/
├── documents/{doc_id}/
│   ├── source.pdf                 original upload
│   ├── structured_nodes.json      extracted document tree
│   ├── chunks.jsonl               raw chunks
│   ├── chunks_clean.jsonl         after TOC filtering
│   ├── chunks_sanitized.jsonl     after path sanitizing — THIS is what gets indexed
│   ├── faiss_index/
│   │   ├── index.faiss            the vectors
│   │   └── index.pkl              docstore + metadata
│   ├── assets/                    extracted figure PNG/JPEG
│   ├── document_registry.json     title, department, version, ...
│   └── status.json                status, chunk_count, enriched_figures, pdf_kind
│
├── machines/{machine_id}/profile.json      ✅ active
├── graph_checkpoints.sqlite                ✅ LangGraph memory
├── signals/{signal_id}/                    ⚠ Phase 4
├── charts/{chart_id}/                      ⚠ Phase 4
└── measurements/index.jsonl                ⚠ Phase 4

logs/interactions.jsonl        one JSON line per chat turn
```

**Currently present:** `cat2` (1841 chunks, 1141 assets), `condition_monitoring`
(1766 chunks, 52 assets), `test_sample_docx` (test fixture), machine `P-101`.

**Interaction log fields (graph mode):** `session_id, mode, question, route, machine_id,
doc_ids, tool_calls, computation_count, source_count, grounded, retrieval_fallback,
answer_preview, timestamp`.

**Un-ingested corpus at repo root (~130 MB):** `Cat3.pdf`, `ISO 10816-3-2009.pdf`,
`vdoc.pub_rolling-bearing-analysis-4th-edition.pdf` (68 MB),
`vdoc.pub_practical-machinery-vibration-analysis`, `vdoc.pub_noise-and-vibration-analysis`,
`vdoc.pub_the-scientist-and-engineers-guide-to-dsp`. All classify as `digital` —
no OCR needed.

---

## 10. Test suite

**323 passing, 3 skipped, ~30 seconds, fully offline.**

| File | Tests | Covers |
|---|---|---|
| `test_domain_bearing.py` | 54 | 6205 known answers, `BPFO+BPFI==n·fr` property, tiering, validation |
| `test_domain_iso.py` | 44 | full 8-row boundary matrix from both sides, group inference |
| `test_domain_units.py` | 30 | reference conversions, round-trip identity, warnings |
| `test_domain_signatures.py` | 29 | fault ranking, cross-check, context gating, provenance |
| `test_domain_machine.py` | 28 | forcing frequencies, degradation, gearbox/belt, store |
| `test_graph_nodes.py` | 25 | each node in isolation with a fake LLM |
| `test_graph_routing.py` | 25 | routing, **loop termination**, compiled-graph e2e |
| `test_graph_tools.py` | 18 | **input precedence**, tool failure modes |
| `test_api_security.py` | 24 | path traversal, doc_id validation |
| `test_services_unit.py` | 22 | SessionService LRU + thread safety, vision enrichment |
| `test_extraction_unit.py` | 9 | section-stack bounding, node backfill |
| `test_retrieval_unit.py` | 7 | single-embed reuse, rerank fallback, dedupe |
| `test_pipeline.py` | 7 (3 skipped) | end-to-end ingest + retrieval |
| `test_agent_skip_unit.py` | 4 | legacy `AGENT_SKIP_FINAL_CALL` optimisation |

**`pytest.ini`:** `addopts = -m "not live" --strict-markers -q`; markers `live` (needs
network / a real key) and `slow`.

**Staying offline:** `tests/fake_llm.py` provides a scriptable `FakeChatModel`
supporting `.invoke()`, `.with_structured_output(Schema)`, and `.bind_tools(tools)`.
Every graph node obtains its model through `llm_provider.get_chat_model`, so patching
that **one function** covers the entire graph. That single seam is much of why the
provider factory exists.

**Notable known-answer values used as external checks:**
- SKF 6205 @ 1750 rpm → BPFO 104.56, BPFI 157.94, BSF 68.75, FTF 11.62 Hz
- ISO Group 2 rigid → 2.79→B, 2.80→B, 2.81→C
- 1.0 g rms @ 100 Hz → 15.61 mm/s rms
- 55 kW / 4-pole / 50 Hz / 1478 rpm / 7-vane → 1× = 24.63 Hz, vane pass 172.43 Hz,
  2×LF = 100 Hz, pole-pass 1.47 Hz

**⚠ Test contention:** `test_pipeline.py` performs a real ingest that takes the
project-global ingest lock and may call OpenAI. Running the suite concurrently with
live queries or a real ingest causes spurious errors. Run it alone if in doubt.

---

## 11. Known limitations and not-built

### Not built — Phase 2 (retrieval tuning + corpus)
- `RETRIEVAL_CANDIDATE_K_MULTI` / `RETRIEVAL_MULTI_DOC_THRESHOLD` declared, not wired
- Chunk size/overlap not configurable — the splitter is hardcoded to
  `_split_text(text, max_chars=900)` with no overlap. The unwired
  `CHUNK_MAX_CHARS` / `CHUNK_OVERLAP_CHARS` constants were removed rather than
  left advertising a knob that did nothing.
- Vibration terms absent from `FIGURE_SIGNALS` / `TABLE_SIGNALS`
- Keyword tokenizer blind to `1x`, `Hz`, `mm/s`, `10816-3`
- 6 root PDFs (including ISO 10816-3 itself) not ingested

### Not built — Phase 4 (measurement intake)
Waiting on the upstream API that will supply machine configs, waveforms, and charts.

- `SIGNALS_DIR`, `CHARTS_DIR`, `MEASUREMENTS_DIR` and `VISION_CHART_IMAGE_DETAIL`
  were declared but unwired; they have been removed and should be reintroduced
  alongside the code that uses them
- `ChatRequest.signal_ids` / `chart_ids` accepted but unused
- `app/domain/signal.py` (FFT, envelope, statistics) — not written
- `app/domain/chart_reader.py` (VLM chart reading) — not written
- `app/domain/plots.py` (matplotlib) — not written; matplotlib **is** installed
- `analyze_signal` / `read_charts` nodes — not in the graph
- `routes_machines.py`, `routes_signals.py`, `routes_charts.py` — not written

The domain layer already takes normalized Python objects, and `SpectralPeak` is
deliberately one representation for peaks whether computed from an FFT or read off a
screenshot. Intake lands as an adapter, not a redesign.

### Not built — Phase 5/6
Structured `Diagnosis` output, measurement trending, analyst report, SSE streaming,
Cat3 and the rolling-bearing book, raising `VISION_MAX_ELEMENTS` and reindexing `cat2`.

### Accepted design limitations
- **Bearing catalog holds 2 entries.** Everything else is estimated at confidence 0.6
  or refused. Deliberate — see §5.1.
- **No roller-bearing estimator.** Ball-tuned ratios applied to a spherical roller
  bearing would be confidently wrong.
- **ISO displacement limits not transcribed.** `displacement_zone()` raises.
- **Fault ranking uses spectral orders only.** Phase measurements, H/V/A comparison, and
  trend history all carry diagnostic information not used.
- **No CLIP / image embeddings.** Multimodality is VLM-captioning-to-text.
- **`ready_documents` includes test fixtures** left behind by `test_pipeline.py`.

### Security notes
- `.env` is gitignored and contains a **live OpenAI key that has been used for testing —
  rotate it**.
- `git init` has not been run. The first `git add .` before `.gitignore` existed would
  have committed the key and 137 MB of PDFs; `.gitignore` now prevents this.
- No authentication on any endpoint. Do not expose this to a network without adding it.

---

## 12. Operational runbook

### Start
```bash
uvicorn app.main:app --reload --port 8000     # UI at http://localhost:8000
```

### Verify the domain layer without the server
```bash
python scripts/vib_cli.py bearing --designation "SKF 6205-2RS" --rpm 1750
python scripts/vib_cli.py iso --vrms 4.9 --power-kw 55 --type pump --foundation rigid
python scripts/vib_cli.py convert 1.0 --from g --to mm/s --freq 100
python scripts/vib_cli.py machine save examples/P-101.json
python scripts/vib_cli.py machine show P-101 --rpm 1478 --point 3H
python scripts/vib_cli.py diagnose --machine P-101 --point 3H --rpm 1478 \
    --peaks "24.6hz:0.25,76.4hz:0.95,152.8hz:0.4"
```
Add `--json` to any command for the full `ComputationRecord`.

**If the CLI and the bot disagree, the bot is wrong.**

### Ingest a document
```bash
python scripts/rag_cli.py ingest path/to/file.pdf
python scripts/ingest_folder.py            # batch from Input_Data/
python scripts/reindex_all.py --list       # re-run pipeline (re-pays vision cost)
```

### Tests
```bash
pytest                          # offline
pytest -m live                  # opt into network tests
pytest tests/test_domain_*.py   # domain only, ~0.5 s
```

### Cost model (gpt-4o-mini)
- **Ingestion:** ~$0.15 per 400 vision elements at `detail=low`. Full remaining corpus
  plus re-doing cat2's ~1000 lost figures ≈ **a couple of dollars**.
- **Per chat turn (graph mode):** 4–6 LLM calls ≈ **$0.01–0.02**.
- **Embeddings and reranking:** local CPU, free.

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| 503 "reasoning budget" | graph hit `RECURSION_LIMIT` | narrow the question, or supply the missing input |
| Answers cite no sources | no documents indexed | ingest a PDF, or check `/health` |
| "I do not know" in graph mode | retrieval genuinely empty | ingest the relevant standard |
| Quota errors take ~30 s | `max_retries` was raised above 0 | restore `max_retries=0` |
| Retrieval quality drops after adding documents | `RERANK_POOL_K` truncation | raise it, or wire `RETRIEVAL_CANDIDATE_K_MULTI` |
| Ingest hangs | project-global ingest lock held | check for a concurrent ingest |
| Wrong ISO zone | machine group guessed | state power + type, or register the machine |
