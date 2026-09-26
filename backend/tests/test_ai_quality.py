"""Whether a capture can be trusted — VIK-022.

The ticket's acceptance is "all eight checks implemented; a deliberately
clipped capture returns Low with the reason". Clipping actually returns
Invalid, which is stronger and is argued for below.

Two things these tests are really about.

**Each check must fire on its own fault and on nothing else.** A quality
engine that flags everything is ignored within a week, and one that flags
the wrong thing sends someone to check the input gain when the sensor is
dead. Both of those happened while this was being written: the first
clipping check reported a quantisation-limited channel and a dead channel as
"clipped", because a channel with two values available repeats its extreme
constantly.

**A check that cannot run must not report a pass.** The steadiness check
compares the halves of a record, and at this machine's 0.28 s each half
holds 1.7 shaft revolutions. Measured across 160 real channel-records of a
pump running perfectly steadily, the level ratio between halves reached 3.0
and the crossing rate moved 150%. The first version duly called half the
channels unstable. Those numbers are the record length, not the machine.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ai.quality import (
    CONFIDENCE_FACTOR,
    HIGH,
    INVALID,
    LOW,
    MEDIUM,
    MIN_REVOLUTIONS_PER_HALF,
    assess_capture,
    assess_channel,
)

FS = 50_000.0
N = 50_000                      # one second, long enough for every check
SHAFT_HZ = 1480 / 60.0
FULL_SCALE_G = 5.0 / 0.100      # +/-5 V at 100 mV/g
STEP_G = 5.0 / 32768 / 0.100    # 0.00153 g, measured on all eight channels

CHECKS = ("missing_data", "clipping", "saturation", "noise_floor",
          "bias_drift", "dc_offset", "unstable_speed", "loose_sensor")


def healthy(seed: int = 0) -> np.ndarray:
    t = np.arange(N) / FS
    rng = np.random.default_rng(seed)
    return 0.05 * np.sin(2 * np.pi * 120 * t) + 0.005 * rng.normal(size=N)


def assess(x, **kw):
    return assess_channel(x, FS, full_scale_g=FULL_SCALE_G,
                          quantisation_step_g=STEP_G, shaft_hz=SHAFT_HZ, **kw)


# ------------------------------------------------- the ticket's acceptance --

def test_a_deliberately_clipped_capture_is_rejected_with_the_reason():
    """The stated acceptance. It returns Invalid rather than Low, and that is
    deliberate: once the peaks are cut off, every amplitude, crest factor and
    harmonic from the channel is understated by an unknown amount. There is
    no confidence figure that makes such a reading safe to act on, so the
    factor is zero.
    """
    result = assess(np.clip(healthy(), -0.04, 0.04))

    assert result.level == INVALID
    assert result.failed == ["clipping"]
    assert result.confidence_factor == 0.0
    assert not result.usable

    reason = result.reasons[0]
    assert "clipped" in reason
    assert "peaks have been cut off" in reason
    assert "understated" in reason


def test_all_eight_checks_are_present_and_run():
    result = assess(healthy())
    assert [c.name for c in result.checks] == list(CHECKS)
    assert len(CHECKS) == 8


def test_a_clean_channel_passes_everything():
    """The half that matters more. An engine that flags a good capture is
    worse than one that misses a bad one, because it teaches people to
    ignore it."""
    result = assess(healthy())
    assert result.level == HIGH
    assert result.failed == []
    assert result.confidence_factor == 1.0
    assert result.usable


# ------------------------------------ each fault, and only its own check --

@pytest.mark.parametrize("name,signal,expected_level,expected_check", [
    ("clipped", lambda: np.clip(healthy(), -0.04, 0.04), INVALID, "clipping"),
    ("saturated", lambda: healthy() / healthy().max() * 45, LOW, "saturation"),
    ("quantisation-limited",
     lambda: np.round(healthy() * 0.02 / STEP_G) * STEP_G, LOW, "noise_floor"),
    ("dead", lambda: np.zeros(N), INVALID, "noise_floor"),
    ("drifting bias", lambda: healthy() + np.linspace(0, 0.3, N), LOW, "bias_drift"),
    ("large offset", lambda: healthy() - 4.0, MEDIUM, "dc_offset"),
    ("speed change",
     lambda: np.concatenate([healthy()[:N // 2], healthy()[N // 2:] * 6]),
     LOW, "unstable_speed"),
    ("loose sensor",
     lambda: healthy() + np.where(
         np.random.default_rng(1).random(N) < 0.0004, 2.0, 0.0),
     LOW, "loose_sensor"),
    ("not finite",
     lambda: np.where(np.arange(N) % 997 == 0, np.nan, healthy()),
     INVALID, "missing_data"),
])
def test_each_fault_is_named_by_its_own_check(name, signal, expected_level,
                                              expected_check):
    result = assess(signal())
    assert result.level == expected_level, f"{name}: {result.failed}"
    assert result.failed == [expected_check], (
        f"{name} should fail only {expected_check}, but failed {result.failed}"
    )
    assert result.reasons and len(result.reasons[0]) > 40


# ---------------------------------------- the two misfires this engine had --

def test_a_channel_with_nothing_to_measure_is_not_called_clipped():
    """A channel spanning one or two converter counts repeats its extreme
    value in long runs, because those are the only values it has. The first
    clipping check read that as a rail, which sends someone to check the
    input gain when the sensor is simply not moving."""
    quantised = np.round(healthy() * 0.02 / STEP_G) * STEP_G
    result = assess(quantised)

    assert "clipping" not in result.failed
    assert "noise_floor" in result.failed
    assert "converter counts" in result.reasons[0]


def test_a_dead_channel_is_called_dead_and_not_clipped():
    result = assess(np.zeros(N))
    assert result.failed == ["noise_floor"]
    assert "does not move at all" in result.reasons[0]
    assert "disconnected" in result.reasons[0]


def test_a_real_rail_is_still_caught_after_that_correction():
    """The guard must not have exempted genuine clipping along with it."""
    assert assess(np.clip(healthy(), -0.04, 0.04)).level == INVALID


# ------------------------------------- a check that cannot run is not a pass --

def test_steadiness_is_not_assessed_on_a_record_too_short_to_judge_it():
    """1.7 revolutions a half is the real capture length on this machine.
    Measured there, a steadily running pump shows level ratios up to 3.0
    between halves purely from record length -- so the honest answer is that
    it was not assessed."""
    short = healthy()[:13_888]          # the real 0.28 s record
    result = assess_channel(short, FS, full_scale_g=FULL_SCALE_G,
                            quantisation_step_g=STEP_G, shaft_hz=SHAFT_HZ)

    assert "unstable_speed" in result.not_assessed
    assert "unstable_speed" not in result.failed
    reason = next(c.reason for c in result.checks if c.name == "unstable_speed")
    assert "shaft revolutions" in reason
    assert "not assessed" in reason
    assert "s capture would settle it" in reason


def test_a_not_assessed_check_does_not_make_the_capture_look_good():
    """The whole point of the third outcome. A short clean record is High
    because everything that ran passed -- but the unassessed check is
    reported, not silently counted as a pass."""
    short = healthy()[:13_888]
    result = assess_channel(short, FS, full_scale_g=FULL_SCALE_G,
                            quantisation_step_g=STEP_G, shaft_hz=SHAFT_HZ)
    assert result.not_assessed == ["unstable_speed"]
    assert "unstable_speed" not in [c.name for c in result.checks if not c.passed
                                    and c.applicable]


def test_steadiness_needs_a_shaft_speed_to_mean_anything():
    result = assess_channel(healthy(), FS, full_scale_g=FULL_SCALE_G,
                            quantisation_step_g=STEP_G, shaft_hz=None)
    assert "unstable_speed" in result.not_assessed
    reason = next(c.reason for c in result.checks if c.name == "unstable_speed")
    assert "shaft speed is unknown" in reason


def test_a_long_enough_record_does_get_assessed():
    """The guard must not have switched the check off altogether."""
    result = assess(healthy())
    assert "unstable_speed" not in result.not_assessed
    assert (N / 2 / FS) * SHAFT_HZ >= MIN_REVOLUTIONS_PER_HALF


# -------------------------------------------------- what is not declared --

def test_checks_needing_the_converter_say_so_rather_than_guessing():
    """A clipping threshold invented without knowing the range is a
    threshold about nothing."""
    result = assess_channel(healthy(), FS, shaft_hz=SHAFT_HZ)
    text = " ".join(c.reason for c in result.checks)
    assert "no converter step declared" in text.lower() or \
        "No converter range declared" in text


# ------------------------------------------------------- the whole capture --

def test_a_capture_takes_the_level_of_its_worst_channel():
    """A summary reporting the best of eight would be useless."""
    channels = {f"ch{i}": healthy(i).tolist() for i in range(7)}
    channels["ch7"] = np.clip(healthy(7), -0.04, 0.04).tolist()

    result = assess_capture(channels, FS, full_scale_g=FULL_SCALE_G,
                            quantisation_step_g=STEP_G, shaft_hz=SHAFT_HZ)

    assert result["level"] == INVALID
    assert result["confidence_factor"] == 0.0
    assert "clipping" in result["failed_checks"]
    assert result["channels"][7]["level"] == INVALID
    assert result["channels"][0]["level"] == HIGH, (
        "one bad channel must not condemn the other seven individually"
    )


def test_the_confidence_factor_falls_with_the_level():
    assert CONFIDENCE_FACTOR[HIGH] == 1.0
    assert CONFIDENCE_FACTOR[INVALID] == 0.0
    levels = [HIGH, MEDIUM, LOW, INVALID]
    factors = [CONFIDENCE_FACTOR[x] for x in levels]
    assert factors == sorted(factors, reverse=True)


def test_invalid_means_no_finding_at_all_not_a_quiet_one():
    """Zero rather than a small number. A capture that cannot be measured
    must not produce a hedged diagnosis -- it must produce none."""
    assert CONFIDENCE_FACTOR[INVALID] == 0.0


# ------------------------------------------------------------ robustness --

@pytest.mark.parametrize("x", [
    [], [1.0], [0.0] * 4, list(np.full(100, np.inf)),
    list(np.full(100, -np.inf)), [1e308] * 100, [-1e308] * 100,
])
def test_nothing_raises_whatever_arrives(x):
    result = assess_channel(x, FS, full_scale_g=FULL_SCALE_G,
                            quantisation_step_g=STEP_G, shaft_hz=SHAFT_HZ)
    assert result.level in (HIGH, MEDIUM, LOW, INVALID)
    assert isinstance(result.confidence_factor, float)


def test_an_empty_capture_does_not_raise():
    assert assess_capture({}, FS)["level"] == HIGH


def test_a_channel_named_oddly_is_skipped_rather_than_crashing():
    result = assess_capture({"ch0": healthy().tolist(), "temperature": [1.0]}, FS,
                            full_scale_g=FULL_SCALE_G, quantisation_step_g=STEP_G,
                            shaft_hz=SHAFT_HZ)
    assert set(result["channels"]) == {0}


def test_every_check_explains_itself_whether_it_passed_or_failed():
    """A reader looking at a passing channel should still be able to see
    what was measured."""
    for check in assess(healthy()).checks:
        assert len(check.reason) > 20, check.name
        assert check.reason.endswith(".") or check.reason.endswith("counts."), check.name


# ------------------------------------------ gaps mutation testing found --

def test_the_flat_top_is_measured_from_rest_not_from_zero():
    """ch7 on this gateway rests at -0.145 g. Measured from zero, a channel
    clipped symmetrically about its own bias has its two rails at different
    distances, so only one of them counts and the run is halved."""
    biased = np.clip(healthy(), -0.04, 0.04) - 0.145
    result = assess(biased)
    assert result.level == INVALID
    assert "clipping" in result.failed


def test_the_clip_run_length_is_clear_of_what_healthy_data_does():
    """Across 160 real channel-records the longest run at the extreme is 1
    in the median case and never exceeds 5. A genuine rail produced 72."""
    from app.ai.quality import CLIP_RUN_LENGTH

    assert CLIP_RUN_LENGTH >= 4 * 5, "too close to what healthy data does"

    # and the margin is real in both directions
    clipped = np.clip(healthy(), -0.04, 0.04)
    deviation = np.abs(clipped - clipped.mean())
    at_extreme = np.isclose(deviation, deviation.max(), rtol=1e-9, atol=0.0)
    longest = max_run = 0
    for flag in at_extreme:
        max_run = max_run + 1 if flag else 0
        longest = max(longest, max_run)
    assert longest > 2 * CLIP_RUN_LENGTH


def test_a_short_record_is_not_accepted_as_a_complete_one():
    """Half a record still produces plausible statistics. What it does not
    produce is a correct time axis, and nothing downstream would notice."""
    result = assess(healthy()[:N // 2], expected_samples=N)
    assert result.failed == ["missing_data"]
    assert result.level == LOW
    assert "50% of the record is missing" in result.reasons[0]


def test_losing_most_of_a_record_is_worse_than_losing_some():
    assert assess(healthy()[:N // 10], expected_samples=N).level == INVALID


def test_a_full_record_is_not_reported_as_short():
    assert "missing_data" not in assess(healthy(), expected_samples=N).failed


# --- the loose-sensor check needs BOTH of its conditions ------------------

def test_a_heavily_impacting_bearing_is_not_called_a_loose_sensor():
    """250 impacts at ten sigma: kurtosis 21 and 131 excursions, but a crest
    factor of 9.5. That is a badly spalled bearing, and calling it a
    mounting problem sends someone to tighten a bolt while the bearing
    fails -- and suppresses the very finding it should support.

    Isolates the crest condition: with that condition removed, this fires.
    """
    signal = healthy().copy()
    sigma = signal.std()
    signal[np.linspace(0, N - 1, 250).astype(int)] += 10.0 * sigma

    result = assess(signal)
    assert "loose_sensor" not in result.failed, (
        "a heavily impacting bearing was reported as a mounting problem"
    )


def test_a_few_sharp_knocks_are_not_called_a_loose_sensor():
    """Six impacts at thirteen sigma: crest factor 14 and six excursions,
    but kurtosis 1.8 -- six events in 50,000 samples barely move it. Someone
    tapped the machine.

    Isolates the kurtosis condition: with that condition removed, this fires.
    """
    signal = healthy().copy()
    sigma = signal.std()
    for i in range(6):
        signal[7000 * (i + 1)] += 13.0 * sigma

    result = assess(signal)
    assert "loose_sensor" not in result.failed


def test_a_single_tap_is_not_called_a_loose_sensor():
    """One knock gives a crest factor of 39 AND a kurtosis of 47 -- it
    clears both of the first two bars on its own, which is why the
    repetition condition exists. Isolates that third condition.
    """
    tapped = healthy().copy()
    tapped[N // 3] = 40 * tapped.std()

    result = assess(tapped)
    assert "loose_sensor" not in result.failed
    reason = next(c.reason for c in result.checks if c.name == "loose_sensor")
    assert "single impact, not a rattle" in reason


def test_rattling_needs_all_three_signs_together():
    """The real thing clears all three bars at once."""
    from app.ai.quality import (LOOSE_CREST_FACTOR, LOOSE_EXCURSION_SIGMA,
                                LOOSE_KURTOSIS, LOOSE_MIN_EXCURSIONS)

    rattle = healthy() + np.where(
        np.random.default_rng(1).random(N) < 0.0004, 2.0, 0.0)
    result = assess(rattle)
    assert result.failed == ["loose_sensor"]

    centred = rattle - rattle.mean()
    spread = centred.std()
    crest = np.abs(centred).max() / spread
    kurtosis = float(np.mean((centred / spread) ** 4) - 3.0)
    excursions = int(np.count_nonzero(
        np.abs(centred) > LOOSE_EXCURSION_SIGMA * spread))
    assert crest > LOOSE_CREST_FACTOR
    assert kurtosis > LOOSE_KURTOSIS
    assert excursions >= LOOSE_MIN_EXCURSIONS


# --- values too extreme to judge ------------------------------------------

def test_values_beyond_arithmetic_are_refused_not_passed():
    """A channel reading 1e308 overflows inside the standard deviation, and
    the kurtosis comes back NaN -- which compares false against every
    threshold, so an unguarded check passes the most obviously broken input
    there is."""
    result = assess([1e308] * 200)
    assert "loose_sensor" in result.not_assessed
    assert "loose_sensor" not in result.failed
    reason = next(c.reason for c in result.checks if c.name == "loose_sensor")
    assert "too extreme" in reason or "not a finite number" in reason


def test_a_flat_top_about_a_bias_is_caught_when_zero_is_nowhere_near_it():
    """Measured from zero rather than from rest, only the rail further from
    zero is seen -- and if the clipping is asymmetric about the bias, the
    far side is not the clipped one. ch7 on this gateway rests at -0.145 g,
    so this is the shape a real clipped channel here would have.
    """
    bias = -0.145
    signal = healthy() + bias
    # clipped on the positive side only, relative to its own resting position
    clipped = np.minimum(signal, bias + 0.02)

    result = assess(clipped)
    assert "clipping" in result.failed, (
        "the rail sits nearer zero than the unclipped side, so measuring "
        "from zero misses it entirely"
    )


def test_a_not_assessed_check_is_not_recorded_as_having_passed():
    """`passed` and `applicable` say different things, and a reader must be
    able to tell a check that ran and succeeded from one that never ran."""
    short = healthy()[:13_888]
    result = assess_channel(short, FS, full_scale_g=FULL_SCALE_G,
                            quantisation_step_g=STEP_G, shaft_hz=SHAFT_HZ)
    speed = next(c for c in result.checks if c.name == "unstable_speed")

    assert speed.applicable is False
    assert speed.passed is False, (
        "a check that did not run must not claim to have passed -- if it "
        "does, the two fields say the same thing and either can be dropped "
        "without anything noticing"
    )
    assert "unstable_speed" not in result.failed
    assert result.level == HIGH, "it must still not count against the capture"


# ------------------------------------------------------------- storage --

def test_the_converter_scale_comes_from_the_sensitivity():
    """Both numbers are properties of the converter and the sensitivity
    applied to it. The EL3632 is +/-5 V over 16 bits."""
    from app.services.quality_storage import converter_scale

    full, step = converter_scale(100.0)
    assert full == pytest.approx(50.0)
    assert step == pytest.approx(5.0 / 32768 / 0.100)
    assert step == pytest.approx(0.001526, abs=1e-6), (
        "this is the step measured on all eight channels of the real gateway"
    )

    full, step = converter_scale(500.0)
    assert full == pytest.approx(10.0)
    assert step == pytest.approx(0.000305, abs=1e-6)


@pytest.mark.parametrize("sensitivity", [None, 0, -100])
def test_an_unknown_sensitivity_yields_no_scale_rather_than_a_guess(sensitivity):
    """The checks that need the converter say so rather than inventing a
    range -- a clipping threshold set without knowing full scale is a
    threshold about nothing."""
    from app.services.quality_storage import converter_scale

    full, step = converter_scale(sensitivity)
    assert full == 0.0
    assert step is None


def test_the_checks_needing_a_scale_degrade_rather_than_fail():
    """With no converter declared, the engine still runs and still reports
    the checks it can."""
    result = assess_channel(healthy(), FS, shaft_hz=SHAFT_HZ)
    assert len(result.checks) == 8
    assert result.level in (HIGH, MEDIUM, LOW, INVALID)


def test_persisting_never_raises_on_a_broken_assessment(monkeypatch):
    """A capture whose quality could not be judged is still worth keeping.
    Losing it to a failure in the thing that grades it would be the worst
    outcome available."""
    import app.services.quality_storage as qs

    def explode(*args, **kwargs):
        raise RuntimeError("assessment blew up")

    monkeypatch.setattr(qs, "assess_capture", explode)

    class NoSession:
        def execute(self, *a, **k):
            raise AssertionError("should not reach the database")

    from uuid import uuid4
    result = qs.persist_quality(
        NoSession(), upload_id=uuid4(), sensor_id=uuid4(),
        channels={"ch0": healthy().tolist()}, sampling_rate_hz=FS)
    assert result["level"] == "unknown"
    assert result["confidence_factor"] == 1.0, (
        "an engine that could not be assessed must not have its confidence "
        "silently cut -- that would be a judgement nobody made"
    )


# ------------------------------------------------- the measured step --
#
# The resolution checks are built on the converter's quantisation step, and
# the step comes from the sensitivity the device applied. Taking that from
# configuration was wrong here: `gateway/.env` declares 500 mV/g on the
# first two channels, and the stored samples are quantised in 0.0015 g steps
# on all eight -- which is 100 mV/g. Measuring the step from the samples
# makes the checks independent of a figure nobody verified.

from app.services.quality_storage import (              # noqa: E402
    ADC_COUNTS,
    ADC_VOLTS,
    SENSITIVITY_TOLERANCE,
    measure_quantisation_step,
    sensitivity_from_step,
)


def quantised(sensitivity_mv_per_g: float, amplitude_g: float = 0.2,
              seed: int = 0) -> np.ndarray:
    """A signal digitised the way this converter digitises one."""
    step = ADC_VOLTS / ADC_COUNTS / (sensitivity_mv_per_g / 1000.0)
    rng = np.random.default_rng(seed)
    t = np.arange(N) / FS
    raw = amplitude_g * np.sin(2 * np.pi * 120 * t) + 0.01 * rng.normal(size=N)
    return np.round(raw / step) * step


@pytest.mark.parametrize("sensitivity", [100.0, 500.0, 10.0])
def test_the_step_is_recovered_from_the_samples(sensitivity):
    """A digitised signal can only take values a whole number of counts
    apart, so the commonest gap between its adjacent distinct values IS one
    count. That makes the step measurable without trusting any config."""
    expected = ADC_VOLTS / ADC_COUNTS / (sensitivity / 1000.0)
    measured = measure_quantisation_step(quantised(sensitivity))
    assert measured == pytest.approx(expected, rel=1e-6)
    assert sensitivity_from_step(measured) == pytest.approx(sensitivity, rel=1e-6)


def test_a_signal_that_is_not_quantised_returns_no_step():
    """The honest answer for a continuous signal is "I cannot tell", not a
    step invented from whatever gap happened to repeat. A wrong step makes
    the resolution check report a fault that is not there."""
    rng = np.random.default_rng(1)
    assert measure_quantisation_step(rng.normal(size=N)) is None


def test_a_dead_channel_returns_no_step():
    """A channel stuck at one value has no gaps to measure. It is a fault
    the other checks catch; this one must not guess at it."""
    assert measure_quantisation_step(np.full(N, 0.137)) is None
    assert measure_quantisation_step(np.array([0.1, 0.2, 0.3])) is None


def test_no_step_means_no_sensitivity_rather_than_zero():
    assert sensitivity_from_step(None) is None
    assert sensitivity_from_step(0.0) is None


class _RecordingSession:
    """Accepts the writes so persist_quality can run end to end."""

    def __init__(self):
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        return None


def _persist(declared, sensitivity_applied):
    from uuid import uuid4
    import app.services.quality_storage as qs
    return qs.persist_quality(
        _RecordingSession(), upload_id=uuid4(), sensor_id=uuid4(),
        channels={f"ch{i}": quantised(sensitivity_applied, seed=i).tolist()
                  for i in range(3)},
        sampling_rate_hz=FS, sensitivity_mv_per_g=declared, shaft_hz=SHAFT_HZ)


def test_the_measured_step_beats_the_declared_one():
    """This is the state this gateway is actually in: the record says 500
    mV/g, the device applied 100. Believing the record would make the
    resolution check wrong by five times -- it would judge the capture
    against a step five times finer than the converter can produce, and find
    every channel coarsely quantised."""
    summary = _persist(declared=500.0, sensitivity_applied=100.0)

    expected = ADC_VOLTS / ADC_COUNTS / 0.100
    assert summary["quantisation_step_g"] == pytest.approx(expected, rel=1e-6)
    assert summary["declared_step_g"] == pytest.approx(
        ADC_VOLTS / ADC_COUNTS / 0.500, rel=1e-6), (
        "the declared step must still be reported -- someone has to be able "
        "to see which of the two figures the engine rejected"
    )
    assert summary["warnings"], (
        "a device that applied a different sensitivity from the one on "
        "record puts every value in g out by the ratio between them; that "
        "cannot be corrected silently"
    )
    assert "100 mV/g" in summary["warnings"][0]
    assert "500 mV/g" in summary["warnings"][0]


def test_an_agreeing_declaration_raises_no_warning():
    """The warning has to mean something. If it fires when the config is
    right, nobody reads it when the config is wrong."""
    assert _persist(declared=100.0, sensitivity_applied=100.0)["warnings"] == []


def test_the_tolerance_admits_rounding_but_not_a_wrong_sensitivity():
    """The stored CSV rounds to four decimals, which moves the implied
    figure by a couple of percent. A five-fold error is not rounding."""
    step = ADC_VOLTS / ADC_COUNTS / 0.100
    just_inside = sensitivity_from_step(step) * (1 + SENSITIVITY_TOLERANCE / 2)
    assert _persist(declared=just_inside, sensitivity_applied=100.0)["warnings"] == []

    way_out = sensitivity_from_step(step) * 5
    assert _persist(declared=way_out, sensitivity_applied=100.0)["warnings"]


def test_an_undeclared_sensitivity_is_recovered_rather_than_left_unknown():
    """Without a declaration the clipping check had nothing to work with and
    stood down. The samples carry the full-scale range too, so it can run."""
    summary = _persist(declared=None, sensitivity_applied=100.0)
    assert summary["quantisation_step_g"] == pytest.approx(
        ADC_VOLTS / ADC_COUNTS / 0.100, rel=1e-6)
    assert summary["declared_step_g"] is None
    assert summary["warnings"] == [], (
        "nothing was declared, so there is nothing to disagree with"
    )
    assert "clipping" not in summary["not_assessed"], (
        "the full-scale range was recoverable from the samples, so the "
        "clipping check had no reason to stand down"
    )


# ------------------------------------------ sensitivity per channel ----
#
# The converter setting is per channel, and making it switchable is the
# point: a quiet channel moved from 100 mV/g to 500 goes from resolving this
# pump's vibration in one and a half steps to about eight. One figure applied
# to all eight channels makes the resolution check wrong by the ratio between
# them wherever they differ.

def _persist_mixed(declared_sensor, channel_map, applied):
    """Persist a capture whose channels were digitised at different settings."""
    from uuid import uuid4
    import app.services.quality_storage as qs
    channels = {f"ch{i}": quantised(applied[i], seed=i).tolist()
                for i in range(len(applied))}
    return qs.persist_quality(
        _RecordingSession(), upload_id=uuid4(), sensor_id=uuid4(),
        channels=channels, sampling_rate_hz=FS,
        sensitivity_mv_per_g=declared_sensor, channel_map=channel_map,
        shaft_hz=SHAFT_HZ)


def noise_floor(summary, channel):
    """The noise-floor verdict for one channel, which is where the converter
    step actually bites. Asserting on this rather than on the step the code
    recorded: the first version of these tests read back the overrides dict
    the code had just built, so removing per-channel handling entirely left
    them passing."""
    for check in summary["channels"][channel]["checks"]:
        if check["check"] == "noise_floor":
            return check
    raise AssertionError(f"channel {channel} has no noise_floor check")


def quantised_to(step_g, sigma, seed=0, n=N):
    """A signal of a chosen size, digitised in a chosen step."""
    rng = np.random.default_rng(seed)
    return np.round(rng.normal(0.0, sigma, n) / step_g) * step_g


STEP_100 = ADC_VOLTS / ADC_COUNTS / 0.100        # 0.00153 g
STEP_500 = ADC_VOLTS / ADC_COUNTS / 0.500        # 0.00031 g


def test_each_channel_is_judged_at_its_own_converter_setting():
    """Two channels digitised at different settings, carrying the same
    physical vibration. The one at 100 mV/g resolves it in two converter
    counts and must fail; the one at 500 resolves it in ten and must pass.
    Applying either channel's step to both gets one of them wrong."""
    sigma = 0.003
    channels = {"ch0": quantised_to(STEP_500, sigma, seed=1).tolist(),
                "ch1": quantised_to(STEP_100, sigma, seed=2).tolist()}

    from uuid import uuid4
    import app.services.quality_storage as qs
    summary = qs.persist_quality(
        _RecordingSession(), upload_id=uuid4(), sensor_id=uuid4(),
        channels=channels, sampling_rate_hz=FS, sensitivity_mv_per_g=100.0,
        channel_map=[{"channel_index": 1, "sensitivity_mv_per_g": 500.0}],
        shaft_hz=SHAFT_HZ)

    fine, coarse = noise_floor(summary, 0), noise_floor(summary, 1)
    assert fine["passed"] is True, (
        f"a channel at 500 mV/g resolves this vibration in "
        f"{fine['value']:.1f} counts and should pass"
    )
    assert coarse["passed"] is False, (
        f"the same vibration at 100 mV/g spans {coarse['value']:.1f} counts "
        f"and is reporting rounding"
    )
    assert fine["value"] == pytest.approx(coarse["value"] * 5, rel=0.05), (
        "five times the sensitivity is five times the resolution"
    )


