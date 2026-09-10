# Vibration Analysis Assistant — Development Report

**What has been built, component by component.**
Snapshot date: 13 August 2026 · Every figure below was read from the live codebase.

> **Layout note (26 August 2026).** This report describes the package layout as it
> stood on the snapshot date: `app/graph/`, `app/pipeline/`, `app/services/` and
> `app/models/`. Those were since regrouped by feature into `app/chat/`,
> `app/ingestion/`, `app/retrieval/`, `app/llm/`, `app/config/` and `app/schemas/`,
> and the numbered pipeline modules (`01b_`, `01c_`, `02_`) were renamed to plain
> module names. The component inventory below is still accurate; only the paths
> moved. See [SYSTEM.md](SYSTEM.md) §3 for the current tree.

For *how it works*, see [SYSTEM.md](SYSTEM.md) (complete technical reference).
For *how to run it*, see [README.md](README.md).
This document answers a different question: **what did we actually build?**

---

## 1. Where the project stands

| | |
|---|---|
| **Product** | LangGraph chatbot for rotating-machinery vibration analysis, over a multimodal document RAG |
| **Phases complete** | 0 (foundations), 1 (deterministic domain layer), 3 (LangGraph orchestration) |
| **Phases not built** | 2 (retrieval tuning + corpus), 4 (measurement intake), 5/6 (reporting, trending, streaming) |
| **Python code** | ~12,300 lines across `app/` (≈8,700), `scripts/` (939), `tests/` (≈2,600), plus a 243-line UI |
| **Tests** | **326 collected — 323 passing, 3 skipped, ~30 s, fully offline** |
| **Runtime** | Python 3.12 · Windows · CPU-only · no Docker · FastAPI + uvicorn |
| **Corpus indexed** | 2 production documents, 3,607 chunks, 1,193 extracted figure assets |
| **Machines registered** | 1 (`P-101`, sample centrifugal pump) |

### The rule the whole system is built around

> **An LLM never computes a number.**

Bearing fault frequencies, ISO severity zones, unit conversions and fault ranking all
come from deterministic Python that is unit-tested against published values. The model
routes, retrieves, calls tools and explains. Every number in an answer carries the
inputs and the formula that produced it.

That rule is why the architecture is split into three layers with hard dependency
boundaries:

| Layer | Package | Depends on |
|---|---|---|
| Deterministic vibration math | `app/domain/` | numpy only — **no LangChain, no OpenAI** |
| Orchestration | `app/graph/` | LangGraph + domain + retrieval |
| Document RAG | `app/pipeline/`, `app/services/` | FAISS, sentence-transformers, OpenAI vision |

The domain layer is importable and testable with zero LLM plumbing. That is what makes
`scripts/vib_cli.py` possible, and what keeps 185 of the 326 tests network-free by
construction rather than by mocking.

---

## 2. Build inventory

Status legend: **✅ built and tested** · **🟡 built, gaps known** · **⚪ declared, not wired**

### 2.1 Domain layer — deterministic vibration math

`app/domain/` · 6 modules + 3 data tables · 1,956 lines · 185 tests

| Module | Lines | What was built | Status |
|---|---|---|---|
| `bearing.py` | 431 | BPFO / BPFI / BSF / 2×BSF / FTF from geometry; 5-tier geometry resolution; designation normalization; ISO 15 bore decoding; boundary-dimension estimator | ✅ |
| `iso10816.py` | 244 | ISO 10816-3 / 20816-3 velocity severity zones — 4 machine groups × 2 foundations × 3 zone boundaries, hardcoded and auditable; machine-group inference | ✅ |
| `units.py` | 267 | g ↔ mm/s ↔ µm ↔ mil conversion with frequency; rms / peak / peak-to-peak measure conversion; integration/differentiation warnings | ✅ |
| `signatures.py` | 495 | 15-rule fault matcher, weighted scoring with contradiction penalties, dynamic order references, physical gating, bearing cross-check; `SpectralPeak` | ✅ |
| `machine.py` | 443 | `MachineProfile` schema (driver / driven / coupling / gearbox / bearings / points); every derived forcing frequency; atomic disk store | ✅ |
| `records.py` | 76 | `ComputationRecord` audit trail — inputs, outputs, formula, source, assumptions, confidence, supporting chunk | ✅ |

