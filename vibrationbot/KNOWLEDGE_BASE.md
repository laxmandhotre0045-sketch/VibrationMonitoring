# The Multimodal RAG and Knowledge Base

**How documents become searchable knowledge — extraction, captioning, chunking, indexing, retrieval.**

Snapshot date: 2 September 2026 · Written against the current `app/ingestion/` +
`app/retrieval/` layout · Every number below was read from the live code and the
live corpus on disk.

Companion documents: [README.md](README.md) (quick start) ·
[SYSTEM.md](SYSTEM.md) (full system reference) ·
[DEVELOPMENT_REPORT.md](DEVELOPMENT_REPORT.md) (what was built)

---

## 1. What this knowledge base is

A per-document vector store over vibration standards and textbooks, built so that
**figures and tables are searchable as text**. There is no image embedding model, no
CLIP, no separate visual index. A vision model converts every figure and table into
English prose during ingestion, and that prose is embedded into the *same* 384-dimension
text vector space as the body text.

That single decision shapes everything downstream:

| Consequence | Why |
|---|---|
| One index, one scoring scale | A figure caption and a paragraph compete on equal terms; no cross-modal score fusion is needed |
| Figures are findable by what they *show* | "spectrum with sidebands at 1× spacing" matches a caption, not a filename |
| Ingestion costs money and time | Every figure is an API call. This is the pipeline's dominant cost and its main bottleneck |
| A figure only exists in the KB if it was captioned | See §7 — this is a hard gate, not a quality knob |

### Live corpus

| doc_id | pdf_kind | raw chunks | indexed | assets on disk | captioned |
|---|---|---|---|---|---|
| `cat2` | digital | 2,964 | **1,841** | 1,141 | 150 |
| `condition_monitoring` | digital | 1,857 | **1,766** | 52 | 71 |
| `test_sample_docx` | — | 7 | 3 | 0 | 1 |

Indexed chunk types:

| doc_id | clause | table | image | section_summary | chapter_summary |
|---|---|---|---|---|---|
| `cat2` | 1,664 | 66 | 84 | 26 | 1 |
| `condition_monitoring` | 1,689 | 19 | 52 | 5 | 1 |

Total live knowledge base: **3,607 indexed chunks / 3,607 vectors** across two documents.

---

## 2. The document lifecycle

One entry point — `run_full_pipeline()` in
[app/ingestion/run_full_pipeline.py](app/ingestion/run_full_pipeline.py) — runs six
steps. Each writes a file the next one reads, so any step can be inspected, re-run, or
debugged in isolation.

```
                     source.pdf / source.docx
                              │
   ┌──────────────────────────▼──────────────────────────┐
   │ 1. CLASSIFY      classify_pdf()                     │  digital | scanned | hybrid
   │                  12 sampled pages → text_ratio      │  → picks the extractor
   └──────────────────────────┬──────────────────────────┘
                              │
   ┌──────────────────────────▼──────────────────────────┐
   │ 2. EXTRACT       digital  → document_pdf_pipeline   │  ──► structured_nodes.json
   │                  scanned  → docling + OCR           │  ──► chunks.jsonl
   │                  hybrid   → docling + OCR           │  ──► assets/*.png|jpeg
   │                  .docx    → docling → python-docx   │  ──► document_registry.json
   └──────────────────────────┬──────────────────────────┘
                              │
   ┌──────────────────────────▼──────────────────────────┐
   │ 3. VISION        figures → caption PREPENDED        │  mutates chunks.jsonl
   │    ENRICH        tables  → caption REPLACES text    │  in place
   └──────────────────────────┬──────────────────────────┘
                              │
   ┌──────────────────────────▼──────────────────────────┐
   │ 4. FILTER        TOC lines, <40-char chunks         │  ──► chunks_clean.jsonl
   └──────────────────────────┬──────────────────────────┘
                              │
   ┌──────────────────────────▼──────────────────────────┐
   │ 5. SANITIZE      collapse/dedupe section paths      │  ──► chunks_sanitized.jsonl ★
   └──────────────────────────┬──────────────────────────┘
                              │
   ┌──────────────────────────▼──────────────────────────┐
   │ 6. INDEX         bge-small-en-v1.5 → FAISS          │  ──► faiss_index/index.faiss
   └─────────────────────────────────────────────────────┘                  index.pkl
```

★ `chunks_sanitized.jsonl` is what gets embedded. Steps 4 and 5 are not cosmetic —
they decide what enters the knowledge base at all.

Step ordering matters and is deliberate: **vision enrichment runs before filtering**, so
a captioned figure has real text by the time the minimum-length filter sees it. The
consequence when a figure *isn't* captioned is documented in §7.

---

## 3. Step 1 — Classification

[app/ingestion/docling_config.py](app/ingestion/docling_config.py) · `classify_pdf()`

The only job here is picking an extractor. Running OCR on a PDF that already has a text
layer wastes minutes per document; skipping OCR on a scan produces an empty knowledge
base entry.

