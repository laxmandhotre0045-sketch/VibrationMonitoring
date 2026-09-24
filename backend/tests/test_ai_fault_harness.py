"""The synthetic fault harness — VIK-017.

A ground truth nobody checks is just an opinion in a dataclass. These tests
measure the waveforms and confirm the recorded answers are actually true of
them, so that when VIK-018 to VIK-053 are scored against this harness, a
failure means the engine is wrong rather than the expectations being wrong.

That direction matters. If the harness claims BPFO dominates the raw spectrum
of the outer-race channel -- which it does not, because the energy rides a
4.2 kHz resonance -- then a correct engine gets marked wrong and someone
"fixes" it until it agrees.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import hilbert

from app.ai.fault_harness import (
    DEMO_FAMILIES,
    FS_HZ,
    SHAFT_HZ,
    SIGNATURES,
    describe,
    generate,
    generate_all,
    order_to_hz,
)


def spectrum(samples, envelope: bool = False):
    x = np.asarray(samples, dtype=float)
    x = x - x.mean()
    if envelope:
        x = np.abs(hilbert(x))
        x = x - x.mean()
    window = np.hanning(len(x))
    amps = np.abs(np.fft.rfft(x * window))
    freqs = np.fft.rfftfreq(len(x), d=1.0 / FS_HZ)
    return freqs, amps


def prominence_at(samples, target_hz, envelope=False, tolerance_hz=4.0):
    """How far the line at target_hz stands above the median line."""
    freqs, amps = spectrum(samples, envelope)
    band = (freqs > 5.0) & (freqs < 2000.0)
    f, a = freqs[band], amps[band]
    idx = int(np.argmin(np.abs(f - target_hz)))
    if abs(f[idx] - target_hz) > tolerance_hz:
        return 0.0
    return float(a[idx] / np.median(a))


def dominant_order(samples, envelope=False):
    freqs, amps = spectrum(samples, envelope)
    band = (freqs > 5.0) & (freqs < 2000.0)
    f, a = freqs[band], amps[band]
    return float(f[int(np.argmax(a))] / SHAFT_HZ)


def excess_kurtosis(samples):
    x = np.asarray(samples, dtype=float)
    d = x - x.mean()
    sd = d.std()
    return float((d ** 4).mean() / sd ** 4 - 3.0) if sd > 0 else 0.0


# ------------------------------------------------ generating on demand --

def test_every_signature_generates():
    for name in SIGNATURES:
        samples, truth = generate(name)
        assert len(samples) == 8192
        assert truth.fault


def test_generating_alone_equals_generating_together():
    """The ticket's "on demand" clause.

    Weak on its own -- generate_all() calls generate(), so this cannot fail by
    construction. Kept because it documents the contract, and paired with the
    seeding test below, which is the one with teeth.
    """
    everything = generate_all()
    for name in SIGNATURES:
        alone, _ = generate(name)
        together, _ = everything[name]
        assert alone == together, f"{name} differs when generated alone"


def test_each_signature_draws_its_own_noise(monkeypatch):
    """The property that makes on-demand generation meaningful.

    The original script advances ONE random state across all eight channels in
    order, so channel 4's noise depends on channels 0-3 having been generated
    first. Seeding per signature removes that coupling -- but seeding every
    signature from the SAME number reintroduces a different bug: eight
    channels sharing one noise realisation, so they correlate and a
    cross-channel test can pass on an artefact.

    Two earlier attempts at this test could not fail. The first compared
    generate() against generate_all(), and generate_all() calls generate().
    The second recomputed the seeds itself rather than observing the ones
    generate() uses. This one watches the constructor.
    """
    import app.ai.fault_harness as fh

    seen: list[int] = []
    real_rng = fh._Rng

    class Recording(real_rng):
        def __init__(self, seed):
            seen.append(seed)
            super().__init__(seed)

    monkeypatch.setattr(fh, "_Rng", Recording)
    for name in SIGNATURES:
        fh.generate(name)

    assert len(seen) == len(SIGNATURES)
    assert len(set(seen)) == len(seen), (
        f"generate() used the same seed for different signatures: {seen}. "
        f"Every channel would then carry an identical noise realisation."
    )


def test_generation_is_deterministic():
    first, _ = generate("unbalance")
    second, _ = generate("unbalance")
    assert first == second


def test_signatures_are_distinguishable_from_each_other():
    """Eight channels that all look the same would score any engine at 100%."""
    rms = {name: float(np.sqrt(np.mean(np.square(s))))
           for name, (s, _) in generate_all().items()}
    assert len(set(round(v, 6) for v in rms.values())) == len(rms)


def test_an_unknown_signature_names_the_available_ones():
    with pytest.raises(KeyError) as exc:
        generate("not_a_signature")
    assert "unbalance" in str(exc.value)


# ------------------------------- the ground truth is true of the waveform --

@pytest.mark.parametrize("name", list(SIGNATURES))
def test_the_recorded_dominant_order_is_the_measured_one(name):
    samples, truth = generate(name)
    if truth.dominant_order is None:
        pytest.skip("no dominant order claimed")
    measured = dominant_order(samples, envelope=truth.dominant_domain == "envelope")
    assert measured == pytest.approx(truth.dominant_order, rel=0.06), (
        f"{name} claims {truth.dominant_order}X dominant in the "
        f"{truth.dominant_domain} spectrum but measures {measured:.2f}X"
    )


@pytest.mark.parametrize("name", list(SIGNATURES))
def test_every_expected_order_is_actually_present(name):
    samples, truth = generate(name)
    missing = [
        order for order in truth.expected_orders
        if prominence_at(samples, order_to_hz(order)) < 3.0
        and prominence_at(samples, order_to_hz(order), envelope=True) < 3.0
    ]
    assert not missing, f"{name} claims orders {missing} that are not in the signal"


@pytest.mark.parametrize("name", ["bearing_outer_race", "bearing_inner_race"])
def test_bearing_defects_are_found_in_the_envelope_not_the_raw_spectrum(name):
    """The physical point the harness exists to encode.

    A bearing defect's energy rides a high-frequency resonance, so the defect
    rate barely shows in the raw spectrum. An engine that looks for BPFO in
    the raw spectrum finds nothing and reports a healthy bearing.
    """
    samples, truth = generate(name)
    defect_order = 3.57 if "outer" in name else 5.43
    raw = prominence_at(samples, order_to_hz(defect_order))
    env = prominence_at(samples, order_to_hz(defect_order), envelope=True)
    assert env > raw, (
        f"{name}: defect at {defect_order}X reads {env:.0f}x in the envelope "
        f"and {raw:.0f}x raw -- the envelope must be the stronger view"
    )
    assert env > 5.0


def test_the_resonance_is_where_the_harness_says_it_is():
    """4.2 kHz for the outer race. If this moves, envelope band selection
    downstream is tuned against the wrong carrier."""
    samples, truth = generate("bearing_outer_race")
    freqs, amps = spectrum(samples)
    high = freqs > 500.0
    peak_hz = float(freqs[high][int(np.argmax(amps[high]))])
    assert peak_hz == pytest.approx(truth.resonance_hz, rel=0.02)


def test_impulsive_faults_raise_kurtosis_and_steady_ones_do_not():
    """The discriminator between a bearing fault and unbalance. Both raise
    RMS; only impacting raises kurtosis."""
    impulsive, _ = generate("bearing_outer_race")
    steady, _ = generate("unbalance")
    assert excess_kurtosis(impulsive) > 3.0
    assert excess_kurtosis(steady) < 1.0


def test_misalignment_puts_2x_above_1x_and_unbalance_does_not():
    """The discriminator between the two most-confused families."""
    mis, _ = generate("misalignment")
    unb, _ = generate("unbalance")
    assert (prominence_at(mis, order_to_hz(2.0))
            > prominence_at(mis, order_to_hz(1.0)))
    assert (prominence_at(unb, order_to_hz(1.0))
            > prominence_at(unb, order_to_hz(2.0)))


def test_looseness_carries_subharmonics_and_misalignment_does_not():
    """Both have long harmonic families; only looseness has 0.5X."""
    loose, _ = generate("looseness")
    mis, _ = generate("misalignment")
    assert prominence_at(loose, order_to_hz(0.5)) > 5.0
    assert prominence_at(mis, order_to_hz(0.5)) < 5.0


def test_inner_race_sidebands_are_present():
    """A defect passing through the load zone once per revolution modulates
    at 1X. The sidebands around BPFI are what separate inner from outer."""
    samples, truth = generate("bearing_inner_race")
    bpfi_hz = order_to_hz(5.43)
    for offset in truth.sideband_offsets:
        sideband_hz = bpfi_hz + order_to_hz(offset)
        assert prominence_at(samples, sideband_hz, envelope=True) > 3.0, (
            f"sideband at {sideband_hz:.0f} Hz is missing"
        )


def test_the_healthy_channels_are_not_impulsive():
    """The controls. An engine that names a fault here is worse than one that
    misses a real fault, because it teaches people to ignore it."""
    for name in ("healthy_horizontal", "healthy_vertical"):
        samples, _ = generate(name)
        assert excess_kurtosis(samples) < 1.0


# ------------------------------------------------------- the demo set --

def test_the_six_demo_families_are_all_present():
    """VIK-053 is scored on exactly these six."""
    assert set(DEMO_FAMILIES) <= set(SIGNATURES)
    assert len(DEMO_FAMILIES) == 6
    for name in DEMO_FAMILIES:
        _, truth = generate(name)
        assert truth.fault != "none"


def test_each_demo_family_has_a_distinct_fault_label():
    labels = [generate(n)[1].fault for n in DEMO_FAMILIES]
    assert len(set(labels)) == len(labels)


def test_the_description_is_serialisable_for_recording_beside_a_score():
    """The ticket: "expected answer stored alongside". It has to survive
    being written to a file next to a result."""
    import json
    for name in SIGNATURES:
        json.dumps(describe(name))
