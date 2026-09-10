# Knowledge-base agent

Cited answers from the indexed vibration books and standards. Terminal only — no
routes, no UI, nothing wired into the dashboard.

```powershell
cd vibrationbot
.\.venv\Scripts\python.exe -m kb_agent docs                                    # what's in the library
.\.venv\Scripts\python.exe -m kb_agent search "ball pass frequency outer race" # retrieval only, no API key
.\.venv\Scripts\python.exe -m kb_agent ask "how do gear mesh sidebands indicate a fault?"
```

> **Use `vibrationbot/.venv`, not `backend/.venv`.** This repo has two virtual
> environments. `backend/.venv` holds FastAPI and SQLAlchemy for the API server and has
> **no** langchain, faiss or sentence-transformers, so running `kb_agent` under it fails
> with `ModuleNotFoundError: No module named 'langchain_core'`. Calling
> `.\.venv\Scripts\python.exe` explicitly, as above, works regardless of which
> environment happens to be activated. To activate instead:
> `deactivate` (if another venv is on), then `.\.venv\Scripts\Activate.ps1`.

The design rule, inherited from the rest of this project: **the model never supplies a
number.** Here it never supplies a *fact* either. Every claim traces to a numbered
excerpt, and the excerpt is printed beside the answer so you can check it.

---

## The corpus, as it actually stands

```
cat2                  Mobius Institute Category 2 course material   1841 chunks, 150 figures
condition_monitoring  Condition Monitoring with Vibration Signals   1766 chunks,  71 figures
test_sample_docx      HR DOCX Manual (ingestion test fixture)          3 chunks
```

**Two real books, not four.** The other PDFs sitting in `vibrationbot/` — ISO 10816-3,
Cat3, and three more vdoc.pub textbooks — are *not ingested*. They are files on disk that
nothing has indexed. To add them:

```bash
python scripts/ingest_folder.py .          # ingest every PDF in a folder
python -m kb_agent docs                    # confirm they appear
```

Ingestion is slow (vision captioning runs per figure) and costs API calls, so it is a
deliberate step, not something this agent does for you.

`test_sample_docx` is an HR manual left over from testing the ingest pipeline. It is
harmless — three chunks that never outrank real vibration content — but exclude it with
`--doc cat2 --doc condition_monitoring` if you want clean provenance.

---

## Commands

| Command | Calls a model? | Use it for |
|---|---|---|
| `docs` | no | What's indexed, how big, how many figures captioned |
| `search "..."` | **no** | Is this topic in the corpus at all? Debugging a bad answer |
| `passage <doc_id> <chunk_id>` | no | Read one passage in full |
| `ask "..."` | yes | A cited answer |
| `check` | yes | Smoke test: corpus reachable, search works, model responds |

Useful flags:

```bash
--doc cat2 --doc condition_monitoring   # restrict to specific books (repeatable)
--top-k 10                              # more excerpts per search
--type table                            # search only tables (search command)
--full                                  # untruncated passage text (search command)
--trace                                 # every model call and search, with timings
--sources 10                            # print more source excerpts (ask command)
--json                                  # the raw result envelope
```

**First run in a process costs ~20 seconds** loading the cross-encoder reranker. Every
search after that is ~1 second. `ask` pays it once no matter how many searches it runs, so
one `ask` with six searches is far cheaper than six separate `search` calls.

---

## How it works

```
question
   |
   v
[1] PLAN        one structured model call -> 2-4 search queries
   |
   v
[2] SEARCH      all planned queries run in code, results pooled and deduped
   |
   v
[3] TOOL LOOP   model reads the pool, runs more searches or fetches full passages
   |            (bounded: KB_MAX_ITERATIONS iterations)
   v
[4] ANSWER      written from the stored full text, every claim cited [n]
```

### Why planning is a separate forced step

The obvious design is to hand the model the tools and tell it in the prompt to decompose
the question first. That was the first implementation, and **it did not work.**

Asked to contrast misalignment with unbalance, `gpt-4o-mini` searched
`"shaft misalignment symptoms"` and `"unbalance symptoms"` — the exact generic phrasings
the prompt told it to avoid. Both hit glossary definitions instead of the diagnosis
chapters, and the agent reported it could not answer a question the corpus answers well.
Strengthening the prompt wording changed nothing.