```
sample_n = min(PDF_CLASSIFY_SAMPLE=12, page_count)
idxs     = evenly spread across the WHOLE document, not the first 12 pages
           → covers front matter, body, and back matter

for each sampled page:
    text = page.get_text("text")
    if len(text) < PDF_CLASSIFY_MIN_CHARS (100):   skip           ← not a text page
    if page has images and len(text) < 200:
        if any single image covers > 85% of page area:  skip      ← a scan with a caption
    else: text_pages += 1

text_ratio = text_pages / sample_size
```

| Ratio | Kind | Extractor | OCR |
|---|---|---|---|
| `>= PDF_DIGITAL_THRESHOLD` (0.80) | `digital` | PyMuPDF + pdfplumber | none |
| `<= PDF_SCANNED_THRESHOLD` (0.15) | `scanned` | Docling | forced on |
| between | `hybrid` | Docling | forced on |

Two heuristics beyond the raw ratio:

- **Garbled ToUnicode detection.** Some OCR'd PDFs carry a text layer whose glyph map is
  broken, so `get_text()` returns mojibake. Pages below the char minimum are inspected
  for printable-character ratio rather than counted blindly.
- **Full-page raster detection.** A scanned page with a typeset caption can clear the
  100-char bar. The `>85% single image area` check reclassifies it as scanned.

Escape hatch: `DIGITAL_PDF_USE_DOCLING=true` routes digital PDFs through Docling anyway
for richer layout and table structure — much slower on large documents, and off by
default.

All six un-ingested PDFs at the repo root classify as `digital`, so none of them need OCR.

---

## 4. Step 2a — The digital extractor (fast path)

[app/ingestion/document_pdf_pipeline.py](app/ingestion/document_pdf_pipeline.py) · 433 lines

This is the path both live documents took. PyMuPDF for text, pdfplumber for tables,
PyMuPDF again for embedded figure assets. No layout model, no OCR — seconds, not minutes.

### Text and table extraction

```
_extract_pages(pdf)
  ├─ fitz: page.get_text("text") for every page          ← fast, single-threaded
  └─ _extract_tables(pdf, n_pages)                        ← pdfplumber, parallel
       │
       ├─ n_pages < PDF_TABLE_PARALLEL_MIN_PAGES (40) ─► serial
       └─ else: split pages into PDF_TABLE_WORKERS (8) contiguous ranges
                ProcessPoolExecutor, one worker per range
                each worker: pdfplumber.open() → extract_tables() → flush_cache()
                any failure ─► fall back to serial (never fails the ingest)
```

**Why processes, not threads.** pdfplumber is pure-Python and CPU-bound, so threads
would serialize on the GIL. It costs ~60 ms/page *whether or not the page has a table*,
and there is no cheap pre-filter — PyMuPDF's `find_tables` costs about as much as the
extraction itself. Splitting across processes is the only lever.

`flush_cache()` per page is load-bearing: pdfplumber retains parsed page objects, and a
500-page document would otherwise hold all of them.

### Structure detection — building the node tree

Headings are detected by regex, and a running `(chapter, section)` cursor assembles a
`section_path` for every body chunk:

```
HEADING_RE          ^(CHAPTER n | SECTION n | 1.2.3 Title | ALL CAPS TITLE)$
                    plus: any all-caps line of ≤12 words
                    bounded to 4–120 characters

CHAPTER_RE   ──► current_chapter = new chapter node, current_section = None
SECTION_RE   ──► current_section = new section node, parented to current_chapter
NUMBERED_RE  ──► same (matches "3.2.1 Bearing defect frequencies")
otherwise    ──► buffer the line as body text
```

Non-heading lines accumulate in a buffer that is flushed into a `clause` node whenever a
heading arrives or the page ends. Clauses shorter than 20 characters are discarded at
this stage. A clause's `title` is the first 80 characters of its own body — these
documents have no per-paragraph headings to borrow.

Node types produced: `chapter` · `section` · `clause` · `table`.

**Heading back-fill.** A heading node has no text of its own, which would make it
unembeddable. Each textless node is given a 500-character preview built from its first
three children:

```python
children_by_parent = defaultdict(list)      # built once, O(n)
for node in nodes:
    if node.parent_id: children_by_parent[node.parent_id].append(node)
for node in nodes:
    if not node.text:
        node.text = " ".join(c.text for c in children_by_parent[node.node_id][:3])[:500]
```

The `defaultdict` index is deliberate. Scanning all nodes per textless node was O(n²)
and degraded sharply on heading-rich documents — a real fix, covered by
`tests/test_extraction_unit.py`.

### Chunking

```python
_split_text(text, max_chars=900)
    collapse all whitespace
    if len <= 900: return [text]
    split on sentence boundaries: (?<=[.!?])\s+
    greedily pack sentences into ≤900-char parts
```

