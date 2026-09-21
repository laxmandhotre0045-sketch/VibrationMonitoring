"""What every feature is called, and how it is judged — VIK-021.

One list, read by three things that were previously kept in step by hand: the
`feature_definitions` rows the frontend renders from, the factory threshold
defaults behind "reset to default", and the migration that seeds a fresh
database. The ticket asks for one source of truth, and this is it.

**Most of these have no alarm limit, on purpose.** The platform measures 46
things per channel; published limits exist for a handful. A spectral centroid
of 3,976 Hz is neither good nor bad on its own, and inventing a number for it
would repeat the failure the requirement already records: one global RMS
limit of 0.02, a lowest-ever reading of 0.024, and 72 of 72 readings coming
back critical. That limit described its own configuration, not any machine.

So each feature is graded one of three ways:

  `percent_baseline`  -- judged against what this machine normally does.
      Right wherever "further from usual is worse" holds. Until a baseline
      exists these report "no baseline", which is the truth.

  an absolute rule    -- only where a real limit exists, from a standard or
      from physics. There are ten of these and they predate this file.

  `informational`     -- measured, plotted, never alarmed on. Used where
      "bigger is worse" is simply false: a dominant frequency of 97 Hz is a
      fact about the machine, not a severity, and a DC offset is a property
      of the transducer.

The third is the one that needed a new status. An unrecognised rule type used
to fall through to "normal", so a feature nobody had assessed read as healthy.
"""

from __future__ import annotations

from typing import NamedTuple, Optional

from app.services.threshold_defaults import THRESHOLD_RULE_DEFAULTS, RuleDefault


class FeatureDefinition(NamedTuple):
    code: str
    name: str
    unit: str
    description: str