def test_the_measured_step_beats_the_declaration_per_channel():
    """The channel is declared 500 mV/g and was digitised at 100. Believing
    the declaration would judge it against a step five times finer than the
    converter can produce and pass a channel that is reporting rounding."""
    from uuid import uuid4
    import app.services.quality_storage as qs
    summary = qs.persist_quality(
        _RecordingSession(), upload_id=uuid4(), sensor_id=uuid4(),
        channels={"ch0": quantised_to(STEP_100, 0.003, seed=3).tolist()},
        sampling_rate_hz=FS, sensitivity_mv_per_g=100.0,
        channel_map=[{"channel_index": 1, "sensitivity_mv_per_g": 500.0}],
        shaft_hz=SHAFT_HZ)

    check = noise_floor(summary, 0)
    assert check["passed"] is False
    assert check["value"] == pytest.approx(2.0, abs=0.5), (
        "judged at the step the samples actually show, not the declared one"
    )
    assert summary["warnings"] and "Channel 0" in summary["warnings"][0]


def test_the_measured_step_is_written_to_the_assessment_row():
    """A baseline is scoped to the step, and it reads it from this row. If
    the step is not stored, switching a channel from 100 mV/g to 500 looks
    to the baseline engine like no change at all."""
    from uuid import uuid4
    import app.services.quality_storage as qs

    session = _RecordingSession()
    qs.persist_quality(
        session, upload_id=uuid4(), sensor_id=uuid4(),
        channels={"ch0": quantised_to(STEP_100, 0.02, seed=4).tolist()},
        sampling_rate_hz=FS, sensitivity_mv_per_g=100.0, shaft_hz=SHAFT_HZ)

    inserts = [params for sql, params in session.statements
               if params and "step_g" in params and params.get("channel") == 0]
    assert inserts, "no per-channel assessment row was written"
    assert inserts[0]["step_g"] == pytest.approx(STEP_100, rel=1e-6)


