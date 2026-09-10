"""Adapters that turn each agent's output into ledger facts.

One function per source of truth. Each takes the ledger, registers what it
found, and returns the structured pieces the template needs. Nothing here
formats prose and nothing here calls a model.

The unit problem is handled here rather than papered over. The platform stores
feature values in ``scaled_eng`` -- its own scaled engineering units -- and
says so in the caveats it returns. ISO 10816-3 limits are in mm/s RMS. The two
are not comparable, so this module will not compare them: it reports the
applicable ISO limits for reference, states plainly that the measured values
are in different units, and does not assign a zone. Producing a zone from
non-comparable numbers would be the same class of error as reading a limit off
the wrong table -- confident, plausible, and wrong.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any

from report_agent.ledger import Ledger

logger = logging.getLogger(__name__)

#: Features worth putting in a summary table, in the order an analyst reads
#: them: overall level first, then shape, then the orders, then the rest.
FEATURE_ORDER = [
    "rms",
    "peak",
    "crest_factor",
    "kurtosis",
    "amplitude_1x",
    "amplitude_2x",
    "amplitude_3x",
    "envelope_rms",
    "noise_floor",
    "fft_band_energy_0_500",
]

_SEVERITY = {"critical": 3, "warning": 2, "no_baseline": 1, "normal": 0}


# --------------------------------------------------------------------------
# Measured -- from the platform, via sql_agent
# --------------------------------------------------------------------------


def collect_measurements(
    ledger: Ledger,
    sensor: str,
    *,
    from_date: str | None = None,
    to_date: str | None = None,
    max_captures: int = 200,
) -> dict[str, Any]:
    """Pull one sensor's history and register the headline facts.

    Returns the identification block, the per-feature summary and the raw
    rows. Raises nothing: a platform failure comes back as ``ok=False`` with
    the reason, so the pipeline can mark the section incomplete rather than
    abandon the report.
    """
    from sql_agent import SensorDataAgent

    result = SensorDataAgent().get_sensor_data(
        sensor, from_date=from_date, to_date=to_date,
        max_captures=max_captures, include_csv=False,
    )
    if not result.ok:
        return {"ok": False, "error": result.error}

    meta, rows = result.meta, result.data
    caveats = list(meta.get("caveats") or [])

    identity = {
        "machine_name": meta.get("machine_name", ""),
        "machine_id": _first(rows, "machine_id"),
        "machine_type": _first(rows, "machine_type"),
        "sensor_id": meta.get("sensor_id", ""),
        "mounting_location": meta.get("mounting_location", ""),
        "orientation": meta.get("orientation", ""),
        "sensor_type": _first(rows, "sensor_type"),
        "plant": meta.get("plant_name", ""),
        "area": meta.get("area", ""),
        "line": meta.get("line", ""),
    }

    window = f"{_short(meta.get('first_observed_at'))} to {_short(meta.get('last_observed_at'))}"
    source = f"platform, sensor {identity['sensor_id']}"

    ids = {
        "captures": ledger.measured(
            "captures in the reporting window", meta.get("captures_exported", 0),
            "", source, caveats=caveats).id,
        "rows": ledger.measured(
            "measurement rows analysed", meta.get("csv_rows", len(rows)), "", source).id,
        "channels": ledger.measured(
            "channels recorded", len(meta.get("channels") or []), "", source).id,
        "window": ledger.measured("reporting window", window, "", source).id,
    }

    counts = meta.get("status_counts") or {}
    for status in ("critical", "warning", "normal", "no_baseline"):
        if status in counts:
            ids[status] = ledger.measured(
                f"readings assessed {status}", counts[status], "", source,
                caveats=caveats if status == "no_baseline" else ()).id

    return {
        "ok": True,
        "fact_ids": ids,
        "identity": identity,
        "window": window,
        "captures": meta.get("captures_exported", 0),
        "captures_available": meta.get("captures_available", 0),
        "channels": meta.get("channels") or [],
        "status_counts": counts,
        "feature_codes": meta.get("feature_codes") or [],
        "rows": rows,
        "caveats": caveats,
        "units_seen": sorted({r.get("unit", "") for r in rows if r.get("unit")}),
    }


def _first(rows: list[dict[str, Any]], key: str) -> str:
    for row in rows:
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _short(stamp: Any) -> str:
    text = str(stamp or "")
    return text[:16].replace("T", " ") if text else "unknown"


# --------------------------------------------------------------------------
# Derived -- statistics over the measured rows
# --------------------------------------------------------------------------


def summarise_features(ledger: Ledger, dataset: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-feature worst reading, latest reading and direction of travel.

    Trend is first-capture against last-capture on the worst channel, which is
    what an analyst looks at. It is deliberately not a fitted slope: with nine
    captures over eight days a regression would imply a precision the sampling
    does not support.
    """
    rows = dataset.get("rows") or []
    if not rows:
        return []

    by_feature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        code = row.get("feature_code")
        if code:
            by_feature[code].append(row)

    ordered = [c for c in FEATURE_ORDER if c in by_feature]
    ordered += [c for c in sorted(by_feature) if c not in FEATURE_ORDER]

    summary: list[dict[str, Any]] = []
    for code in ordered:
        entries = by_feature[code]
        worst = max(entries, key=lambda r: (_SEVERITY.get(r.get("status", ""), 0),
                                            _as_float(r.get("value"))))
        unit = worst.get("unit", "")
        name = worst.get("feature_name") or code

        channel = worst.get("channel")
        same_channel = sorted(
            (r for r in entries if r.get("channel") == channel),
            key=lambda r: str(r.get("observed_at") or ""),
        )
        first_value = _as_float(same_channel[0].get("value")) if same_channel else None
        last_value = _as_float(same_channel[-1].get("value")) if same_channel else None
        change = _change(first_value, last_value)

        worst_fact = ledger.measured(
            f"worst {name}", _as_float(worst.get("value")), unit,
            f"channel {channel}, capture {str(worst.get('upload_id'))[:8]}, "
            f"{_short(worst.get('observed_at'))}",
            detail={"feature_code": code, "status": worst.get("status")},
            caveats=dataset.get("caveats", []),
        )
        latest_fact = ledger.measured(
            f"latest {name} on channel {channel}", last_value, unit,
            f"channel {channel}, {_short(same_channel[-1].get('observed_at'))}" if same_channel else "",
            detail={"feature_code": code},
        )

        statuses = {r.get("status", "") for r in entries}
        summary.append({
            "code": code,
            "name": name,
            "unit": unit,
            "worst_fact": worst_fact.id,
            "worst_value": worst_fact.rendered(),
            "worst_channel": channel,
            "worst_status": worst.get("status", ""),
            "latest_fact": latest_fact.id,
            "latest_value": latest_fact.rendered(),
            "change_pct": change,
            "direction": _direction(change),
            # Distinct CHANNELS carrying a critical reading, not rows. Nine
            # captures across eight channels give 72 rows per feature, so
            # counting rows produced "72 of 8 channels critical".
            "channels_critical": len(
                {r.get("channel") for r in entries if r.get("status") == "critical"}
            ),
            "channels_total": len({r.get("channel") for r in entries}),
            "worst_of_statuses": _worst_status(statuses),
        })
    return summary