#: Every feature the extractor produces, in FEATURE_CODES order. The order is
#: the frontend's display order, so new codes append and nothing is reordered.
FEATURE_DEFINITIONS: tuple[FeatureDefinition, ...] = (
    # --- the original ten -------------------------------------------------
    FeatureDefinition("rms", "RMS", "scaled_eng",
                      "Overall vibration level: the energy in the whole signal."),
    FeatureDefinition("peak", "Peak", "scaled_eng",
                      "The largest single excursion in the record."),
    FeatureDefinition("crest_factor", "Crest Factor", "dimensionless",
                      "Peak divided by RMS. Rises when the signal becomes spiky."),
    FeatureDefinition("kurtosis", "Kurtosis", "dimensionless",
                      "How heavy the tails are. Rises with impacting, not with level."),
    FeatureDefinition("fft_band_energy_0_500", "Band Energy 0-500 Hz", "scaled_eng_sq",
                      "Energy below 500 Hz, where shaft-related faults live."),
    FeatureDefinition("amplitude_1x", "1X Amplitude", "scaled_eng",
                      "Height of the line at running speed. Unbalance shows here."),
    FeatureDefinition("amplitude_2x", "2X Amplitude", "scaled_eng",
                      "Twice running speed. Misalignment shows here."),
    FeatureDefinition("amplitude_3x", "3X Amplitude", "scaled_eng",
                      "Three times running speed. Part of a misalignment family."),
    FeatureDefinition("envelope_rms", "Envelope RMS", "scaled_eng",
                      "Level of the rectified envelope; sensitive to repeated impacts."),
    FeatureDefinition("noise_floor", "Noise Floor", "dB",
                      "Mean spectrum magnitude. Rises as a machine gets generally noisier."),

    # --- time domain, VIK-018 ---------------------------------------------
    FeatureDefinition("peak_to_peak", "Peak to Peak", "scaled_eng",
                      "Highest value minus lowest. The full swing of the signal."),
    FeatureDefinition("std_dev", "Standard Deviation", "scaled_eng",
                      "Spread about the mean, with any sensor bias removed."),
    FeatureDefinition("skewness", "Skewness", "dimensionless",
                      "Whether the signal leans positive or negative. Zero is symmetric."),
    FeatureDefinition("impulse_factor", "Impulse Factor", "dimensionless",
                      "Peak over mean absolute value. Rises with impacting."),
    FeatureDefinition("shape_factor", "Shape Factor", "dimensionless",
                      "RMS over mean absolute value. Barely moves for a single spike."),
    FeatureDefinition("clearance_factor", "Clearance Factor", "dimensionless",
                      "The most sensitive of the three shape ratios to early bearing damage."),
    FeatureDefinition("burst_count", "Burst Count", "count",
                      "Samples beyond four standard deviations. Counts impacts."),
    FeatureDefinition("shock_index", "Shock Index", "dimensionless",
                      "How far the worst sample goes past the burst threshold. Above 1 means at least one."),
    FeatureDefinition("modulation_index", "Modulation Index", "dimensionless",
                      "Depth of amplitude modulation at running speed. Separates inner-race from outer-race."),
    FeatureDefinition("rms_change_short", "RMS Change (short)", "fraction",
                      "End of the record against its start. Catches a fault growing within one capture."),
    FeatureDefinition("rms_change_long", "RMS Change (long)", "fraction",
                      "End of the record against the whole record."),
    FeatureDefinition("zero_crossing_rate", "Zero Crossing Rate", "Hz",
                      "Crossings of the mean per second. A rough frequency measure without an FFT."),
    FeatureDefinition("dc_offset", "DC Offset", "scaled_eng",
                      "Standing bias on the channel. A property of the sensor, not vibration."),

    # --- frequency domain, VIK-019 ----------------------------------------
    FeatureDefinition("dominant_frequency", "Dominant Frequency", "Hz",
                      "Where the largest line sits. A fact about the machine, not a severity."),
    FeatureDefinition("dominant_prominence", "Dominant Prominence", "dimensionless",
                      "How far that line stands above the noise. Below about 6 there is no tone."),
    FeatureDefinition("harmonic_count", "Harmonic Count", "count",
                      "How many multiples of running speed carry a real line. Looseness shows the longest family."),
    FeatureDefinition("harmonic_energy_ratio", "Harmonic Energy Ratio", "fraction",
                      "Share of energy on exact multiples of running speed. High means a shaft fault, low means a bearing."),
    FeatureDefinition("sideband_spacing", "Sideband Spacing", "Hz",
                      "Spacing of the lines either side of the loudest one. The spacing names the cause."),
    FeatureDefinition("sideband_energy_ratio", "Sideband Energy Ratio", "fraction",
                      "Share of energy in those sidebands."),
    FeatureDefinition("spectral_centroid", "Spectral Centroid", "Hz",
                      "The spectrum's centre of mass. Rises as high-frequency content appears."),
    FeatureDefinition("spectral_spread", "Spectral Spread", "Hz",
                      "How widely the energy is scattered around that centre."),
    FeatureDefinition("spectral_entropy", "Spectral Entropy", "dimensionless",
                      "0 is one pure tone, 1 is flat noise. Separates ringing from general roughness."),
    FeatureDefinition("broadband_noise", "Broadband Noise", "scaled_eng",
                      "The median spectrum line: the floor rather than any peak."),
    FeatureDefinition("haystack_score", "Haystack Score", "dimensionless",
                      "Near 1 means a raised rounded floor rather than discrete lines. Late bearing damage and cavitation."),
    FeatureDefinition("narrowband_ratio", "Narrowband Ratio", "fraction",
                      "Share of energy in lines that stand out at all. The mirror of entropy."),
    FeatureDefinition("peak_drift", "Peak Drift", "fraction",
                      "Movement of the dominant line since the previous capture. Needs two captures."),

    # --- envelope, VIK-020 -------------------------------------------------
    FeatureDefinition("ftf_band_energy", "Cage (FTF) Energy", "dimensionless",
                      "Strength of the cage defect rate in the demodulated signal. The cage holds the balls apart."),
    FeatureDefinition("bsf_band_energy", "Ball Spin (BSF) Energy", "dimensionless",
                      "Strength of the ball defect rate. On this machine it shares a line with twice shaft speed and with mains."),
    FeatureDefinition("bpfo_band_energy", "Outer Race (BPFO) Energy", "dimensionless",
                      "Strength of the outer-race defect rate. The commonest bearing fault, and the clearest in the envelope."),
    FeatureDefinition("bpfi_band_energy", "Inner Race (BPFI) Energy", "dimensionless",
                      "Strength of the inner-race defect rate. Modulated at shaft rate as the defect passes through the load zone."),
    FeatureDefinition("bearing_harmonic_energy", "Bearing Harmonic Energy", "dimensionless",
                      "How much of a repeating family the strongest defect rate has. A real defect repeats; noise at one frequency does not."),
    FeatureDefinition("envelope_peak", "Envelope Peak", "scaled_eng",
                      "The tallest line in the demodulated signal, whatever is causing it."),
    FeatureDefinition("envelope_kurtosis", "Envelope Kurtosis", "dimensionless",
                      "How sharply the demodulated energy concentrates into lines. One of the strongest bearing indicators."),
    FeatureDefinition("demodulated_peak_prominence", "Demodulated Peak Prominence", "dimensionless",
                      "How far that tallest line stands above the demodulated noise floor."),
    FeatureDefinition("repetition_impact_frequency", "Impact Repetition Rate", "Hz",
                      "How often the impacts repeat. Compare it against the bearing frequencies to name the cause."),
    FeatureDefinition("resonance_band_energy", "Resonance Band Energy", "dimensionless",
                      "How strongly the structure is ringing at the band that was demodulated. Low means there is no resonance to read."),
)

