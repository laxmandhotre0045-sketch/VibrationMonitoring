"""Machine profile, derived forcing frequencies, and the JSON store."""

from __future__ import annotations

import pytest

from app.domain.machine import (
    BearingSlot,
    Coupling,
    Driven,
    Driver,
    Gearbox,
    GearStage,
    MachineProfile,
    MachineStore,
    MeasurementPoint,
    bearing_orders_for,
    derived_frequencies,
    shaft_speeds,
)


@pytest.fixture
def pump() -> MachineProfile:
    """55 kW, 4-pole, 50 Hz, 1480 rpm, 7-vane pump with a 6312 at the motor DE."""
    return MachineProfile(
        machine_id="P-101",
        name="Boiler feed pump 101",
        type="pump",
        driver=Driver(kind="motor", power_kw=55, poles=4, line_freq_hz=50, rated_rpm=1480),
        driven=Driven(kind="centrifugal_pump", rated_rpm=1480, n_vanes=7),
        coupling=Coupling(kind="direct"),
        foundation="rigid",
        bearings=[BearingSlot(position="motor_de", designation="6312", shaft="driver")],
        points=[MeasurementPoint(point_id="3H", location="motor_de", direction="H")],
    )


class TestForcingFrequencies:
    def test_running_speed_orders(self, pump):
        freqs = derived_frequencies(pump, actual_rpm=1478)

        assert freqs["1x"].hz == pytest.approx(24.633, abs=0.01)
        assert freqs["1x"].order == pytest.approx(1.0)
        assert freqs["2x"].hz == pytest.approx(49.267, abs=0.01)
        assert freqs["3x"].order == pytest.approx(3.0)

    def test_vane_pass(self, pump):
        freqs = derived_frequencies(pump, actual_rpm=1478)
        assert freqs["vane_pass"].order == pytest.approx(7.0)
        assert freqs["vane_pass"].hz == pytest.approx(172.43, abs=0.05)

    def test_twice_line_frequency_is_pinned_to_the_supply(self, pump):
        """100 Hz regardless of shaft speed — that is what identifies it."""
        at_rated = derived_frequencies(pump, actual_rpm=1480)
        at_slow = derived_frequencies(pump, actual_rpm=1400)

        assert at_rated["line_2x"].hz == pytest.approx(100.0)
        assert at_slow["line_2x"].hz == pytest.approx(100.0)
        # ...but its ORDER moves, because order is relative to shaft speed.
        assert at_slow["line_2x"].order > at_rated["line_2x"].order

    def test_pole_pass_from_slip(self, pump):
        """4-pole on 50 Hz syncs at 1500 rpm; running at 1478 gives 22 rpm slip."""
        freqs = derived_frequencies(pump, actual_rpm=1478)
        assert freqs["pole_pass"].hz == pytest.approx((1500 - 1478) / 60 * 4, abs=1e-6)

    def test_no_pole_pass_at_synchronous_speed(self, pump):
        assert "pole_pass" not in derived_frequencies(pump, actual_rpm=1500)

    def test_bearing_frequencies_present_and_flagged(self, pump):
        freqs = derived_frequencies(pump, point_id="3H", actual_rpm=1478)

        assert "bpfo" in freqs and "bpfi" in freqs and "ftf" in freqs
        # 6312 is not in the catalogue, so its geometry is estimated.
        assert freqs["bpfo"].confidence < 1.0
        assert freqs["bpfo"].kind == "bearing"

    def test_bpfo_plus_bpfi_invariant_holds_through_the_profile(self, pump):
        """The bearing invariant must survive the machine-profile plumbing."""
        orders = bearing_orders_for(pump, "3H", 1478)
        geom_n_balls = 9  # estimated for a 6312
        assert orders["bpfo"] + orders["bpfi"] == pytest.approx(geom_n_balls, abs=1e-6)

    def test_measured_speed_overrides_nameplate(self, pump):
        """Fault frequencies scale with true speed; the nameplate would skew them."""
        rated = derived_frequencies(pump)
        measured = derived_frequencies(pump, actual_rpm=1400)

        assert rated["1x"].hz == pytest.approx(1480 / 60, abs=1e-6)
        assert measured["1x"].hz == pytest.approx(1400 / 60, abs=1e-6)