def detect_identical_captures(dataset: dict[str, Any]) -> dict[str, Any]:
    """Are the captures actually different measurements?

    The first real dataset this was run against held nine captures spanning
    eight days whose every feature value was byte-identical -- one sample file
    uploaded nine times during testing. A trend line over that is flat, and a
    report presenting it as "steady over eight days" would be stating an
    observation that was never made.

    So it is detected and said out loud. A reader can act on "these are the
    same file"; they cannot act on a flat line they believe is real.
    """
    rows = dataset.get("rows") or []
    if not rows:
        return {"identical": False, "captures": 0}

    per_capture: dict[str, set[tuple]] = defaultdict(set)
    for row in rows:
        upload = str(row.get("upload_id") or "")
        per_capture[upload].add(
            (row.get("channel"), row.get("feature_code"), str(row.get("value")))
        )

    signatures = {frozenset(values) for values in per_capture.values()}
    identical = len(per_capture) > 1 and len(signatures) == 1
    filenames = {str(r.get("original_filename") or "") for r in rows if r.get("original_filename")}
    return {
        "identical": identical,
        "captures": len(per_capture),
        "distinct_signatures": len(signatures),
        "filenames": sorted(filenames),
        "note": (
            f"All {len(per_capture)} captures in this window carry identical feature "
            "values. They appear to be the same source file ingested repeatedly rather "
            "than separate measurements, so no trend can be assessed and the readings "
            "below describe one measurement, not a history."
        ) if identical else "",
    }