**900 characters, sentence-aligned, zero overlap.** The splitter never cuts mid-sentence,
but it also never repeats a sentence across two chunks. On technical prose that means a
derivation spanning a chunk boundary is severed — the setup lands in one vector, the
result in another, and neither retrieves well on its own. There is currently no config
knob for this; `max_chars` is a Python default argument in two modules.

Node type maps to chunk type:

| node_type | chunk_type |
|---|---|
| `chapter` | `chapter_summary` |
| `section` | `section_summary` |
| `clause` | `clause` |
| `table` | `table` |

Chunk ids are `chunk_000001`, `chunk_000002`, … **restarting at 1 in every document.**
This is why every downstream cache, dedupe key, and lookup must be keyed by
`(doc_id, chunk_id)` and never `chunk_id` alone.

### Figure asset extraction

```
for each page, for each embedded image:
    doc.extract_image(xref)
    skip if width < MIN_IMAGE_PX (80) or height < 80      ← rules out rules, bullets, logos
    write to assets/page{NNN}_img{NN}.{ext}
    emit an image chunk:
        text        = "Figure on page {N}"                ← a PLACEHOLDER, 18-ish chars
        meta.asset_path = "assets/page017_img00.png"
```

That placeholder text is the crux of §7. The image chunk exists, points at a real file
on disk, and carries no searchable content until the vision model gives it some.

---

## 5. Step 2b — The Docling extractor (scanned, hybrid, DOCX)

[app/ingestion/document_multimodal_pipeline.py](app/ingestion/document_multimodal_pipeline.py) · 656 lines

Docling gives layout-aware extraction with real table structure and OCR, at a much
higher memory and time cost. Large technical PDFs crashed it with `std::bad_alloc`, so
this module is built defensively around that.

### Bounded page windows

```
windows = [(1,10), (11,20), (21,30), …]           DOCLING_PAGE_BATCH = 10
open the source PDF ONCE
for each window:
    split pages [start,end] into a temp sub-PDF   (fitz insert_pdf)
    converter.convert(sub_pdf)                    ← parses 10 pages, not 500
    process items, page_offset = start - 1        ← restores absolute page numbers
    delete result; unlink sub-pdf; gc.collect()
finally: close source, rmtree temp dir
```

Each conversion sees only a handful of pages, so peak memory is bounded regardless of
document length. Opening the source once rather than per window matters at scale — a
500-page PDF would otherwise reopen it 50 times. A window that throws is logged and
skipped; the run continues.

Converter settings ([docling_config.py](app/ingestion/docling_config.py) `build_converter`)
are all tuned low for the same reason: `DOCLING_NUM_THREADS=2`, `QUEUE_MAX=4`,
`LAYOUT_BATCH=4`, `TABLE_BATCH=4`, `OCR_BATCH=2`, `generate_page_images=False`. Light
mode (auto-enabled past 15 MB or 80 pages) additionally forces OCR off and caps
`images_scale` at 0.75.

### The degenerate-extraction guard

```python
coverage = len(pages_with_content) / total_pages
if coverage < DOCLING_MIN_PAGE_COVERAGE (0.5):
    raise DegenerateExtraction(...)
```

An OOM inside Docling does not always raise — it can silently return a document with
most pages empty. Without this guard the pipeline would happily index a 5%-complete
book and report success. On this exception the caller falls back to the memory-safe
PyMuPDF path, so a hard Docling failure degrades to the fast extractor rather than
failing the ingest.

### Section-stack bounding

```python
MAX_SECTION_DEPTH = 6

def _push_section(stack, title, level):
    if isinstance(level, int) and 0 <= level < MAX_SECTION_DEPTH:
        del stack[level:]              # truncate deeper levels — a real tree pop
    stack.append(title)
    if len(stack) > MAX_SECTION_DEPTH:
        del stack[: len(stack) - MAX_SECTION_DEPTH]   # shed OLDEST, keep innermost
```

The stack was originally appended to and never popped, so `section_path` accumulated
every heading in the document — multi-kilobyte paths duplicated into every node, every
chunk, and every FAISS metadata entry. Two details in the fix are easy to get backwards:
truncation uses Docling's own tree `level`, and when the cap is hit the *front* is
dropped, because the innermost headings are the relevant context. Trimming the tail
instead would freeze `section_path` on the document's opening headings forever.

### Item routing and fallbacks

| Docling item | Becomes | Notes |
|---|---|---|
| `TextItem` matching a heading pattern | `section` node | pushes the section stack |
| `TextItem` otherwise | `clause` node | titled by the enclosing section |
| `TableItem` | `table` node | `export_to_markdown()`, kept in `meta.table_markdown` |
| `PictureItem` | `image` node | `item.get_image(doc).save(...)` → `assets/figure_NNNN.png` |

Three layered fallbacks:

1. `docling_core` types unimportable → `doc.export_to_markdown()` + `_chunk_markdown()`,
   which reconstructs headings from `#` depth and applies the same stack bounding.
