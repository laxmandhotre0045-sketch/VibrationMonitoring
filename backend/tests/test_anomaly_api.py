"""The Phase 2 read surface — VIK-041 to VIK-046 over the API.

Everything Phase 2 built wrote to the database and none of it was
reachable: 36,456 scores, 1,984 detector verdicts and 368 tracked features,
with no way to ask for any of them. These tests cover the surface that
fixed that.

The distinction defended most often below is the one the whole platform
rests on, and it is easiest to lose at the edge: **unscored is not zero, and
must survive the trip through JSON.** A serialiser that filled a null with a
default would undo, at the last step, everything the engines were careful
about.
"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

pytestmark = pytest.mark.db

SCORES = "/api/v1/anomaly/scores"
DETECTORS = "/api/v1/anomaly/detectors"
ALARMS = "/api/v1/anomaly/alarms"
SENSITIVITY = "/api/v1/anomaly/sensitivity"
MODES = "/api/v1/operating-modes"


@pytest.fixture
def equipment_id(db, sensor_id):
    return db.execute(sa.text(
        "SELECT equipment_id FROM sensor_configurations WHERE id = :s"
    ), {"s": str(sensor_id)}).scalar()


@pytest.fixture
def upload_with_scores(db, sensor_id):
    """A capture carrying one scored feature and one that could not be scored.

    Both are needed in every test below: the pair is the thing the API has
    to keep apart.
    """
    upload_id = uuid.uuid4()
    db.execute(sa.text("""
        INSERT INTO sensor_data_uploads (id, sensor_id, channel_count, pdf_path)
        VALUES (:id, :s, 8, '')
    """), {"id": str(upload_id), "s": str(sensor_id)})

    db.execute(sa.text("""
        INSERT INTO feature_anomaly_scores
            (upload_id, sensor_id, channel, feature_code, score, band,
             is_scored, z_score, confidence, baseline_version, reason)
        VALUES (:u, :s, 0, 'rms', 82.0, 'high', true, 3.9, 0.9, 7, 'high'),
               (:u, :s, 0, 'peak', NULL, NULL, false, NULL, 0.0, NULL,
                'No normal has been learned for this feature.')
    """), {"u": str(upload_id), "s": str(sensor_id)})
    db.flush()
    return upload_id


# ------------------------------------------------------ scores --------

def test_a_capture_reports_what_it_could_and_could_not_score(
    client, admin_headers, upload_with_scores
):
    response = client.get(SCORES, params={"upload_id": str(upload_with_scores)},
                          headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["scored"] == 1
    assert body["unscored"] == 1
    assert len(body["scores"]) == 2


def test_an_unscored_feature_comes_back_as_null_not_zero(
    client, admin_headers, upload_with_scores
):
    """The distinction the whole platform rests on, at the edge where it is
    easiest to lose. A serialiser filling the null with a default would make
    a feature nothing has ever been compared to look perfectly ordinary."""
    response = client.get(SCORES, params={"upload_id": str(upload_with_scores)},
                          headers=admin_headers)
    unscored = next(s for s in response.json()["scores"]
                    if s["feature_code"] == "peak")

    assert unscored["is_scored"] is False
    assert unscored["score"] is None, "a null score must not become 0"
    assert unscored["band"] is None
    assert unscored["reason"]


def test_unscored_features_are_returned_by_default(
    client, admin_headers, upload_with_scores
):
    """A caller that never sees them cannot tell "nothing is wrong here"
    from "nothing has ever been learned here", and those need different
    actions."""
    body = client.get(SCORES, params={"upload_id": str(upload_with_scores)},
                      headers=admin_headers).json()
    assert any(not s["is_scored"] for s in body["scores"])

    filtered = client.get(SCORES, params={"upload_id": str(upload_with_scores),
                                          "scored_only": "true"},
                          headers=admin_headers).json()
    assert all(s["is_scored"] for s in filtered["scores"])


def test_the_worst_is_a_scored_feature_or_nothing(
    client, admin_headers, upload_with_scores
):
    body = client.get(SCORES, params={"upload_id": str(upload_with_scores)},
                      headers=admin_headers).json()
    assert body["worst"]["feature_code"] == "rms"
    assert body["worst"]["score"] == 82.0


def test_a_capture_with_nothing_scored_has_no_worst(
    client, admin_headers, db, sensor_id
):
    """Inventing a worst at the bottom of the range would report the capture
    as the healthiest thing on the machine."""
    upload_id = uuid.uuid4()
    db.execute(sa.text("""
        INSERT INTO sensor_data_uploads (id, sensor_id, channel_count, pdf_path)
        VALUES (:id, :s, 8, '')
    """), {"id": str(upload_id), "s": str(sensor_id)})
    db.execute(sa.text("""
        INSERT INTO feature_anomaly_scores
            (upload_id, sensor_id, channel, feature_code, is_scored, confidence)
        VALUES (:u, :s, 0, 'rms', false, 0.0)
    """), {"u": str(upload_id), "s": str(sensor_id)})
    db.flush()

    body = client.get(SCORES, params={"upload_id": str(upload_id)},
                      headers=admin_headers).json()
    assert body["worst"] is None
    assert body["scored"] == 0


def test_an_unknown_capture_is_a_404_not_an_empty_answer(client, admin_headers):
    """An empty score list would read as "this capture is clean"."""
    response = client.get(SCORES, params={"upload_id": str(uuid.uuid4())},
                          headers=admin_headers)
    assert response.status_code == 404


def test_scores_can_be_narrowed_to_one_channel(
    client, admin_headers, upload_with_scores
):
    body = client.get(SCORES, params={"upload_id": str(upload_with_scores),
                                      "channel": 5},
                      headers=admin_headers).json()
    assert body["scores"] == []


# ---------------------------------------------------- detectors -------

def test_detector_verdicts_are_returned_with_their_drivers(
    client, admin_headers, db, sensor_id, upload_with_scores
):
    db.execute(sa.text("""
        INSERT INTO capture_detector_scores
            (upload_id, sensor_id, channel, method, score, is_scored, raw,
             drivers, reason, training_samples)
        VALUES (:u, :s, 0, 'pca_residual', 96.0, true, 4.2,
                '[{"feature": "rms", "share": 0.62}]'::jsonb, 'does not fit', 120),
               (:u, :s, 0, 'isolation_forest', NULL, false, NULL,
                '[]'::jsonb, 'not enough history', NULL)
    """), {"u": str(upload_with_scores), "s": str(sensor_id)})
    db.flush()

    rows = client.get(DETECTORS,
                      params={"upload_id": str(upload_with_scores)},
                      headers=admin_headers).json()
    by_method = {r["method"]: r for r in rows}

    assert by_method["pca_residual"]["drivers"][0]["feature"] == "rms"
    assert by_method["isolation_forest"]["score"] is None, (
        "a detector that could not run must not report a zero"
    )
    assert by_method["isolation_forest"]["is_scored"] is False


# ------------------------------------------------------- alarms -------

@pytest.fixture
def alarm_rows(db, sensor_id):
    db.execute(sa.text("""
        INSERT INTO feature_alarm_state
            (sensor_id, channel, feature_code, alarming, run_length, required,
             score, band, confidence, held_back, reason, first_alarmed_at)
        VALUES (:s, 0, 'rms', true, 4, 3, 88.0, 'high', 0.9, NULL,
                'sustained', now()),
               (:s, 1, 'peak', false, 1, 3, 95.0, 'critical', 0.9,
                'not_persistent', 'one capture only', NULL),
               (:s, 2, 'kurtosis', false, 0, 3, 12.0, 'normal', 0.9, NULL,
                'quiet', NULL)
    """), {"s": str(sensor_id)})
    db.flush()


def test_alarms_separate_what_rings_from_what_is_held_back(
    client, admin_headers, sensor_id, alarm_rows
):
    """A finding past the line and held back is the most useful thing to
    show somebody who thinks the platform is too quiet."""
    body = client.get(ALARMS, params={"sensor_id": str(sensor_id)},
                      headers=admin_headers).json()

    assert body["alarming"] == 1
    assert body["held_back"] == 1
    assert body["alarms"][0]["feature_code"] == "rms"
    assert body["suppressed"][0]["held_back"] == "not_persistent"


def test_a_quiet_feature_is_in_neither_list(
    client, admin_headers, sensor_id, alarm_rows
):
    """Held back means "past the line and not acted on". A quiet feature is
    not being suppressed and counting it as though it were would make the
    platform look like it was hiding things."""
    body = client.get(ALARMS, params={"sensor_id": str(sensor_id)},
                      headers=admin_headers).json()
    named = {a["feature_code"] for a in body["alarms"] + body["suppressed"]}
    assert "kurtosis" not in named


def test_an_alarm_carries_when_it_started_and_what_it_needed(
    client, admin_headers, sensor_id, alarm_rows
):
    body = client.get(ALARMS, params={"sensor_id": str(sensor_id)},
                      headers=admin_headers).json()
    alarm = body["alarms"][0]
    assert alarm["first_alarmed_at"] is not None
    assert alarm["run_length"] == 4
    assert alarm["required"] == 3


def test_acknowledging_records_who_and_does_not_silence_it(
    client, admin_headers, sensor_id, alarm_rows
):
    """The machine has not got better. What changes is that somebody has
    looked -- and an acknowledgement that stopped the alarm would make
    "seen" and "resolved" the same word."""
    response = client.post("/api/v1/anomaly/alarms/acknowledge",
                           json={"sensor_id": str(sensor_id), "channel": 0,
                                 "feature_code": "rms"},
                           headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["alarming"] == 1, "acknowledging must not silence it"
    assert body["alarms"][0]["acknowledged_at"] is not None
    assert body["alarms"][0]["acknowledged_by"]


def test_a_quiet_feature_cannot_be_acknowledged(
    client, admin_headers, sensor_id, alarm_rows
):
    """There is nothing for an acknowledgement of a quiet feature to mean."""
    response = client.post("/api/v1/anomaly/alarms/acknowledge",
                           json={"sensor_id": str(sensor_id), "channel": 2,
                                 "feature_code": "kurtosis"},
                           headers=admin_headers)
    assert response.status_code == 404


def test_a_viewer_cannot_acknowledge(client, viewer_headers, sensor_id,
                                     alarm_rows):
    response = client.post("/api/v1/anomaly/alarms/acknowledge",
                           json={"sensor_id": str(sensor_id), "channel": 0,
                                 "feature_code": "rms"},
                           headers=viewer_headers)
    assert response.status_code == 403


# -------------------------------------------------- sensitivity -------

def test_an_unconfigured_machine_reports_the_recommended_default(
    client, admin_headers, equipment_id
):
    """Not an error. It is being monitored at that setting right now."""
    body = client.get(SENSITIVITY, params={"equipment_id": str(equipment_id)},
                      headers=admin_headers).json()
    assert body["profile"] == "balanced"


def test_the_profile_returns_the_numbers_it_sets(
    client, admin_headers, equipment_id
):
    """So a settings screen can show what choosing one will do rather than
    describing it in prose."""
    body = client.get(SENSITIVITY, params={"equipment_id": str(equipment_id)},
                      headers=admin_headers).json()
    for key in ("score_threshold", "persistence", "min_confidence",
                "baseline_days"):
        assert body[key] is not None, f"{key} is missing"


def test_switching_the_profile_changes_the_numbers(
    client, admin_headers, equipment_id
):
    """VIK-046 over the wire: choosing a profile has to visibly change how
    readily this machine will alarm."""
    before = client.get(SENSITIVITY, params={"equipment_id": str(equipment_id)},
                        headers=admin_headers).json()

    response = client.put(SENSITIVITY,
                          params={"equipment_id": str(equipment_id)},
                          json={"profile": "early_warning"},
                          headers=admin_headers)
    assert response.status_code == 200, response.text
    after = response.json()

    assert after["profile"] == "early_warning"
    assert after["persistence"] < before["persistence"]
    assert after["updated_by"]


def test_expert_values_are_clamped_rather_than_rejected(
    client, admin_headers, equipment_id
):
    """Both extremes look like a working setup from a settings page: a
    threshold of 100 says nothing ever, a persistence of 1 says everything
    always."""
    body = client.put(SENSITIVITY, params={"equipment_id": str(equipment_id)},
                      json={"profile": "expert",
                            "overrides": {"persistence": 1,
                                          "score_threshold": 100}},
                      headers=admin_headers).json()
    assert body["persistence"] >= 2
    assert body["score_threshold"] < 100


def test_an_unknown_profile_is_refused_with_the_choices(
    client, admin_headers, equipment_id
):
    response = client.put(SENSITIVITY,
                          params={"equipment_id": str(equipment_id)},
                          json={"profile": "aggressive"},
                          headers=admin_headers)
    assert response.status_code == 422
    assert "balanced" in response.text


# ---------------------------------------------- operating modes -------

def test_a_machine_with_no_bands_returns_an_empty_list(
    client, admin_headers, equipment_id
):
    """The common case, and a real answer: every capture on it is unknown
    because the engine declines to invent what load it was under."""
    response = client.get(MODES, params={"equipment_id": str(equipment_id)},
                          headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


def test_a_band_can_be_defined_and_read_back(
    client, admin_headers, equipment_id
):
    created = client.post(MODES, params={"equipment_id": str(equipment_id)},
                          json={"label": "high_load", "rpm_min": 1450,
                                "rpm_max": 1550},
                          headers=admin_headers)
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "configured"

    listed = client.get(MODES, params={"equipment_id": str(equipment_id)},
                        headers=admin_headers).json()
    assert [m["label"] for m in listed] == ["high_load"]


def test_a_band_that_ends_before_it_starts_is_refused(
    client, admin_headers, equipment_id
):
    """It would match nothing and send every capture to unknown, while the
    machine looked configured."""
    response = client.post(MODES, params={"equipment_id": str(equipment_id)},
                           json={"label": "high_load", "rpm_min": 1600,
                                 "rpm_max": 1400},
                           headers=admin_headers)
    assert response.status_code == 422


def test_a_band_with_no_bounds_is_refused(client, admin_headers, equipment_id):
    """It would match everything and make every other band unreachable."""
    response = client.post(MODES, params={"equipment_id": str(equipment_id)},
                           json={"label": "normal_running"},
                           headers=admin_headers)
    assert response.status_code == 422


def test_two_bands_cannot_share_a_label(client, admin_headers, equipment_id):
    body = {"label": "high_load", "rpm_min": 1450, "rpm_max": 1550}
    assert client.post(MODES, params={"equipment_id": str(equipment_id)},
                       json=body, headers=admin_headers).status_code == 201
    second = client.post(MODES, params={"equipment_id": str(equipment_id)},
                         json=body, headers=admin_headers)
    assert second.status_code == 409


def test_retiring_a_band_keeps_it_rather_than_deleting_it(
    client, admin_headers, equipment_id
):
    """Captures already classified into it point at this row. Deleting it
    would leave them naming a mode that no longer exists."""
    mode_id = client.post(MODES, params={"equipment_id": str(equipment_id)},
                          json={"label": "high_load", "rpm_min": 1450,
                                "rpm_max": 1550},
                          headers=admin_headers).json()["id"]

    assert client.delete(f"{MODES}/{mode_id}",
                         headers=admin_headers).status_code == 204
    assert client.get(MODES, params={"equipment_id": str(equipment_id)},
                      headers=admin_headers).json() == []

    still_there = client.get(MODES,
                             params={"equipment_id": str(equipment_id),
                                     "include_inactive": "true"},
                             headers=admin_headers).json()
    assert [m["label"] for m in still_there] == ["high_load"]


def test_correcting_a_derived_band_marks_it_configured(
    client, admin_headers, db, equipment_id
):
    """A later re-derivation must not undo a correction somebody made."""
    db.execute(sa.text("""
        INSERT INTO operating_modes
            (equipment_id, label, rpm_min, rpm_max, source)
        VALUES (:e, 'normal_running', 1400, 1600, 'discovered')
    """), {"e": str(equipment_id)})
    db.flush()

    mode_id = client.get(MODES, params={"equipment_id": str(equipment_id)},
                         headers=admin_headers).json()[0]["id"]
    updated = client.put(f"{MODES}/{mode_id}",
                         json={"label": "normal_running", "rpm_min": 1420,
                               "rpm_max": 1580},
                         headers=admin_headers).json()

    assert updated["source"] == "configured"
    assert updated["rpm_min"] == 1420


def test_a_capture_never_classified_is_a_404_not_unknown(
    client, admin_headers, upload_with_scores
):
    """"We looked and could not tell" is a different fact from "nothing has
    ever looked at this"."""
    response = client.get(f"{MODES}/capture",
                          params={"upload_id": str(upload_with_scores)},
                          headers=admin_headers)
    assert response.status_code == 404