So the plan became a typed object the model must fill in (`SearchPlan.queries`), executed
in code before the loop starts. The decomposition now happens whether or not the model
would have chosen it. The same question, same model, after the change:

```
plan searches   shaft misalignment axial vibration symptoms
                shaft unbalance vibration spectrum characteristics
                vibration harmonics misalignment vs unbalance
                radial vibration amplitude misalignment and unbalance
```

...and a correct, four-way cited answer. **A structural fix beat a prompt fix.** That is
the same lesson as `tools_domain.py`, where machine facts are injected rather than accepted
as model arguments.

### Why the model reads snippets and the answer reads full text

Tools return 700-character snippets. The full passage goes into a `PassageStore` the model
never sees, and the *answer* prompt is built from that store at 1800 characters per
excerpt. Two reasons: six full book passages across four iterations would fill the context
with text the model skims, and a passage cannot be quietly reworded on its way through a
tool transcript.

Same split as `app/chat/graph/tools_domain.py` — the model sees a summary, the real payload
travels where it cannot be paraphrased.

### Why the answer policy is stricter than the chatbot's

Graph mode uses a tiered policy: `<COMPUTED>` results outrank `<EXCERPTS>`, because it has
deterministic tools producing real numbers. This agent computes nothing, so the older and
stricter rule applies — everything from the excerpts, or it says it could not find it.

For calculations, use the domain tools, which are unit-tested against published values:

```bash
python scripts/vib_cli.py bearing --designation "SKF 6205-2RS" --rpm 1750
python scripts/vib_cli.py iso --vrms 4.9 --power-kw 55 --type pump --foundation rigid
```

---

## What to ask, and how to phrase it

The single biggest factor in answer quality is **whether your question names an
observable**. The books are organised by symptom and mechanism, so a query carrying
`axial`, `radial`, `1X`, `2X`, `harmonic`, `phase`, `sideband`, `spectrum` or `waveform`
lands in a diagnosis chapter. A query with only a fault name lands in a glossary.

The planner adds these for you, but it works from what you gave it — a richer question
produces a richer plan.

### Questions this corpus answers well

Coverage is uneven, and it is worth knowing where it is deep. Mentions in the indexed text:

| Topic | cat2 | condition_monitoring |
|---|---:|---:|
| resonance / natural frequency | 229 | 37 |
| gear mesh sidebands | 154 | 4 |
| motor electrical faults (rotor bar, stator) | 82 | 22 |
| cavitation | 52 | 3 |
| phase analysis | 48 | 0 |
| vane / blade pass frequency | 43 | 0 |
| soft foot | 40 | 0 |
| bent shaft | 23 | 3 |
| bearing defect stages | 10 | 4 |
| cage frequency / FTF | 10 | 4 |
| rotor and shaft rub | 5 | 1 |
| mechanical looseness | 3 | 1 |
| **oil whirl** | **2** | **5** |

Questions in the deep half, which return well-cited answers:

```bash
python -m kb_agent ask "What are the vibration symptoms that distinguish shaft misalignment from unbalance?"
python -m kb_agent ask "How do sidebands around gear mesh frequency indicate a gear fault?"
python -m kb_agent ask "How is resonance identified and how does it differ from a forcing frequency?"
python -m kb_agent ask "What spectral signature indicates a broken rotor bar in an induction motor?"
python -m kb_agent ask "How does cavitation appear in a pump vibration spectrum?"
python -m kb_agent ask "Why is phase measurement useful when diagnosing a bent shaft?"
python -m kb_agent ask "What is soft foot and how is it detected from vibration?"
python -m kb_agent ask "How does a spectrum change as a rolling element bearing defect progresses?"
python -m kb_agent ask "What is vane pass frequency and what does elevated vane pass vibration indicate?"
```

### A worked example of a correct "not found"

Oil whirl is a classic journal-bearing question, and this corpus cannot answer it:

```
Q: What causes oil whirl in journal bearings and at what frequency does it appear?

I could not find specific information on the causes of oil whirl in journal bearings
or the frequency at which it appears. The searches ... returned excerpts discussing
oil whirl as a source of energy in the sub-synchronous region [9], but did not provide
details on its causes or specific frequency characteristics.
```