**Hardcoded reference data built** (`app/domain/data/`):

| File | Contents |
|---|---|
| `bearings.json` | 2 catalog bearings (SKF 6203, 6205) with published geometry + **59** ISO 15 boundary-dimension entries across series 60/62/63/64 |
| `iso10816_3.json` | Complete velocity boundary matrix — 4 groups × 2 foundations × 3 boundaries |
| `fault_signatures.json` | **15** fault rules, each with mechanism paragraph, 2–3 confirming checks, and a retrieval `query_hint` |

**The 15 fault rules built:** unbalance · parallel misalignment · angular misalignment ·
bent shaft · mechanical looseness · structural looseness / soft foot · bearing outer race ·
bearing inner race · bearing rolling element · bearing cage · gear mesh · blade/vane pass ·
electrical · oil whirl · belt drive.

**Design decisions worth recording:**

- **The bearing catalog holds only 2 entries, deliberately.** Filling it with
  plausible-looking geometry would produce confidently wrong fault frequencies — a wrong
  ball count shifts BPFO by ~11%. Everything else is estimated at confidence 0.6 with a
  surfaced assumption string, or refused outright.
- **Roller bearings return `None` rather than ball-bearing geometry.** `22312`, `NU312`,
  `32210` are refused; ball-tuned ratios on a spherical roller bearing would be
  confidently wrong.
- **RAG is never a geometry source ahead of the catalog.** A rerank miss must not be able
  to change a fault frequency.
- **Confidence travels with every result.** Catalog geometry is 1.0; estimated geometry is
  0.6 and carries an assumption the answer must surface.
- **`SpectralPeak` is one representation** whether a peak came from a computed FFT or was
  read off an analyser screenshot — differing only in `source` and `confidence`. That is
  what makes Phase 4 an adapter instead of a redesign.

### 2.2 Document ingestion pipeline

`app/pipeline/` · 14 files · 2,223 lines

| Module | Lines | What was built | Status |
|---|---|---|---|
| `run_full_pipeline.py` | 149 | 6-step orchestrator: classify → extract → filter TOC → sanitize paths → vision-enrich → index | ✅ |
| `docling_config.py` | 242 | PDF classifier (`digital` / `scanned` / `hybrid`) sampling 12 pages; garbled-ToUnicode detection; full-page-raster detection; Docling converter config | ✅ |
| `document_pdf_pipeline.py` | 433 | Fast path — PyMuPDF text + pdfplumber tables in an 8-worker `ProcessPoolExecutor` | ✅ |
| `document_multimodal_pipeline.py` | 656 | Docling path with OCR, bounded 10-page sub-PDF windows, `DegenerateExtraction` guard | ✅ |
| `vision_enrichment.py` | 491 | VLM figure and table captioning, token-bucket pacing, transient-error retry | ✅ |
| `01b_filter_toc.py` | 54 | Dot-leader / TOC / page-number-only chunk removal | ✅ |
| `01c_sanitize_section_path.py` | 43 | Section-path whitespace collapse, dedupe, chapter-prefix strip | ✅ |
| `02_index_faiss.py` | 68 | FAISS build / load / save | ✅ |
| `progress.py`, `importlib_loader.py`, 3 shims | 86 | Progress reporting, numeric-prefix module loading, back-compat import shims | ✅ |

**What makes the RAG multimodal:** VLM-captioning-to-text. Figures and tables are turned
into English prose by the vision model and embedded in the *same* text vector space as
everything else — one unified index. There is no CLIP and no image embedding.

- **Figures** — the extracted asset PNG is sent; the caption is *prepended* to the
  existing text and stored in `meta.vision_caption`.
- **Tables** — the whole source page is rasterized and sent, anchored by the rough
  pdfplumber extraction. The caption *replaces* the text; the original is preserved in
  `meta.local_table_text`.
- **At answer time**, retrieved `image` / `diagram` chunks have their actual PNG bytes
  base64-attached to the final synthesis call.

**Six chunk types built:** `clause` · `section_summary` · `chapter_summary` · `table` ·
`image` · `diagram`.

