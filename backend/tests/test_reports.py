"""Automatic reports — section 17.

Section 17.1 lists eighteen things a report should contain, 17.2 lists nine
kinds. Almost all the content exists elsewhere; a report is the act of
gathering it for one audience and one period.

**The tests that matter are about the empty sections.** On this gateway
most of a machine report cannot be filled — no fault is named because the
spectrum cannot resolve one, no RUL because there are five days of history,
no analyst comments because nobody has commented. A report that silently
omits those reads as a clean bill of health, and a monthly reliability
report that looks clean because half its inputs were missing is the most
expensive document this platform could produce.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.services.reports import (
    REPORT_TYPES,
    available_reports,
    fleet_report,
    machine_report,
)


# The `sensor_id` fixture creates a real machine and sensor through the
# same tables the application uses. Looking one up instead found nothing in
# the throwaway test database and passed `None` into every query.


# --------------------------------------------------- the nine types -----

def test_all_nine_report_types_from_section_17_2_exist():
    expected = {
        "Daily AI summary", "Weekly machine health report",
        "Monthly reliability report", "Critical alarm report",
        "Fault evolution report", "Bearing defect report",
        "Gearbox defect report", "Fleet health report",
        "Management summary report",
    }
    assert {spec["name"] for spec in REPORT_TYPES.values()} == expected
    assert len(available_reports()) == 9


def test_each_type_declares_its_scope_and_window():
    for report in available_reports():
        assert report["scope"] in ("machine", "fleet")
        assert report["period_days"] >= 1


def test_an_unknown_report_type_is_refused(db, sensor_id):
    with pytest.raises(ValueError, match="section 17.2"):
        machine_report(db, sensor_id=sensor_id, report_type="astrology")


# --------------------------------- every section says why it is empty ---

def test_no_section_is_ever_empty_without_a_reason(db, sensor_id):
    """The rule the whole module turns on. An empty section with no reason
    is a silent omission, and a reader takes it for "nothing to report"."""
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="weekly_machine_health")

    silent = [s["title"] for s in report["sections"]
              if not s["present"] and not s["reason"]]
    assert not silent, f"sections empty with no explanation: {silent}"
    assert report["sections_without_a_reason"] == []


def test_a_report_says_how_much_of_it_could_be_filled(db, sensor_id):
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="weekly_machine_health")
    assert "sections have content" in report["reason"]
    if report["sections_absent"]:
        assert "could not be filled" in report["reason"]


def test_an_absent_fault_does_not_read_as_a_healthy_machine(db, sensor_id):
    """The specific inference this platform exists to prevent, in the one
    document most likely to be read by somebody who was not there."""
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="weekly_machine_health")
    fault = next(s for s in report["sections"]
                 if s["title"] == "Fault suspected")
    if not fault["present"]:
        assert "not the machine being well" in fault["reason"] \
            or "spectrum" in fault["reason"]


def test_confidence_absent_is_not_confidence_of_zero(db, sensor_id):
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="weekly_machine_health")
    confidence = next(s for s in report["sections"]
                      if s["title"] == "Confidence")
    if not confidence["present"]:
        assert confidence["content"] is None
        assert "not confidence of zero" in confidence["reason"]


def test_rul_absent_carries_the_reason_from_section_13(db, sensor_id):
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="monthly_reliability")
    rul = next(s for s in report["sections"] if s["title"] == "RUL")
    if not rul["present"]:
        assert "RUL prediction not available" in rul["reason"]


# ------------------------------------------------------ 17.1's content --

def test_the_machine_report_covers_section_17_1s_items(db, sensor_id):
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="weekly_machine_health")
    titles = {s["title"] for s in report["sections"]}

    required = {
        "Asset details", "Measurement point", "Current health score",
        "Anomaly score", "Fault suspected", "Fault severity", "Confidence",
        "Baseline comparison", "Evidence summary", "Recommended plots",
        "Recommended action", "Analyst comments", "Maintenance feedback",
        "RUL",
    }
    assert required <= titles, f"missing: {sorted(required - titles)}"


def test_plots_are_referenced_rather_than_redrawn(db, sensor_id):
    """Redrawing them here would create a second set that could disagree
    with the screens."""
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="weekly_machine_health")
    plots = next(s for s in report["sections"]
                 if s["title"] == "Recommended plots")
    if plots["present"]:
        for entries in plots["content"].values():
            for entry in entries:
                assert "plot_type" in entry
                assert "what_to_look_for" in entry


def test_a_bearing_report_only_covers_bearing_faults(db, sensor_id):
    assert REPORT_TYPES["bearing_defect"]["faults"] == (
        "bearing_outer_race", "bearing_inner_race", "bearing_ball_defect",
        "bearing_cage")
    report = machine_report(db, sensor_id=sensor_id,
                            report_type="bearing_defect")
    evidence = next(s for s in report["sections"]
                    if s["title"] == "Evidence summary")
    for item in (evidence["content"] or []):
        assert "bearing" in item["fault"].lower()


# ------------------------------------------------------------- fleet ----

def test_a_fleet_report_names_the_machines_it_could_not_score(db, sensor_id):
    """An average over half a plant that does not say so is worse than
    none."""
    report = fleet_report(db, report_type="fleet_health")
    section = next(s for s in report["sections"]
                   if s["title"] == "Machines that could not be scored")
    assert section["present"] or section["reason"]


def test_a_quiet_alarm_section_does_not_claim_all_is_well(db, sensor_id):
    report = fleet_report(db, report_type="critical_alarms")
    alarms = next(s for s in report["sections"] if s["title"] == "Alarms")
    if not alarms["present"]:
        assert "not necessarily good news" in alarms["reason"]


def test_every_report_carries_the_versions_that_produced_it(db, sensor_id):
    """Section 22 and section 17 meet here: a report read in six months has
    to say which engine produced it."""
    for report in (machine_report(db, sensor_id=sensor_id),
                   fleet_report(db)):
        assert report["governance"]
        assert all("version" in c for c in report["governance"])