#: Features that are recorded and plotted but never alarmed on, because
#: "further from usual is worse" is not true of them. Everything not listed
#: here and not already carrying an absolute rule is judged against baseline.
INFORMATIONAL: frozenset[str] = frozenset({
    "dominant_frequency",   # a fact about the machine, not a severity
    "sideband_spacing",     # likewise: the spacing names a cause, it is not a level
    "dc_offset",            # a property of the transducer
    "skewness",             # symmetric about zero; neither sign is worse
    "zero_crossing_rate",   # descriptive; meaningful only beside the others
    "peak_drift",           # a change, already relative, and zero means unknown
    "harmonic_count",       # a count of a family, not a magnitude
    "repetition_impact_frequency",  # a rate, to be compared, not graded
})

#: Baseline comparison for a feature with no published limit. Deliberately
#: loose: these exist to notice a machine departing from its own habit, not
#: to draw a line nobody can defend. 150% of normal warns, 200% is critical.
_BASELINE_DEFAULT = RuleDefault(
    "percent_baseline", 150.0, 200.0, None, None,
    {"basis": "no published limit for this feature; judged against this "
              "machine's own learned normal"},
)

_INFORMATIONAL_DEFAULT = RuleDefault(
    "informational", None, None, None, None,
    {"basis": "measured and plotted, never alarmed on: higher is not worse "
              "for this feature"},
)


def default_rule_for(code: str) -> RuleDefault:
    """The factory rule for one feature code.

    Absolute limits win where they exist, because they come from a standard
    or from physics. Everything else is baseline-relative unless it is in
    INFORMATIONAL.
    """
    if code in THRESHOLD_RULE_DEFAULTS:
        return THRESHOLD_RULE_DEFAULTS[code]
    if code in INFORMATIONAL:
        return _INFORMATIONAL_DEFAULT
    return _BASELINE_DEFAULT


def all_default_rules() -> dict[str, RuleDefault]:
    """Every feature's factory rule, in definition order."""
    return {d.code: default_rule_for(d.code) for d in FEATURE_DEFINITIONS}


def definition_for(code: str) -> Optional[FeatureDefinition]:
    for definition in FEATURE_DEFINITIONS:
        if definition.code == code:
            return definition
    return None


def seed_rows() -> list[dict]:
    """Definition rows in the shape the table wants, with sort order applied."""
    return [
        {"code": d.code, "name": d.name, "unit": d.unit,
         "description": d.description, "sort_order": i, "is_active": True}
        for i, d in enumerate(FEATURE_DEFINITIONS, start=1)
    ]


# --------------------------------------------------------------- seeding --

def sync_to_database(bind) -> tuple[int, int]:
    """Bring `feature_definitions` and the factory rules in line with this file.

    Called from the migrations rather than restated by them, which is what
    makes this module the single source of truth the ticket asks for. Adding
    a feature group then needs a migration that calls this and nothing else.

    Idempotent, and deliberately asymmetric between the two tables:

      Definitions are upserted. They are descriptive text, the frontend reads
      them, and the newest wording should win. Existing rows are updated in
      place rather than replaced, because feature_threshold_rules references
      them and their ids are worth keeping.

      Rules are only inserted where none exists. Overwriting a limit someone
      tuned, during an upgrade, is the kind of silent change that surfaces
      weeks later as an alarm that never fired.

    Returns (definitions written, rules created).
    """
    import json as _json

    import sqlalchemy as _sa

    for row in seed_rows():
        bind.execute(_sa.text("""
            INSERT INTO feature_definitions (id, code, name, unit, description,
                                             sort_order, is_active)
            VALUES (gen_random_uuid(), :code, :name, :unit, :description,
                    :sort_order, :is_active)
            ON CONFLICT (code) DO UPDATE SET
                name        = EXCLUDED.name,
                unit        = EXCLUDED.unit,
                description = EXCLUDED.description,
                sort_order  = EXCLUDED.sort_order,
                is_active   = EXCLUDED.is_active
        """), row)

    columns = {c["name"] for c in _sa.inspect(bind).get_columns("feature_threshold_rules")}
    scoped = [c for c in ("machine_type", "channel") if c in columns]
    where_global = "".join(f" AND {c} IS NULL" for c in scoped)

    created = 0
    for code, rule in all_default_rules().items():
        exists = bind.execute(_sa.text(
            f"SELECT 1 FROM feature_threshold_rules WHERE feature_code = :code"
            f"{where_global} LIMIT 1"), {"code": code}).fetchone()
        if exists:
            continue
        bind.execute(_sa.text("""
            INSERT INTO feature_threshold_rules (id, feature_code, rule_type,
                                                 normal_max, warning_max,
                                                 normal_min, warning_min,
                                                 metadata, is_active)
            VALUES (gen_random_uuid(), :code, :rule_type, :normal_max,
                    :warning_max, :normal_min, :warning_min,
                    CAST(:meta AS jsonb), true)
        """), {
            "code": code, "rule_type": rule.rule_type,
            "normal_max": rule.normal_max, "warning_max": rule.warning_max,
            "normal_min": rule.normal_min, "warning_min": rule.warning_min,
            "meta": _json.dumps(rule.metadata or {}),
        })
        created += 1
    return len(FEATURE_DEFINITIONS), created