class TestGracefulDegradation:
    def test_speed_only_profile_still_yields_running_orders(self):
        bare = MachineProfile(machine_id="X1", driver=Driver(rated_rpm=3000))
        freqs = derived_frequencies(bare)

        assert freqs["1x"].hz == pytest.approx(50.0)
        assert "vane_pass" not in freqs
        assert "bpfo" not in freqs

    def test_empty_profile_returns_nothing_rather_than_raising(self):
        assert derived_frequencies(MachineProfile(machine_id="X2")) == {}

    def test_unknown_bearing_type_is_skipped_not_guessed(self):
        """A spherical roller bearing has no estimator; it must not appear."""
        profile = MachineProfile(
            machine_id="X3",
            driver=Driver(rated_rpm=1500),
            bearings=[BearingSlot(position="de", designation="22312")],
        )
        freqs = derived_frequencies(profile)
        assert not any(f.kind == "bearing" for f in freqs.values())

    def test_journal_bearings_produce_no_defect_frequencies(self):
        profile = MachineProfile(
            machine_id="X4",
            driver=Driver(rated_rpm=3000),
            bearings=[BearingSlot(position="de", designation="6205", kind="journal")],
        )
        assert not any(f.kind == "bearing" for f in derived_frequencies(profile).values())


class TestGearboxAndBelt:
    def test_gear_mesh_per_stage(self):
        profile = MachineProfile(
            machine_id="G1",
            driver=Driver(rated_rpm=1500),
            gearbox=Gearbox(stages=[GearStage(teeth_in=23, teeth_out=71)]),
        )
        freqs = derived_frequencies(profile)
        assert freqs["gmf_stage1"].hz == pytest.approx(23 * 25.0, abs=1e-6)

    def test_gearbox_reduces_driven_shaft_speed(self):
        profile = MachineProfile(
            machine_id="G2",
            driver=Driver(rated_rpm=1500),
            gearbox=Gearbox(stages=[GearStage(teeth_in=20, teeth_out=60)]),
        )
        assert shaft_speeds(profile)["driven"] == pytest.approx(500.0)

    def test_belt_drive_changes_driven_speed(self):
        profile = MachineProfile(
            machine_id="B1",
            driver=Driver(rated_rpm=1500),
            coupling=Coupling(kind="belt", driver_sheave_dia_mm=200, driven_sheave_dia_mm=400, belt_length_mm=2000),
        )
        assert shaft_speeds(profile)["driven"] == pytest.approx(750.0)
        assert "belt" in derived_frequencies(profile)


class TestIsoGroupResolution:
    def test_pump_with_separate_driver_is_group_3(self, pump):
        assert pump.resolved_iso_group() == 3

    def test_explicit_group_wins_over_inference(self, pump):
        pump.iso_group = 1
        assert pump.resolved_iso_group() == 1

    def test_integrated_driver_pump_is_group_4(self):
        profile = MachineProfile(
            machine_id="P2", type="pump",
            driver=Driver(power_kw=55), driven=Driven(integrated_driver=True),
        )
        assert profile.resolved_iso_group() == 4


class TestStore:
    def test_round_trip(self, pump, tmp_path):
        store = MachineStore(root=tmp_path)
        store.save(pump)
        loaded = store.load("P-101")

        assert loaded is not None
        assert loaded.machine_id == "P-101"
        assert loaded.driver.power_kw == 55
        assert loaded.bearings[0].designation == "6312"

    def test_missing_machine_returns_none(self, tmp_path):
        assert MachineStore(root=tmp_path).load("nope") is None

    def test_list_and_delete(self, pump, tmp_path):
        store = MachineStore(root=tmp_path)
        store.save(pump)

        assert store.list_ids() == ["P-101"]
        assert store.delete("P-101") is True
        assert store.list_ids() == []
        assert store.delete("P-101") is False

    @pytest.mark.parametrize("machine_id", ["../escape", "a/b", "..", "", "x" * 65, "with space"])
    def test_path_traversal_and_bad_ids_rejected(self, machine_id, tmp_path):
        """machine_id becomes a directory name, so it must be constrained."""
        store = MachineStore(root=tmp_path)
        with pytest.raises(ValueError, match="Invalid machine_id"):
            store.load(machine_id)

    def test_write_is_atomic(self, pump, tmp_path):
        """A crash mid-write must not leave an unparseable profile."""
        store = MachineStore(root=tmp_path)
        store.save(pump)
        store.save(pump)

        leftovers = list((tmp_path / "P-101").glob("*.tmp"))
        assert leftovers == []
        assert store.load("P-101") is not None