def convert_to_velocity(
    ledger: Ledger,
    dataset: dict[str, Any],
    shaft: dict[str, Any],
    acceleration_unit: str | None,
) -> dict[str, Any]:
    """Convert the 1X acceleration amplitude to velocity in mm/s.

    ISO 10816-3 grades broadband velocity, and the platform stores
    acceleration in "scaled_eng" -- its own scaled engineering units. Two
    things are needed to bridge that: what the stored number physically is,
    and a frequency to integrate at.

    The frequency is now available: the 1X amplitude sits at the shaft speed
    by definition, so converting it is a genuine single-frequency conversion
    rather than an approximation over a band.

    What the number IS cannot be determined from the data. The sensor is a
    100 mV/g IEPE accelerometer and the plot configuration declares
    "acceleration", but nothing records whether the stored value is volts off
    the accelerometer or g after the sensitivity was applied -- and the two
    differ by a factor of ten. "scaled_eng" is a name for exactly that
    uncertainty. So it is asked for rather than assumed: without
    ``acceleration_unit`` no conversion happens and the report says why.
    Guessing here would put a severity zone out by an order of magnitude,
    which is the failure this project has spent its effort eliminating.

    Note this converts 1X only. ISO grades the 10-1000 Hz broadband level,
    which needs the whole waveform integrated, not one spectral line. The
    result is therefore a lower bound on the ISO input, and is reported as
    such rather than graded.
    """
    if not shaft.get("ok"):
        return {"ok": False, "reason": "No shaft speed, so acceleration cannot be integrated."}
    if acceleration_unit not in ("g", "v"):
        return {"ok": False, "reason": (
            "The stored acceleration values are in 'scaled_eng' and nothing records whether "
            "that is volts from the accelerometer or g after its 100 mV/g sensitivity was "
            "applied. The two differ by a factor of ten, so no conversion has been made. "
            "Re-run with --acceleration-unit g or --acceleration-unit v once the "
            "acquisition chain is confirmed."
        )}

    from app.domain import units as unit_lib

    sensitivity_mv_per_g = 100.0
    frequency_hz = float(shaft["hz"])
    rows = [r for r in (dataset.get("rows") or []) if r.get("feature_code") == "amplitude_1x"]
    if not rows:
        return {"ok": False, "reason": "No 1X amplitude was recorded."}

    worst = max(rows, key=lambda r: _as_float(r.get("value")) or 0.0)
    raw = _as_float(worst.get("value")) or 0.0
    in_g = raw if acceleration_unit == "g" else raw / (sensitivity_mv_per_g / 1000.0)

    try:
        result = unit_lib.convert_amplitude(in_g, "g", "mm/s", frequency_hz, "rms", "rms")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"Conversion failed: {exc}"}

    velocity = float(getattr(result, "value", 0.0))
    assumption = (
        "stored values taken as g" if acceleration_unit == "g"
        else f"stored values taken as volts, divided by {sensitivity_mv_per_g:g} mV/g"
    )

    fact = ledger.computed(
        "1X velocity amplitude, worst channel", round(velocity, 4), "mm/s RMS",
        f"app/domain/units.convert_amplitude at {frequency_hz:g} Hz",
        detail={"raw": raw, "raw_unit": "scaled_eng", "as_g": in_g,
                "frequency_hz": frequency_hz, "channel": worst.get("channel")},
        caveats=[
            f"Velocity was derived by integrating the 1X acceleration at the estimated "
            f"shaft speed, {assumption}. It is the 1X component only, not the 10-1000 Hz "
            "broadband level ISO 10816-3 grades, so it is a lower bound on the ISO input "
            "and no zone has been assigned from it.",
        ],
    )

    return {
        "ok": True,
        "velocity_mm_s": round(velocity, 4),
        "raw": raw,
        "as_g": round(in_g, 5),
        "channel": worst.get("channel"),
        "frequency_hz": frequency_hz,
        "assumption": assumption,
        "fact": fact.id,
    }


