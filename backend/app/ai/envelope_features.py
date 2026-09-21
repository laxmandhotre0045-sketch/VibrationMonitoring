"""Ten envelope measurements — VIK-020.

This is the group the roadmap calls the most important one for the demo, and
it is the only one that can actually name a bearing defect.

**Why the ordinary spectrum cannot do it.** A spalled bearing does not ring at
its defect rate. Each time a rolling element strikes the fault it excites a
structural resonance a few kilohertz up, and the defect rate is the rate at
which those rings repeat -- an amplitude modulation, not a tone. In the raw
spectrum almost nothing appears at the defect frequency. Measured on the
harness, the outer-race channel's largest line is the 4.2 kHz resonance, and
BPFO barely registers.

Worse, at the resolution real captures have, three of the four bearing
frequencies of the test pump sit in the same spectrum line as an ordinary
shaft harmonic:

    BPFO   75.58 Hz   vs  3x shaft  74.00 Hz
    BPFI  121.75 Hz   vs  5x shaft 123.33 Hz
    BSF    49.83 Hz   vs  2x shaft  49.33 Hz  (and mains, at 50.00)

So looking for them in the ordinary spectrum does not merely fail, it
produces a bearing diagnosis for a loose foot.

**What this does instead.** Band-pass around the resonance, take the envelope
of that band with a Hilbert transform, and transform the envelope. Shaft
harmonics are not carried on the resonance, so they largely disappear, and
the repetition rate of the impacts appears directly. Measured across the
harness, the outer-race channel scores 151 on BPFO against 1.0 on the other
three, and the inner-race channel scores 24 on BPFI.

**Choosing the band matters and is not obvious.** Spectral kurtosis is the
textbook selector and it picked the wrong band here -- 1600 Hz for both
bearings, against true resonances of 4200 and 3100 -- because a low band
holds impulsive content with fewer competing tones. The largest line in the
raw spectrum above 500 Hz found both to within 1% (4194 and 3122). So that
is the selector, and band kurtosis is kept as a feature, where it is
genuinely useful: 6.9 and 12.1 on the two bearing channels against 0.1-0.3
on everything else.

**What this still cannot do**, and says so rather than guessing: a defect
frequency closer than one line to a shaft harmonic cannot be told apart from
it, and one below about two lines cannot be resolved at all. On the test pump
that is BSF and FTF respectively. Both are reported with the collision named.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from app.services.signal_processing import compute_envelope_spectrum

#: Appended to FEATURE_CODES after the frequency-domain block.
ENVELOPE_FEATURE_CODES = [
    "ftf_band_energy",
    "bsf_band_energy",
    "bpfo_band_energy",
    "bpfi_band_energy",
    "bearing_harmonic_energy",
    "envelope_peak",
    "envelope_kurtosis",
    "demodulated_peak_prominence",
    "repetition_impact_frequency",
    "resonance_band_energy",
]

#: Nothing below this is a structural resonance; it is the machine's own
#: running speed and its harmonics. Both harness resonances (3100, 4200) and
#: any realistic bearing resonance sit well above it.
RESONANCE_FLOOR_HZ = 500.0

#: Half-width of the demodulation band, as a fraction of the resonance
#: frequency, with a floor.
#:
#: The fraction is the easy part: wide enough to hold the ringing and its
#: sidebands, narrow enough to leave the shaft harmonics below it out.
#:
#: The floor is there for a harder reason -- the band-pass cannot deliver a
#: narrow band at these frequencies, and fails quietly rather than raising.
#: Asked for a band around 4,194 Hz, the share of the filtered signal's
#: energy that actually lies inside the band it was given:
#:
#:      +/-   5 Hz   19.9%        +/- 400 Hz   80.8%
#:      +/-  50 Hz   21.9%        +/- 800 Hz   90.3%
#:      +/- 100 Hz   50.7%        +/-1258 Hz   94.9%
#:
#: Below a few hundred hertz the output is mostly content from outside the
#: requested band, so "demodulating the resonance" would be demodulating the
#: whole signal while appearing to have selected something. 800 Hz is where
#: the filter starts doing what it is asked.
BAND_FRACTION = 0.30
BAND_MIN_HALF_WIDTH_HZ = 800.0

#: Block length for the envelope transform, and the cap it is allowed to
#: reach.
#:
#: compute_envelope_spectrum defaults to 1024 for plotting, which gives 25 Hz
#: lines -- coarser than the gap between BPFO and BPFI on this machine, so the
#: two could not be told apart. Its own cap of 4096 is not enough either: on a
#: 50 kSPS capture that is 12.2 Hz, and BPFO sits 1.58 Hz from three times
#: shaft speed. The cap, not the record length, was the limit -- a longer
#: capture with a 4096 block resolves nothing new.
#:
#: 32768 gives 1.53 Hz at 50 kSPS, which is just enough to separate them, and
#: it is taken only when the record is long enough to fill it. A shorter
#: record falls back to whatever it can fill, which is what happens today.
ENVELOPE_FFT_LINES = 32768
ENVELOPE_MAX_SEGMENT = 32768

#: How many multiples of the strongest defect rate to add up for
#: bearing_harmonic_energy. A real defect repeats, so its envelope carries
#: harmonics; noise at one frequency does not.
MAX_DEFECT_HARMONIC = 5

#: Shaft orders a defect frequency might be confused with. Integer orders
#: plus the half order looseness produces.
SHAFT_ORDERS = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)

#: A defect frequency needs at least this many spectrum lines beneath it to
#: be a measurement rather than a rounding. Below two, the line is adjacent
#: to DC and its amplitude is the envelope's own mean leaking in.
MIN_RESOLVABLE_LINES = 2.0


@dataclass
class EnvelopeBand:
    """The demodulation band, and how confident we are it is a resonance."""
    centre_hz: float = 0.0
    low_hz: float = 0.0
    high_hz: float = 0.0
    prominence: float = 0.0
    note: Optional[str] = None


def _prominence_at(freqs: np.ndarray, amps: np.ndarray, target_hz: float,
                   tolerance_hz: float) -> float:
    """Height of the envelope line at target_hz, over the median line.

    A ratio rather than an absolute amplitude, because the envelope's scale
    depends on the band that was demodulated, and a number that moves with
    the band cannot be compared between channels or over time.
    """
    if target_hz <= 0 or freqs.size == 0:
        return 0.0
    near = np.abs(freqs - target_hz) <= tolerance_hz
    if not np.any(near):
        return 0.0
    median = float(np.median(amps)) or 1e-30
    return float(np.max(amps[near])) / median


def find_resonance(freqs: np.ndarray, amplitudes: np.ndarray,
                   floor_hz: float = RESONANCE_FLOOR_HZ) -> EnvelopeBand:
    """The band to demodulate: around the largest line above the floor.

    Returns the band whatever it finds, with `prominence` saying how much to
    trust it. On a machine with no bearing defect the largest high-frequency
    line is arbitrary -- 11,384 Hz on the unbalance signature -- and the
    envelope of an arbitrary band shows nothing, which is the right answer.
    Measured prominence separates the two cleanly: 174 and 39 on the bearing
    channels, 3 to 4 on the other six.
    """
    band = EnvelopeBand()
    if freqs is None or amplitudes is None or len(freqs) < 4:
        band.note = "no spectrum supplied, so no resonance could be located"
        return band

    freqs = np.asarray(freqs, dtype=float)
    amplitudes = np.asarray(amplitudes, dtype=float)
    above = freqs > floor_hz
    if not np.any(above):
        band.note = f"nothing above {floor_hz:g} Hz to demodulate"
        return band

    high_freqs, high_amps = freqs[above], amplitudes[above]
    peak = int(np.argmax(high_amps))
    band.centre_hz = float(high_freqs[peak])
    median = float(np.median(high_amps)) or 1e-30
    band.prominence = float(high_amps[peak]) / median

    half = max(BAND_MIN_HALF_WIDTH_HZ, band.centre_hz * BAND_FRACTION)
    band.low_hz = max(floor_hz * 0.4, band.centre_hz - half)
    band.high_hz = band.centre_hz + half
    return band


def _shaft_collision(defect_hz: float, shaft_hz: Optional[float],
                     resolution_hz: float) -> Optional[str]:
    """Which shaft harmonic this defect rate cannot be told apart from."""
    if not shaft_hz or shaft_hz <= 0 or defect_hz <= 0:
        return None
    for order in SHAFT_ORDERS:
        harmonic = order * shaft_hz
        if abs(defect_hz - harmonic) <= resolution_hz:
            return (
                f"{defect_hz:.2f} Hz is within one spectrum line "
                f"({resolution_hz:.2f} Hz) of {order:g}x shaft "
                f"({harmonic:.2f} Hz), so a reading here cannot be told apart "
                f"from ordinary shaft content"
            )
    return None


def extract_envelope_features(
    samples: list[float] | np.ndarray,
    sampling_rate_hz: float,
    *,
    freqs: Optional[np.ndarray] = None,
    amplitudes: Optional[np.ndarray] = None,
    shaft_hz: Optional[float] = None,
    bearing_orders: Optional[dict[str, Optional[float]]] = None,
) -> dict[str, dict[str, Any]]:
    """All ten, from one envelope transform.

    `bearing_orders` is FTF/BSF/BPFO/BPFI as multiples of shaft speed, from
    the catalogue via VIK-010. Without it the four band energies are 0.0 with
    a note saying no bearing is known -- not because nothing was found, but
    because nothing was looked for, and those are different answers.

    `freqs` / `amplitudes` are the raw spectrum already computed for the
    frequency features, used to locate the resonance. Passing them avoids a
    third transform per channel.
    """
    data = np.asarray(samples, dtype=np.float64)
    if data.size < 64 or sampling_rate_hz <= 0:
        return _empty("too few samples to demodulate")

    band = find_resonance(freqs, amplitudes)
    if band.centre_hz <= 0:
        return _empty(band.note or "no resonance band could be chosen")

    try:
        spectrum = compute_envelope_spectrum(
            data.tolist(), sampling_rate_hz,
            fft_lines=ENVELOPE_FFT_LINES,
            max_segment=ENVELOPE_MAX_SEGMENT,
            low_cut_hz=band.low_hz, high_cut_hz=band.high_hz,
        )
    except Exception as exc:                       # pragma: no cover
        return _empty(f"envelope transform failed: {exc}")

    env_freqs = np.asarray(spectrum["x"], dtype=float)
    env_amps = np.asarray(spectrum["y"], dtype=float)
    resolution_hz = float(spectrum["metadata"]["delta_f_hz"])
    tolerance_hz = resolution_hz * 1.5

    # Ignore the very bottom of the envelope spectrum. The envelope of any
    # signal has a large mean, and its leakage into the first line or two
    # would otherwise be read as a very slow defect.
    usable = env_freqs > resolution_hz * MIN_RESOLVABLE_LINES
    search_freqs = env_freqs[usable]
    search_amps = env_amps[usable]
    if search_freqs.size < 4:
        return _empty("envelope spectrum too short to measure")

    # --- the four defect rates ----------------------------------------
    orders = bearing_orders or {}
    band_energy: dict[str, float] = {}
    notes: dict[str, str] = {}
    for name in ("ftf", "bsf", "bpfo", "bpfi"):
        order = orders.get(name)
        if not shaft_hz or shaft_hz <= 0:
            band_energy[name] = 0.0
            notes[name] = ("shaft speed unknown, so this defect rate cannot "
                           "be placed; 0.0 here means not looked for")
            continue
        if not order or order <= 0:
            band_energy[name] = 0.0
            notes[name] = ("no bearing is resolved for this machine, so the "
                           "defect rate is unknown; 0.0 means not looked for")
            continue

        defect_hz = float(order) * shaft_hz
        if defect_hz < resolution_hz * MIN_RESOLVABLE_LINES:
            band_energy[name] = 0.0
            notes[name] = (
                f"{name.upper()} is {defect_hz:.2f} Hz and the envelope "
                f"spectrum's lines are {resolution_hz:.2f} Hz apart, so it "
                f"sits below the first usable line and cannot be resolved. A "
                f"longer capture is the only fix."
            )
            continue

        band_energy[name] = _prominence_at(search_freqs, search_amps,
                                           defect_hz, tolerance_hz)
        collision = _shaft_collision(defect_hz, shaft_hz, resolution_hz)
        if collision:
            notes[name] = collision

    # --- how much of a family the strongest defect has ----------------
    # A real defect repeats, so its envelope carries harmonics. One line on
    # its own is as likely to be noise as a bearing.
    strongest = max(band_energy, key=lambda k: band_energy[k]) if band_energy else None
    harmonic_energy = 0.0
    harmonic_basis = "no defect rate was measurable"
    if strongest and band_energy.get(strongest, 0.0) > 0 and shaft_hz:
        base_hz = float(orders.get(strongest) or 0.0) * shaft_hz
        if base_hz > 0:
            found = [
                _prominence_at(search_freqs, search_amps, k * base_hz, tolerance_hz)
                for k in range(1, MAX_DEFECT_HARMONIC + 1)
            ]
            harmonic_energy = float(sum(found))
            harmonic_basis = (
                f"sum of prominence at 1x to {MAX_DEFECT_HARMONIC}x "
                f"{strongest.upper()} ({base_hz:.2f} Hz)"
            )

    # --- the envelope itself ------------------------------------------
    envelope_peak = float(np.max(search_amps))
    median_line = float(np.median(search_amps)) or 1e-30
    demodulated_peak_prominence = envelope_peak / median_line
    repetition_hz = float(search_freqs[int(np.argmax(search_amps))])

    centred = search_amps - float(np.mean(search_amps))
    spread = float(np.std(centred))
    envelope_kurtosis = (
        float(np.mean(centred ** 4) / spread ** 4 - 3.0) if spread > 1e-30 else 0.0
    )

    repetition_order = (repetition_hz / shaft_hz) if shaft_hz else None

    return {
        "ftf_band_energy": _feature(band_energy.get("ftf", 0.0), band, notes.get("ftf")),
        "bsf_band_energy": _feature(band_energy.get("bsf", 0.0), band, notes.get("bsf")),
        "bpfo_band_energy": _feature(band_energy.get("bpfo", 0.0), band, notes.get("bpfo")),
        "bpfi_band_energy": _feature(band_energy.get("bpfi", 0.0), band, notes.get("bpfi")),
        "bearing_harmonic_energy": {
            "value": harmonic_energy, "unit": "dimensionless",
            "metadata": {"basis": harmonic_basis, "strongest": strongest},
        },
        "envelope_peak": {
            "value": envelope_peak, "unit": "scaled_eng",
            "metadata": {"band_hz": [band.low_hz, band.high_hz]},
        },
        "envelope_kurtosis": {
            "value": envelope_kurtosis, "unit": "dimensionless",
            "metadata": {"basis": "excess kurtosis of the envelope spectrum; "
                                  "rises when energy concentrates into lines"},
        },
        "demodulated_peak_prominence": {
            "value": demodulated_peak_prominence, "unit": "dimensionless",
            "metadata": {"basis": "tallest envelope line / median line"},
        },
        "repetition_impact_frequency": {
            "value": repetition_hz, "unit": "Hz",
            "metadata": {"order": repetition_order,
                         "note": "how often the impacts repeat, whatever is "
                                 "causing them"},
        },
        "resonance_band_energy": {
            "value": band.prominence, "unit": "dimensionless",
            "metadata": {"centre_hz": band.centre_hz,
                         "band_hz": [band.low_hz, band.high_hz],
                         "basis": "the resonance line over the median line of "
                                  "the raw spectrum above "
                                  f"{RESONANCE_FLOOR_HZ:g} Hz"},
        },
    }


def _feature(value: float, band: EnvelopeBand, note: Optional[str]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "band_hz": [band.low_hz, band.high_hz],
        "resonance_hz": band.centre_hz,
    }
    if note:
        meta["note"] = note
    return {"value": value, "unit": "dimensionless", "metadata": meta}


def _empty(reason: str) -> dict[str, dict[str, Any]]:
    """Zeros with a reason, never missing keys: an absent key breaks a caller."""
    units = {
        "ftf_band_energy": "dimensionless", "bsf_band_energy": "dimensionless",
        "bpfo_band_energy": "dimensionless", "bpfi_band_energy": "dimensionless",
        "bearing_harmonic_energy": "dimensionless",
        "envelope_peak": "scaled_eng", "envelope_kurtosis": "dimensionless",
        "demodulated_peak_prominence": "dimensionless",
        "repetition_impact_frequency": "Hz",
        "resonance_band_energy": "dimensionless",
    }
    return {code: {"value": 0.0, "unit": units[code], "metadata": {"note": reason}}
            for code in ENVELOPE_FEATURE_CODES}