def test_the_channel_map_beats_the_sensor_wide_figure():
    """The sensor-level sensitivity is a fallback for channels the map does
    not name, not a default that overrides the ones it does."""
    sigma = 0.003
    from uuid import uuid4
    import app.services.quality_storage as qs
    summary = qs.persist_quality(
        _RecordingSession(), upload_id=uuid4(), sensor_id=uuid4(),
        channels={"ch0": quantised_to(STEP_500, sigma, seed=5).tolist(),
                  "ch1": quantised_to(STEP_100, sigma, seed=6).tolist()},
        sampling_rate_hz=FS, sensitivity_mv_per_g=100.0,
        channel_map=[{"channel_index": 1, "sensitivity_mv_per_g": 500.0}],
        shaft_hz=SHAFT_HZ)

    assert summary["warnings"] == [], (
        "channel 0 matches its map entry and channel 1 matches the sensor "
        "fallback, so nothing disagrees"
    )
    assert noise_floor(summary, 0)["value"] > noise_floor(summary, 1)["value"]


def test_switching_a_channel_to_500_improves_its_resolution():
    """The reason this is configurable at all. The same signal measured at
    500 mV/g lands on five times as many converter steps as at 100, which is
    the difference between a shape measurement describing the machine and one
    describing rounding."""
    quiet = 0.0023                      # what ch5 on this pump actually does
    at_100 = quiet / STEP_100
    at_500 = quiet / STEP_500

    assert at_100 < 2, "at 100 mV/g this channel is reporting rounding"
    assert at_500 > 7, "at 500 mV/g it has real resolution"
    assert at_500 == pytest.approx(at_100 * 5, rel=1e-6)