2. Docling produced **no** figure nodes → `_extract_pdf_images()` sweeps the PDF with
   PyMuPDF so figures are never lost to a layout-model miss.
3. Docling raises anything at all (including `DegenerateExtraction`) → the whole
   extraction reruns on `document_pdf_pipeline`.

DOCX adds a fourth: Docling first, then `python-docx` (`_extract_docx_basic`) walking
paragraphs by style name and tables cell by cell.

---

## 6. Step 3 — Vision enrichment: what makes this RAG multimodal

[app/ingestion/vision_enrichment.py](app/ingestion/vision_enrichment.py) · 491 lines

Body text stays with the fast local extractor. Only **visual** content goes through the
LLM. Figures and tables take genuinely different paths.

### Figures: caption is prepended

```
asset PNG ──► PIL: verify ≥80×80, convert to RGB, re-encode PNG ──► base64 data URL
          ──► VISION_MODEL, detail="low", max_tokens=550, temperature=0.1
          ──► FIGURE_PROMPT: "chart type, axes labels, units, trends, key values,
                              legends, visible text/numbers. 3-6 sentences."
          ──► chunk["text"] = f"{caption}\n\n{existing}"
              chunk["meta"]["vision_caption"] = caption
```

The original text is *kept* after the caption. On the digital path that original is only
the `"Figure on page N"` placeholder, but the ordering means nothing is ever destroyed.

An unreadable image returns `""` and the chunk is left alone — the code explicitly never
sends a figure job as text-only, because a caption invented without pixels would be
indistinguishable from a real one in the index.

### Tables: caption replaces the text

```
source page rendered at VISION_PAGE_RENDER_DPI (150) ──► base64 PNG
rough pdfplumber extraction (first VISION_TABLE_ANCHOR_CHARS=1500 chars) embedded
                                                          in the prompt as an ANCHOR
          ──► TABLE_PROMPT: "reconstruct THAT table as GitHub-flavored Markdown,
                             then a 2-3 sentence summary with quantities, units,
                             thresholds. Use only what is visible."
          ──► chunk["text"]  = result                    ← REPLACED
              meta["local_table_text"] = original        ← preserved as fallback
              meta["vision_table"]     = result
              meta["table_markdown"]   = result
```

Two things are doing real work here. **The whole page is sent, not a crop** — a table's
meaning usually lives in its caption, footnotes, and units row, which sit outside the
cell grid. And **the rough extraction is passed in as an anchor** so the model knows
*which* table on the page to transcribe; without it, a page with three tables is a
coin flip.

There is a text-only fallback (`TABLE_PROMPT_TEXT_ONLY`) when the source page cannot be
rendered — acceptable for tables because the local extraction already carries the cell
values, which is exactly why the same fallback is refused for figures.

### The per-document cap, and how it prioritises

```python
total = len(table_jobs) + len(figure_jobs)
if VISION_MAX_ELEMENTS > 0 and total > VISION_MAX_ELEMENTS:      # default 150
    table_jobs  = table_jobs[:VISION_MAX_ELEMENTS]
    figure_jobs = figure_jobs[: max(0, VISION_MAX_ELEMENTS - len(table_jobs))]
    logger.warning("Vision cap: ... skipping %d ...")            # never silent
```

**Tables outrank figures.** A table is structured data that is almost always worth a
call; a catalog's thousands of incidental figures are not. The skip is logged with the
exact count and the name of the variable to raise.

One ordering detail worth noting: job descriptors are collected in pass 1, the cap is
applied, and *only then* are source pages rendered for the surviving table jobs — so
tables dropped by the cap never pay the page-rasterization cost.

### Rate limiting: the token bucket

This is the part that took real engineering. Retries alone cannot fix a
tokens-per-minute ceiling, because TPM is a *sustained-rate* limit, not a transient one.

```python
class _TokenBucket:
    capacity = VISION_TPM_LIMIT (200_000) * VISION_TPM_HEADROOM (0.8)
    tokens   = 0.0        # starts EMPTY, not full
    rate     = capacity / 60.0
```

Starting empty is the non-obvious bit: a full bucket would release roughly a minute's
worth of calls instantly before pacing engaged, and that opening burst is exactly what
clips the ceiling. Starting at zero makes calls pace smoothly from the first one.

Cost is estimated per call as `len(prompt)//4 + VISION_MAX_TOKENS + 1100 if image`.
`VISION_IMAGE_TOKEN_EST=1100` is deliberately generous against a `detail=low` image's
actual ~85 tokens, so pacing errs under the ceiling rather than over it.

### Error handling: three distinct classes

