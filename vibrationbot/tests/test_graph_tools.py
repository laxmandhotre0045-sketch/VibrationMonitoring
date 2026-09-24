"""Tool-layer tests.

The theme: a tool argument supplied by the model is the *least* trustworthy
input available, because the model will happily invent one. Where a value is
derivable from stated facts or a machine profile, the derived value must win.
"""

from __future__ import annotations

import pytest

from app.domain.machine import BearingSlot, Driven, Driver, MachineProfile
from app.chat.graph.tools_domain import DomainContext, build_domain_tools


def tool(ctx: DomainContext, name: str):
    return next(t for t in build_domain_tools(ctx) if t.name == name)


def run(ctx: DomainContext, name: str, **kwargs):
    """Invoke a tool the way ToolNode does, returning (summary, artifact)."""
    result = tool(ctx, name).invoke(
        {"name": name, "args": kwargs, "id": "call_1", "type": "tool_call"}
    )
    return result.content, result.artifact


class TestIsoGroupPrecedence:
    """Regression tests for a real bug: a live run had the model pass
    machine_group=1 for a 55 kW pump, which is Group 3. It was harmless only
    because Groups 1 and 3 share limits — on a Group 2 machine the same guess
    returns the wrong zone."""

    def test_derived_group_beats_the_models_argument(self):
        ctx = DomainContext(stated={"power_kw": 55, "machine_type": "pump"})
        _, record = run(ctx, "iso_severity_zone", velocity_rms_mm_s=4.9, machine_group=1, foundation="rigid")

        assert record["inputs"]["machine_group"] == 3
        assert any("not 1" in a for a in record["assumptions"])
        # Correcting the guess with a derived value is more trustworthy, not less.
        assert record["confidence"] == 1.0

    def test_user_stated_group_beats_the_models_argument(self):
        ctx = DomainContext(stated={"machine_group": 2})
        _, record = run(ctx, "iso_severity_zone", velocity_rms_mm_s=3.0, machine_group=1, foundation="rigid")

        assert record["inputs"]["machine_group"] == 2
        assert record["outputs"]["zone"] == "C"  # Group 2 rigid: 1.4/2.8/4.5

    def test_machine_profile_group_beats_the_models_argument(self):
        profile = MachineProfile(
            machine_id="P-1", type="pump",
            driver=Driver(power_kw=55), driven=Driven(integrated_driver=True),
        )
        ctx = DomainContext(profile=profile)
        _, record = run(ctx, "iso_severity_zone", velocity_rms_mm_s=3.0, machine_group=1)

        assert record["inputs"]["machine_group"] == 4
        assert record["inputs"]["foundation"] == "rigid"  # from the profile

    def test_undeterminable_group_falls_back_but_flags_it(self):
        """Using the model's guess is acceptable only if it is announced."""
        ctx = DomainContext()
        summary, record = run(ctx, "iso_severity_zone", velocity_rms_mm_s=3.0, machine_group=2, foundation="rigid")

        assert record["inputs"]["machine_group"] == 2
        assert record["confidence"] < 1.0
        assert "NOTE:" in summary
        assert any("not stated" in a for a in record["assumptions"])

    def test_no_group_anywhere_asks_rather_than_guessing(self):
        summary, record = run(DomainContext(), "iso_severity_zone", velocity_rms_mm_s=3.0, foundation="rigid")

        assert record is None
        assert "Cannot assign a zone" in summary
        assert "machine group" in summary.lower()

    def test_missing_foundation_asks_rather_than_assuming(self):
        """Rigid and flexible limits differ substantially; a default would mislead."""
        ctx = DomainContext(stated={"machine_group": 2})
        summary, record = run(ctx, "iso_severity_zone", velocity_rms_mm_s=3.0)

        assert record is None
        assert "foundation" in summary.lower()


