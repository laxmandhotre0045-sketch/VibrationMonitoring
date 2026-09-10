# Vibration Analysis Assistant

A LangGraph chatbot for rotating-machinery vibration analysis, built on a multimodal
document RAG over vibration standards and textbooks.

The design principle throughout: **an LLM never computes a number.** Bearing fault
frequencies, ISO severity zones, and unit conversions come from deterministic Python
that is unit-tested against published values. The model orchestrates, retrieves, and
explains — and every number it states carries the inputs and formula that produced it.

---

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env                                # then add your OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>.

---

## The domain tools (no LLM, no server)

Everything the bot can calculate is reachable from the CLI. If the CLI and the bot
disagree, the bot is wrong.

```bash
python scripts/vib_cli.py bearing --designation "SKF 6205-2RS" --rpm 1750
#   BPFO = 104.56 Hz (3.585x)   BPFI = 157.94 Hz (5.415x)
#   BSF  =  68.74 Hz (2.357x)   FTF  =  11.62 Hz (0.398x)

python scripts/vib_cli.py iso --vrms 4.9 --power-kw 55 --type pump --foundation rigid
#   ZONE C — unsatisfactory for long-term continuous operation

python scripts/vib_cli.py convert 1.0 --from g --to mm/s --freq 100
#   15.61 mm/s rms

python scripts/vib_cli.py machine save examples/P-101.json
python scripts/vib_cli.py machine show P-101 --rpm 1478 --point 3H
#   full forcing-frequency table: 1x/2x/3x, vane pass, 2xLF, pole-pass, BPFO/BPFI/BSF/FTF

python scripts/vib_cli.py diagnose --machine P-101 --point 3H --rpm 1478 \
    --peaks "24.6hz:0.25,76.4hz:0.95,152.8hz:0.4"
#   1. Rolling-element bearing — outer race defect (score 0.83)
#      Non-synchronous peak at 76.40 Hz (3.101x) matches computed BPFO within 0.05%
```

| Module | What it does |
|---|---|
| `app/domain/bearing.py` | BPFO/BPFI/BSF/FTF. Geometry resolves catalog → estimator → ask; **never** a guess. |
| `app/domain/iso10816.py` | ISO 10816-3 / 20816-3 zone lookup, hardcoded and auditable. |
| `app/domain/units.py` | g ↔ mm/s ↔ µm ↔ mil, rms/peak/pk-pk. |
| `app/domain/signatures.py` | Rule-table fault ranking, cross-checked against computed bearing frequencies. |
| `app/domain/machine.py` | Machine profile + every forcing frequency it can produce. |

Confidence travels with every result. Catalog geometry is 1.0; geometry estimated from
boundary dimensions is 0.6 and carries an assumption string the answer must surface.

---

## Chat modes

`POST /api/v1/chat?mode=graph|agent|simple`

- **`graph`** (default) — LangGraph vibration analyst. Routes by question type, grades
  retrieval and retries once, calls domain tools, grounds each computation against the
  passage that defines its formula, then checks the answer for unsupported claims.
- **`agent`** — the original hand-rolled OpenAI tool loop. Unchanged.
- **`simple`** — single-shot retrieve-and-answer. Unchanged.

The graph flow:

```
prepare → classify ─┬─ chitchat ─────────────────────────────► generate
                    ├─ theory ─► retrieve → grade ─┬─ ok ────► agent
                    │                              └─ weak ─► rewrite (×1) ─► retrieve
                    └─ numeric/data/hybrid ─► resolve_machine_context ─► retrieve → …

agent ⇄ execute_tools → ground_computations → generate
generate ─ figures? ─► vision_answer ─► check_groundedness ─ ungrounded (×1) ─► generate
                                                           └─ ok ─► finalize
```

Both cycles are hard-bounded (`GRAPH_MAX_REWRITES`, `GRAPH_MAX_REGENS`,
`AGENT_MAX_ITERATIONS`) and covered by termination tests. Memory is a SQLite
checkpointer keyed by `session_id`, so **graph-mode history survives a restart** —
agent and simple mode history does not.