```
_call_with_retry(make_call, label, quota_flag)
  │
  ├─ quota / auth error  (401, 403, 429+insufficient_quota, AuthenticationError)
  │     └─ set the SHARED quota_flag → every remaining worker short-circuits to ""
  │        Sleeping cannot recover a depleted billing quota within one run.
  │
  ├─ transient (429 rate-limit, 500, 503, timeouts)
  │     └─ honour the API's retry-after (header or "try again in 1.2s" in the message)
  │        else exponential backoff 1s → 30s, PLUS jitter
  │        up to VISION_MAX_RETRIES (6) attempts
  │
  └─ exhausted → return "", log, continue with the next element
```

Three deliberate choices: the OpenAI client is built with `max_retries=0` so the SDK
never blocks the pipeline with its own backoff sleeps; the quota flag is shared across
all workers via `threading.Event`, so one worker discovering an empty account stops the
other three immediately; and jitter is added to every backoff so four workers hitting
the same limit do not retry in lockstep.

**Enrichment failure never fails ingestion.** A depleted quota logs one warning and the
pipeline proceeds to filter, sanitize, and index — you get a text-only knowledge base
rather than no knowledge base.

### Concurrency model

```
main thread   render all table source pages (PyMuPDF docs are NOT thread-safe)
              │
ThreadPoolExecutor(VISION_CAPTION_WORKERS = 4)
              │  only the network calls run in parallel
              ▼
pool.map(run, jobs)   → results in job order
              │
main thread   merge results back by original chunk index, rewrite chunks.jsonl
```

Workers are capped at 4 by default because low-tier OpenAI accounts have a small
concurrent-request cap and reject bursts with 503 "Too many concurrent requests".

---

## 7. Steps 4 and 5 — Filtering and sanitizing (and a real finding)

### Filter

[app/ingestion/filter_toc.py](app/ingestion/filter_toc.py) — a chunk is dropped if:

| Rule | Test |
|---|---|
| Too short | `len(text) < MIN_CHUNK_CHARS` (**40**) |
| Table-of-contents keyword | matches `table of contents\|contents\|index` **and** `len(text) < 200` |
| Dot-leader density | more than **40%** of lines match `\.{3,}\s*\d+\s*$` |
| Page number only | text is `^\s*\d+\s*$` |

### Sanitize

[app/ingestion/sanitize_section_path.py](app/ingestion/sanitize_section_path.py) —
collapse whitespace, split on `>`, drop consecutive duplicate segments, strip a leading
`CHAPTER n >` / `SECTION n >`, default to `"Unknown Section"`. Citations render from
this field, so it is a display concern, not a retrieval one.

### ⚠ The finding: the vision cap silently deletes figures from the knowledge base

The two steps interact in a way that is not obvious from either one alone, and the live
`cat2` corpus shows it exactly.

An **uncaptioned** image chunk's only text is the placeholder `"Figure on page 17"` —
about 18 characters. `MIN_CHUNK_CHARS` is 40. So every figure the vision cap skipped is
**dropped by the filter before it ever reaches the embedder.**

Measured on disk:

```
cat2:  1,141 image chunks in chunks.jsonl
       1,057 of them under 40 characters      ← uncaptioned placeholders
          84 survive into chunks_sanitized.jsonl

       VISION_MAX_ELEMENTS = 150
       minus 66 table jobs (tables are prioritised)
       = 84 figure jobs                        ← exactly the 84 that survived
```

The arithmetic closes perfectly. `condition_monitoring` confirms it from the other
direction: 52 image chunks, **0** under 40 characters, `enriched_figures = 71 = 52
figures + 19 tables` — under the cap, so every figure was captioned and every figure
survived.

**So `cat2` has 1,141 figure PNGs on disk and 84 of them in the knowledge base.** The
other 1,057 files are unreferenced by any vector: not retrievable, not citable, not
attachable to a vision answer. The cap is not a quality knob that yields lower-fidelity
figures — it is a hard gate on whether a figure exists in the KB at all.

Nothing here is a bug in isolation. The cap logs its skip loudly, the filter's 40-char
minimum is sensible, and vision-before-filter is the right order. The gap is that no
single log line says *"1,057 figures were dropped from the index."*

Worth considering, in rough order of effort:

1. Raise `VISION_MAX_ELEMENTS` past `1141 + 66` and reindex `cat2` — a couple of dollars
   at `detail=low`, and the single highest-value action available for retrieval quality.
2. Make the placeholder carry indexable context — `"Figure on page 17 — <section_path>"`
   would clear 40 characters and keep uncaptioned figures at least findable by section.
3. Exempt chunks with a `meta.asset_path` from the minimum-length rule, so an image
   chunk's survival is never decided by its placeholder's length.

---

## 8. Step 6 — Embedding and indexing

[app/retrieval/embeddings.py](app/retrieval/embeddings.py) ·
[app/retrieval/faiss_index.py](app/retrieval/faiss_index.py)

### The embedding model

| Property | Value |
|---|---|
| Model | `BAAI/bge-small-en-v1.5` |
| Dimensions | 384 |
| Device | CPU |
| Normalization | `normalize_embeddings=True` |
| Query prefix | `"Represent this sentence for searching relevant passages: "` |
| Lifecycle | Module-global singleton behind a `threading.Lock`, warm-loaded at FastAPI startup |