The agent ran **eight** searches and pooled 29 excerpts before saying so. Checking the raw
text confirms it: oil whirl appears twice in `cat2`, both times as one item in a list of
sub-synchronous energy sources, and five times in `condition_monitoring`, every one of them
as a label in a machine-learning fault-classification paper rather than an explanation.

**There is no passage explaining the mechanism, so the honest answer is the one it gave.**
A "not found" from this agent is evidence about the corpus, not about the subject. Ingest a
rotordynamics text and the same question will answer.

### Questions to phrase differently

| Instead of | Ask |
|---|---|
| "Is 4.9 mm/s bad?" | "What do the ISO evaluation zones mean and how are the boundaries defined?" — then run `vib_cli.py iso` for the actual zone |
| "What's the BPFO formula?" | "What is Ball Pass Frequency Outer race and what inputs does its calculation need?" |
| "Bearing noise" | "Rolling element bearing outer race defect spectrum" |
| "My pump vibrates" | "Centrifugal pump vane pass frequency vibration causes" |
| "Tell me about vibration" | Anything narrower — a broad query retrieves index pages and tables of contents |

### The equations are missing, and this is not the agent's fault

Displayed formulas did not survive PDF text extraction. In the Mobius material they appear
as empty brackets:

> "We can compute the Ball Pass Frequency Outer race using the formula below. The
> calculation is independent of whether the inner race or outer race is rotating.
> **`[ ( ) ( )]`** This frequency will be non-synchronous..."

The equation was an image in the PDF; the extractor produced brackets. The agent is told
about this and will say the source *does* give a formula at that page but it did not
survive extraction, and cite the page so you can read it yourself. It will not invent the
equation.

So: **ask what a quantity means and what it depends on. Do not ask the agent to quote a
formula, and do not read a missing equation as the book not having one.**

Variable definitions usually *did* survive — `condition_monitoring` p.49 defines Nb, Ssh,
db, Dp and the contact angle in plain prose — so "what inputs does BPFO need?" works where
"what is the BPFO formula?" does not.

### Reading the output

- `[n]` markers in the answer map to the numbered `Sources` block below it.
- A `*` beside a source means the answer actually cited it.
- **`WARNING: the answer cited no excerpt`** means the model wrote from its own knowledge
  despite the prompt. Treat that answer as unverified and re-ask more specifically.
- `--trace` shows every search and its timing, which is how you tell a retrieval problem
  from a reasoning problem.

### When an answer looks wrong

Run the same query through `search` first:

```bash
python -m kb_agent search "your topic in textbook terms" --top-k 10 --full
```

If the passages are bad, the problem is retrieval — re-word toward the books' vocabulary.
If the passages are good but the answer is not, the problem is the answer step, and
`--trace` will show what the model actually saw.

---

## Configuration

Environment variables, all optional:

| Variable | Default | Effect |
|---|---|---|
| `KB_TOP_K` | 6 | Excerpts per search |
| `KB_MAX_ITERATIONS` | 4 | Tool-loop bound — the cost ceiling per question |
| `KB_SNIPPET_CHARS` | 700 | Excerpt text the model reads during the loop |
| `KB_ANSWER_CHARS` | 1800 | Excerpt text in the final answer prompt |
| `KB_ANSWER_EXCERPTS` | 10 | Excerpts carried into the answer |

The model itself comes from the app's settings — `OPENAI_MODEL`, or `LLM_PROVIDER=anthropic`
with `ANTHROPIC_MODEL`.

---

## Relationship to the rest of the project

```
kb_agent/     documents  -> cited prose        (this package)
sql_agent/    sensors    -> measurement rows
app/domain/   numbers    -> computed values, unit-tested
app/chat/     all three, wired into a LangGraph chatbot with a UI
```

Unlike `sql_agent`, this package **does** import `app.retrieval`. The knowledge base *is*
the chatbot's retrieval stack — the same FAISS indexes, embeddings and cross-encoder — and
a second search implementation would give two agents two different answers from one corpus.
Everything above retrieval (planning, tools, prompts, the answer contract) is local to this
package and changeable without touching the chatbot.
