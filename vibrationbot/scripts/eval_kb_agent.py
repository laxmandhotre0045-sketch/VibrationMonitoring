"""Adversarial evaluation of the knowledge-base agent.

Runs a spread of questions and checks each answer against the excerpts it was
actually given, mechanically. The point is not "does the answer read well" --
a fluent answer is exactly what a hallucinating model produces -- but "can
every claim be traced back to retrieved text".

    python scripts/eval_kb_agent.py                 # all questions
    python scripts/eval_kb_agent.py --only absent   # one class
    python scripts/eval_kb_agent.py --json out.json

Four automated checks, in rough order of how badly a failure matters:

DANGLING CITATION
    The answer cites [7] but no excerpt 7 was retrieved. The model invented a
    reference, which is the most direct evidence of fabrication there is.

UNSUPPORTED NUMBER
    A number appears in the answer that appears in none of the cited excerpts.
    Numbers are where hallucination does real damage in this domain -- a
    plausible-looking threshold is worse than no threshold -- and unlike prose
    they can be checked by string comparison. Orders like "1X" and ordinary
    small integers in prose ("two causes") are excluded; everything else has to
    be findable.

UNCITED ANSWER
    Substantive prose carrying no [n] at all. Whatever the prompt said, that
    answer was written from the model's own knowledge.

WRONG REFUSAL BEHAVIOUR
    Questions are labelled with what the corpus can actually support, verified
    beforehand by grepping the raw chunk files. An "absent" question must be
    declined; an "answerable" one must not be.

A question labelled ``absent`` is not a weakness of the agent. Declining it
correctly is the single most important behaviour here: a knowledge base that
answers everything is one that makes things up.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb_agent import KnowledgeBaseAgent  # noqa: E402

logging.disable(logging.WARNING)

# --------------------------------------------------------------------------
# The question set
# --------------------------------------------------------------------------
# kind:
#   answerable  -- the corpus covers this; a refusal is a miss
#   partial     -- the corpus covers PART of it; the answer must give the covered
#                  half with citations AND decline the rest in the same breath.
#                  Oil whirl is the type case: the books name its cause and put
#                  it in the sub-synchronous region, but never give its ratio.
#   absent      -- the corpus does NOT cover this; an answer is a hallucination
#   figure_only -- the fact exists but lives in a figure, so it must not be quoted
#
# The "absent" and "figure_only" rows are the ones that matter. They were
# chosen from measured corpus coverage, not guessed.

QUESTIONS: list[tuple[str, str, str]] = [
    # -- concepts and mechanisms -------------------------------------------
    ("answerable", "definition",
     "What is vibration severity and over what frequency range is it measured?"),
    ("answerable", "mechanism",
     "How does resonance differ from a forcing frequency, and how is it identified?"),
    ("answerable", "diagnosis",
     "What spectral signature indicates a broken rotor bar in an induction motor?"),
    ("answerable", "diagnosis",
     "How does cavitation appear in a pump vibration spectrum?"),
    ("answerable", "diagnosis",
     "What is soft foot and how is it detected from vibration measurements?"),
    ("answerable", "diagnosis",
     "How do sidebands around gear mesh frequency indicate a gear fault?"),
    ("answerable", "comparison",
     "What are the vibration symptoms that distinguish shaft misalignment from unbalance?"),
    ("answerable", "procedure",
     "Why is phase measurement useful when diagnosing a bent shaft?"),
    ("answerable", "concept",
     "What is vane pass frequency and what does elevated vane pass vibration indicate?"),
    ("answerable", "concept",
     "What is the cage frequency of a rolling element bearing and why is it non-synchronous?"),
    ("answerable", "progression",
     "How does the spectrum change as a rolling element bearing defect progresses?"),
    ("answerable", "signal_processing",
     "What is the purpose of a Hann window in FFT analysis and what does it cost?"),

    ("answerable", "signal_processing",
     "What is envelope detection and why is it used for rolling element bearing faults?"),
    ("answerable", "signal_processing",
     "What does the time waveform show that the spectrum does not?"),
    ("answerable", "signal_processing",
     "Why is averaging used when collecting a spectrum, and what does overlap processing do?"),
    ("answerable", "instrumentation",
     "When should a proximity probe be used instead of an accelerometer?"),
    ("answerable", "diagnosis",
     "How does mechanical looseness appear in a vibration spectrum?"),
    ("answerable", "diagnosis",
     "What frequencies are generated by a belt drive and how are belt faults identified?"),

    # -- was "partial" against the 2-book corpus; cat3 changed that ---------
    # Ingesting Cat 3 added a whole Journal Bearing Analysis chapter, which
    # gives both the causes (p.448) and the 0.38X-0.48X ratio (p.448). Ground
    # truth is a property of the corpus, not of the question, so the label had
    # to move when the corpus did.
    ("answerable", "journal_bearing",
     "What causes oil whirl in journal bearings and at what frequency does it appear?"),

    # -- must decline ------------------------------------------------------
    ("absent", "out_of_scope",
     "What is the recommended lubricating oil change interval for a Cummins QSK60 diesel engine?"),
    ("absent", "not_in_corpus",
     "What does API 610 specify as the maximum allowable vibration for a centrifugal pump?"),

    # -- an equation that survived extraction MANGLED: quote, never tidy ---
    # Regression test for an observed bug. The source reads
    #   "BPFO = NbSsh 2 ( 1  db Dp cos )"
    # with the division bar, the fraction bar and the minus sign all lost. The
    # agent used to "helpfully" restore two of the three and drop the divide by
    # two, producing a clean-looking formula that doubles every BPFO.
    ("verbatim", "equation",
     "What is the formula for Ball Pass Frequency Outer race and what inputs does it need?"),

    # -- a scoped table value: must refer, not answer ----------------------
    # Regression test for the worst error this agent produced, and for the
    # worse one this comment used to contain.
    #
    # It previously read "a 55 kW pump is Group 2, so rigid B/C is 2,8 mm/s".
    # That is wrong. ISO 10816-3 groups pumps by DRIVER ARRANGEMENT, not by
    # rated power: Group 3 with a separate driver, Group 4 with an integrated
    # one, at any power. Groups 1 and 2 are power-banded and do not contain
    # pumps at all. A 55 kW pump with a separate driver on a rigid foundation
    # is Group 3, whose B/C boundary is 4,5 mm/s -- the very figure the old
    # check rejected as "wrong machine group".
    #
    # So the eval demanded the wrong number and failed the right one. It
    # encoded the same misreading the agent had, which is why neither caught
    # the other. The rule itself lives in app/domain/iso10816.py and is pinned
    # by tests/test_domain_iso.py; nothing here should restate it.
    #
    # The expectation now is behavioural: this agent must decline and name
    # iso_agent. Numbers are checked in iso_agent's tests, against the
    # unit-tested tables rather than a model's reading of a PDF.
    ("scoped_value", "table_value",
     "What is the ISO 10816-3 Zone B to Zone C boundary in mm/s for a 55 kW pump on a rigid foundation?"),
]

# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

CITE_RE = re.compile(r"\[(\d{1,2})\]")
#: Numbers worth checking. Orders ("1X"), list counts ("three causes") and
#: bare small integers in prose are excluded -- they are language, not data.
NUMBER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?![\w])")
ORDER_RE = re.compile(r"\d+\s*[xX]\b")
#: Phrasings the model actually uses to decline. Collected from observed runs
#: rather than guessed -- the first version missed "not specified in the
#: indexed excerpts" and "not explicitly stated", and so scored three correct
#: refusals as failures. A refusal detector that is too narrow makes an honest
#: agent look like a hallucinating one, which is the wrong way to be wrong.
REFUSAL_MARKERS = (
    "could not find", "not in the indexed", "do not provide", "does not provide",
    "not provided", "no excerpts", "did not survive", "not available in",
    "not found", "not covered", "no information", "not specified",
    "do not specify", "does not specify", "not explicitly stated", "not stated",
    "not included in the excerpts", "are not included", "is not included",
    "cannot be determined", "not detailed",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).lower()


def check_dangling(answer: str, labels: set[int]) -> list[str]:
    cited = {int(n) for n in CITE_RE.findall(answer or "")}
    return [f"[{n}]" for n in sorted(cited - labels)]


#: Standards are named by number. "ISO 10816-3", "API 610", "ISO 7919" are
#: identifiers, not measurements, and flagging them as unsupported data
#: penalises an answer for naming the standard it is quoting -- which is
#: something the system prompt explicitly requires it to do.
STANDARD_REF_RE = re.compile(
    r"\b(?:ISO|API|ANSI|IEC|BS|DIN|ASTM|AGMA|NEMA)\s*[-\s]?\d[\d.\-/]*", re.IGNORECASE
)


def check_numbers(answer: str, evidence: str, question: str = "") -> list[str]:
    """Numbers in the answer that appear nowhere in the retrieved excerpts."""
    body = ORDER_RE.sub(" ", answer or "")           # 1X / 2X are orders, not data
    body = CITE_RE.sub(" ", body)                    # [13] is a citation marker
    body = STANDARD_REF_RE.sub(" ", body)            # ISO 10816-3 is a name
    # The question is part of the haystack: an answer restating "API 610" or
    # "55 kW pump" from the question is quoting the asker, not inventing data.
    haystack = _norm(evidence) + " " + _norm(question)
    missing: list[str] = []
    for raw in NUMBER_RE.findall(body):
        value = raw.rstrip("0").rstrip(".") if "." in raw else raw
        if len(value) <= 1:                          # "two of three" style prose
            continue
        if value in haystack or raw in haystack:
            continue
        # 3.5 may be written 3.50 in the source, and 1000 as 1,000.
        if value.replace(".", ",") in haystack or f"{int(float(raw)):,}" in haystack:
            continue
        missing.append(raw)
    return sorted(set(missing))


def is_refusal(answer: str, scope: str = "lead") -> bool:
    """Did the answer decline?

    ``scope`` matters. For a question the corpus cannot support, the refusal
    has to LEAD -- an answer that asserts for two paragraphs and hedges at the
    end has already misled the reader. For a partly-supported question the
    opposite is true: the prompt tells the model to answer what it can and mark
    the gap in one line at the END, so the marker must be looked for anywhere.
    """
    text = _norm(answer)
    window = text if scope == "anywhere" else text[:400]
    return any(m in window for m in REFUSAL_MARKERS)


#: Multi-word technical terms carry the subject of a question. If a bullet
#: asserts something about "oil whirl" and cites [6], excerpt 6 had better
#: contain the words "oil whirl" -- otherwise the model has bridged two
#: neighbouring topics the corpus keeps apart and dressed the bridge as
#: sourced. Single words are too common to test this way.
TOPIC_STOPWORDS = {
    "what", "when", "why", "how", "does", "the", "and", "for", "from", "with",
    "that", "this", "are", "is", "it", "in", "of", "to", "a", "an", "at",
    "used", "show", "not", "its", "do", "be", "on", "or", "which", "should",
    "appear", "indicate", "mean", "give", "need", "needs", "cause", "causes",
}


def question_topics(question: str) -> list[str]:
    """Distinctive two-word phrases from the question."""
    words = [w for w in re.findall(r"[a-z]+", question.lower())
             if w not in TOPIC_STOPWORDS and len(w) > 2]
    return [f"{a} {b}" for a, b in zip(words, words[1:])]


#: Letter-spaced chapter banners ("C H A P T E R 4  S I G N A L P R O C E S S
#: I N G") sit at the head of most chunks and would let any word in a chapter
#: title satisfy a topic test for the whole chapter. Stripped before matching.
BANNER_RE = re.compile(r"(?:\b[a-z]\s+){4,}", re.IGNORECASE)
BOILER_RE = re.compile(
    r"\d{4}-\d{4} mobius institute|all rights reserved|www\.\S+|produced by \S+",
    re.IGNORECASE,
)


#: Marks a sentence as asserting an absence rather than a fact.
NEGATION_RE = re.compile(
    r"\b(do(es)? not|did not|does nt|is not|are not|no longer|never|without|"
    r"not (mention|specify|state|provide|include|cover|address|detail))\b",
    re.IGNORECASE,
)


def _excerpt_body(text: str) -> str:
    """Excerpt text with chapter banners and publisher furniture removed."""
    return _norm(BOILER_RE.sub(" ", BANNER_RE.sub(" ", text or "")))


def check_topic_match(answer: str, sources: list[dict], question: str) -> list[str]:
    """Flag a citation attached to a claim its excerpt does not discuss.

    Matching is deliberately loose: a claim about "belt faults" is satisfied by
    an excerpt saying "Belt Damage", because books rarely echo the asker's
    phrasing. Requiring the exact bigram produced three false alarms for every
    real find. Requiring only that ONE distinctive word of the phrase survives
    in the excerpt body kept the real find -- a claim about "overlap
    processing" cited to a passage that discusses only time synchronous
    averaging -- and dropped the noise.
    """
    by_label = {int(s["label"]): _excerpt_body(s.get("text", ""))
                for s in sources if s.get("label") is not None}
    topics = question_topics(question)
    if not topics:
        return []
    problems: list[str] = []
    for line in (answer or "").splitlines():
        cited = {int(n) for n in CITE_RE.findall(line)}
        if not cited:
            continue
        low = _norm(line)
        # A claim that an excerpt does NOT discuss something is satisfied by
        # that excerpt not discussing it. Without this the check punishes the
        # agent for being right: "ISO 2372/10816 ... does not specifically
        # mention API 610 or centrifugal pumps [10]" was flagged because
        # excerpt 10 never mentions centrifugal pumps, which was the claim.
        if NEGATION_RE.search(low):
            continue
        present = [t for t in topics if t in low]
        if not present:
            continue
        for label in sorted(cited):
            body = by_label.get(label, "")
            if not body:
                continue
            # Any content word of any matched phrase is enough.
            words = {w for t in present for w in t.split()}
            if not any(w in body for w in words):
                problems.append(
                    f"CITATION TOPIC MISMATCH [{label}] -- the claim is about "
                    f"{present[0]!r} but that excerpt discusses none of it"
                )
    return sorted(set(problems))


def evaluate(kind: str, answer: str, sources: list[dict], question: str = "") -> list[str]:
    labels = {int(s["label"]) for s in sources if s.get("label") is not None}
    cited = {int(n) for n in CITE_RE.findall(answer or "")}
    evidence = " ".join(s.get("text", "") for s in sources if s.get("label") in cited) or \
               " ".join(s.get("text", "") for s in sources)

    problems: list[str] = []
    for bad in check_dangling(answer, labels):
        problems.append(f"DANGLING CITATION {bad} -- no such excerpt was retrieved")
    # Severity depends on where the number is NOT. Absent from the cited
    # excerpts but present in one that was retrieved is a citation-precision
    # gap: the figure is real and the agent saw it, it just pointed at the
    # wrong [n]. Absent from everything retrieved is fabrication. Reporting
    # both as the same failure buries the serious one.
    everything = " ".join(s.get("text", "") for s in sources)
    missing_from_cited = check_numbers(answer, evidence, question)
    missing_from_all = set(check_numbers(answer, everything, question))
    for num in missing_from_cited:
        if num in missing_from_all:
            problems.append(
                f"UNSUPPORTED NUMBER {num!r} -- absent from every retrieved excerpt"
            )
        else:
            problems.append(
                f"CITATION GAP {num!r} -- in a retrieved excerpt, but not in a cited one"
            )
    problems.extend(check_topic_match(answer, sources, question))

    refused = is_refusal(answer, "anywhere" if kind == "partial" else "lead")
    # A refusal cites nothing by definition; only an ASSERTION needs sources.
    if len(answer or "") > 240 and not cited and not refused:
        problems.append("UNCITED ANSWER -- substantive prose with no [n] at all")

    if kind == "partial":
        if not cited:
            problems.append("WRONG REFUSAL -- the supported half was not answered")
        if not refused:
            problems.append("WRONG REFUSAL -- the unsupported half was not declined")
    if kind == "verbatim":
        low = _norm(answer)
        if "nbssh" not in low:
            problems.append("NOT QUOTED -- the equation was not reproduced as extracted")
        for tidied in ("db/dp", "db / dp", "(1 - db", "1 - db"):
            if tidied in low:
                problems.append(
                    f"EQUATION TIDIED -- inserted {tidied!r}, an operator the "
                    "extracted text does not contain"
                )
        # Quoting the damaged equation is only half safe. Reproduced without a
        # warning, "NbSsh 2 ( 1  db Dp cos )" reads as a complete formula, and
        # the reader has no way to know a divide, a fraction bar and a minus
        # sign were lost in extraction.
        if not any(w in low for w in ("extraction", "extracted", "may have dropped",
                                      "missing", "operator", "verify", "check it against",
                                      "against the page", "as it appears")):
            problems.append(
                "NO DAMAGE WARNING -- the equation was quoted but the answer never "
                "says extraction may have dropped operators"
            )
    if kind == "scoped_value":
        # This check used to demand "2,8 mm/s" and flag "4.5" as the wrong
        # machine group. Both were wrong, and wrong in the same way the agent
        # was: ISO 10816-3 places pumps in Group 3 or Group 4 by DRIVER
        # ARRANGEMENT, not in Group 1 or 2 by rated power. A 55 kW pump with a
        # separate driver on a rigid foundation is Group 3, whose B/C boundary
        # is 4.5 mm/s. 2,8 is Group 4, for an integrated driver.
        #
        # So the check demanded the wrong figure and rejected the right one --
        # it would have failed a correct agent and passed a broken one, which
        # is worse than having no check at all.
        #
        # The expectation is now the behaviour the split introduced: kb_agent
        # does not answer severity limits, it names the agent that does. The
        # numbers themselves are covered by iso_agent's own tests, against the
        # unit-tested tables rather than against a model's reading of a PDF.
        if "iso_agent" not in (answer or ""):
            problems.append(
                "NO REFERRAL -- a scoped limit was asked for and the answer does "
                "not point at iso_agent, which is the only place the number is "
                "looked up rather than read"
            )
        quoted = [v for v in ("2.8", "4.5", "7.1", "1.4")
                  if v in _norm(answer or "").replace(",", ".")]
        if quoted:
            problems.append(
                f"QUOTED A LIMIT -- stated {', '.join(quoted)} mm/s. Choosing the "
                "right row was measured at 1 correct in 5; this agent must refer, "
                "not answer"
            )
    if kind == "absent" and not refused:
        problems.append("WRONG REFUSAL -- corpus does not cover this, but it answered")
    if kind == "answerable" and refused and len(cited) < 2:
        problems.append("WRONG REFUSAL -- corpus covers this, but it declined")
    if kind == "figure_only" and not refused:
        problems.append("WRONG REFUSAL -- the value lives in a figure/lost equation, "
                        "so it must say so rather than state one")
    return problems


# --------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate kb_agent for hallucination.")
    ap.add_argument("--only", choices=["answerable", "partial", "absent", "figure_only", "verbatim", "scoped_value"])
    ap.add_argument("--json", metavar="PATH", help="Write full results as JSON")
    ap.add_argument("--limit", type=int, default=0, help="Run only the first N")
    args = ap.parse_args()

    rows = [q for q in QUESTIONS if not args.only or q[0] == args.only]
    if args.limit:
        rows = rows[: args.limit]

    agent = KnowledgeBaseAgent()
    results: list[dict] = []
    started = time.perf_counter()

    for i, (kind, topic, question) in enumerate(rows, start=1):
        print(f"[{i}/{len(rows)}] ({kind}/{topic}) {question[:78]}", flush=True)
        t0 = time.perf_counter()
        try:
            res = agent.ask(question)
        except Exception as exc:  # noqa: BLE001
            results.append({"kind": kind, "topic": topic, "question": question,
                            "problems": [f"CRASHED -- {exc}"], "answer": "", "sources": 0})
            print(f"      CRASHED: {exc}", flush=True)
            continue

        if not res.ok:
            results.append({"kind": kind, "topic": topic, "question": question,
                            "problems": [f"ERROR -- {res.error}"], "answer": "", "sources": 0})
            print(f"      ERROR: {res.error}", flush=True)
            continue

        answer = res.meta.get("answer", "")
        problems = evaluate(kind, answer, res.data, question)
        results.append({
            "kind": kind, "topic": topic, "question": question,
            "answer": answer,
            "cited": res.meta.get("cited_labels", []),
            "sources": len(res.data),
            "searches": res.meta.get("searches", []),
            "citations": [s["citation"] for s in res.data
                          if s.get("label") in set(res.meta.get("cited_labels", []))],
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "problems": problems,
        })
        mark = "PASS" if not problems else "FAIL"
        print(f"      {mark}  {len(res.data)} excerpts, cited {res.meta.get('cited_labels')}, "
              f"{int((time.perf_counter()-t0)*1000)} ms", flush=True)
        for p in problems:
            print(f"        - {p}", flush=True)

    # ---- report ----
    print("\n" + "=" * 92)
    print("  SUMMARY")
    print("=" * 92)
    by_kind: dict[str, list[int]] = {}
    for r in results:
        ok = not r["problems"]
        by_kind.setdefault(r["kind"], [0, 0])
        by_kind[r["kind"]][0] += 1 if ok else 0
        by_kind[r["kind"]][1] += 1
    for kind, (ok, total) in sorted(by_kind.items()):
        print(f"  {kind:<12} {ok}/{total} clean")
    failures = [r for r in results if r["problems"]]
    print(f"\n  TOTAL {len(results) - len(failures)}/{len(results)} clean, "
          f"{int(time.perf_counter() - started)}s")
    if failures:
        print("\n  Problems:")
        for r in failures:
            print(f"    ({r['kind']}) {r['question'][:70]}")
            for p in r["problems"]:
                print(f"        - {p}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n  full results -> {args.json}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