The BGE query instruction is asymmetric by design — it is applied to queries only, never
to indexed passages. It arrives automatically through `HuggingFaceBgeEmbeddings`, which
is why retrieval must route every embed call through `get_embeddings()` rather than
building its own encoder.

### The vector store

```python
documents  = [_chunk_to_document(c) for c in chunks_sanitized]
vectorstore = FAISS.from_documents(documents, embeddings)
vectorstore.save_local(index_dir)     # → index.faiss + index.pkl
```

FAISS `IndexFlatL2` — 384-dim, L2 metric, exhaustive brute force. No IVF, no HNSW, no
product quantization. At corpus scale (3,607 vectors ≈ 5.5 MB of floats) an approximate
index would add tuning surface and recall risk to buy microseconds.

**One index per document**, at `data/documents/{doc_id}/faiss_index/`. There is no
collection concept; `doc_id` is the unit of everything. `load_faiss_index` passes
`allow_dangerous_deserialization=True` because `index.pkl` is a pickle — safe here since
the file is produced locally by this pipeline, and a genuine constraint on ever
accepting an index from an untrusted source.

Metadata written per vector:

```python
chunk_id, chunk_type, page_start, page_end, section_path, node_id,
doc_id, asset_path,
**{every remaining meta key}          # vision_caption, table_markdown,
                                      # local_table_text, title, version, …
```

The `**meta` splat is what carries `vision_caption` and `table_markdown` into FAISS
metadata, so an answer can show the reconstructed Markdown table without re-reading
`chunks_sanitized.jsonl`.

### Why per-document indexes

`retrieve_across_documents` already merges and reranks on the merged pool, so splitting
by document costs nothing at query time and buys:

- Free incremental re-ingest — one document reindexes without touching the others
- Per-document cache invalidation
- `doc_ids` filtering with no metadata-filter machinery
- A failed ingest that cannot corrupt a shared index

At ~8 documents that is roughly 30k × 384 floats ≈ 46 MB and ~15 ms of serial search — a
rounding error against the ~900 ms rerank. The comment in the code sets the revisit point
at ~25 documents / ~200k vectors.

---

## 9. The knowledge base on disk

```
data/
├── documents/{doc_id}/
│   ├── source.pdf | source.docx        the original upload, byte-for-byte
│   ├── document_registry.json          title, department, version, source_format, pdf_kind
│   ├── structured_nodes.json           the full node tree (parents, children, section paths)
│   ├── chunks.jsonl                    raw chunks — MUTATED IN PLACE by vision enrichment
│   ├── chunks_clean.jsonl              after TOC/short-chunk filtering
│   ├── chunks_sanitized.jsonl        ★ what was embedded; the KB's source of truth
│   ├── assets/                         extracted figure PNG/JPEG
│   ├── faiss_index/
│   │   ├── index.faiss                 the vectors
│   │   └── index.pkl                   docstore + metadata
│   └── status.json                     status, chunk_count, enriched_figures, pdf_kind
│
├── machines/{machine_id}/profile.json
├── graph_checkpoints.sqlite
└── .ingest.lock                        cross-process ingest mutex
```

Everything under `data/` is gitignored and fully reproducible from `source.pdf` — the
only irreproducible cost is the vision spend.

`status.json` is the readiness contract. `IndexService.is_ready()` reads exactly one
field (`status == "ready"`), and `list_ready_doc_ids()` treats **every subdirectory of
`DOCUMENTS_DIR` as a document**. That is why `MACHINES_DIR` is deliberately a sibling of
`documents/` and never a child — anything stored underneath would surface in the document
picker as a failed document. Any future `signals/` or `charts/` directory must follow the
same rule.

### Caching

`IndexService` ([app/retrieval/index_service.py](app/retrieval/index_service.py)) is a
lock-guarded singleton holding three caches:

| Cache | Contents | Invalidation |
|---|---|---|
| `_cache` | `{doc_id: FAISS}` | `invalidate(doc_id)` on re-ingest |
| `_chunk_cache` | `{doc_id: {chunk_id: chunk}}` | same |
| `_ready_cache` | `list[doc_id]` | 5-second TTL, plus explicit `invalidate_ready()` |

The chunk map exists because a single chunk lookup previously re-parsed the entire
`.jsonl` (~1,700 `json.loads` calls), and an answer citing six figures did that six
times. The ready-list TTL exists because `list_ready_doc_ids()` runs on *every* chat
request and otherwise walks the directory and parses one `status.json` per document;
`_write_status` calls `invalidate_ready()` so a newly-ready document appears immediately
rather than waiting out the TTL.

### Ingest locking

[app/ingestion/ingest_service.py](app/ingestion/ingest_service.py) — a cross-process
mutex at `data/.ingest.lock`, acquired with `O_CREAT | O_EXCL` and holding
`"{pid} {timestamp}"`.