### 2.3 Retrieval

`app/services/retrieval_service.py`, `index_service.py` · 410 lines · 7 tests

| Piece | What was built | Status |
|---|---|---|
| Embeddings | `BAAI/bge-small-en-v1.5`, 384-dim, CPU, normalized, BGE query-instruction prefix, lock-guarded global singleton | ✅ |
| Vector store | FAISS `IndexFlatL2`, one index per document, exhaustive search | ✅ |
| Hybrid scoring | `0.7 × vector + 0.3 × keyword + 0.12 type boost` | 🟡 |
| Cross-document merge | Merge → sort → two-level dedupe (identity, then normalized text) | ✅ |
| Reranking | `cross-encoder/ms-marco-MiniLM-L-6-v2`, once on the merged pool of 48, lazy singleton, order-preserving fallback on failure | ✅ |
| Follow-up handling | 10 regex patterns (`tell me more`, `elaborate`, …) → query becomes `"{last_question} {question}"` | ✅ |
| Index caching | `IndexService` singleton caching FAISS objects and chunk maps, 5-second TTL on ready-document listing | ✅ |

**Everything is explicit** — there is no LangChain retriever object, no MMR, no
`ParentDocumentRetriever`, no BM25.

**Known gaps carried forward to Phase 2 (🟡):**

- The figure/table type-boost signal words are generic English. **No vibration term**
  (`spectrum`, `waterfall`, `cascade`, `orbit`, `bode`, `nyquist`, `envelope`, `fft`,
  `waveform`, `polar`) triggers the figure boost.
- The keyword tokenizer drops tokens of length ≤ 2 and splits on non-alphanumerics, so it
  discards `1x`, `2x`, `Hz`, `mm`, `g`, `dB`, and shreds `mm/s` → `{mm, s}` and
  `10816-3` → `{10816, 3}`. The keyword half of the hybrid score is effectively blind to
  this domain's vocabulary.

**Why per-document indexes rather than one unified index:** merge-and-rerank already
happens on the merged pool, so per-document gives free incremental re-ingest,
per-document cache invalidation, and `doc_ids` filtering with no metadata-filter
machinery. At ~8 documents that is ~46 MB and ~15 ms of serial search — a rounding error
next to the ~900 ms rerank. Revisit past ~25 documents.

### 2.4 LangGraph orchestration

`app/graph/` · 6 modules · 1,720 lines · 68 tests

| Module | Lines | What was built | Status |
|---|---|---|---|
| `state.py` | 136 | `GraphState` TypedDict + reducers | ✅ |
| `nodes.py` | 724 | **13 node functions + 6 routers** | ✅ |
| `prompts.py` | 162 | **8 prompt templates** | ✅ |
| `build.py` | 138 | `StateGraph` wiring, `SqliteSaver` checkpointer, singletons | ✅ |
| `tools_domain.py` | 389 | **5 domain tools**, all `content_and_artifact` | ✅ |
| `tools_retrieval.py` | 171 | **3 retrieval tools** + `RetrievalContext` | ✅ |

**The flow built:**

```
START → prepare → classify ─┬─ chitchat ──────────────────────────► generate
                            ├─ theory ─► retrieve → grade ─┬─ ok ─► agent
                            │                              └─ weak ─► rewrite (×1) ─┐
                            │                                    ▲                  │
                            │                                    └──────────────────┘
                            └─ numeric/data/hybrid ─► resolve_machine_context ─► retrieve

agent ⇄ execute_tools  (bounded by AGENT_MAX_ITERATIONS = 4)
      └─► ground_computations ─► generate

generate ─ figures? ─► vision_answer ─► check_groundedness ─┬─ ungrounded (×1) ─► generate
                                                            └─ ok ─► finalize → END
```

**The 13 nodes built:** `prepare` · `classify` · `resolve_machine_context` · `retrieve` ·
`grade` · `rewrite` · `agent` · `execute_tools` · `ground_computations` · `generate` ·
`vision_answer` · `check_groundedness` · `finalize`.

