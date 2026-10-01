"""Reference rows for the two faults section 23 names — cavitation, rotor bar.

Revision ID: 042
Revises: 041

Section 23 accepts the module only if it identifies a listed set of basic
faults, and two of them had no rule: cavitation and rotor-bar defect. Both
are now in the rule table, so both need the reference material every other
fault has -- which plot proves it, and what to do about it. Two existing
tests demanded exactly this and failed until it was added, which is what
they are for.

**Cavitation was the harder of the two and it needed the engine extended.**
It is the one fault here with no discrete frequency at all: thousands of
bubbles collapsing independently raise the broadband floor and produce no
line anywhere. An order-matching engine cannot express that, which is why
cavitation had no rule rather than a bad one. The rule now carries feature
conditions instead of orders, and is recognised by high spectral entropy,
almost no harmonic energy, a non-impulsive waveform and enough signal to
mean something.

The thresholds came from the 1,000 feature rows already stored rather than
from judgement: spectral entropy runs 0.16 to 0.93 here, and harmonic
energy ratio 0 to 0.54. A first draft guessed them and got both wrong in
the same direction -- the dominant condition was always true and the
contradiction sat above the highest value ever recorded -- so a pure
harmonic series was ranked as cavitation.
"""

from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None

PLOTS = "fault_plot_evidence"
ACTIONS = "fault_recommendations"

PLOT_ROWS = (
    ("cavitation", "fft_spectrum", 1,
     "Raised random broadband energy, typically above 2 kHz, with no "
     "discrete order anywhere.",
     "Cavitation is the absence of a peak rather than the presence of one. "
     "The full spectrum is the only view that shows energy everywhere and a "
     "line nowhere, which is the signature."),
    ("cavitation", "time_waveform", 2,
     "Continuous random noise rather than repeating impacts.",
     "This is what separates cavitation from a bearing defect, which also "
     "lifts the high-frequency floor but repeats. If the waveform is "
     "impulsive it is not cavitation."),
    ("cavitation", "trend_plot", 3,
     "Broadband energy that changes with suction conditions rather than "
     "with speed.",
     "Cavitation follows the process -- valve position, level, temperature "
     "-- while every mechanical fault follows the rotation. Trending it "
     "against operating point is the cheapest confirmation there is."),
    ("rotor_bar", "fft_spectrum", 1,
     "Sidebands either side of running speed, spaced at the pole-pass "
     "frequency, and a line at twice supply frequency.",
     "The sideband spacing is slip times the pole count, which is a few "
     "hertz at most, so this needs the full spectrum and a long record. "
     "Both sidebands should be present and roughly symmetric."),
    ("rotor_bar", "trend_plot", 2,
     "Sidebands that grow with load.",
     "Slip increases with load, so the spacing widens and the sidebands "
     "rise. A mechanical fault does not care about load in that way, and "
     "this is the distinction that avoids dismantling a healthy motor."),
    ("rotor_bar", "envelope_spectrum", 3,
     "The pole-pass modulation resolved more clearly.",
     "The sidebands are amplitude modulation of running speed, so "
     "demodulating makes the spacing readable when the raw spectrum is too "
     "coarse to separate them."),
)

ACTION_ROWS = (
    ("cavitation",
     "Change the suction conditions now. Cavitation erodes the impeller "
     "continuously, and the damage is not recoverable.",
     "Investigate the suction side: strainer, valve position, tank level "
     "and net positive suction head. Trend the broadband energy against "
     "operating point.",
     "Listen at the pump first -- cavitation sounds like gravel going "
     "through it, and that costs nothing to check. Throttling the "
     "discharge should change the noise; a bearing fault will not care."),
    ("rotor_bar",
     "Involve the electrical team now, and plan a motor inspection. A "
     "broken bar overloads its neighbours, so the failure accelerates.",
     "Plan a motor current signature analysis, which is the definitive "
     "test and far cheaper than dismantling the motor.",
     "Confirm the pole count and measure the actual running speed first. "
     "The sideband spacing is derived from slip, so a guessed speed moves "
     "the frequency you are looking for."),
)


def upgrade() -> None:
    op.bulk_insert(
        sa.table(PLOTS,
                 sa.column("fault_key", sa.String),
                 sa.column("plot_type", sa.String),
                 sa.column("rank", sa.Integer),
                 sa.column("what_to_look_for", sa.Text),
                 sa.column("why_this_plot", sa.Text)),
        [{"fault_key": k, "plot_type": p, "rank": r,
          "what_to_look_for": look, "why_this_plot": why}
         for k, p, r, look, why in PLOT_ROWS])

    op.bulk_insert(
        sa.table(ACTIONS,
                 sa.column("fault_key", sa.String),
                 sa.column("action_now", sa.Text),
                 sa.column("action_planned", sa.Text),
                 sa.column("check_first", sa.Text)),
        [{"fault_key": k, "action_now": now, "action_planned": planned,
          "check_first": check}
         for k, now, planned, check in ACTION_ROWS])


def downgrade() -> None:
    keys = "('cavitation', 'rotor_bar')"
    op.execute(f"DELETE FROM {PLOTS} WHERE fault_key IN {keys}")
    op.execute(f"DELETE FROM {ACTIONS} WHERE fault_key IN {keys}")
