"""Plain-language summaries and suggestions — MOM item 6.

This is where a language model finally belongs. Item 4 decided what is true;
this says it in a sentence someone can act on. The split matters: a model asked
to *decide* whether a 50 Hz line is mains or a shaft order will answer fluently
and sometimes wrongly, while a model asked to *rephrase* a decision that has
already been made can only get the wording wrong.

Even so, rephrasing is not safe by default, because the most useful thing to
rephrase is a number and a number is the easiest thing to drift. So the output
is verified before it is shown:

  Every number in the generated text must appear in the findings it was given.

That check is cheap and it catches the failure that matters — a plausible
figure that was never measured. It cannot catch a wrong *word* ("rising" for
"falling"), so the prompt is kept narrow enough that there is little room for
one: the model receives the findings and nothing else, and is told it may not
add.

If there is no API key, if the call fails, or if verification rejects the text,
a deterministic summary is written from the same findings. The platform always
produces a summary; the model only ever changes how it reads.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services import ai_analysis, llm
from app.services.ai_analysis import Analysis, Finding

#: Numbers below this are ordinals, counts and years rather than measurements,
#: and demanding they be grounded rejects harmless prose ("the 2 channels").
#: Grounding is about measured quantities, not about arithmetic.
_TRIVIAL = {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"}

_NUMBER = re.compile(r"\d+(?:\.\d+)?")

SYSTEM_PROMPT = (
    "You are writing for a maintenance engineer who will act on what you say.\n"
    "\n"
    "You are given findings that a measurement system has already established. "
    "Your job is to say what they mean in plain language, not to analyse.\n"
    "\n"
    "Rules, in order of importance:\n"
    "1. Never state a number that is not in the findings. Not an estimate, not "
    "a rounding, not a conversion.\n"
    "2. Never add a cause, a fault or a component that the findings do not "
    "name. If the findings say a machine is stopped, do not speculate about "
    "bearings.\n"
    "3. If a finding carries a caveat, the caveat is part of the finding. Do "
    "not report the claim without it.\n"
    "4. Say plainly when something cannot be determined. 'Not enough data yet' "
    "is a useful answer and you should give it rather than hedge.\n"
    "5. Be brief. Three or four sentences of summary, then at most three "
    "suggestions as short imperative lines starting with '- '.\n"
    "\n"
    "Write the summary first, then a blank line, then the suggestions."
)


@dataclass
class Summary:
    generated_at: datetime
    headline: str
    summary: str
    suggestions: list[str] = field(default_factory=list)
    #: "model" when a language model wrote it, "template" when the platform
    #: did. Surfaced rather than hidden: a reader is entitled to know whether
    #: a machine wrote the prose, and it is the first thing to check when the
    #: wording looks odd.
    source: str = "template"
    #: Set when a model's text was produced and then rejected.
    rejected_reason: Optional[str] = None
    model: Optional[str] = None


def _grounded_numbers(findings: list[Finding], extra: list[str]) -> set[str]:
    """Every number the model is allowed to use.

    Drawn from the rendered text of the findings rather than from their
    structured evidence, because that is what the model is shown -- grounding
    against something it never saw would reject correct output.
    """
    allowed: set[str] = set()
    for f in findings:
        for blob in (f.title, f.detail, f.caveat or ""):
            allowed.update(_NUMBER.findall(blob))
        for value in (f.evidence or {}).values():
            if isinstance(value, (int, float)):
                allowed.update(_NUMBER.findall(f"{value}"))
                allowed.update(_NUMBER.findall(f"{value:.5f}" if isinstance(value, float) else ""))
    for blob in extra:
        allowed.update(_NUMBER.findall(blob))
    return allowed


def _ungrounded(text: str, allowed: set[str]) -> list[str]:
    """Numbers in `text` that no finding contains.

    A number counts as grounded if it appears in the allowed set, or if it is a
    prefix of an allowed one -- the model writing "0.02" for a measured
    "0.024" is rounding what it was given, not inventing. The reverse is not
    accepted: "0.0244" when it was given "0.02" would be added precision.
    """
    bad: list[str] = []
    for number in _NUMBER.findall(text):
        if number in _TRIVIAL or number in allowed:
            continue
        if any(a.startswith(number) for a in allowed):
            continue
        bad.append(number)
    return bad


def _render_prompt(analysis: Analysis) -> str:
    lines = [f"MACHINE: {analysis.context_summary.get('machine_name') or 'unknown'}",
             f"RUNNING: {analysis.context_summary.get('machine_running')}",
             "", "FINDINGS:"]
    for f in analysis.findings:
        where = f"ch{f.channel_index}: " if f.channel_index is not None else ""
        lines.append(f"- [{f.severity}/{f.confidence}] {where}{f.title}")
        lines.append(f"  {f.detail}")
        if f.caveat:
            lines.append(f"  CAVEAT: {f.caveat}")
    if analysis.cannot_conclude:
        lines += ["", "THIS DATA CANNOT ANSWER:"]
        lines += [f"- {c}" for c in analysis.cannot_conclude]
    return "\n".join(lines)


def _split(text: str) -> tuple[str, list[str]]:
    """Separate the prose from the '- ' suggestion lines."""
    prose: list[str] = []
    suggestions: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")):
            suggestions.append(stripped[2:].strip())
        elif stripped:
            prose.append(stripped)
    return " ".join(prose).strip(), suggestions


def _template(analysis: Analysis) -> tuple[str, list[str]]:
    """The platform's own words, used whenever the model's are not available.

    Deliberately written to be useful rather than to be a placeholder: on a
    deployment with no API key this is the summary, permanently.
    """
    hard = [f for f in analysis.findings if f.severity in ("critical", "warning")]
    advisory = [f for f in analysis.findings if f.severity == "advisory"]
    running = analysis.context_summary.get("machine_running")

    parts = [analysis.headline]
    if hard:
        parts.append(
            "Needing attention: "
            + "; ".join(f.title for f in hard[:3])
            + ("." if len(hard) <= 3 else f", and {len(hard) - 3} more.")
        )
    if advisory:
        parts.append("Also noted: " + advisory[0].title + ".")
    if not running:
        parts.append(
            "Because the machine is stopped, none of the measured values "
            "describes its mechanical condition."
        )

    suggestions: list[str] = []
    for f in hard[:3]:
        if f.caveat:
            suggestions.append(f.caveat)
    if not running:
        suggestions.append(
            "Take a capture while the machine is running before drawing any "
            "conclusion about its condition."
        )
    for c in analysis.cannot_conclude:
        if "trend" in c.lower() and len(suggestions) < 3:
            suggestions.append("Keep collecting; trends need more elapsed time.")
            break
    return " ".join(parts), suggestions[:3]


def build(db: Session, sensor_id: Optional[UUID] = None) -> Summary:
    analysis = ai_analysis.analyse(db, sensor_id)
    now = datetime.now(timezone.utc)

    prose, suggestions = _template(analysis)
    result = Summary(
        generated_at=now,
        headline=analysis.headline,
        summary=prose,
        suggestions=suggestions,
        source="template",
    )

    if not llm.is_configured():
        return result

    text = llm.complete(SYSTEM_PROMPT, _render_prompt(analysis))
    if not text:
        result.rejected_reason = "the language model did not return a response"
        return result

    model_prose, model_suggestions = _split(text)
    if not model_prose:
        result.rejected_reason = "the language model returned no prose"
        return result

    allowed = _grounded_numbers(analysis.findings,
                                extra=[analysis.headline] + analysis.cannot_conclude)
    invented = _ungrounded(model_prose + " " + " ".join(model_suggestions), allowed)
    if invented:
        # The template stands. Rejecting is not a failure mode to be tidied
        # away -- it is the check working, and the reason is surfaced so a
        # pattern of rejections is visible rather than silent.
        result.rejected_reason = (
            "the generated text contained "
            + ", ".join(sorted(set(invented))[:5])
            + ", which no finding supports"
        )
        return result

    result.summary = model_prose
    result.suggestions = model_suggestions[:3]
    result.source = "model"
    result.model = llm.model_name()
    return result


def to_dict(s: Summary) -> dict[str, Any]:
    return asdict(s)