# -------------------------------------------- the capture picker -------

def test_the_capture_list_comes_from_the_scores_not_the_upload_status(
    client, admin_headers, db, sensor_id, upload_with_scores
):
    """`features_status` cannot answer which captures were analysed.

    On the live platform 157 uploads say "pending" while 120 of them carry
    scores: the column is written by the ingest path and the scores were
    also written by backfill scripts that never touched it. A picker
    filtered on it showed four captures out of a hundred and twenty-four.

    So this fixture is the awkward case made explicit -- an upload marked
    pending that has been scored, beside one marked ready that has not.
    """
    db.execute(sa.text(
        "UPDATE sensor_data_uploads SET features_status = 'pending' WHERE id = :u"
    ), {"u": str(upload_with_scores)})

    never_scored = uuid.uuid4()
    db.execute(sa.text("""
        INSERT INTO sensor_data_uploads
            (id, sensor_id, channel_count, pdf_path, features_status)
        VALUES (:id, :s, 8, '', 'ready')
    """), {"id": str(never_scored), "s": str(sensor_id)})
    db.flush()

    rows = client.get("/api/v1/anomaly/captures",
                      params={"sensor_id": str(sensor_id)},
                      headers=admin_headers).json()
    listed = {row["upload_id"] for row in rows}

    assert str(upload_with_scores) in listed, (
        "a scored capture must be offered however its status column reads"
    )
    assert str(never_scored) not in listed, (
        "a capture with no scores must not be offered, 'ready' or not"
    )


