"""The four fault outputs requirement 9.2 asks for and nothing produced.

Revision ID: 040
Revises: 039

Requirement 9.2 lists nine things that must appear beside every suspected
fault. An audit against the document rather than against memory found four
missing, and they are the four a maintenance engineer reads first:

  * **family** -- the group an analyst files it under, which is what decides
    who gets called out. Now on the rule itself in `fault_signatures.json`,
    and copied onto the finding so a row is readable on its own.
  * **score_history / direction** -- is this getting worse, holding, or
    recovering? The row held `score` and `peak_score`, which cannot answer
    it: the worst it has ever been and where it is now say nothing about
    which way it is travelling.
  * **urgency** -- requirement 14 puts it as "How urgent is it?". A stage is
    not an answer to that question; "severe" describes the fault, not what
    to do about it this afternoon.
  * **recommended_action** -- requirement 14's "What should the analyst do
    next?", and the last line of the AI card in requirement 20.

**The action text is a seeded table, for the same reason the plot mapping
is.** What to do about an outer-race defect is maintenance knowledge, and
the people who have it are not the people who deploy. A site that greases
its own bearings and a site with a contract should be able to differ
without a release.

**Urgency is stored resolved rather than derived on read.** It depends on
how confident the engine was and how well the machine could be seen *at the
time*, and both move. A finding that was capped at "inspect" because the
capture was untrustworthy should still say so next month, when the same
sensor is behaving and the stored stage would otherwise recompute into a
shutdown recommendation about a reading nobody can go back and check.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None

FINDINGS = "fault_findings"
TABLE = "fault_recommendations"

#: Least to most urgent. `immediate` is the only level that puts stopping
#: the machine on the table, and the engine caps its way down to it rather
#: than up.
URGENCY = ("none", "monitor", "inspect_when_convenient", "inspect_soon",
           "plan_maintenance", "immediate")

DIRECTIONS = ("rising", "steady", "falling", "unknown")

#: (fault_key, what to do if it is urgent, what to do otherwise, what to
#: check first). Keys are `vibcore.signatures`' own -- a test checks them
#: against the rule table, because the first draft of the plot mapping
#: invented nine keys that would have rendered as empty panels.
ACTIONS = (
    ("unbalance",
     "Stop at the next available window and balance the rotor in place. "
     "Running heavy unbalance loads the bearings continuously.",
     "Plan in-situ balancing. Check first for the ordinary causes: product "
     "build-up on the impeller, a missing balance weight, erosion.",
     "Look for fouling or material loss on the rotor before assuming a "
     "balance problem -- cleaning is cheaper than balancing."),
    ("bent_shaft",
     "Take the machine out of service. A bowed shaft damages seals and "
     "bearings continuously and does not recover.",
     "Plan a shaft runout check with a dial indicator at the next shutdown. "
     "Compare axial readings across the coupling.",
     "Confirm with a runout measurement before dismantling -- a bent shaft "
     "and a badly seated coupling look alike in the spectrum."),
    ("misalignment_parallel",
     "Realign the coupling at the next stop. Misalignment loads the "
     "bearings on both machines, not just this one.",
     "Plan a laser alignment check. Record cold and hot readings; a machine "
     "that grows into alignment is a different problem.",
     "Check soft foot and pipe strain first. Aligning a machine that is "
     "being pulled by its pipework will not hold."),
    ("misalignment_angular",
     "Realign the coupling at the next stop, paying attention to the "
     "angular offset rather than the parallel one.",
     "Plan a laser alignment check including the angular component, and "
     "inspect the coupling element for wear.",
     "Compare axial readings either side of the coupling; the larger one is "
     "usually the machine that has moved."),
    ("mechanical_looseness",
     "Find and tighten the loose joint before anything else. Looseness "
     "makes every other fault worse and every other measurement harder.",
     "Plan an inspection of hold-down bolts, bearing housing fits and "
     "component clearances.",
     "Work outward from the bearing housing: fits first, then the "
     "pedestal, then the hold-down bolts."),
    ("structural_looseness",
     "Address the base before treating anything else on this machine. A "
     "soft foot invalidates the alignment as well.",
     "Plan a soft-foot check with the coupling disconnected, and inspect "
     "the grout and baseplate.",
     "Slacken each foot in turn and watch the movement; the one that moves "
     "is the one to shim."),
    ("bearing_outer_race",
     "Plan bearing replacement. An outer-race defect does not heal and the "
     "interval from detectable to failed shortens as it grows.",
     "Review the envelope spectrum and trend the defect frequency. Check "
     "lubrication -- some early indications recover with correct greasing.",
     "Confirm the defect frequency in the envelope spectrum before "
     "ordering a bearing; on this machine it sits close to a shaft "
     "harmonic."),
    ("bearing_inner_race",
     "Plan bearing replacement. Inner-race defects usually progress faster "
     "than outer-race ones because the defect is in the loaded zone every "
     "revolution.",
     "Review the envelope spectrum for the defect frequency and its "
     "running-speed sidebands, and trend both.",
     "The sidebands spaced at running speed are what separate this from an "
     "outer-race defect. Check they are there."),
    ("bearing_ball_defect",
     "Plan bearing replacement. A damaged rolling element usually means "
     "debris is already circulating.",
     "Review the envelope spectrum and check the lubricant for metal.",
     "Look for cage-rate sidebands; a rolling-element defect rarely "
     "appears alone."),
    ("bearing_cage",
     "Plan bearing replacement promptly. Cage failure is the mode that "
     "seizes rather than degrading gracefully.",
     "Review the envelope spectrum at the cage frequency and inspect the "
     "lubricant.",
     "Irregular rather than evenly spaced impacts in the waveform support "
     "a cage problem over a race defect."),
    ("gear_mesh",
     "Stop and inspect the gearbox. Continuing to run a damaged mesh "
     "scatters debris through the whole train.",
     "Plan a gearbox inspection. Trend the mesh frequency and its "
     "sidebands, and sample the oil for wear particles.",
     "Sideband spacing names which shaft the fault is on -- check it "
     "before opening the box."),
    ("blade_vane_pass",
     "Investigate the hydraulic condition now: a large rise here usually "
     "means a blocked or damaged impeller.",
     "Trend the vane-pass amplitude against flow and pressure. Every pump "
     "shows vane pass; only a change in it means anything.",
     "Check suction conditions and strainers before opening the pump."),
    ("oil_whirl",
     "Change the operating point immediately if possible -- whirl can "
     "develop into whip, which damages the bearing quickly.",
     "Review the bearing loading and oil supply. Check oil temperature, "
     "viscosity grade and clearance.",
     "Note the speed at which the sub-synchronous line appears; whirl has "
     "an onset speed and the machine may simply need to run away from it."),
    ("electrical",
     "Involve the electrical team now. Some electrical faults progress to "
     "winding failure quickly.",
     "Plan an electrical inspection: check the supply, and inspect for "
     "rotor bar and air-gap problems.",
     "Confirm it is electrical by watching whether the line disappears the "
     "instant power is removed -- mechanical vibration coasts down, "
     "electrical does not."),
    ("belt_drive",
     "Stop and inspect the belts. A failing belt can take the guard and "
     "the sheaves with it.",
     "Plan a belt inspection: tension, alignment, wear and sheave "
     "condition.",
     "Check sheave alignment as well as belt condition; a misaligned "
     "sheave destroys a new belt as fast as the old one."),
)


def upgrade() -> None:
    # Requirement 9.2's "fault family", copied onto the row so a finding is
    # readable without joining back to the rule table.
    op.add_column(FINDINGS, sa.Column("family", sa.String(64), nullable=True))

    # The scores this finding has been given, oldest first, capped. `score`
    # and `peak_score` cannot answer "which way is it going" -- one is where
    # it is and the other is the worst it has been.
    op.add_column(FINDINGS, sa.Column(
        "score_history", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb")))
    op.add_column(FINDINGS, sa.Column(
        "direction", sa.String(16), nullable=False, server_default="unknown"))
    op.add_column(FINDINGS, sa.Column("direction_reason", sa.Text(),
                                      nullable=True))

    op.add_column(FINDINGS, sa.Column(
        "urgency", sa.String(32), nullable=False, server_default="none"))
    # What the stage alone would have proposed, kept beside what was
    # actually recommended. Without it a capped urgency is indistinguishable
    # from a mild fault, and the whole point of capping is that somebody can
    # see it happened and go and fix the cause.
    op.add_column(FINDINGS, sa.Column(
        "proposed_urgency", sa.String(32), nullable=True))
    op.add_column(FINDINGS, sa.Column(
        "urgency_capped", sa.Boolean(), nullable=False,
        server_default=sa.text("false")))
    op.add_column(FINDINGS, sa.Column("urgency_reason", sa.Text(),
                                      nullable=True))
    op.add_column(FINDINGS, sa.Column("recommended_action", sa.Text(),
                                      nullable=True))
    # Requirement 9.2's last line: "whether immediate shutdown is needed or
    # only inspection is required". A boolean because it is the one field
    # somebody may act on without reading the rest.
    op.add_column(FINDINGS, sa.Column(
        "shutdown_advised", sa.Boolean(), nullable=False,
        server_default=sa.text("false")))

    op.create_check_constraint(
        f"ck_{FINDINGS}_direction", FINDINGS,
        "direction IN (" + ", ".join(f"'{d}'" for d in DIRECTIONS) + ")")
    op.create_check_constraint(
        f"ck_{FINDINGS}_urgency", FINDINGS,
        "urgency IN (" + ", ".join(f"'{u}'" for u in URGENCY) + ")")
    # A shutdown recommendation is only ever the top level. Enforced rather
    # than trusted: this is the one field that stops a production line.
    op.create_check_constraint(
        f"ck_{FINDINGS}_shutdown_only_when_immediate", FINDINGS,
        "NOT shutdown_advised OR urgency = 'immediate'")

    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("fault_key", sa.String(64), nullable=False, unique=True),
        sa.Column("action_now", sa.Text(), nullable=False),
        sa.Column("action_planned", sa.Text(), nullable=False),
        sa.Column("check_first", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.bulk_insert(
        sa.table(TABLE,
                 sa.column("fault_key", sa.String),
                 sa.column("action_now", sa.Text),
                 sa.column("action_planned", sa.Text),
                 sa.column("check_first", sa.Text)),
        [{"fault_key": k, "action_now": now, "action_planned": planned,
          "check_first": check} for k, now, planned, check in ACTIONS])


def downgrade() -> None:
    op.drop_table(TABLE)
    for name in ("shutdown_advised", "recommended_action", "urgency_reason",
                 "urgency_capped", "proposed_urgency", "urgency",
                 "direction_reason", "direction", "score_history", "family"):
        op.drop_column(FINDINGS, name)
