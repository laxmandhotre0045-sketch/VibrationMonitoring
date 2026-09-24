"""Analysis over the AI context — MOM item 4.

Item 4 asks for AI-based analysis that produces useful insights. This is the
first consumer of the item 8 contract, and it is deliberately *deterministic*:
every finding below is derived by rule from measured values, and each carries
the evidence it was derived from.

Why rules rather than a language model, when the item says "AI":

  A language model is the right tool for *explaining* a finding to a person.
  It is the wrong tool for *deciding* whether a 50 Hz line is a shaft order or
  mains ingress, because that decision has one correct answer and a model will
  produce a fluent wrong one whenever the context is thin. This module decides;
  items 5 and 6 can narrate what it decided. That split is what keeps a summary
  from inventing a fault.

  It also means the findings are testable. A rule that says "crest factor above
  5.0 with kurtosis above 3.5 suggests impacting" can be checked against known
  inputs. A paragraph cannot.

Every finding carries `confidence`, and the gating is severe on purpose. On an
idle machine almost everything is `informational`, because almost nothing can
be concluded -- and saying that clearly is the useful output, not a hedge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.services import ai_context
from app.services.ai_context import (
    AIContext,
    ARTEFACT_MAINS,
    ARTEFACT_MAINS_AMBIGUOUS,
    TONE_PROMINENCE_MIN,
)

Severity = Literal["critical", "warning", "advisory", "informational"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class Finding:
    """One statement the system is prepared to defend.

    `evidence` holds the numbers the rule fired on, so a reader -- or a model
    narrating this -- can check the claim rather than trust it. `caveat` is not
    decoration: it is what stops a true statement being used for a question it
    does not answer.
    """
    code: str
    title: str
    detail: str
    severity: Severity
    confidence: Confidence
    channel_index: Optional[int] = None
    evidence: dict[str, Any] = field(default_factory=dict)
    caveat: Optional[str] = None


# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------

def _rule_machine_state(ctx: AIContext) -> list[Finding]:
    ds = ctx.data_state
    if not ds.get("has_data"):
        return [Finding(
            code="no_data", title="No captures stored",
            detail="Nothing has been ingested for this sensor.",
            severity="warning", confidence="high",
        )]
    if ds.get("machine_running"):
        return [Finding(
            code="machine_running", title="Machine is turning",
            detail=(f"Loudest channel AC RMS is "
                    f"{ds['loudest_channel_ac_rms_g']:.5f} g, above the "
                    f"{ds['running_threshold_g']} g running threshold."),
            severity="informational", confidence="high",
            evidence={"ac_rms_g": ds["loudest_channel_ac_rms_g"]},
        )]
    return [Finding(
        code="machine_idle", title="Machine is not running",
        detail=(f"Every channel sits at or below the measured idle floor: the "
                f"loudest is {ds['loudest_channel_ac_rms_g']:.5f} g against an "
                f"idle ceiling of {ds['idle_ceiling_g']} g. What the sensors "
                f"are reading is bias and electrical noise, not motion."),
        severity="informational", confidence="high",
        evidence={"ac_rms_g": ds["loudest_channel_ac_rms_g"],
                  "idle_ceiling_g": ds["idle_ceiling_g"]},
        caveat=("No mechanical conclusion can be drawn while the machine is "
                "stationary. Vibration diagnosis requires it to be running."),
    )]


def _rule_instrumentation(ctx: AIContext) -> list[Finding]:
    """Artefacts first, and loudly.

    Ordering matters more than it looks. An analyser that reports "50 Hz
    content on ch2" before saying "ch2 has mains ingress" has already told the
    reader a fault exists. The artefact has to come first or it arrives as a
    footnote to a conclusion the reader has already formed.
    """
    out: list[Finding] = []
    for ch in ctx.channels:
        for art in ch.artefacts:
            if art.startswith(ARTEFACT_MAINS_AMBIGUOUS):
                # Reported, not suppressed. The measurement cannot separate
                # mains from a shaft order at this line spacing, and saying so
                # is the finding -- silently dropping it would leave a reader
                # believing the channel is clean.
                out.append(Finding(
                    code="mains_or_shaft_ambiguous",
                    title=f"ch{ch.index}: 50 Hz line cannot be attributed",
                    detail=art,
                    severity="advisory", confidence="low",
                    channel_index=ch.index,
                    evidence={"dominant_frequency_hz": ch.dominant_frequency_hz},
                    caveat=("Do not treat this as either a fault or an "
                            "instrument problem until it is resolved."),
                ))
            elif art.startswith(ARTEFACT_MAINS):
                out.append(Finding(
                    code="mains_ingress",
                    title=f"ch{ch.index}: electrical interference, not vibration",
                    detail=art,
                    severity="warning", confidence="high",
                    channel_index=ch.index,
                    evidence={"dominant_frequency_hz": ch.dominant_frequency_hz,
                              "noise_floor": ch.noise_floor_amplitude},
                    caveat=("Fix the screening or grounding before any baseline "
                            "is taken on this channel; a baseline built over "
                            "mains ingress bakes it in as normal."),
                ))
    return out


def _rule_no_tone(ctx: AIContext) -> list[Finding]:
    quiet = [c for c in ctx.channels if c.dominant_prominence is not None
             and not c.dominant_is_a_tone]
    if not quiet:
        return []
    return [Finding(
        code="no_dominant_tone",
        title=f"No real tone on {len(quiet)} of {len(ctx.channels)} channels",
        detail=("The largest spectral line on these channels stands only "
                + ", ".join(f"ch{c.index} {c.dominant_prominence:.0f}x"
                            for c in quiet[:8])
                + f" above the noise floor. An FFT always returns a largest "
                  f"bin; below {TONE_PROMINENCE_MIN:.0f}x it is noise, not a "
                  f"frequency worth naming."),
        severity="informational", confidence="high",
        evidence={"channels": [c.index for c in quiet]},
        caveat=("Do not quote these dominant frequencies as machine orders."),
    )]


def _rule_tones(ctx: AIContext) -> list[Finding]:
    """Real tones. Collapsed to one finding while the machine is stopped.

    A tone on a stationary machine is genuinely interesting -- something is
    exciting the structure -- but it is one observation about the installation,
    not eight findings about a pump. Listed individually they crowd out the
    instrumentation faults, which are actionable today.
    """
    running = ctx.data_state.get("machine_running")
    tonal = [c for c in ctx.channels
             if c.dominant_is_a_tone and c.dominant_frequency_hz is not None
             and not any(a.startswith(ARTEFACT_MAINS) for a in c.artefacts)]
    if not tonal:
        return []

    if running:
        return [Finding(
            code="tone_present",
            title=f"ch{c.index}: tone at {c.dominant_frequency_hz:.0f} Hz",
            detail=(f"{c.dominant_prominence:.0f}x the noise floor at "
                    f"{c.dominant_amplitude:.5f} g."),
            severity="advisory", confidence="medium", channel_index=c.index,
            evidence={"frequency_hz": c.dominant_frequency_hz,
                      "prominence": c.dominant_prominence,
                      "amplitude_g": c.dominant_amplitude},
        ) for c in tonal]

    strongest = max(tonal, key=lambda c: c.dominant_prominence or 0)
    # Channels sharing a frequency point at one source, which is worth saying:
    # three channels at 688 Hz is one thing happening, not three.
    shared = [c for c in tonal
              if abs((c.dominant_frequency_hz or 0)
                     - (strongest.dominant_frequency_hz or 0)) < 20]
    return [Finding(
        code="tones_on_idle_machine",
        title=(f"Tonal content on {len(tonal)} channels with the machine stopped"),
        detail=(f"Strongest is ch{strongest.index} at "
                f"{strongest.dominant_frequency_hz:.0f} Hz, "
                f"{strongest.dominant_prominence:.0f}x the noise floor"
                + ("; ch" + ", ch".join(str(c.index) for c in shared if c is not strongest)
                   + " carry the same frequency, so it is one source, not several"
                   if len(shared) > 1 else "")
                + "."),
        severity="advisory", confidence="medium",
        evidence={"channels": [c.index for c in tonal],
                  "strongest_hz": strongest.dominant_frequency_hz,
                  "strongest_prominence": strongest.dominant_prominence},
        caveat=("The machine is stationary, so none of this is shaft rotation. "
                "Identify the source before it is mistaken for a machine order "
                "once the pump runs."),
    )]


def _rule_thresholds(ctx: AIContext) -> list[Finding]:
    """Limit breaches — one finding per channel when running, one in total when not.

    On a stationary machine the factory limits are being applied to sensor
    noise, so every channel breaches something and the output was twenty-odd
    identical caveated lines. That is not more information, it is less: a reader
    who sees twenty-six findings stops reading, and the three that matter (the
    mains ingress) are buried under the ones that do not.

    So while the machine is idle these collapse into a single informational
    statement. Nothing is hidden -- the per-channel verdicts are still in the
    context payload -- but the analysis stops presenting them as findings.
    """
    running = ctx.data_state.get("machine_running")
    breaches: list[tuple[int, str, str, Any]] = []
    for ch in ctx.channels:
        for code, verdict in (ch.threshold_status or {}).items():
            if "above" not in verdict and "below" not in verdict:
                continue
            value = getattr(ch, {"kurtosis": "kurtosis_excess"}.get(code, code), None)
            breaches.append((ch.index, code, verdict, value))

    if not breaches:
        return []

    if not running:
        channels = sorted({b[0] for b in breaches})
        return [Finding(
            code="thresholds_not_applicable",
            title=f"Factory limits breached on {len(channels)} channels, but the "
                  f"machine is stopped",
            detail=(f"{len(breaches)} limit comparison(s) across ch"
                    + ", ch".join(str(c) for c in channels)
                    + " read as breaches. The limits assume a turning machine; "
                      "here they are being applied to sensor noise and bias, so "
                      "none of them indicates a fault."),
            severity="informational", confidence="high",
            evidence={"breach_count": len(breaches), "channels": channels},
            caveat=("Re-evaluate once the machine is running. Per-channel "
                    "verdicts are in the context payload if needed."),
        )]

    out: list[Finding] = []
    for index, code, verdict, value in breaches:
        out.append(Finding(
            code=f"threshold_{code}",
            title=f"ch{index}: {code.replace('_', ' ')} {verdict}",
            detail=(f"Measured {value:.5g}. " if value is not None else "")
                   + "Compared against the platform's factory limit.",
            severity="warning", confidence="high",
            channel_index=index,
            evidence={code: value, "verdict": verdict},
        ))
    return out


def _rule_trends(ctx: AIContext) -> list[Finding]:
    out: list[Finding] = []
    for w in ctx.history.get("windows", []):
        moving = [t for t in w["trends"]
                  if t["trend"] is not None and t["direction"] in ("rising", "falling")]
        if moving:
            worst = max(moving, key=lambda t: abs(t["trend"]))
            out.append(Finding(
                code="trend_moving",
                title=(f"ch{worst['channel_index']}: level {worst['direction']} "
                       f"{abs(worst['trend']) * 100:.0f}% over {w['days']} days"),
                detail=(f"Mean AC RMS {worst['ac_rms_mean']:.5f} g across "
                        f"{w['captures']} captures."),
                severity="warning" if worst["direction"] == "rising" else "advisory",
                confidence="medium",
                channel_index=worst["channel_index"],
                evidence=worst,
            ))
            continue
        withheld = next((t["withheld_because"] for t in w["trends"]
                         if t["withheld_because"]), None)
        if withheld:
            out.append(Finding(
                code="trend_unavailable",
                title=f"No {w['days']}-day trend yet",
                detail=withheld,
                severity="informational", confidence="high",
                evidence={"captures": w["captures"],
                          "coverage_fraction": w["coverage_fraction"]},
                caveat=("Any statement about levels rising or falling over this "
                        "window would be extrapolation, not measurement."),
            ))
    return out


RULES = (_rule_machine_state, _rule_instrumentation, _rule_no_tone,
         _rule_tones, _rule_thresholds, _rule_trends)

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "advisory": 2, "informational": 3}


@dataclass
class Analysis:
    generated_at: datetime
    headline: str
    findings: list[Finding]
    cannot_conclude: list[str]
    context_summary: dict[str, Any]


def _headline(ctx: AIContext, findings: list[Finding]) -> str:
    """One sentence, and it must not overstate.

    Severity is not enough on its own: a warning on a stationary machine is a
    warning about the instrument, not the pump, and a headline that does not
    say so is the single most likely thing to be quoted out of context.
    """
    if not ctx.data_state.get("has_data"):
        return "No data has been recorded for this sensor."

    running = ctx.data_state.get("machine_running")
    hard = [f for f in findings if f.severity in ("critical", "warning")]

    if not running:
        instrument = [f for f in hard if f.code == "mains_ingress"]
        if instrument:
            return (f"The machine is stopped, and {len(instrument)} channel(s) "
                    f"carry mains interference that should be fixed before "
                    f"monitoring begins.")
        return ("The machine is stopped. The readings describe sensor noise, "
                "not machine condition.")

    if hard:
        return (f"{len(hard)} item(s) need attention on a running machine; "
                f"the most severe is: {hard[0].title}.")
    return "The machine is running and no measured value is outside its limit."


def analyse(db: Session, sensor_id: Optional[UUID] = None) -> Analysis:
    ctx = ai_context.build(db, sensor_id)
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(ctx))
    findings.sort(key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9),
                                 f.channel_index if f.channel_index is not None else -1))
    return Analysis(
        generated_at=datetime.now(timezone.utc),
        headline=_headline(ctx, findings),
        findings=findings,
        cannot_conclude=ctx.cannot_conclude,
        context_summary={
            "machine_name": (ctx.machine or {}).get("machine_name"),
            "machine_running": ctx.data_state.get("machine_running"),
            "last_entry_age_seconds": ctx.data_state.get("last_entry_age_seconds"),
            "channel_count": len(ctx.channels),
            "sample_rate_hz": ctx.acquisition.get("sample_rate_hz"),
        },
    )


def to_dict(a: Analysis) -> dict[str, Any]:
    return asdict(a)
