"""Section 10.2's last two persistence checks — corroboration, acceleration.

Revision ID: 043
Revises: 042

Section 10.2 lists six things to check before one abnormal reading becomes
an alarm. Four were recorded from VIK-044 onwards: repetition, a rising
trend, steady speed and trustworthy data. The other two were never built:

  "Is the same symptom appearing in multiple plots?" -- one feature going
  high is one measurement. The same abnormality showing in the waveform,
  the spectrum and the envelope is three measurements that are computed
  differently and fail differently, and that is a materially stronger claim.

  "Is the trend accelerating?" -- something getting worse steadily and
  something getting worse faster and faster are different amounts of time
  to act in, and only the second has a deadline.

**Nullable, with no default.** Both can legitimately be unanswerable: a
capture whose peer features were not scored cannot say whether anything
corroborates, and a finding seen three times has too short a run to judge
acceleration. Stored as NULL, those read as "not established". Defaulting
them to false would record "we checked and it does not" for a check that
never ran, which is the confusion this whole platform is built to avoid.

**Neither is added to the escalation gate.** The existing four answer
whether a finding is real and worsening, which is what escalation turns on.
These two answer how sure and how fast -- they strengthen a finding rather
than validating it, and requiring them would make escalation harder on a
gateway where it is already dormant for want of a longer capture. They are
reported on the alarm and they feed the priority score.
"""

from alembic import op
import sqlalchemy as sa

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None

TABLE = "feature_alarm_state"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("cond_corroborated", sa.Boolean(),
                                   nullable=True))
    op.add_column(TABLE, sa.Column("cond_accelerating", sa.Boolean(),
                                   nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "cond_accelerating")
    op.drop_column(TABLE, "cond_corroborated")