**Why a project-global lock rather than per-document.** Ingest is bounded by the OpenAI
tokens-per-minute limit, and each process paces itself to a *fraction* of that limit. Two
concurrent ingests would each pace to that fraction and their sum would exceed the account
ceiling — the exact cause of the 429 storms the token bucket was built to prevent. A
second ingest fails fast with `IngestBusyError` and a message naming the holding PID.

A stale lock is reclaimed automatically when the owning PID is gone (checked via
`OpenProcess` on Windows, `os.kill(pid, 0)` elsewhere) or the lock is older than 6 hours,
so a crash never wedges ingest permanently. The lock sits **outside** the pipeline's
`try/except` so a busy-error propagates cleanly instead of being recorded as a pipeline
failure with a half-created document directory.

---

## 10. The read path — retrieval

[app/retrieval/retrieval_service.py](app/retrieval/retrieval_service.py) · 260 lines

There is no LangChain retriever object anywhere. No MMR, no `ParentDocumentRetriever`,
no `MultiVectorRetriever`, no BM25. Everything is explicit.

```
query
  │
  ├─ embed ONCE (only when >1 index) via get_embeddings().embed_query
  │    reused across every index — otherwise similarity_search_with_score
  │    re-embeds the identical string per document
  │
  ├─ per document index:
  │    FAISS search, k = max(RETRIEVAL_CANDIDATE_K=30, top_k × 5)
  │    optional chunk_types filter (table_search uses this)
  │    hybrid rescore:
  │        vector_score = 1.0 / (1.0 + L2_distance)
  │        kw_score     = |query keywords in text| / |query keywords|
  │        type_boost   = +0.12
  │        combined     = 0.7 × vector + 0.3 × keyword + boost
  │
  ├─ merge across documents, sort by hybrid_score
  │
  ├─ two-level dedupe
  │    1. identity (doc_id, chunk_id)      ← doc_id REQUIRED: ids restart per document
  │    2. normalized text                  ← same passage in re-uploads / overlapping editions
  │       pre-sorted, so first seen (best-scoring) wins
  │
  └─ cross-encoder rerank the top RERANK_POOL_K=48 → return top_k
```

**The serial per-index loop is intentional.** FAISS search is ~7 ms across 24 indexes; the
cross-encoder rerank is ~900 ms — over 99% of retrieval time. Threading the search
measurably added overhead for no gain and the parallelism was removed. Retrieval is made
faster by shrinking `RERANK_POOL_K`, never by parallelising search.

**The reranker must run once on the merged pool.** `cross-encoder/ms-marco-MiniLM-L-6-v2`,
lazy singleton behind a lock. Reranking per document and then merging would compare
unbounded, frequently negative cross-encoder logits against 0–1 hybrid scores — an
incoherent ordering. On any reranker failure the hybrid ordering is preserved, so `score`
stays on one scale either way.

### The type boost, and its blind spot

```python
TABLE_SIGNALS  = {table, row, column, value, values, data, cell, cells}
FIGURE_SIGNALS = {chart, graph, figure, diagram, plot, image,
                  picture, visual, trend, axis, axes}
```

These are generic English. **No vibration term triggers the figure boost** — not
`spectrum`, `waterfall`, `cascade`, `orbit`, `bode`, `nyquist`, `envelope`, `fft`,
`waveform`, or `polar`. "Show me the envelope spectrum of a bearing fault" gets no figure
boost at all.

### The tokenizer, and its larger blind spot

```python
def _extract_keywords(query):
    tokens = re.findall(r"[a-zA-Z0-9]+", query.lower())
    return {t for t in tokens if len(t) > 2 and t not in STOPWORDS}   # 105 stopwords
```

Length `> 2` and splitting on every non-alphanumeric means the keyword half of the hybrid
score discards or shreds exactly this domain's vocabulary:

| Query term | Becomes |
|---|---|
| `1x`, `2x`, `Hz`, `mm`, `g`, `dB` | **dropped** (≤2 chars) |
| `mm/s` | `{mm, s}` → both dropped |
| `10816-3` | `{10816, 3}` |
| `4.5` | `{4, 5}` |
| `BPFO`, `envelope`, `bearing` | survive intact |

30% of the hybrid score is effectively blind to units, orders, and standard numbers. This
is the single highest-leverage unfixed item in the retrieval layer.

### Follow-up handling

Ten regex patterns (`tell me more`, `elaborate`, `expand on`, `go deeper`, `clarify`,
`in more detail`, …). On a match the retrieval query becomes `"{last_question}
{question}"`, so "explain that in more detail" retrieves against the previous topic
rather than against six words of pronouns.

### The fourth multimodal mechanism

Captioning is three of four. The fourth runs at **answer time**: retrieved `image` /
`diagram` chunks have their actual PNG bytes base64-attached to the final synthesis call
(the `vision_answer` node in graph mode, `_final_answer_with_vision` in agent mode). The
caption gets the figure *retrieved*; the pixels then get it *read*.