def derive_shaft_speed(ledger: Ledger, dataset: dict[str, Any]) -> dict[str, Any]:
    """Recover the shaft speed the platform estimated from the spectrum.

    No capture in the database records ``rotation_speed_rpm``, so it looked at
    first as though no shaft speed existed and nothing diagnostic was possible.
    It does exist: the feature extractor stores its FFT-derived estimate in the
    metadata of the 1X/2X/3X features, where nothing downstream was reading it.

    The estimate is per channel and the channels do not always agree. On the
    reference pump seven channels report 25 Hz and one reports 50 Hz --
    exactly double, which is the estimator locking onto the 2X peak rather
    than the fundamental. The majority is taken as the working value and the
    disagreement is reported, because a shaft speed wrong by a factor of two
    puts every derived bearing frequency out by the same factor.

    This is an estimate from the signal, not a measurement of the machine. A
    tachometer reading recorded on the capture would be better and is what
    ``rotation_speed_rpm`` is for.
    """
    rows = dataset.get("rows") or []
    per_channel: dict[Any, float] = {}
    for row in rows:
        hz = (row.get("metadata") or {}).get("estimated_shaft_hz")
        if hz:
            per_channel.setdefault(row.get("channel"), float(hz))

    if not per_channel:
        return {"ok": False, "reason": (
            "No shaft speed is available. No capture records rotation_speed_rpm and no "
            "spectral estimate was stored, so no order-based or bearing frequency can "
            "be derived."
        )}

    tally: dict[float, list[Any]] = defaultdict(list)
    for channel, hz in per_channel.items():
        tally[hz].append(channel)
    consensus_hz = max(tally, key=lambda hz: len(tally[hz]))
    agreeing = sorted(tally[consensus_hz], key=str)
    dissenting = {hz: sorted(chs, key=str) for hz, chs in tally.items() if hz != consensus_hz}

    fact = ledger.computed(
        "shaft speed (estimated from the spectrum)", round(consensus_hz * 60.0), "rpm",
        f"platform FFT estimate, agreed by {len(agreeing)} of {len(per_channel)} channels",
        detail={"hz": consensus_hz, "channels_agreeing": agreeing, "dissenting": dissenting},
        confidence=len(agreeing) / len(per_channel),
        caveats=[
            "Shaft speed here is estimated from the vibration spectrum, not measured. "
            "No capture carries a tachometer reading (rotation_speed_rpm is empty on "
            "every capture), so every order and bearing frequency derived from it "
            "inherits that uncertainty."
        ],
    )

    return {
        "ok": True,
        "hz": consensus_hz,
        "rpm": round(consensus_hz * 60.0),
        "fact": fact.id,
        "agreeing": agreeing,
        "dissenting": dissenting,
        "confidence": round(100 * len(agreeing) / len(per_channel)),
        "note": _dissent_note(dissenting, consensus_hz) if dissenting else "",
    }



def _dissent_note(dissenting: dict, consensus_hz: float) -> str:
    """Explain the channels that disagreed with the consensus shaft speed.

    Written out rather than inlined for two reasons: the singular case has to
    read as English ("Channel 3 reports", not "Channels 3 report"), and the
    harmonic explanation is only true when the dissenting frequency really is
    a multiple of the consensus. Offering it for an unrelated frequency would
    hand the reader a confident diagnosis of the wrong thing.
    """
    channels = sorted(sum((list(v) for v in dissenting.values()), []))
    listed = ", ".join(str(c) for c in channels)
    subject = f"Channel {listed} reports" if len(channels) == 1 else f"Channels {listed} report"
    speeds = ", ".join(f"{hz:g} Hz" for hz in dissenting)

    harmonics = sorted({
        round(hz / consensus_hz) for hz in dissenting
        if consensus_hz > 0 and abs(hz / consensus_hz - round(hz / consensus_hz)) < 0.05
        and round(hz / consensus_hz) >= 2
    })
    if harmonics:
        orders = ", ".join(f"{n}X" for n in harmonics)
        tail = (
            f" That is an exact {orders} of the consensus, which normally means the "
            "estimator locked onto a harmonic peak rather than the fundamental on that "
            "channel."
        )
    else:
        tail = (
            " That is not a harmonic of the consensus, so it is a genuine disagreement "
            "rather than a peak-picking artefact, and the consensus is weaker than the "
            "channel count suggests."
        )
    return f"{subject} {speeds} instead.{tail}"

#: A feature every one of whose readings breaches the critical threshold is
#: evidence about the threshold, not about the machine. Set at 95% rather than
#: 100% so a single normal reading does not hide the problem.
_ALL_CRITICAL_SHARE = 0.95