class TestBearingTool:
    def test_shaft_speed_from_the_machine_profile(self):
        profile = MachineProfile(
            machine_id="M1",
            driver=Driver(rated_rpm=1750),
            bearings=[BearingSlot(position="de", designation="6205")],
        )
        ctx = DomainContext(profile=profile)
        _, record = run(ctx, "bearing_fault_frequencies", designation="6205")

        assert record["inputs"]["shaft_rpm"] == pytest.approx(1750)
        assert record["outputs"]["BPFO_hz"] == pytest.approx(104.56, abs=0.05)

    def test_measured_speed_beats_the_nameplate(self):
        """Fault frequencies scale with true speed, not the rating."""
        profile = MachineProfile(machine_id="M1", driver=Driver(rated_rpm=1800))
        ctx = DomainContext(profile=profile, actual_rpm=1750)
        _, record = run(ctx, "bearing_fault_frequencies", designation="6205")

        assert record["inputs"]["shaft_rpm"] == pytest.approx(1750)

    def test_unknown_speed_asks_rather_than_assuming(self):
        summary, record = run(DomainContext(), "bearing_fault_frequencies", designation="6205")

        assert record is None
        assert "shaft speed is unknown" in summary.lower()

    def test_unresolvable_bearing_asks_for_geometry(self):
        """A roller bearing has no estimator — it must not get ball geometry."""
        summary, record = run(
            DomainContext(stated={"shaft_rpm": 1500}), "bearing_fault_frequencies", designation="22312"
        )

        assert record is None
        assert "pitch diameter" in summary.lower()

    def test_estimated_geometry_lowers_confidence(self):
        _, record = run(
            DomainContext(stated={"shaft_rpm": 1480}), "bearing_fault_frequencies", designation="6312"
        )
        assert record["confidence"] < 1.0
        assert any("estimated" in a.lower() for a in record["assumptions"])


class TestConvertTool:
    def test_conversion_produces_a_record(self):
        _, record = run(
            DomainContext(), "convert_amplitude",
            value=1.0, from_unit="g", to_unit="mm/s", frequency_hz=100,
        )
        assert record["outputs"]["value"] == pytest.approx(15.61, abs=0.01)

    def test_missing_frequency_explains_rather_than_crashing(self):
        summary, record = run(
            DomainContext(), "convert_amplitude", value=1.0, from_unit="g", to_unit="mm/s"
        )
        assert record is None
        assert "frequency_hz" in summary


class TestDiagnoseTool:
    def test_stated_peaks_produce_a_ranking(self):
        ctx = DomainContext(stated={"shaft_rpm": 1750})
        summary, record = run(
            ctx, "match_fault_signatures", peaks_orders=[1.0, 2.0], peaks_amplitudes=[0.9, 0.2]
        )
        assert record["outputs"]["hypotheses"][0]["fault_key"] == "unbalance"
        assert "Unbalance" in summary

    def test_no_peaks_asks_rather_than_inventing_them(self):
        summary, record = run(DomainContext(stated={"shaft_rpm": 1750}), "match_fault_signatures")
        assert record is None
        assert "no spectral peaks" in summary.lower()

    def test_bearing_cross_check_uses_the_machine_profile(self):
        profile = MachineProfile(
            machine_id="M1",
            driver=Driver(rated_rpm=1750),
            bearings=[BearingSlot(position="de", designation="6205")],
        )
        ctx = DomainContext(profile=profile)
        _, record = run(ctx, "match_fault_signatures", peaks_orders=[1.0, 3.585], peaks_amplitudes=[0.2, 0.95])

        assert record["outputs"]["bearing_cross_check"]
        assert "BPFO" in record["outputs"]["bearing_cross_check"][0]


class TestForcingFrequenciesTool:
    def test_lists_the_machines_frequencies(self):
        profile = MachineProfile(
            machine_id="P-101", type="pump",
            driver=Driver(rated_rpm=1480, poles=4, line_freq_hz=50),
            driven=Driven(n_vanes=7),
        )
        summary, record = run(DomainContext(profile=profile), "machine_forcing_frequencies")

        assert "Vane pass" in summary
        assert record["outputs"]["vane_pass"]["order"] == pytest.approx(7.0)
        assert record["outputs"]["line_2x"]["hz"] == pytest.approx(100.0)

    def test_without_a_profile_it_says_so(self):
        summary, record = run(DomainContext(), "machine_forcing_frequencies")
        assert record is None
        assert "no machine profile" in summary.lower()
