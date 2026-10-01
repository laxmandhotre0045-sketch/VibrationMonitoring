"""The four conditions behind an escalation, recorded separately — VIK-044.

Revision ID: 036
Revises: 035

The ticket asks for something the first cut did not deliver: "Escalation
needs repetition, a rising trend, steady speed and trustworthy data. Record
each condition separately so the reason for escalating can be audited."

What shipped had repetition and trustworthy data, collapsed into a single
`held_back` string. Two of the four were missing outright, and the two that
existed could not be told apart from each other after the fact -- which
defeats the point of the sentence. Somebody reviewing an alarm months later
wants to know *which* condition was short, and a single string cannot say
"it repeated and was trustworthy but never climbed".

So: four booleans, one per condition, plus `escalating` for all four
together.

**Escalating is a stronger claim than alarming, never a weaker one.** An
alarm needs the finding to have repeated and the baseline to be worth
trusting. Escalation needs those plus a climb on a machine whose speed held
steady -- it is the claim that the machine is getting *worse*, not merely
that it is unusual. A rising trend is deliberately not required to ring: a
bearing that jumped to 95 and stayed there is not rising, and is exactly
what an alarm exists for. Requiring a climb would silence the worst
findings a machine can produce, which is why the constraint below enforces
the implication in one direction only.

Booleans rather than jsonb, unlike `contributions` on the score table. The
set is fixed by the ticket and each one is queried on its own -- "what is
escalating on this plant" and "what stopped escalating when the speed went
unstable" are both ordinary questions, and neither is pleasant against a
jsonb key.
"""

from alembic import op
import sqlalchemy as sa

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None

TABLE = "feature_alarm_state"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("escalating", sa.Boolean(), nullable=False,
                                   server_default=sa.text("false")))
    # Each condition on its own, so a finding that did not escalate can say
    # which of the four it was short of.
    for name in ("cond_repetition", "cond_rising", "cond_steady_speed",
                 "cond_trustworthy"):
        op.add_column(TABLE, sa.Column(name, sa.Boolean(), nullable=False,
                                       server_default=sa.text("false")))
    # How the shaft speed behaved during the capture that produced this
    # verdict, kept beside the condition it decided.
    op.add_column(TABLE, sa.Column("stability", sa.String(16), nullable=True))

    op.create_check_constraint(
        f"ck_{TABLE}_stability", TABLE,
        "stability IS NULL OR stability IN ('steady', 'variable', 'unstable')")
    # Escalating implies alarming, and never the other way round. A row that
    # escalates without ringing would be a fault getting worse that nobody
    # is being told about.
    op.create_check_constraint(
        f"ck_{TABLE}_escalating_implies_alarming", TABLE,
        "(NOT escalating) OR alarming")
    # And escalating means all four conditions were met, so the flag can
    # never disagree with the evidence recorded beside it.
    op.create_check_constraint(
        f"ck_{TABLE}_escalating_has_all_conditions", TABLE,
        "(NOT escalating) OR (cond_repetition AND cond_rising "
        "AND cond_steady_speed AND cond_trustworthy)")

    op.create_index(f"ix_{TABLE}_escalating", TABLE, ["sensor_id", "score"],
                    postgresql_where=sa.text("escalating"))


def downgrade() -> None:
    op.drop_index(f"ix_{TABLE}_escalating", table_name=TABLE)
    op.drop_constraint(f"ck_{TABLE}_escalating_has_all_conditions", TABLE)
    op.drop_constraint(f"ck_{TABLE}_escalating_implies_alarming", TABLE)
    op.drop_constraint(f"ck_{TABLE}_stability", TABLE)
    op.drop_column(TABLE, "stability")
    for name in ("cond_trustworthy", "cond_steady_speed", "cond_rising",
                 "cond_repetition"):
        op.drop_column(TABLE, name)
    op.drop_column(TABLE, "escalating")
