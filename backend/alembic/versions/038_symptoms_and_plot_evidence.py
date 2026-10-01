"""What the signal was doing, and where to go and look — VIK-051/059.

Revision ID: 038
Revises: 037

Two additions, both about making a finding checkable rather than believable.

**`symptoms` on a finding (VIK-051).** The rule table answers "is there a
peak at this order"; a symptom answers "what is this spectrum doing" -- a
harmonic series is present, there are sidebands 24.7 Hz either side of the
mesh frequency, the waveform is impacting. The two are not the same, and the
difference matters most when no rule matched: a capture that names no fault
still has observations, and on a machine whose spectrum cannot resolve its
own bearing frequencies those observations are the only thing there is to
say. Stored per finding rather than per capture, which duplicates them
across a channel's findings exactly as `resolution` and
`context_completeness` are already duplicated -- a finding travels alone to
whoever reads it, and it has to carry its own context.

**`fault_plot_evidence` (VIK-059).** The ticket asks for a table, not code,
and is right to: which plot shows a fault is reference material an analyst
should be able to correct without a deploy. Every plot named here already
exists in the frontend -- the mapping points at screens that are built, not
at ones that would have to be.

Its real job is to close the loop on "why should I believe this". A finding
says "outer race defect, 3.064x series, stage developing"; this table says
open the envelope spectrum, look for the series at 3.064x, and the reason
the envelope rather than the ordinary spectrum is that a bearing impact is
modulation and the envelope is what demodulates it. Without that, the
evidence is a list of numbers only the engine can read.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None

FINDINGS = "fault_findings"
TABLE = "fault_plot_evidence"

#: The plot types the frontend actually renders, from
#: `app.schemas.measurement.PLOT_TYPES`. Constrained rather than free text:
#: a row naming a plot that does not exist sends an analyst looking for a
#: screen that was never built, which is worse than no guidance.
PLOT_TYPES = ("time_waveform", "circular_time_waveform", "fft_spectrum",
              "envelope_spectrum", "envelope_waveform", "trend_plot")

#: (fault_key, plot_type, rank, what to look for, why this plot)
#:
#: Rank 1 is the plot to open first. The fault keys are `vibcore.signatures`'
#: own, so a key that drifts out of the rule table leaves a row pointing at
#: nothing -- which the seeding test checks for, because a silent mismatch
#: here degrades to an empty panel rather than an error.
MAPPING = (
    # ---------------------------------------------------------- unbalance
    ("unbalance", "fft_spectrum", 1,
     "A dominant peak at 1x running speed, with 2x well below it.",
     "Unbalance is one event per revolution, so it is a single line at 1x. "
     "The spectrum is the only view that separates it from everything else "
     "at once."),
    ("unbalance", "time_waveform", 2,
     "A smooth, repeating sinusoid at running speed.",
     "A clean 1x sinusoid distinguishes unbalance from looseness, which is "
     "also strongest at 1x but has a distorted waveform."),
    ("unbalance", "trend_plot", 3,
     "A 1x amplitude that grew and then held steady.",
     "Mass does not come off gradually. Unbalance steps up when something "
     "breaks or fouls, then stays; a steadily rising 1x is more often a "
     "bearing or a looseness developing."),
    # ------------------------------------------------------- misalignment
    ("misalignment_parallel", "fft_spectrum", 1,
     "2x running speed at or above 1x.",
     "Parallel misalignment loads the coupling twice per revolution, which "
     "puts the energy at 2x. The ratio of 2x to 1x is the diagnosis."),
    ("misalignment_parallel", "time_waveform", 2,
     "Two peaks per revolution rather than one.",
     "Confirms the 2x line is genuinely twice per turn and not a harmonic "
     "of something else the spectrum happens to place there."),
    ("misalignment_angular", "fft_spectrum", 1,
     "1x and 2x in the axial direction, axial amplitude comparable to "
     "radial.",
     "Angular misalignment pushes along the shaft. A radial-only spectrum "
     "cannot show that, so the axial channel is the evidence."),
    ("misalignment_angular", "trend_plot", 2,
     "Axial amplitude rising while radial stays flat.",
     "Separates a coupling going out of alignment from a general rise in "
     "level, which moves both directions together."),
    # -------------------------------------------------------- bent shaft
    ("bent_shaft", "fft_spectrum", 1,
     "1x dominant with a strong axial component, and 2x present.",
     "A bent shaft looks like unbalance radially. The axial line is what "
     "separates them, because a bow pushes along the shaft and a heavy "
     "spot does not."),
    ("bent_shaft", "circular_time_waveform", 2,
     "The same deflection at the same angular position every revolution.",
     "A bow is fixed to the shaft, so it repeats at one angle. This is the "
     "view that shows angle directly."),
    # ---------------------------------------------------------- looseness
    ("mechanical_looseness", "fft_spectrum", 1,
     "A long series of running-speed harmonics -- often 1x through 8x or "
     "beyond -- and sometimes a half-order line.",
     "Looseness clips the waveform, and a clipped sinusoid is a harmonic "
     "series. The length of the series is the severity."),
    ("mechanical_looseness", "time_waveform", 2,
     "A distorted, flattened or truncated waveform rather than a sinusoid.",
     "This is the mechanism itself: the surface stops moving when it hits "
     "its limit, and that clipping is what generates the harmonics."),
    ("mechanical_looseness", "circular_time_waveform", 3,
     "The distortion falling at the same angular position each revolution.",
     "A fixed angular position means a physical location on the machine to "
     "go and inspect, which the linear waveform cannot show."),
    ("structural_looseness", "fft_spectrum", 1,
     "1x and 2x with a raised axial component, and little beyond 3x.",
     "A soft foot twists the frame rather than clipping a surface, so it "
     "stops at low harmonics where mechanical looseness keeps going. The "
     "length of the series is what tells the two apart."),
    ("structural_looseness", "trend_plot", 2,
     "Amplitude that changes after the machine is restarted or re-bolted.",
     "A base problem moves when the base is disturbed. Nothing else on "
     "this list does."),
    # ------------------------------------------------------------ bearing
    ("bearing_outer_race", "envelope_spectrum", 1,
     "A series at the outer-race order (3.064x on this pump), with "
     "harmonics.",
     "A bearing impact is a high-frequency ring modulated at the defect "
     "rate, not a tone at the defect rate. The envelope demodulates it; "
     "the ordinary spectrum shows the ringing and buries the rate."),
    ("bearing_outer_race", "envelope_waveform", 2,
     "Evenly spaced impacts at the defect rate.",
     "Counting impacts in time confirms the rate before trusting a line in "
     "a spectrum that has other reasons to have energy there -- on this "
     "gateway the outer-race order and the third shaft harmonic land in "
     "the same bin."),
    ("bearing_outer_race", "fft_spectrum", 3,
     "Raised broadband energy in the bearing band, above the order region.",
     "The ringing itself. Broadband lift with no matching order is a "
     "bearing signature even when the defect rate cannot be resolved."),
    ("bearing_inner_race", "envelope_spectrum", 1,
     "A series at the inner-race order (4.936x here), with sidebands "
     "spaced at running speed.",
     "The inner race turns with the shaft, so the defect passes in and out "
     "of the load zone once per revolution. Those sidebands are what "
     "separate an inner-race defect from an outer-race one."),
    ("bearing_inner_race", "envelope_waveform", 2,
     "Impacts whose amplitude rises and falls once per revolution.",
     "The same load-zone modulation, seen directly in time."),
    ("bearing_ball_defect", "envelope_spectrum", 1,
     "A series at the ball-spin order, often with cage-rate sidebands.",
     "The ball-spin frequency is close to 2x on this bearing, so it needs "
     "the envelope and a long record to be told from a shaft harmonic."),
    ("bearing_ball_defect", "envelope_waveform", 2,
     "Impacts at an interval that is not a whole fraction of a revolution.",
     "A rolling element spins at its own rate, unrelated to the shaft. "
     "That is the cleanest way to rule out a harmonic."),
    ("bearing_cage", "envelope_spectrum", 1,
     "A low sub-synchronous line at the cage order (0.383x here), and "
     "sidebands at the cage rate around other bearing orders.",
     "The cage rate is below running speed. The envelope keeps it clear of "
     "the sub-synchronous noise the ordinary spectrum has down there."),
    ("bearing_cage", "time_waveform", 2,
     "Irregular, unevenly spaced impacts.",
     "A damaged cage lets elements wander, so the impacts lose their even "
     "spacing. A race defect keeps it."),
    # --------------------------------------------------------------- gear
    ("gear_mesh", "fft_spectrum", 1,
     "A peak at tooth count x running speed, with sidebands spaced at "
     "running speed.",
     "Mesh frequency sits far above the order region and needs the full "
     "spectrum span. Sideband spacing names which shaft the fault is on."),
    ("gear_mesh", "envelope_spectrum", 2,
     "Sidebands around the mesh frequency resolved more clearly.",
     "The sidebands are modulation, so demodulating makes the spacing "
     "readable when the raw spectrum smears it."),
    ("gear_mesh", "time_waveform", 3,
     "One impact per revolution of the affected gear.",
     "A single broken tooth is one event per turn. In a spectrum it "
     "becomes a harmonic series easily mistaken for looseness; in the "
     "waveform it is unmistakable, and it separates one bad tooth from "
     "general wear across all of them."),
    # --------------------------------------------------------------- flow
    ("blade_vane_pass", "fft_spectrum", 1,
     "A peak at vane or blade count x running speed.",
     "Blade pass is a flow phenomenon at a known order. Its presence is "
     "normal; a rise in it is not, which is why the trend matters more "
     "than the level."),
    ("blade_vane_pass", "trend_plot", 2,
     "A vane-pass amplitude rising over weeks.",
     "Every pump shows vane pass. Only a change in it means anything."),
    # ---------------------------------------------------- journal bearing
    ("oil_whirl", "fft_spectrum", 1,
     "A sub-synchronous line just under half running speed, typically "
     "0.38x to 0.48x.",
     "Oil whirl is the oil film driving the shaft at slightly less than "
     "half speed. No balanced fault produces a fractional order, so this "
     "is unambiguous when the resolution can show it."),
    ("oil_whirl", "trend_plot", 2,
     "The sub-synchronous line appearing above a particular speed.",
     "Whirl has an onset speed. Seeing it arrive as speed rises is the "
     "confirmation, and the reason the machine may simply need a "
     "different operating point."),
    # -------------------------------------------------------- electrical
    ("electrical", "fft_spectrum", 1,
     "Lines at twice line frequency (100 Hz here) and pole-pass sidebands "
     "around 1x.",
     "An electrical fault is tied to the supply, not the shaft. A line at "
     "twice line frequency that ignores speed changes is the evidence."),
    ("electrical", "trend_plot", 2,
     "Amplitude that follows load rather than speed.",
     "Mechanical faults follow speed; electrical ones follow current. The "
     "trend against operating mode is what separates them."),
    # --------------------------------------------------------------- belt
    ("belt_drive", "fft_spectrum", 1,
     "A sub-synchronous line at belt rate and its harmonics.",
     "Belt rate is below running speed because the belt is longer than "
     "the pulley circumference. That places it in a region nothing else "
     "on a belt-driven machine occupies."),
    ("belt_drive", "time_waveform", 2,
     "An impact or disturbance once per belt revolution.",
     "Confirms the low line is a real repeating event and not spectral "
     "leakage from 1x, which is the usual false positive down there."),
)


def upgrade() -> None:
    # Default '[]' rather than nullable: an existing finding predates symptom
    # detection, and an empty list says "none recorded" where NULL would be
    # read as "none present" -- the same confusion this phase exists to stop.
    op.add_column(FINDINGS, sa.Column(
        "symptoms", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb")))

    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("fault_key", sa.String(64), nullable=False),
        sa.Column("plot_type", sa.String(32), nullable=False),
        # 1 is the plot to open first.
        sa.Column("rank", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("what_to_look_for", sa.Text(), nullable=False),
        # Why this plot and not another. Without it the table is a lookup
        # nobody can argue with, which is the failure mode of the whole
        # phase in miniature.
        sa.Column("why_this_plot", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        f"uq_{TABLE}_fault_plot", TABLE, ["fault_key", "plot_type"])
    op.create_index(f"ix_{TABLE}_fault", TABLE, ["fault_key", "rank"])
    op.create_check_constraint(
        f"ck_{TABLE}_plot_type", TABLE,
        "plot_type IN (" + ", ".join(f"'{p}'" for p in PLOT_TYPES) + ")")
    op.create_check_constraint(f"ck_{TABLE}_rank", TABLE, "rank >= 1")

    op.bulk_insert(
        sa.table(
            TABLE,
            sa.column("fault_key", sa.String),
            sa.column("plot_type", sa.String),
            sa.column("rank", sa.Integer),
            sa.column("what_to_look_for", sa.Text),
            sa.column("why_this_plot", sa.Text),
        ),
        [{"fault_key": key, "plot_type": plot, "rank": rank,
          "what_to_look_for": look, "why_this_plot": why}
         for key, plot, rank, look, why in MAPPING])


def downgrade() -> None:
    op.drop_table(TABLE)
    op.drop_column(FINDINGS, "symptoms")