**The 5 domain tools built:** `bearing_fault_frequencies` · `iso_severity_zone` ·
`convert_amplitude` · `match_fault_signatures` · `machine_forcing_frequencies`.
Each returns a short summary to the model while the `ComputationRecord` travels as an
artifact the model never reads.

**The 3 retrieval tools built:** `semantic_search` · `table_search` (filtered to table
chunks, retrying unfiltered with a `"table "` prefix if empty) · `get_figure` (bypasses
vectors entirely).

**Engineering decisions worth recording:**

- **Graph mode needed its own system prompt.** The legacy modes instruct the model to
  answer *only* from retrieved excerpts and otherwise say "I do not know from the provided
  document excerpts." Under that rule the model **refuses to state a number a tool just
  computed**, because it appears in no excerpt. Graph mode uses a tiered evidence policy:
  `<COMPUTED>` results are authoritative, `<EXCERPTS>` supply interpretation, nothing else
  is permitted. Copying the legacy prompt across would have been the single most likely
  way to ship a broken bot. The legacy prompts are untouched.
- **`classify` does route + query rewrite + fact extraction in one call.** A separate
  rewrite node would double latency for no gain.
- **`grade` grades all excerpts in one batched call.** Per-excerpt calls would cost
  `top_k×` for a binary decision.
- **Every loop is hard-bounded and termination-tested:** tool calling 4, retrieval rewrite
  1, answer regeneration 1, graph recursion 24. `GraphRecursionError` subclasses
  `RecursionError`, so `routes_chat.py` catches it explicitly and it can never surface as
  an opaque 500.
- **No auxiliary node can fail the turn.** `classify` failure defaults to `hybrid`;
  `grade` failure keeps all excerpts; `check_groundedness` failure passes through;
  `vision_answer` failure keeps the draft; `generate` failure with a recognised OpenAI
  error degrades to a retrieval-only answer.
- **`ground_computations` runs one retrieval per *distinct* `query_hint`**, so a computed
  value cites two things: the tool that produced it, and the textbook passage that defines
  the formula.
- **Input precedence was a real bug, found and fixed** — covered by dedicated tests in
  `test_graph_tools.py`.

### 2.5 Services

`app/services/` · 10 modules · 1,961 lines · 22 tests

| Module | Lines | What was built | Status |
|---|---|---|---|
| `graph_rag_service.py` | 189 | `graph_answer()` — the `mode=graph` entry point | ✅ |
| `agent_rag_service.py` | 459 | Legacy hand-rolled OpenAI tool loop, vision final answer | ✅ |
| `rag_service.py` | 198 | Legacy single-shot retrieve-and-answer | ✅ |
| `retrieval_service.py` | 260 | Hybrid scoring + cross-encoder rerank (see §2.3) | 🟡 |
| `index_service.py` | 150 | FAISS + chunk-cache singleton | ✅ |
| `ingest_service.py` | 372 | Upload handling + cross-process ingest lock with stale-lock reclaim | ✅ |
| `llm_provider.py` | 105 | `get_chat_model(purpose)` — **the single test seam**; OpenAI + Anthropic | ✅ |
| `session_service.py` | 74 | In-memory LRU chat history, thread-safe | ✅ |
| `warmup_service.py` | 62 | Embedding-model singleton, warm-loaded at startup | ✅ |
| `openai_utils.py` | 92 | Client factory + error classification driving the retrieval fallback | ✅ |

**`llm_provider.get_chat_model` is the highest-leverage thing in the services layer.**
Every graph node obtains its model through it, so patching that *one* function keeps the
entire graph test suite off the network. That is much of why the provider factory exists
at all.

### 2.6 API and web UI

`app/api/`, `app/main.py`, `app/models/`, `static/` · 874 lines · 24 security tests

| Endpoint | Built |
|---|---|
| `POST /api/v1/chat?mode=graph\|agent\|simple` | ✅ default `graph`; unknown mode → 400 |
| `POST /api/v1/chat/simple`, `/chat/agent` | ✅ aliases |
| `POST /api/v1/documents/upload` | ✅ multipart, `?async_process=true` for background |
| `GET /api/v1/documents` · `/{doc_id}` · `/{doc_id}/chunks` · `/{doc_id}/assets/{filename}` | ✅ list / detail / paged chunks / figure images |
| `GET /api/v1/health` | ✅ embedding readiness, ready docs, graph readiness, provider, registered machines |
| `GET /` | ✅ serves the single-file UI |
| `GET /docs`, `/redoc`, `/openapi.json` | ✅ FastAPI built-ins |

