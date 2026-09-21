"""Synthetic faults with their answers written down — VIK-017.

This is the scoring ground truth for everything from VIK-018 to VIK-053.
Without it the diagnosis engine can be demonstrated but never proven right:
someone runs it on a capture, reads a plausible answer, and has no way to know
whether it is the correct one. With it, "the engine finds the injected fault
on all six channels" is a statement that either passes or fails.

Built on scripts/create_sample_sensor_csv.py, which already generates eight
channels each carrying a different fault. Two things are added.

**Each signature can be generated alone, and alone means the same as
together.** The original advances one random state across all eight channels
in order, so channel 4 on its own draws different noise from channel 4 within
the set. That makes a single-signature test irreproducible against the batch,
which defeats the point. Each signature now seeds from the base seed plus its
own index, so it is identical either way.

**The expected answer travels with the waveform.** Not just a fault name: the
orders that should appear, the features that should be elevated, and the ones
that should not. A test that only checks the fault name passes an engine that
gets the right answer for the wrong reason, and that engine will be wrong on
the next machine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

#: Matches the existing generator exactly, so a capture produced here is the
#: same asset the rest of the test data describes: a motor and pump train at
#: 1500 rpm.
FS_HZ = 25_600.0
N_SAMPLES = 8_192
SHAFT_HZ = 25.0
BASE_SEED = 20_250_820


@dataclass
class GroundTruth:
    """What a correct diagnosis of this signature looks like."""
    fault: str
    #: Shaft orders that must be present, e.g. 1.0 for 1X, 3.57 for BPFO.
    expected_orders: tuple[float, ...] = ()
    #: The order that should dominate, and WHERE it dominates.
    #:
    #: The domain is not a detail. A bearing defect's energy sits on a
    #: high-frequency resonance, so in the raw spectrum 1X still dominates and
    #: the defect rate is nowhere near the top -- measured here, the outer-race
    #: channel peaks at 1X in the raw spectrum and at 3.62X in the envelope.
    #: Scoring an engine against "dominant_order = 3.57" in the raw spectrum
    #: would mark a correct engine wrong.
    dominant_order: Optional[float] = None
    #: "raw" or "envelope" -- which spectrum dominant_order refers to.
    dominant_domain: str = "raw"
    #: Orders that must be PRESENT in the envelope spectrum even if not
    #: dominant. This is where a bearing fault actually shows.
    envelope_orders: tuple[float, ...] = ()
    #: Sidebands expected around the defect rate, as offsets in orders.
    #: A defect passing through the load zone once per revolution modulates
    #: at 1X, and the sidebands are what distinguish inner race from outer.
    sideband_offsets: tuple[float, ...] = ()
    #: Carrier resonance the impulses ride on, in Hz. What makes envelope
    #: analysis the right tool and a plain spectrum the wrong one.
    resonance_hz: Optional[float] = None
    #: Features a correct engine should find elevated, by FEATURE_CODES name.
    elevated_features: tuple[str, ...] = ()
    #: Features that must NOT be elevated. Stated explicitly because an
    #: engine that flags everything scores well on the positives alone.
    normal_features: tuple[str, ...] = ()
    notes: str = ""


@dataclass
class Signature:
    name: str
    channel_index: int
    description: str
    truth: GroundTruth
    _build: Callable[[list[float], "_Rng"], None] = field(repr=False, default=None)


class _Rng:
    """The generator's own LCG, isolated per signature.

    Reimplementing it rather than importing keeps the harness independent of a
    script that is meant to be runnable and editable; the constants are the
    script's, so a signature generated here matches one generated there.
    """

    def __init__(self, seed: int):
        self._state = seed

    def rnd(self) -> float:
        self._state = (1_103_515_245 * self._state + 12_345) % (2 ** 31)
        return self._state / (2 ** 31)

    def gauss(self) -> float:
        # Sum of twelve uniforms minus six: the script's approximation, kept
        # so the waveforms match.
        return sum(self.rnd() for _ in range(12)) - 6.0


def _sine(amp: float, freq: float, phase: float, t: float) -> float:
    return amp * math.sin(2.0 * math.pi * freq * t + phase)


def _add_impulses(buf: list[float], defect_hz: float, amp: float, tau: float,
                  resonance_hz: float, mod_depth: float) -> None:
    """A decaying resonance burst at each defect strike.

    This is what makes a bearing signature a bearing signature: energy at the
    defect rate carried on a high-frequency resonance, which is why envelope
    analysis finds it and a plain spectrum struggles.
    """
    period = 1.0 / defect_hz
    n = len(buf)
    strike = 0.0
    while strike < n / FS_HZ:
        start = int(strike * FS_HZ)
        modulation = 1.0 + mod_depth * math.sin(2.0 * math.pi * SHAFT_HZ * strike)
        for k in range(int(6 * tau * FS_HZ)):
            idx = start + k
            if idx >= n:
                break
            dt = k / FS_HZ
            buf[idx] += (amp * modulation * math.exp(-dt / tau)
                         * math.sin(2.0 * math.pi * resonance_hz * dt))
        strike += period


# --------------------------------------------------------------------------
# the eight signatures
# --------------------------------------------------------------------------

def _healthy_h(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0015 + _sine(0.045, SHAFT_HZ, 0.0, t) + _sine(0.012, 2 * SHAFT_HZ, 0.7, t)
                  + _sine(0.005, 3 * SHAFT_HZ, 1.9, t) + _sine(0.008, 100.0, 0.3, t)
                  + 0.010 * rng.gauss())


def _healthy_v(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0010 + _sine(0.030, SHAFT_HZ, 1.2, t) + _sine(0.008, 2 * SHAFT_HZ, 2.4, t)
                  + _sine(0.006, 100.0, 1.1, t) + 0.009 * rng.gauss())


def _unbalance(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0020 + _sine(0.420, SHAFT_HZ, 0.4, t) + _sine(0.050, 2 * SHAFT_HZ, 1.5, t)
                  + _sine(0.020, 3 * SHAFT_HZ, 2.8, t) + 0.012 * rng.gauss())


def _misalignment(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0025 + _sine(0.180, SHAFT_HZ, 2.1, t) + _sine(0.550, 2 * SHAFT_HZ, 0.9, t)
                  + _sine(0.150, 3 * SHAFT_HZ, 1.7, t) + _sine(0.040, 4 * SHAFT_HZ, 0.2, t)
                  + 0.015 * rng.gauss())


def _bearing_outer(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0010 + _sine(0.060, SHAFT_HZ, 1.0, t) + _sine(0.025, 2 * SHAFT_HZ, 2.2, t)
                  + 0.020 * rng.gauss())
    _add_impulses(buf, 3.57 * SHAFT_HZ, 1.200, 0.0012, 4200.0, 0.0)


def _looseness(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0018 + _sine(0.120, 0.5 * SHAFT_HZ, 0.6, t) + _sine(0.300, SHAFT_HZ, 1.4, t)
                  + _sine(0.100, 1.5 * SHAFT_HZ, 2.6, t) + _sine(0.220, 2 * SHAFT_HZ, 0.8, t)
                  + _sine(0.080, 2.5 * SHAFT_HZ, 1.9, t) + _sine(0.180, 3 * SHAFT_HZ, 0.1, t)
                  + _sine(0.100, 4 * SHAFT_HZ, 2.0, t) + _sine(0.070, 5 * SHAFT_HZ, 1.3, t)
                  + 0.030 * rng.gauss())


def _bearing_inner(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0008 + _sine(0.050, SHAFT_HZ, 2.5, t) + _sine(0.020, 2 * SHAFT_HZ, 0.5, t)
                  + 0.018 * rng.gauss())
    _add_impulses(buf, 5.43 * SHAFT_HZ, 0.150, 0.0009, 3100.0, 0.6)


def _cavitation(buf, rng):
    for i in range(N_SAMPLES):
        t = i / FS_HZ
        buf[i] = (0.0012 + _sine(0.040, SHAFT_HZ, 1.8, t) + _sine(0.200, 5 * SHAFT_HZ, 0.3, t)
                  + _sine(0.090, 10 * SHAFT_HZ, 2.7, t) + 0.350 * rng.gauss())


SIGNATURES: dict[str, Signature] = {
    "healthy_horizontal": Signature(
        "healthy_horizontal", 0, "Motor DE horizontal, no fault",
        GroundTruth(
            fault="none",
            expected_orders=(1.0, 2.0, 3.0),
            dominant_order=1.0,
            normal_features=("kurtosis", "crest_factor", "rms"),
            notes="A healthy machine still shows 1X. The test is that nothing "
                  "is flagged, not that the spectrum is empty.",
        ),
        _healthy_h),
    "healthy_vertical": Signature(
        "healthy_vertical", 1, "Motor DE vertical, no fault",
        GroundTruth(
            fault="none",
            expected_orders=(1.0, 2.0),
            dominant_order=1.0,
            normal_features=("kurtosis", "crest_factor", "rms"),
        ),
        _healthy_v),
    "unbalance": Signature(
        "unbalance", 2, "Motor NDE horizontal, unbalance",
        GroundTruth(
            fault="unbalance",
            expected_orders=(1.0, 2.0, 3.0),
            dominant_order=1.0,
            elevated_features=("amplitude_1x", "rms"),
            normal_features=("kurtosis",),
            notes="1X dominant and well clear of 2X. Unbalance is not "
                  "impulsive, so kurtosis must stay normal -- an engine that "
                  "calls every raised RMS a bearing fault fails here.",
        ),
        _unbalance),
    "misalignment": Signature(
        "misalignment", 3, "Motor NDE axial, misalignment",
        GroundTruth(
            fault="misalignment",
            expected_orders=(1.0, 2.0, 3.0, 4.0),
            dominant_order=2.0,
            elevated_features=("amplitude_2x", "rms"),
            normal_features=("kurtosis",),
            notes="2X dominant over 1X is the discriminator against "
                  "unbalance. Both raise RMS; only this one raises 2X above 1X.",
        ),
        _misalignment),
    "bearing_outer_race": Signature(
        "bearing_outer_race", 4, "Pump DE horizontal, outer-race defect (BPFO 3.57X)",
        GroundTruth(
            fault="bearing_outer_race",
            expected_orders=(1.0, 3.57),
            dominant_order=3.57,
            dominant_domain="envelope",
            envelope_orders=(3.57,),
            resonance_hz=4200.0,
            elevated_features=("kurtosis", "crest_factor", "envelope_rms"),
            normal_features=("amplitude_1x",),
            notes="Impulsive, so kurtosis and crest rise while 1X does not. "
                  "The energy sits on a 4.2 kHz resonance, which is why "
                  "envelope analysis finds it and a plain spectrum does not.",
        ),
        _bearing_outer),
    "looseness": Signature(
        "looseness", 5, "Pump DE vertical, mechanical looseness",
        GroundTruth(
            fault="looseness",
            expected_orders=(0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0),
            dominant_order=1.0,
            elevated_features=("rms", "fft_band_energy_0_500"),
            notes="Half-order subharmonics plus a long harmonic family is the "
                  "signature. The 0.5X content is what separates it from "
                  "misalignment, which has harmonics but no subharmonics.",
        ),
        _looseness),
    "bearing_inner_race": Signature(
        "bearing_inner_race", 6, "Pump NDE horizontal, early inner-race defect (BPFI 5.43X)",
        GroundTruth(
            fault="bearing_inner_race",
            # 1X dominates even the ENVELOPE here, because the defect is
            # modulated at shaft rate by design. BPFI is present at 5.38X and
            # its sidebands at +/-1X are the discriminator, not its height.
            expected_orders=(1.0, 5.43),
            dominant_order=1.0,
            dominant_domain="envelope",
            envelope_orders=(1.0, 5.43, 10.86),
            sideband_offsets=(-1.0, 1.0),
            resonance_hz=3100.0,
            elevated_features=("kurtosis", "envelope_rms"),
            notes="Early-stage and 1X-modulated: the defect passes through "
                  "the load zone once per revolution, producing sidebands at "
                  "+/-1X around BPFI. Amplitude is deliberately an eighth of "
                  "the outer-race case -- an engine that only finds loud "
                  "faults finds this one too late to be useful.",
        ),
        _bearing_inner),
    "cavitation": Signature(
        "cavitation", 7, "Pump NDE axial, cavitation",
        GroundTruth(
            fault="cavitation",
            expected_orders=(1.0, 5.0, 10.0),
            dominant_order=5.0,
            elevated_features=("noise_floor", "rms"),
            normal_features=("amplitude_1x",),
            notes="Vane pass at 5X on a raised broadband floor. The broadband "
                  "rise is the discriminator: a vane-pass peak alone is "
                  "normal pump behaviour.",
        ),
        _cavitation),
}

#: The six the demo is scored on (VIK-053). The two healthy channels are the
#: controls: an engine that names a fault on these is worse than one that
#: misses a real fault, because it trains people to ignore it.
DEMO_FAMILIES = (
    "unbalance", "misalignment", "bearing_outer_race",
    "looseness", "bearing_inner_race", "cavitation",
)


def generate(name: str) -> tuple[list[float], GroundTruth]:
    """One signature's samples and its expected answer.

    Seeded from the signature's own channel index, so generating it alone
    produces exactly what generating the whole set produces. The original
    script advances one random state across all eight channels in order, which
    makes a single-channel test irreproducible against the batch.
    """
    if name not in SIGNATURES:
        raise KeyError(
            f"Unknown signature {name!r}. Available: {', '.join(sorted(SIGNATURES))}"
        )
    signature = SIGNATURES[name]
    buf = [0.0] * N_SAMPLES
    signature._build(buf, _Rng(BASE_SEED + signature.channel_index))
    return buf, signature.truth


def generate_all() -> dict[str, tuple[list[float], GroundTruth]]:
    """Every signature. Equivalent to calling generate() for each name."""
    return {name: generate(name) for name in SIGNATURES}


def order_to_hz(order: float, shaft_hz: float = SHAFT_HZ) -> float:
    """A shaft order as a frequency. Kept here so a test does not have to
    remember which shaft speed the harness used."""
    return order * shaft_hz


def describe(name: str) -> dict[str, Any]:
    """The ground truth as a plain dict, for recording alongside a score."""
    signature = SIGNATURES[name]
    truth = signature.truth
    return {
        "signature": name,
        "channel_index": signature.channel_index,
        "description": signature.description,
        "fault": truth.fault,
        "expected_orders": list(truth.expected_orders),
        "expected_hz": [order_to_hz(o) for o in truth.expected_orders],
        "dominant_order": truth.dominant_order,
        "dominant_domain": truth.dominant_domain,
        "dominant_hz": (order_to_hz(truth.dominant_order)
                        if truth.dominant_order else None),
        "envelope_orders": list(truth.envelope_orders),
        "envelope_hz": [order_to_hz(o) for o in truth.envelope_orders],
        "sideband_offsets": list(truth.sideband_offsets),
        "resonance_hz": truth.resonance_hz,
        "elevated_features": list(truth.elevated_features),
        "normal_features": list(truth.normal_features),
        "shaft_hz": SHAFT_HZ,
        "sampling_rate_hz": FS_HZ,
        "sample_count": N_SAMPLES,
        "notes": truth.notes,
    }
