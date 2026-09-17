"""The data an AI is allowed to reason from — MOM item 8.

Item 8 asks that what reaches the AI comes from machine details, graphs and
analysis data, so it can speak about RMS, kurtosis and the rest. That is a
contract, not a feature, which is why it is built before items 4, 5 and 6
rather than after them: build the bot first and the shape gets hard-coded into
prompts, and all three get reworked when the contract moves.

Three rules shape everything below, and each of them exists because this
deployment has already produced the failure it prevents.

**Nothing arrives unqualified.** An FFT always has a largest bin. Measured
here, an idle pump reports a stable 5509 Hz "dominant frequency" that is simply
the tallest blade of grass in the noise. A summary handed that number with no
measure of prominence will state it as a finding, because it has no way not to.
So every number that can be meaningless carries the thing that says whether it
is.

**The machine's state is a fact, not an assumption.** Every capture on this
deployment so far is of a stationary pump. Analysis that assumes rotation reads
sensor bias as vibration and produces confident nonsense. `machine_running` is
therefore stated explicitly, derived from AC RMS against a measured idle floor.

**Known instrumentation faults travel with the data.** ch2 and ch7 carry a
50.4 Hz line at 93-97x the median line — mains ingress, not motion. On a 50 Hz
supply that sits exactly where a 3000 rpm shaft order would, so an analyser
that does not know it is an artefact will report a shaft-rate fault on a
stationary machine. Declaring it is cheaper and safer than hoping the reader
notices.

The contract also carries an explicit `cannot_conclude` list. Most of what goes
wrong with automated analysis is not a wrong number but a right number used for
a question it cannot answer, and saying so in the payload is more reliable than
hoping a prompt remembers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import crud
from app.crud import measurement as measurement_crud
from app.services import capture_history
from app.services.acquisition_config import build_acquisition_config
from app.services.raw_analysis import (
    channel_samples,
    compute_raw_spectrum,
    compute_raw_statistics,
)
from app.services.threshold_defaults import THRESHOLD_RULE_DEFAULTS

#: Below this the largest spectral line is not a tone, it is the tallest part
#: of the noise.
#:
#: Derived rather than tuned, so it does not have to be recalibrated whenever
#: the line count or averaging changes. For a spectrum of N lines of pure
#: Rayleigh-magnitude noise the largest line sits about 3.4x the median at
#: N=1600 and 3.6x at N=3200, reaching 4.7x in the worst of 200 simulated
#: runs. Twelve is roughly three times that worst case: comfortably above what
#: noise alone produces, and far below the 36-276x that the real tones on this
#: deployment reach.
#:
#: An earlier version of this comment claimed noise sat "near 30x", which was a
#: misreading of channels that genuinely carry tones -- and would have meant
#: noise passing this threshold, since 30 > 12.
#:
#: Used only to LABEL. The frequency is always reported; this says whether it
#: means anything.
TONE_PROMINENCE_MIN = 12.0

#: AC RMS above which the machine is treated as turning. The measured idle
#: ceiling across every capture taken on this deployment is 0.0244 g.
RUNNING_AC_RMS_G = 0.035
IDLE_CEILING_G = 0.0244

#: Mains frequency. A line here in an accelerometer channel is electrical
#: pickup; at 50 Hz it is indistinguishable by frequency alone from a 3000 rpm
#: shaft order, which is exactly why it has to be labelled rather than left for
#: the consumer to spot.
MAINS_HZ = 50.0
MAINS_ARTEFACT_RATIO = 12.0


@dataclass
class Provenance:
    """Where a number came from, so a consumer can weigh it.

    `measured` is read from the samples. `configured` is what a human typed
    into Equipment Master and may be stale or wrong. `derived` is computed from
    measured values. The distinction matters: a rated RPM that was typed in is
    not evidence about what the shaft is doing right now.
    """
    source: str
    detail: Optional[str] = None


@dataclass
class ChannelContext:
    index: int
    label: Optional[str]
    machine_axis: Optional[str]
    signal_type: Optional[str]

    # time domain, all in g
    rms: Optional[float] = None
    ac_rms: Optional[float] = None
    dc_offset: Optional[float] = None
    peak: Optional[float] = None
    crest_factor: Optional[float] = None
    kurtosis_excess: Optional[float] = None
    skewness: Optional[float] = None

    # frequency domain
    dominant_frequency_hz: Optional[float] = None
    dominant_amplitude: Optional[float] = None
    dominant_prominence: Optional[float] = None
    #: False when the largest line is not prominent enough to be a tone. The
    #: frequency is still reported -- hiding it would be its own dishonesty --
    #: but this says whether it means anything.
    dominant_is_a_tone: bool = False
    noise_floor_amplitude: Optional[float] = None

    #: Instrumentation problems found in this channel. Not machine faults.
    artefacts: list[str] = field(default_factory=list)
    #: Threshold comparisons, each naming the limit it used.
    threshold_status: dict[str, str] = field(default_factory=dict)


@dataclass
class AIContext:
    generated_at: datetime
    machine: dict[str, Any]
    acquisition: dict[str, Any]
    data_state: dict[str, Any]
    channels: list[ChannelContext]
    history: dict[str, Any]
    #: Questions this data cannot answer. Stated in the payload rather than
    #: left to a prompt, because a prompt is advice and this is a fact about
    #: the measurements.
    cannot_conclude: list[str]
    provenance: dict[str, Provenance]


def _machine_details(db: Session, sensor) -> dict[str, Any]:
    """Equipment Master fields, marked as configured rather than measured."""
    eq = db.execute(text("""
        SELECT machine_name, machine_type, machine_criticality, manufacturer,
               model, rated_power_kw, rated_rpm, drive_type, load_type,
               foundation_type, coupling_details, bearing_details,
               plant_name, area, line
          FROM equipment_masters WHERE id = :eid
    """), {"eid": str(sensor.equipment_id)}).fetchone()
    if not eq:
        return {}
    out = dict(eq._mapping)
    # Numeric(10,4) and friends arrive as Decimal, which json cannot encode.
    for k, v in list(out.items()):
        if hasattr(v, "quantize"):
            out[k] = float(v)
    return out


def _threshold_status(stats: dict[str, float],
                      ac_rms: Optional[float] = None) -> dict[str, str]:
    """Compare against the platform's factory limits, naming each limit used.

    The RMS limit is applied to AC RMS, not raw RMS. Raw RMS includes the
    sensor's standing DC bias -- ch7 sits near -0.146 g -- so comparing it
    against a 0.01/0.02 g vibration limit flags every channel on a stationary
    machine for having a bias it is supposed to have. The limits are plainly
    written for vibration, so vibration is what they are given.

    Deliberately reports the limit alongside the verdict. "kurtosis warning" is
    unusable on its own -- the reader cannot tell whether the limit is on the
    excess scale (Gaussian = 0) or Pearson (Gaussian = 3), and those differ by
    exactly 3.0.
    """
    out: dict[str, str] = {}
    for code, value in (("rms", ac_rms if ac_rms is not None else stats.get("rms")),
                        ("peak", stats.get("peak")),
                        ("crest_factor", stats.get("crest_factor")),
                        ("kurtosis", stats.get("kurtosis"))):
        rule = THRESHOLD_RULE_DEFAULTS.get(code)
        if rule is None or value is None:
            continue
        if rule.rule_type == "absolute_max":
            if rule.warning_max is not None and value > rule.warning_max:
                verdict = f"above critical limit {rule.warning_max:g}"
            elif rule.normal_max is not None and value > rule.normal_max:
                verdict = f"above warning limit {rule.normal_max:g}"
            else:
                verdict = f"within limit {rule.normal_max:g}"
        elif rule.rule_type == "range":
            if rule.normal_min is not None and value < rule.normal_min:
                verdict = f"below normal range minimum {rule.normal_min:g}"
            elif rule.normal_max is not None and value > rule.normal_max:
                verdict = f"above normal range maximum {rule.normal_max:g}"
            else:
                verdict = f"within range {rule.normal_min:g}-{rule.normal_max:g}"
        else:
            continue
        # kurtosis limits on this platform are EXCESS (Gaussian reads 0).
        scale = (" (excess scale, Gaussian = 0)" if code == "kurtosis"
                 else " (AC RMS, DC bias removed)" if code == "rms" else "")
        out[code] = verdict + scale
    return out


def build(db: Session, sensor_id: Optional[UUID] = None) -> AIContext:
    now = datetime.now(timezone.utc)

    last = capture_history.last_entry(db, sensor_id)
    if last is None:
        return AIContext(
            generated_at=now, machine={}, acquisition={},
            data_state={"has_data": False},
            channels=[], history={},
            cannot_conclude=["No captures exist for this sensor; nothing can be "
                             "concluded about the machine at all."],
            provenance={},
        )

    upload = measurement_crud.get_upload_by_id(db, UUID(last["upload_id"]))
    sensor = crud.get_sensor_by_id(db, upload.sensor_id)
    plot_config = measurement_crud.get_plot_config_by_sensor(db, sensor.id)
    acq = build_acquisition_config(sensor, plot_config)

    from app.services.raw_storage import load_capture
    parsed = load_capture(db, upload.id) or {}
    rate = float(parsed.get("sample_rate") or acq.get("sampleRateHz") or 0.0)

    mapping = acq.get("channelMapping") or []
    channels: list[ChannelContext] = []
    running_votes: list[float] = []

    for idx in range(int(upload.channel_count or 0)):
        entry = mapping[idx] if idx < len(mapping) else {}
        ctx = ChannelContext(
            index=idx,
            label=entry.get("label"),
            machine_axis=entry.get("machineAxis") or entry.get("machine_axis"),
            signal_type=entry.get("signalType") or entry.get("signal_type"),
        )
        try:
            samples = channel_samples(parsed, idx)
        except Exception:
            channels.append(ctx)
            continue

        stats = compute_raw_statistics(samples, rate)
        mean = sum(samples) / len(samples) if samples else 0.0
        ac = (sum((s - mean) ** 2 for s in samples) / len(samples)) ** 0.5 if samples else 0.0
        running_votes.append(ac)

        ctx.rms = stats["rms"]
        ctx.ac_rms = ac
        ctx.dc_offset = mean
        ctx.peak = stats["peak"]
        ctx.crest_factor = stats["crest_factor"]
        ctx.kurtosis_excess = stats["kurtosis_excess"]
        ctx.skewness = stats["skewness"]
        ctx.threshold_status = _threshold_status(stats, ac_rms=ac)

        spec = compute_raw_spectrum(
            samples, rate,
            fft_lines=acq.get("lor"),
            frequency_max_hz=acq.get("fmaxHz"),
        )
        ctx.dominant_frequency_hz = spec["dominant_frequency_hz"]
        ctx.dominant_amplitude = spec["dominant_amplitude"]
        ctx.dominant_prominence = spec.get("dominant_prominence")
        ctx.noise_floor_amplitude = spec.get("noise_floor_amplitude")
        ctx.dominant_is_a_tone = (ctx.dominant_prominence or 0.0) >= TONE_PROMINENCE_MIN

        # Mains ingress, checked per channel rather than assumed from a list.
        # Hard-coding "ch2 and ch7" would go stale the moment the cable is
        # fixed, and would miss it appearing anywhere else.
        # Mains ingress, from the ratios measured on the full spectrum.
        # Searching the returned arrays would search a decimated copy, where a
        # harmonic that survives thinning is luck rather than evidence.
        ratios = spec.get("mains_line_ratios") or {}
        fundamental = ratios.get("h1", 0.0)
        harmonics = {n: ratios.get(f"h{n}", 0.0) for n in (2, 3, 4)}
        strongest_n = max(harmonics, key=lambda n: harmonics[n]) if harmonics else None
        # A single 50 Hz line is not proof: a machine order can sit there too.
        # Mains carries harmonics, so requiring one separates electrical ingress
        # from a mechanical coincidence. On the captures measured here it makes
        # no difference -- ch2 and ch7 carry both -- but it is the criterion
        # that stays right when a shaft happens to run at 3000 rpm.
        if (fundamental >= MAINS_ARTEFACT_RATIO
                and strongest_n is not None
                and harmonics[strongest_n] >= MAINS_ARTEFACT_RATIO):
            ctx.artefacts.append(
                f"Mains pickup: {MAINS_HZ:g} Hz line at {fundamental:.0f}x the "
                f"noise floor, with its harmonic at "
                f"{MAINS_HZ * strongest_n:.0f} Hz at "
                f"{harmonics[strongest_n]:.0f}x. This is electrical ingress, "
                f"not motion. On a {MAINS_HZ:g} Hz supply it coincides with a "
                f"{MAINS_HZ * 60:.0f} rpm shaft order and must not be read as "
                f"one."
            )
        if not ctx.dominant_is_a_tone:
            ctx.artefacts.append(
                f"No tone: the largest line ({ctx.dominant_frequency_hz:.0f} Hz) "
                f"is only {ctx.dominant_prominence:.0f}x the noise floor. An FFT "
                f"always has a largest bin; this one carries no information."
            )
        channels.append(ctx)

    peak_ac = max(running_votes) if running_votes else 0.0
    running = peak_ac > RUNNING_AC_RMS_G

    history = capture_history.history(db, sensor_id=sensor.id)

    cannot: list[str] = []
    if not running:
        cannot.append(
            f"Whether the machine has a fault. Loudest channel AC RMS is "
            f"{peak_ac:.5f} g against an idle ceiling of {IDLE_CEILING_G} g, so "
            f"the machine is not turning. Vibration diagnosis needs a running "
            f"machine; nothing here describes its mechanical condition."
        )
    cannot.append(
        "An ISO 10816 severity zone. These values are acceleration in g; the "
        "standard's zones are defined on velocity in mm/s, and no conversion "
        "has been applied."
    )
    # capture_history returns Window/ChannelTrend dataclasses, not dicts.
    for w in history.get("windows", []):
        blocked = next((c.trend_blocked_reason for c in w.channels
                        if c.trend_blocked_reason), None)
        if blocked:
            cannot.append(f"Whether levels are rising over {w.days} days: {blocked}.")
    if any(a.startswith("Mains pickup") for c in channels for a in c.artefacts):
        cannot.append(
            "That any 50 Hz content is mechanical. At least one channel carries "
            "mains ingress, which is electrical."
        )

    return AIContext(
        generated_at=now,
        machine=_machine_details(db, sensor),
        acquisition={
            "sample_rate_hz": acq.get("sampleRateHz"),
            "ksps": acq.get("ksps"),
            "fmax_hz": acq.get("fmaxHz"),
            "lor": acq.get("lor"),
            "window_type": acq.get("windowType"),
            "channel_count": acq.get("totalChannelCount"),
            "sensitivity_mv_per_g": acq.get("sensitivityMvPerG"),
            "sample_unit": "g",
            "collection_interval_minutes": acq.get("collectionIntervalMinutes"),
        },
        data_state={
            "has_data": True,
            "last_entry_at": last["at"],
            "last_entry_age_seconds": last["age_seconds"],
            "capture_id": last["capture_id"],
            "sample_count": last["sample_count"],
            "machine_running": running,
            "loudest_channel_ac_rms_g": peak_ac,
            "idle_ceiling_g": IDLE_CEILING_G,
            "running_threshold_g": RUNNING_AC_RMS_G,
        },
        channels=channels,
        history={
            "days_with_data": len(history.get("entries_by_date") or []),
            "windows": [
                {
                    "days": w.days, "captures": w.captures,
                    "coverage_fraction": w.coverage_fraction,
                    "span_hours": w.span_hours,
                    "trends": [
                        {"channel_index": c.channel_index,
                         "ac_rms_mean": c.rms_mean,
                         "trend": c.trend,
                         "direction": c.direction,
                         "withheld_because": c.trend_blocked_reason}
                        for c in w.channels
                    ],
                }
                for w in history.get("windows", [])
            ],
        },
        cannot_conclude=cannot,
        provenance={
            "machine": Provenance("configured", "Equipment Master; typed by a "
                                                "person and not verified against "
                                                "the running machine"),
            "acquisition": Provenance("configured", "Acquisition & DAQ settings"),
            "channels": Provenance("measured", "computed from the stored samples "
                                               "of the latest capture"),
            "history": Provenance("derived", "aggregated from stored per-channel "
                                             "statistics"),
        },
    )


def to_dict(ctx: AIContext) -> dict[str, Any]:
    out = asdict(ctx)
    out["provenance"] = {k: asdict(v) if hasattr(v, "source") else v
                         for k, v in (ctx.provenance or {}).items()}
    return out