**Also built:**

- `app/models/config.py` — **~70 env-backed constants**, `load_dotenv(override=True)` so
  `.env` beats stale shell variables.
- `app/models/schemas.py` — Pydantic request/response models. `ChatResponse` gained
  `route`, `computations`, `plots`, `grounded`, `trace`, **all defaulted so existing
  clients are unaffected**.
- `static/index.html` — 243-line single-file UI, no build step.
- Full error mapping: `FileNotFoundError`→404, `ValueError`→400, `RuntimeError`→503,
  `RecursionError`→503, else 500.
- `logs/interactions.jsonl` — one JSON line per chat turn with route, tool calls,
  computation count, groundedness and fallback flags.

**Two API traps found and documented:** new response fields must live on `ChatResponse`
itself, never a subclass (FastAPI's `response_model` silently filters unknown fields); and
computations must not be folded into `sources`, because `SourceCitation` requires integer
pages and would render "pp.0-0".

**Path-traversal hardening:** `DOC_ID_RE = ^[A-Za-z0-9_-]{1,128}$`, `MACHINE_ID_RE =
^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$`, and `_safe_asset_path` using `Path.is_relative_to`
containment — covered by 24 tests including a canary file placed outside `DOCUMENTS_DIR`.

### 2.7 Command-line tooling

`scripts/` · 8 scripts · 939 lines

| Script | What was built |
|---|---|
| `vib_cli.py` | **Every domain calculation, reachable without an LLM or a server** — `bearing`, `iso`, `convert`, `machine save/show`, `diagnose`. `--json` gives the full `ComputationRecord` |
| `rag_cli.py` | `ingest` / `ask` / `chat` / `list` |
| `ingest_folder.py` | Batch ingest from `Input_Data/` |
| `reindex_all.py` | Re-run the pipeline over `data/documents/*` (`--list` to preview) |
| `warmup.py`, `test_retrieval.py` | Model warm-load, retrieval smoke test |
| `create_sample_pdf.py`, `create_sample_docx.py` | Fixture generators (template leftovers) |

**`vib_cli.py` is the oracle:** if the CLI and the bot disagree, the bot is wrong.

### 2.8 Test suite

`tests/` · 14 files + 2 helpers · 326 tests · fully offline by default

| File | Tests | Covers |
|---|---|---|
| `test_domain_bearing.py` | 54 | 6205 known answers, `BPFO+BPFI == n·fr` property test, tiering, validation |
| `test_domain_iso.py` | 44 | Full 8-row boundary matrix from both sides, group inference |
| `test_domain_units.py` | 30 | Reference conversions, round-trip identity, warnings |
| `test_domain_signatures.py` | 29 | Fault ranking, cross-check, context gating, provenance |
| `test_domain_machine.py` | 28 | Forcing frequencies, graceful degradation, gearbox/belt, store |
| `test_graph_nodes.py` | 25 | Each node in isolation against a fake LLM |
| `test_graph_routing.py` | 25 | Routing, **loop termination**, compiled-graph end-to-end |
| `test_api_security.py` | 24 | Path traversal, `doc_id` validation |
| `test_services_unit.py` | 22 | Session LRU + thread safety, ingest lock, token bucket, vision retry |
| `test_graph_tools.py` | 18 | **Input precedence**, tool failure modes |
| `test_extraction_unit.py` | 9 | Section-stack bounding, node backfill |
| `test_retrieval_unit.py` | 7 | Single-embed reuse, rerank fallback, dedupe |
| `test_pipeline.py` | 7 (3 skipped) | End-to-end ingest + retrieval |
| `test_agent_skip_unit.py` | 4 | Legacy `AGENT_SKIP_FINAL_CALL` optimisation |

**Known-answer values used as external checks** — these are the anchors that make the
domain layer trustworthy:

- SKF 6205 @ 1750 rpm → BPFO 104.56, BPFI 157.94, BSF 68.75, FTF 11.62 Hz
- ISO Group 2 rigid → 2.79 → B, 2.80 → B, 2.81 → C
- 1.0 g rms @ 100 Hz → 15.61 mm/s rms
- 55 kW / 4-pole / 50 Hz / 1478 rpm / 7-vane → 1× = 24.63 Hz, vane pass 172.43 Hz,
  2×LF = 100 Hz, pole-pass 1.47 Hz
- Property test: `BPFO + BPFI == n·fr` over 25 random geometries — catches sign and factor
  errors instantly

**Test infrastructure built:** `tests/fake_llm.py` provides a scriptable `FakeChatModel`
supporting `.invoke()`, `.with_structured_output(Schema)` and `.bind_tools(tools)`;
`conftest.py` isolates the ingest lock. `pytest.ini` defaults to `-m "not live"`.

### 2.9 Configuration and dependency management

| Artifact | What was built |
|---|---|
| `app/models/config.py` | ~70 env-backed constants across paths, models, generation, per-purpose model settings, sessions, retrieval, chunking, vision, agent/graph bounds, Docling, PDF classification |
| `.env.example` | 60+ documented variables |
| `requirements.txt` | **Fully pinned, deliberately** — with the reasoning written into the file |
| `.gitignore` | Protects `.env`, `data/`, `logs/`, `*.pdf`, `*.sqlite` |

**Why the pins are load-bearing:** `langchain-core` 1.4.2 and `openai` 2.41.0 are
load-bearing. `langgraph>=1.2.9` requires `core>=1.4.7`, and `langchain-openai>=1.3`
requires `openai>=2.45`, either of which would move `openai` out from under the
`isinstance(exc, openai.AuthenticationError)` checks in `openai_utils.py` and **silently
disable the retrieval fallback**. After any change, run `pip install --dry-run -r
requirements.txt` and confirm neither package appears in the "Would install" line.

---

## 3. Data assets produced

### Corpus ingested

| Document | Chunks | Assets | Figures captioned | Kind |
|---|---|---|---|---|
| `cat2` | 1,841 (1,664 clause · 66 table · 84 image · 26 section · 1 chapter) | 1,141 | 150 — **hit the `VISION_MAX_ELEMENTS` cap** | digital |
| `condition_monitoring` | 1,766 (1,689 clause · 19 table · 52 image · 5 section · 1 chapter) | 52 | 71 | digital |
| `test_sample_docx` | test fixture left by `test_pipeline.py` | — | — | — |

`cat2` reached the 150-element vision cap with 1,141 assets available, so roughly 1,000
figures are indexed by their surrounding text only. Raising the cap and reindexing is
queued for Phase 5/6 and costs a couple of dollars.

### Other stored state built

- `data/machines/P-101/profile.json` — sample centrifugal pump profile (also at
  `examples/P-101.json`)
- `data/graph_checkpoints.sqlite` — LangGraph memory. **Graph-mode history survives a
  restart**; agent and simple mode history does not.
- `logs/interactions.jsonl` — per-turn structured log

Everything under `data/` and `logs/` is gitignored and reproducible from source documents
via `scripts/reindex_all.py`.

### Corpus staged but not yet ingested (~130 MB at repo root)

`Cat3.pdf` · `ISO 10816-3-2009.pdf` · rolling-bearing-analysis 4th ed. (68 MB) ·
practical-machinery-vibration-analysis · noise-and-vibration-analysis ·
scientist-and-engineers-guide-to-DSP. All six classify as `digital`, so no OCR is needed.

---

## 4. What is not built

### Phase 2 — retrieval tuning and corpus expansion

- `RETRIEVAL_CANDIDATE_K_MULTI` / `RETRIEVAL_MULTI_DOC_THRESHOLD` — ⚪ declared, not wired
- `CHUNK_MAX_CHARS` / `CHUNK_OVERLAP_CHARS` — ⚪ declared, not wired; the splitter is still
  hardcoded at 900/0. `180` overlap suits technical books where zero overlap severs
  derivations. Changing it requires a reindex.
- Vibration terms absent from the figure/table boost signal lists
- Keyword tokenizer blind to `1x`, `Hz`, `mm/s`, `10816-3`
- The 6 root PDFs above, including ISO 10816-3 itself, not ingested

### Phase 4 — measurement intake

Designed but not implemented, pending the upstream API that will supply machine configs,
waveforms and charts.

- `SIGNALS_DIR`, `CHARTS_DIR`, `MEASUREMENTS_DIR`, `VISION_CHART_IMAGE_DETAIL` — ⚪
  declared, not wired
- `ChatRequest.signal_ids` / `chart_ids` — ⚪ accepted but unused
- `app/domain/signal.py` (FFT, envelope, statistics) — not written
- `app/domain/chart_reader.py` (VLM chart reading) — not written
- `app/domain/plots.py` (matplotlib) — not written; matplotlib **is** installed
- `analyze_signal` / `read_charts` nodes — not in the graph
- `routes_machines.py`, `routes_signals.py`, `routes_charts.py` — not written

**This lands as one adapter, not a redesign.** The domain layer already takes normalized
Python objects, and `SpectralPeak` is deliberately the single representation for peaks
whether they come from a computed FFT or a vision-read screenshot.

### Phase 5/6

Structured `Diagnosis` output · measurement trending · analyst report · SSE streaming ·
ingesting Cat3 and the rolling-bearing book · raising `VISION_MAX_ELEMENTS` and reindexing
`cat2`.

---

## 5. Accepted limitations

These are choices, not oversights — each is documented with its reasoning.

| Limitation | Why it was accepted |
|---|---|
| Bearing catalog holds 2 entries | Plausible-looking geometry produces confidently wrong frequencies; everything else is estimated at 0.6 confidence or refused |
| No roller-bearing estimator | Ball-tuned ratios on a spherical roller bearing would be confidently wrong |
| ISO displacement limits not transcribed | `displacement_zone()` raises rather than guessing |
| Fault ranking uses spectral orders only | Phase measurements, H/V/A comparison and trend history carry diagnostic information not yet used |
| No CLIP / image embeddings | Multimodality is VLM-captioning-to-text in one unified vector space |
| `ready_documents` includes test fixtures | Left behind by `test_pipeline.py` |

---

## 6. Open items to action

| # | Item | Why it matters |
|---|---|---|
| 1 | **Rotate the OpenAI key in `.env`** | It is a live key that has been used for testing. `.gitignore` protects it now, but it should be rotated |
| 2 | **`git init` has not been run** | The project is not under version control. A first `git add .` before `.gitignore` existed would have committed the key and 137 MB of PDFs — `.gitignore` now prevents that, but the repo still needs initializing |
| 3 | **No authentication on any endpoint** | Do not expose this to a network without adding it |
| 4 | Raise `VISION_MAX_ELEMENTS` and reindex `cat2` | ~1,000 figures currently indexed by surrounding text only |
| 5 | Ingest the 6 staged PDFs, ISO 10816-3 first | The system currently reasons about ISO zones from a hardcoded table with no retrievable standard text behind it |
| 6 | Wire the Phase 2 retrieval fixes | The keyword half of hybrid scoring is blind to `1x`, `Hz`, `mm/s`, `10816-3` |

---

## 7. Operating cost, measured

- **Ingestion:** ~$0.15 per 400 vision elements at `detail=low`. The full remaining corpus
  plus redoing cat2's ~1,000 lost figures ≈ **a couple of dollars**.
- **Per chat turn (graph mode):** 4–6 LLM calls ≈ **$0.01–0.02**.
- **Embeddings and reranking:** local CPU, free.

---

## 8. Summary

Three of six planned phases are complete, and the parts that are complete are the parts
that are hard to retrofit: a deterministic domain layer with published-value tests, a
bounded and failure-isolated orchestration graph, and a multimodal ingestion pipeline that
turns figures and tables into searchable prose.

The remaining phases are additive. Measurement intake attaches to a `SpectralPeak`
representation that already exists; retrieval tuning changes scoring constants and a
tokenizer inside one module; reporting consumes records the graph already produces. The
expensive architectural decisions — never letting the model compute, keeping the domain
layer free of LLM plumbing, funnelling every model call through one provider seam — were
made early and are what make the rest cheap.