def test_each_listed_capture_carries_enough_to_choose_between_them(
    client, admin_headers, sensor_id, upload_with_scores
):
    """A timestamp alone makes every option look the same. The worst score
    is what lets somebody pick the capture worth opening."""
    row = next(
        r for r in client.get("/api/v1/anomaly/captures",
                              params={"sensor_id": str(sensor_id)},
                              headers=admin_headers).json()
        if r["upload_id"] == str(upload_with_scores)
    )
    assert row["scored"] == 1
    assert row["unscored"] == 1
    assert row["worst_score"] == 82.0
    assert row["worst_band"] == "high"


def test_a_machine_with_nothing_scored_returns_an_empty_list(
    client, admin_headers, sensor_id
):
    """Empty is a real answer: nothing has looked at this machine yet, which
    is not the same as it being clean."""
    response = client.get("/api/v1/anomaly/captures",
                          params={"sensor_id": str(sensor_id)},
                          headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == []


# ------------------------------ the four conditions over the API -------

def test_an_alarm_carries_the_four_conditions_separately(
    client, admin_headers, db, sensor_id
):
    """VIK-044 asks for each condition recorded so an escalation can be
    audited. Over the wire that means four named booleans, not one flag --
    "it repeated and was trustworthy but never climbed" is the only useful
    thing to know about an alarm that did not escalate."""
    db.execute(sa.text("""
        INSERT INTO feature_alarm_state
            (sensor_id, channel, feature_code, alarming, escalating,
             cond_repetition, cond_rising, cond_steady_speed, cond_trustworthy,
             stability, run_length, required, score, band, confidence,
             reason, first_alarmed_at)
        VALUES (:s, 0, 'rms', true, false, true, false, true, true,
                'steady', 4, 3, 88.0, 'high', 0.9, 'sustained', now())
    """), {"s": str(sensor_id)})
    db.flush()

    body = client.get(ALARMS, params={"sensor_id": str(sensor_id)},
                      headers=admin_headers).json()
    alarm = body["alarms"][0]

    assert alarm["escalating"] is False
    assert alarm["conditions"] == {
        "repetition": True, "rising": False,
        "steady_speed": True, "trustworthy": True,
    }
    assert alarm["stability"] == "steady"
    assert body["escalating"] == 0


def test_escalating_alarms_are_counted_and_ranked_first(
    client, admin_headers, db, sensor_id
):
    """A fault getting worse is the one to look at first, even when a flat
    finding scores higher."""
    db.execute(sa.text("""
        INSERT INTO feature_alarm_state
            (sensor_id, channel, feature_code, alarming, escalating,
             cond_repetition, cond_rising, cond_steady_speed, cond_trustworthy,
             run_length, required, score, band, confidence, first_alarmed_at)
        VALUES
            (:s, 0, 'flat', true, false, true, false, true, true,
             9, 3, 99.0, 'critical', 0.9, now()),
            (:s, 1, 'climbing', true, true, true, true, true, true,
             4, 3, 80.0, 'high', 0.9, now())
    """), {"s": str(sensor_id)})
    db.flush()

    body = client.get(ALARMS, params={"sensor_id": str(sensor_id)},
                      headers=admin_headers).json()

    assert body["escalating"] == 1
    assert body["alarms"][0]["feature_code"] == "climbing"
    assert body["alarms"][1]["score"] > body["alarms"][0]["score"], (
        "the flat one scores higher, which is exactly why ranking on score "
        "alone would bury the one that is getting worse"
    )


def test_the_database_refuses_an_escalation_that_is_not_an_alarm(
    db, sensor_id
):
    """A fault getting worse that nobody is being told about is the worst
    state available here, so the schema forbids it."""
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    with _pytest.raises(IntegrityError):
        db.execute(sa.text("""
            INSERT INTO feature_alarm_state
                (sensor_id, channel, feature_code, alarming, escalating,
                 cond_repetition, cond_rising, cond_steady_speed,
                 cond_trustworthy, run_length, required)
            VALUES (:s, 7, 'rms', false, true, true, true, true, true, 5, 3)
        """), {"s": str(sensor_id)})
        db.flush()


def test_the_database_refuses_an_escalation_missing_a_condition(db, sensor_id):
    """The flag can never disagree with the evidence recorded beside it."""
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    with _pytest.raises(IntegrityError):
        db.execute(sa.text("""
            INSERT INTO feature_alarm_state
                (sensor_id, channel, feature_code, alarming, escalating,
                 cond_repetition, cond_rising, cond_steady_speed,
                 cond_trustworthy, run_length, required, first_alarmed_at)
            VALUES (:s, 6, 'rms', true, true, true, false, true, true, 5, 3,
                    now())
        """), {"s": str(sensor_id)})
        db.flush()