### Why graph mode has a different system prompt

The legacy modes instruct the model to answer *only* from retrieved excerpts, and
otherwise reply "I do not know from the provided document excerpts." Under that rule a
model will refuse to state a number a tool just computed, because it appears in no
excerpt. Graph mode uses a tiered evidence policy instead: `<COMPUTED>` results are
authoritative, `<EXCERPTS>` supply interpretation, and nothing else is permitted. The
legacy prompts are untouched.

---

## Architecture

```
app/
  domain/      deterministic vibration math — no LangChain, no OpenAI
  chat/        the three chat modes; chat/graph/ is the LangGraph analyst
  retrieval/   embeddings, FAISS store, index cache, hybrid scoring + rerank
  ingestion/   PDF classification → extraction → vision captioning → FAISS
  llm/         chat-model factory (the test seam) + raw OpenAI client
  config/      env-derived settings, grouped by topic
  schemas/     Pydantic request/response DTOs
  api/         FastAPI routes
```

Dependencies run one way, and a test asserts it:

```
api → chat → retrieval → {llm, domain, schemas, config}
api → ingestion → retrieval → …
```

**Ingestion** classifies each PDF (`digital` / `scanned` / `hybrid`) and routes it:
digital PDFs take the fast PyMuPDF + pdfplumber path; scanned ones go through Docling
with OCR in bounded page windows. Figures and tables are captioned by a vision model
into searchable prose — that is what makes the RAG multimodal; there is no CLIP and no
image embedding, just one unified text vector space.

**Retrieval** is per-document FAISS (`IndexFlatL2`, 384-dim `BAAI/bge-small-en-v1.5`,
CPU) merged across indexes, hybrid-scored (0.7 vector + 0.3 keyword + type boost),
deduped, then reranked once on the merged pool by
`cross-encoder/ms-marco-MiniLM-L-6-v2`.

---

## Tests

```bash
pytest                 # offline, no API calls
pytest -m live         # opt in to tests that hit a real API
```

323 tests. The domain modules are held to published known answers — SKF 6205 at
1750 rpm, the full ISO boundary matrix from both sides, `1 g rms @ 100 Hz =
15.61 mm/s` — plus a property test that `BPFO + BPFI == n·fr` for any geometry, which
catches sign and factor errors instantly.

Graph tests use a scriptable fake model injected through `llm_provider.get_chat_model`.
That single seam keeps the whole suite off the network, which is much of why the
provider factory exists.

---

## Configuration

See `.env.example`. Notable:

| Variable | Default | Why it matters |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `anthropic` swaps the graph's chat model (needs `langchain-anthropic`). |
| `GRAPH_MAX_REWRITES` | `1` | Bounds the retrieval-retry cycle. |
| `GRAPH_MAX_REGENS` | `1` | Bounds the groundedness-retry cycle. |
| `RERANK_POOL_K` | `48` | Candidates reaching the reranker. Raise with the corpus, or recall silently drops. |
| `VISION_MAX_ELEMENTS` | `150` | Per-document cap on figure captioning. `cat2` hit this with 1141 assets — raise it before ingesting image-heavy books. |

**Dependencies are pinned, deliberately.** `langchain-core` 1.4.2 and `openai` 2.41.0
are load-bearing: `langgraph>=1.2.9` and `langchain-openai>=1.3` would upgrade `openai`
out from under the `isinstance(exc, openai.AuthenticationError)` checks in
`openai_utils.py` and silently disable the retrieval fallback. After changing
`requirements.txt`, run `pip install --dry-run -r requirements.txt` and confirm neither
package appears in the "Would install" line.

---

## Not built yet

Measurement intake — time waveforms, analyser chart images, and machine configs — is
designed but not implemented, pending the upstream API that will supply it. The domain
layer already takes normalized Python objects, so it lands as one adapter rather than a
redesign. `SpectralPeak` is deliberately the single representation for peaks whether
they come from a computed FFT or a vision-read screenshot.
