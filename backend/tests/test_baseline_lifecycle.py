"""When a learned normal starts, stops moving, and is replaced — VIK-026.

The ticket's acceptance is "a reset must start a new version rather than
editing the old one, so a finding can always be traced to the baseline that
produced it". That is one test here. The rest are about the states in
between, and two of them matter more than the headline.

**A frozen baseline must refuse to roll.** Freezing exists because a normal
that keeps learning from a machine that is slowly degrading follows it down,
and the fault never becomes anomalous. A freeze that a later roll quietly
undoes is worse than no freeze at all, because somebody believes the normal
is pinned.

**One version in force, enforced by the database.** Two active baselines is
not a richer answer; it is an ambiguity that every reader downstream would
resolve differently. Tested against the constraint rather than against the
code that is careful about it, because the code will not always be careful.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.services import baseline_lifecycle as lc


def start_and_activate(db, sensor_id, reason="under test"):
    version = lc.start(db, sensor_id, reason=reason)["version"]
    return lc.activate(db, sensor_id, version)


# ---------------------------------------------------------- the states --

def test_a_new_version_is_not_in_force_until_it_is_activated(db, sensor_id):
    """The gap between building and active is where somebody can look at
    what was learned before anything is judged against it. A version that
    went live the moment it was created would remove that."""
    record = lc.start(db, sensor_id, reason="first")
    assert record["state"] == lc.BUILDING
    assert lc.in_force(db, sensor_id) is None


def test_activating_supersedes_what_held_that_place(db, sensor_id):
    first = start_and_activate(db, sensor_id)
    second = start_and_activate(db, sensor_id)

    assert second["version"] == first["version"] + 1
    assert lc.in_force(db, sensor_id)["version"] == second["version"]

    retired = lc.get_version(db, sensor_id, first["version"])
    assert retired["state"] == lc.SUPERSEDED
    assert retired["superseded_by"] == second["version"]
    assert retired["superseded_at"] is not None


def test_a_superseded_version_is_kept_rather_than_deleted(db, sensor_id):
    """The whole reason versions exist. A finding recorded three months ago
    was judged against a particular normal, and stays explainable only if
    that normal still exists, unchanged, with the finding pointing at it."""
    first = start_and_activate(db, sensor_id)
    start_and_activate(db, sensor_id)

    assert lc.get_version(db, sensor_id, first["version"]) is not None
    assert len(lc.history(db, sensor_id)) == 2


def test_a_retired_version_cannot_be_brought_back(db, sensor_id):
    """Reactivating it would silently rewrite what every finding recorded
    since then was judged against."""
    first = start_and_activate(db, sensor_id)
    start_and_activate(db, sensor_id)

    with pytest.raises(lc.LifecycleError, match="superseded"):
        lc.activate(db, sensor_id, first["version"])


def test_activating_the_version_already_in_force_changes_nothing(db, sensor_id):
    record = start_and_activate(db, sensor_id)
    again = lc.activate(db, sensor_id, record["version"])
    assert again["activated_at"] == record["activated_at"]


def test_activating_a_version_that_does_not_exist_is_refused(db, sensor_id):
    with pytest.raises(lc.LifecycleError, match="no baseline version"):
        lc.activate(db, sensor_id, 7)


# ---------------------------------------------------------- freezing ----

def test_freezing_keeps_the_baseline_in_force(db, sensor_id):
    """Frozen means stopped learning, not stopped applying. A frozen
    baseline that fell out of force would leave the sensor with no normal
    at all, which is the opposite of what freezing is for."""
    record = start_and_activate(db, sensor_id)
    frozen = lc.freeze(db, sensor_id, reason="pump known good this week")

    assert frozen["state"] == lc.FROZEN
    assert frozen["frozen_at"] is not None
    assert lc.in_force(db, sensor_id)["version"] == record["version"]


def test_a_frozen_baseline_refuses_to_roll(db, sensor_id):
    """The point of the ticket. A freeze a later roll quietly undoes is
    worse than no freeze, because somebody believes the normal is pinned."""
    start_and_activate(db, sensor_id)
    lc.freeze(db, sensor_id, reason="pinned")

    with pytest.raises(lc.LifecycleError, match="does not roll"):
        lc.require_rollable(db, sensor_id)


def test_freezing_keeps_the_reason_the_version_was_started_with(db, sensor_id):
    """Why a normal was learned and why it was later pinned are different
    facts. Overwriting the first loses it."""
    start_and_activate(db, sensor_id, reason="learned after the rebuild")
    frozen = lc.freeze(db, sensor_id, reason="commissioning accepted")

    assert "learned after the rebuild" in frozen["reason"]
    assert "commissioning accepted" in frozen["reason"]


def test_thawing_lets_it_roll_again_and_clears_the_pin(db, sensor_id):
    start_and_activate(db, sensor_id)
    lc.freeze(db, sensor_id, reason="pinned")
    thawed = lc.thaw(db, sensor_id)

    assert thawed["state"] == lc.ACTIVE
    assert thawed["frozen_at"] is None, (
        "a version frozen and released must not still read as pinned"
    )
    assert lc.require_rollable(db, sensor_id)["version"] == thawed["version"]


def test_freezing_and_thawing_nothing_is_refused_not_ignored(db, sensor_id):
    with pytest.raises(lc.LifecycleError, match="nothing to freeze"):
        lc.freeze(db, sensor_id)
    with pytest.raises(lc.LifecycleError, match="nothing to thaw"):
        lc.thaw(db, sensor_id)


def test_rolling_with_no_baseline_in_force_is_refused(db, sensor_id):
    """Not silently treated as "build the first one". A sensor with no
    baseline has no learned normal, and a roll that invented one would be a
    baseline nobody chose to activate."""
    lc.start(db, sensor_id, reason="built but never activated")
    with pytest.raises(lc.LifecycleError, match="no baseline in force"):
        lc.require_rollable(db, sensor_id)


# ------------------------------------------------- what the database --
#                                                    refuses on its own

def test_the_database_permits_only_one_version_in_force(db, sensor_id):
    """Enforced by a partial unique index, not by this module being careful.
    The module will not always be careful."""
    start_and_activate(db, sensor_id)
    second = lc.start(db, sensor_id, reason="second")["version"]

    with pytest.raises(IntegrityError):
        db.execute(text(
            "UPDATE baseline_versions SET state = 'active', activated_at = now() "
            " WHERE sensor_id = :s AND version = :v"),
            {"s": str(sensor_id), "v": second})
        db.flush()


def test_a_frozen_version_must_say_when_it_was_frozen(db, sensor_id):
    """Otherwise "how long has this normal been pinned" has no answer."""
    record = start_and_activate(db, sensor_id)
    with pytest.raises(IntegrityError):
        db.execute(text(
            "UPDATE baseline_versions SET state = 'frozen', frozen_at = NULL "
            " WHERE sensor_id = :s AND version = :v"),
            {"s": str(sensor_id), "v": record["version"]})
        db.flush()


def test_an_unknown_state_is_refused(db, sensor_id):
    record = lc.start(db, sensor_id)
    with pytest.raises(IntegrityError):
        db.execute(text(
            "UPDATE baseline_versions SET state = 'retired' "
            " WHERE sensor_id = :s AND version = :v"),
            {"s": str(sensor_id), "v": record["version"]})
        db.flush()


def test_two_sensors_keep_separate_versions(db, sensor_id):
    """The constraint is per sensor. A fleet where activating one machine's
    baseline retired another's would be unusable."""
    import uuid
    other = uuid.uuid4()
    start_and_activate(db, sensor_id)
    start_and_activate(db, other)

    assert lc.in_force(db, sensor_id) is not None
    assert lc.in_force(db, other) is not None
    assert lc.in_force(db, sensor_id)["version"] == 1
    assert lc.in_force(db, other)["version"] == 1
