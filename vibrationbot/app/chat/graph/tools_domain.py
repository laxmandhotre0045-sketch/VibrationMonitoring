"""Domain tools exposed to the agent.

Each tool uses ``response_format="content_and_artifact"``: the model sees a
short summary string, while the full ComputationRecord travels as an artifact
that the model never reads and therefore cannot paraphrase or corrupt. The
graph pulls artifacts into ``state["computations"]``, where they become the
authoritative <COMPUTED> block and the basis for citation.

Machine context is injected by the caller rather than accepted as tool
arguments. Letting the model pass shaft speed or bearing geometry would let it
hallucinate the very inputs the computation depends on — the whole point of
these tools is that their inputs are traceable.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from vibcore import bearing as bearing_mod
from vibcore import iso10816, signatures, units
from app.domain.machine import MachineProfile, bearing_orders_for
from vibcore.records import ComputationRecord

logger = logging.getLogger(__name__)


class DomainContext:
    """Machine facts available to the tools for this turn."""

    def __init__(
        self,
        profile: MachineProfile | None = None,
        point_id: str | None = None,
        actual_rpm: float | None = None,
        stated: dict[str, Any] | None = None,
        peaks: list[signatures.SpectralPeak] | None = None,
    ) -> None:
        self.profile = profile
        self.point_id = point_id
        self.stated = stated or {}
        self.peaks = peaks or []
        self.calls: list[str] = []
        self._actual_rpm = actual_rpm

    @property
    def shaft_rpm(self) -> float | None:
        """Measured speed beats a stated speed beats the nameplate.

        Fault frequencies scale with true running speed, and an induction motor
        under load sits a few percent below its rated speed — enough to miss a
        +/-1.5% bearing match if the nameplate is used instead.
        """
        if self._actual_rpm:
            return float(self._actual_rpm)
        if self.stated.get("shaft_rpm"):
            return float(self.stated["shaft_rpm"])
        if self.profile and self.profile.driver.rated_rpm:
            return float(self.profile.driver.rated_rpm)
        return None

    def signature_context(self) -> signatures.MachineContext:
        profile, rpm = self.profile, self.shaft_rpm
        if profile is None:
            return signatures.MachineContext(
                shaft_rpm=rpm,
                bearing_orders=self._bearing_orders_from_stated(rpm),
                line_freq_hz=self.stated.get("line_freq_hz"),
            )
        return signatures.MachineContext(
            shaft_rpm=rpm,
            bearing_orders=bearing_orders_for(profile, self.point_id, rpm),
            vane_pass_order=float(profile.driven.n_vanes) if profile.driven.n_vanes else None,
            gear_mesh_orders=[
                float(s.teeth_in) for s in (profile.gearbox.stages if profile.gearbox else [])
            ],
            line_freq_hz=profile.driver.line_freq_hz or self.stated.get("line_freq_hz"),
            has_journal_bearings=profile.has_journal_bearings(),
            has_rolling_bearings=profile.has_rolling_bearings(),
        )

    def _bearing_orders_from_stated(self, rpm: float | None) -> dict[str, float]:
        designation = self.stated.get("bearing_designation")
        if not (designation and rpm):
            return {}
        geom = bearing_mod.resolve_bearing(designation)
        if geom is None:
            return {}
        freqs = bearing_mod.fault_frequencies(geom, rpm)
        return {
            "bpfo": freqs.bpfo_order,
            "bpfi": freqs.bpfi_order,
            "bsf": freqs.bsf_order,
            "bsf2x": freqs.bsf_2x_order,
            "ftf": freqs.ftf_order,
        }


# --------------------------------------------------------------------------
# Argument schemas
# --------------------------------------------------------------------------


class BearingArgs(BaseModel):
    shaft_rpm: float | None = Field(
        None, gt=0, description="Shaft speed in RPM. Omit to use the machine profile."
    )
    designation: str | None = Field(None, description="Bearing designation, e.g. '6205' or 'SKF 6312'")
    n_balls: int | None = Field(None, gt=0, description="Rolling element count, if known from the datasheet")
    ball_dia_mm: float | None = Field(None, gt=0)
    pitch_dia_mm: float | None = Field(None, gt=0)
    contact_angle_deg: float = Field(0.0, ge=0, le=90)


class IsoArgs(BaseModel):
    velocity_rms_mm_s: float = Field(..., ge=0, description="Broadband velocity, mm/s RMS, 10-1000 Hz")
    machine_group: int | None = Field(None, ge=1, le=4, description="ISO group; inferred if omitted")
    foundation: str | None = Field(None, description="'rigid' or 'flexible'")
    standard: str = Field("10816-3", description="'10816-3' or '20816-3'")


class ConvertArgs(BaseModel):
    value: float
    from_unit: str = Field(..., description="g, m/s2, mm/s, in/s, um, mil")
    to_unit: str = Field(..., description="g, m/s2, mm/s, in/s, um, mil")
    frequency_hz: float | None = Field(None, gt=0, description="Required when the quantity changes")
    from_measure: str = Field("rms", description="rms, peak, or pk-pk")
    to_measure: str = Field("rms", description="rms, peak, or pk-pk")


class DiagnoseArgs(BaseModel):
    peaks_orders: list[float] | None = Field(
        None, description="Peak positions as orders of running speed, if stated by the user"
    )
    peaks_amplitudes: list[float] | None = Field(None, description="Amplitudes matching peaks_orders")
    top_n: int = Field(5, ge=1, le=8)


class ForcingArgs(BaseModel):
    actual_rpm: float | None = Field(None, gt=0, description="Measured speed; overrides the nameplate")


# --------------------------------------------------------------------------


def build_domain_tools(ctx: DomainContext) -> list[StructuredTool]:
    """Build domain tools bound to this turn's machine context."""

    def bearing_fault_frequencies(
        shaft_rpm: float | None = None,
        designation: str | None = None,
        n_balls: int | None = None,
        ball_dia_mm: float | None = None,
        pitch_dia_mm: float | None = None,
        contact_angle_deg: float = 0.0,
    ) -> tuple[str, dict[str, Any] | None]:
        """Compute BPFO, BPFI, BSF and FTF for a rolling-element bearing.

        Give a designation (e.g. '6205') or explicit geometry. Shaft speed comes
        from the machine profile when not supplied.
        """
        ctx.calls.append("bearing_fault_frequencies")
        rpm = shaft_rpm or ctx.shaft_rpm
        if not rpm:
            return (
                "Cannot compute: shaft speed is unknown. Ask the user for the running "
                "speed in RPM, or register the machine's rated speed.",
                None,
            )

        designation = designation or ctx.stated.get("bearing_designation")
        geom = bearing_mod.geometry_from_inputs(
            designation=designation,
            n_balls=n_balls,
            ball_dia_mm=ball_dia_mm,
            pitch_dia_mm=pitch_dia_mm,
            contact_angle_deg=contact_angle_deg,
        )
        if geom is None:
            return (
                f"Cannot compute: bearing geometry for {designation or 'the bearing'} is not "
                "in the bundled catalogue and cannot be estimated for this bearing type "
                "(estimation is only defensible for deep-groove ball bearings). Ask the user "
                "for the rolling element count, ball diameter and pitch diameter, or search "
                "the indexed bearing catalogues with table_search.",
                None,
            )

        freqs = bearing_mod.fault_frequencies(geom, rpm)
        record = bearing_mod.build_record(freqs)
        return bearing_mod.summarize(freqs), record.as_dict()

    def iso_severity_zone(
        velocity_rms_mm_s: float,
        machine_group: int | None = None,
        foundation: str | None = None,
        standard: str = "10816-3",
    ) -> tuple[str, dict[str, Any] | None]:
        """Assign an ISO 10816-3 / 20816-3 evaluation zone (A/B/C/D) to a velocity reading.

        Machine group and foundation come from the machine profile when not supplied.
        """
        ctx.calls.append("iso_severity_zone")
        profile = ctx.profile
        notes: list[str] = []

        # Precedence matters here, and the model's own argument comes LAST.
        # ISO groups are derivable from the machine record, and a model asked
        # for a group will happily guess one instead.
        #
        # Note what "derivable" means, because getting this wrong has cost this
        # project twice: pumps are grouped by DRIVER ARRANGEMENT -- Group 3
        # separate, Group 4 integrated -- at any rated power, while Groups 1
        # and 2 are power-banded and contain no pumps. Rated power alone does
        # not determine the group. infer_machine_group() in app/domain/iso10816
        # is the single place that rule is expressed; do not restate it here.
        #
        # Observed in practice: a 55 kW pump classified as Group 1. Harmless
        # only because Groups 1 and 3 happen to share limits; the same guess on
        # a machine where they differ returns the wrong zone with full
        # confidence.
        group = ctx.stated.get("machine_group")
        if group is None and profile is not None:
            group = profile.resolved_iso_group()
        if group is None:
            group = iso10816.infer_machine_group(
                power_kw=ctx.stated.get("power_kw"),
                machine_type=ctx.stated.get("machine_type"),
            )

        # Only an unverifiable group is a caveat. Overriding the model's guess
        # with a derived value makes the result *more* trustworthy, not less,
        # so that case is reported without a confidence penalty.
        group_unverified = False
        if group is None:
            group = machine_group
            if group is not None:
                group_unverified = True
                notes.append(
                    f"Machine group {group} was not stated by the user and could not be "
                    "derived from the machine's power and type. Confirm it against "
                    "ISO 10816-3 Clause 5 before relying on this zone."
                )
        elif machine_group is not None and int(machine_group) != int(group):
            notes.append(
                f"Machine group {int(group)} was used (derived from the machine's power and "
                f"type), not {int(machine_group)}."
            )

        if group is None:
            return (
                "Cannot assign a zone: the ISO machine group is unknown. Ask the user for "
                "the rated power and machine type (e.g. '55 kW centrifugal pump'), or for "
                "the group directly (1-4).",
                None,
            )

        found = foundation or ctx.stated.get("foundation") or (profile.foundation if profile else None)
        if not found:
            return (
                "Cannot assign a zone: the foundation type is unknown. Ask the user whether "
                "the machine is on a rigid or flexible foundation — the limits differ "
                "substantially between them.",
                None,
            )

        try:
            result = iso10816.severity_zone(velocity_rms_mm_s, int(group), found, standard)
        except ValueError as exc:
            return f"Cannot assign a zone: {exc}", None

        record = iso10816.build_record(result)
        record.assumptions.extend(notes)
        if group_unverified:
            record.confidence = 0.7
        summary = iso10816.summarize(result)
        if notes:
            summary += "\n" + "\n".join(f"NOTE: {n}" for n in notes)
        return summary, record.as_dict()

    def convert_amplitude(
        value: float,
        from_unit: str,
        to_unit: str,
        frequency_hz: float | None = None,
        from_measure: str = "rms",
        to_measure: str = "rms",
    ) -> tuple[str, dict[str, Any] | None]:
        """Convert a vibration amplitude between units (g, mm/s, um, mil) and measures (rms, peak, pk-pk).

        A frequency is required when converting between acceleration, velocity and displacement.
        """
        ctx.calls.append("convert_amplitude")
        try:
            result = units.convert_amplitude(
                value, from_unit, to_unit, frequency_hz, from_measure, to_measure
            )
        except ValueError as exc:
            return f"Cannot convert: {exc}", None
        return units.summarize(result, value), units.build_record(result, value).as_dict()

    def match_fault_signatures(
        peaks_orders: list[float] | None = None,
        peaks_amplitudes: list[float] | None = None,
        top_n: int = 5,
    ) -> tuple[str, dict[str, Any] | None]:
        """Rank likely faults from spectral peaks, cross-checked against the machine's
        computed bearing and forcing frequencies.

        Uses peaks already extracted from an uploaded measurement when available;
        otherwise pass orders and amplitudes the user stated.
        """
        ctx.calls.append("match_fault_signatures")
        peaks = ctx.peaks
        if not peaks and peaks_orders:
            rpm = ctx.shaft_rpm
            if not rpm:
                return (
                    "Cannot diagnose: shaft speed is unknown, so peak positions cannot be "
                    "converted to orders. Ask the user for the running speed.",
                    None,
                )
            shaft_hz = rpm / 60.0
            amplitudes = peaks_amplitudes or [1.0] * len(peaks_orders)
            peaks = [
                signatures.SpectralPeak(
                    frequency_hz=order * shaft_hz, amplitude=amp, order=order, source="user"
                )
                for order, amp in zip(peaks_orders, amplitudes)
            ]

        if not peaks:
            return (
                "Cannot diagnose: no spectral peaks are available. Either upload a "
                "measurement, or state the peak positions as orders of running speed.",
                None,
            )

        sig_ctx = ctx.signature_context()
        notes = signatures.cross_check_bearing_peaks(peaks, sig_ctx.bearing_orders)
        hypotheses = signatures.match_faults(peaks, sig_ctx, top_n=top_n)
        record = signatures.build_record(hypotheses, peaks, sig_ctx, notes)
        return signatures.summarize(hypotheses, notes), record.as_dict()

    def machine_forcing_frequencies(actual_rpm: float | None = None) -> tuple[str, dict[str, Any] | None]:
        """List every frequency the registered machine can produce — running-speed orders,
        vane/blade pass, gear mesh, electrical, and bearing defect frequencies.

        Use this to identify what a peak in the spectrum corresponds to.
        """
        ctx.calls.append("machine_forcing_frequencies")
        if ctx.profile is None:
            return (
                "No machine profile is registered for this conversation. Ask the user to "
                "register the machine, or supply the running speed and bearing designation "
                "directly.",
                None,
            )
        from app.domain.machine import derived_frequencies, summarize_frequencies

        rpm = actual_rpm or ctx.shaft_rpm
        freqs = derived_frequencies(ctx.profile, ctx.point_id, rpm)
        if not freqs:
            return (
                f"Machine {ctx.profile.machine_id} has no running speed recorded, so no "
                "forcing frequencies can be computed. Ask the user for the shaft speed.",
                None,
            )

        record = ComputationRecord(
            tool="machine_forcing_frequencies",
            inputs={"machine_id": ctx.profile.machine_id, "point_id": ctx.point_id, "shaft_rpm": rpm},
            outputs={key: freq.as_dict() for key, freq in freqs.items()},
            formula="Forcing frequencies derived from the machine profile geometry and running speed",
            assumptions=[
                "Frequencies are computed from the registered machine profile. If the "
                "nameplate data is wrong, every value here is wrong by the same factor."
            ],
            confidence=min((f.confidence for f in freqs.values()), default=1.0),
        )
        return summarize_frequencies(freqs), record.as_dict()

    specs = [
        (bearing_fault_frequencies, "bearing_fault_frequencies", BearingArgs),
        (iso_severity_zone, "iso_severity_zone", IsoArgs),
        (convert_amplitude, "convert_amplitude", ConvertArgs),
        (match_fault_signatures, "match_fault_signatures", DiagnoseArgs),
        (machine_forcing_frequencies, "machine_forcing_frequencies", ForcingArgs),
    ]
    return [
        StructuredTool.from_function(
            func=func, name=name, args_schema=schema, response_format="content_and_artifact"
        )
        for func, name, schema in specs
    ]