def assess_threshold_calibration(dataset: dict[str, Any]) -> dict[str, Any]:
    """Do these thresholds look calibrated to this sensor?

    Written after the first real report announced "Action required -- 270
    critical" on a pump whose RMS threshold is 0.02 while every reading it has
    ever produced falls between 0.024 and 0.424. Every reading was critical,
    by a factor of up to twenty-one. That is a threshold configured for a
    different scale, not a machine in distress, and a report that calls it
    "action required" sends an engineer to look at a healthy pump -- or, worse,
    teaches them that critical means nothing here.

    The test is deliberately blunt: a feature whose readings are essentially
    all critical is reported as uncalibrated. A genuinely failing machine
    normally shows some spread, and if it truly is uniformly critical, the
    trend and the baseline will say so once they exist.
    """
    rows = dataset.get("rows") or []
    if not rows:
        return {"suspect": [], "assessable": [], "checked": False}

    by_feature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("feature_code"):
            by_feature[row["feature_code"]].append(row)

    suspect: list[dict[str, Any]] = []
    assessable: list[str] = []
    for code, entries in sorted(by_feature.items()):
        graded = [r for r in entries if r.get("status") in ("normal", "warning", "critical")]
        if not graded:
            continue
        critical = [r for r in graded if r.get("status") == "critical"]
        share = len(critical) / len(graded)
        if share >= _ALL_CRITICAL_SHARE:
            values = [v for v in (_as_float(r.get("value")) for r in graded) if v is not None]
            suspect.append({
                "code": code,
                "name": entries[0].get("feature_name") or code,
                "critical_share": round(100 * share),
                "readings": len(graded),
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "unit": entries[0].get("unit", ""),
            })
        else:
            assessable.append(code)

    return {
        "checked": True,
        "suspect": suspect,
        "assessable": assessable,
        "note": (
            f"{len(suspect)} of {len(by_feature)} features have essentially every reading "
            "marked critical. A threshold that no reading has ever satisfied is describing "
            "its own configuration rather than the machine, so those features are reported "
            "below but not treated as evidence of a fault. Calibrating them against a "
            "healthy baseline for this sensor is the first thing that would make this "
            "report diagnostic."
        ) if suspect else "",
    }


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _change(first: float | None, last: float | None) -> float | None:
    if first is None or last is None or first == 0:
        return None
    return round(100.0 * (last - first) / abs(first), 1)


def _direction(change: float | None) -> str:
    if change is None:
        return "unknown"
    if change > 20:
        return "rising"
    if change < -20:
        return "falling"
    return "steady"


def _worst_status(statuses: set[str]) -> str:
    return max(statuses, key=lambda s: _SEVERITY.get(s, 0)) if statuses else ""


# --------------------------------------------------------------------------
# Computed -- from app/domain, the unit-tested library
# --------------------------------------------------------------------------


def iso_reference(
    ledger: Ledger,
    machine_type: str,
    *,
    power_kw: float | None = None,
    foundation: str | None = None,
    integrated_driver: bool | None = None,
) -> dict[str, Any]:
    """The ISO 10816-3 limits that would apply, and whether they are usable.

    Registered as reference only. ``comparable`` is False whenever the
    measured values are not in mm/s RMS, and the report must then present the
    limits as context rather than as a verdict. This is the single most
    dangerous place in a vibration report to be approximately right.
    """
    from app.domain import iso10816
    import json

    group = iso10816.infer_machine_group(
        power_kw=power_kw, machine_type=machine_type,
        integrated_driver=bool(integrated_driver),
    )
    ambiguous = "pump" in (machine_type or "").lower() and integrated_driver is None

    if group is None:
        return {"ok": False, "reason": (
            "The ISO group could not be determined from the machine type and rated "
            "power available. Below 15 kW, ISO 10816-3 Groups 1-4 do not apply."
        )}

    data = json.loads(iso10816.DATA_PATH.read_text(encoding="utf-8"))
    groups = [3, 4] if ambiguous else [group]
    supports = [foundation] if foundation in ("rigid", "flexible") else ["rigid", "flexible"]

    tables: list[dict[str, Any]] = []
    for candidate in groups:
        info = data["groups"][str(candidate)]
        for support in supports:
            values = data["velocity_rms_mm_s"][str(candidate)][support]
            facts = {}
            for name, value in zip(("A/B", "B/C", "C/D"), values):
                fact = ledger.computed(
                    f"ISO 10816-3 Group {candidate} {support} {name} boundary",
                    value, "mm/s RMS",
                    "app/domain/iso10816 (unit-tested reference tables)",
                    detail={"group": candidate, "support": support, "boundary": name},
                )
                facts[name] = fact.id
            tables.append({
                "group": candidate,
                "group_name": info["name"],
                "scope": info["description"],
                "support": support,
                "boundaries": dict(zip(("A/B", "B/C", "C/D"), values)),
                "fact_ids": facts,
            })

    return {
        "ok": True,
        "tables": tables,
        "ambiguous": ambiguous,
        "ambiguity_note": (
            "ISO 10816-3 classifies pumps as Group 3 (separate driver) or Group 4 "
            "(integrated driver) regardless of rated power. The driver arrangement "
            "was not supplied, so both are shown. They differ by roughly 60%."
        ) if ambiguous else "",
        "convention": iso10816.BOUNDARY_CONVENTION,
    }