This is the second consequence of §7 — a figure dropped from the index can never reach
this stage either, because nothing retrieves it.

---

## 11. Tuning reference

| Variable | Default | Effect | When to change |
|---|---|---|---|
| `VISION_MAX_ELEMENTS` | 150 | Vision calls per document | **Raise before ingesting image-heavy books.** Below the figure count it silently removes figures from the KB — see §7 |
| `VISION_IMAGE_DETAIL` | `low` | ~85 tokens/image vs thousands | `high` on a higher account tier for maximum table fidelity |
| `VISION_CAPTION_WORKERS` | 4 | Concurrent vision calls | Raise once the account tier allows; 503 "too many concurrent requests" means lower it |
| `VISION_TPM_LIMIT` | 200000 | Token-bucket ceiling | Match your account's actual TPM; `0` disables pacing |
| `VISION_TPM_HEADROOM` | 0.8 | Fraction of TPM used | Lower if still seeing sustained 429s |
| `VISION_PAGE_RENDER_DPI` | 150 | Table page rasterization | Raise for dense numeric tables |
| `MIN_CHUNK_CHARS` | 40 | Minimum indexed chunk | The gate that drops uncaptioned figures |
| `RERANK_POOL_K` | 48 | Candidates reaching the reranker | **Raise with the corpus, or recall silently drops.** Also the main latency lever |
| `RETRIEVAL_CANDIDATE_K` | 30 | Per-index candidates | Floor; effective value is `max(30, top_k × 5)` |
| `PDF_TABLE_WORKERS` | 8 | pdfplumber processes | Match core count |
| `DOCLING_PAGE_BATCH` | 10 | Pages per Docling window | Lower if still hitting OOM |
| `DIGITAL_PDF_USE_DOCLING` | false | Route digital PDFs to Docling | Richer tables, much slower |

### Declared but not wired

`RETRIEVAL_CANDIDATE_K_MULTI` (15) and `RETRIEVAL_MULTI_DOC_THRESHOLD` (3) are defined in
[app/config/retrieval.py](app/config/retrieval.py) and referenced by nothing else in the
codebase. The intent is documented in the config comment: past 3 indexes the per-index
candidate count should drop so the merged pool stays near the rerank budget instead of
building 240 candidates and discarding most of them on the crude hybrid score alone.
Until it is wired, adding documents grows the merged pool linearly while `RERANK_POOL_K`
stays fixed — recall degrades quietly as the corpus grows.

`CHUNK_MAX_CHARS` / `CHUNK_OVERLAP_CHARS` no longer exist; they were removed in the
dead-config cleanup. The 900-char, zero-overlap splitter is currently a Python default
argument in two modules, not configuration.

---

## 12. Known limitations

| Limitation | Detail |
|---|---|
| **Uncaptioned figures are dropped, not degraded** | §7. `cat2` has 1,141 figure assets and 84 indexed |
| **Zero chunk overlap** | 900-char sentence-aligned splits sever derivations that cross a boundary |
| **Keyword scoring is domain-blind** | `1x`, `Hz`, `mm/s`, `10816-3` are dropped or shredded |
| **Type boost has no vibration vocabulary** | `spectrum`, `orbit`, `envelope`, `bode` trigger nothing |
| **No `diagram` chunks are ever produced** | Both extractors emit `image`; `diagram` is handled everywhere downstream but never created |
| **ISO 10816-3 is not in the corpus** | The standard is at the repo root, un-ingested. ISO answers compute from a hardcoded table with no retrievable text behind them |
| **`index.pkl` is a pickle** | Loaded with `allow_dangerous_deserialization=True`; never accept an index from an untrusted source |
| **`ready_documents` includes test fixtures** | `test_sample_docx` (3 chunks) is left behind by `test_pipeline.py` and appears as a real document |
| **Re-ingest re-pays the vision cost** | There is no caption cache keyed by asset hash |

---

## 13. Highest-value next actions

1. **Raise `VISION_MAX_ELEMENTS` above 1,207 and reindex `cat2`.** Recovers 1,057 figures
   into the knowledge base. A couple of dollars at `detail=low`. Nothing else available
   improves retrieval this much for this little.
2. **Fix `_extract_keywords`** to keep short alphanumeric tokens and unit strings.
   Restores 30% of the hybrid score on the queries this system actually receives.
3. **Ingest `ISO 10816-3-2009.pdf` first**, then the remaining five root PDFs — all
   classify as `digital`, so no OCR and no Docling.
4. **Add vibration terms to `FIGURE_SIGNALS`.** A one-line change.
5. **Wire `RETRIEVAL_CANDIDATE_K_MULTI`** before the corpus reaches ~8 documents.
6. **Give uncaptioned image chunks indexable placeholder text**, so the vision cap
   degrades figure quality instead of deleting figures.
