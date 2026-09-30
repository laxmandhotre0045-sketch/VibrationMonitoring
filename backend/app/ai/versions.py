"""Every version the platform stamps on its output — section 22.

Section 22 ends with the line that matters: "No model should be changed
silently without version tracking." That is a claim about process, and a
constant sitting in each service module cannot enforce it -- five modules
each declaring `ENGINE_VERSION = "1"` is five places to forget.

So the versions live here, in one list, and the registry table in the
database is checked against this list by a test. Bump a version without
registering what changed and the suite fails. That is the same shape as
the released-revisions manifest that guards the migration chain, and for
the same reason: the thing being protected is a promise about history,
which no amount of checking the current state can verify.

**Two of section 22's nine items did not exist before this.** Feature
extraction and processing had no version at all, so a change to how a
feature is computed was indistinguishable from a change in the machine --
every stored value would shift and nothing would say why.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: One component of the pipeline whose output is stamped with a version.
@dataclass(frozen=True)
class Component:
    key: str
    name: str
    version: str
    #: What this component's version stamps, so a reader knows which rows
    #: become incomparable when it changes.
    stamps: str


#: The canonical set. A service module must import its version from here
#: rather than declaring its own, so there is one place to change and one
#: place to check.
COMPONENTS: tuple[Component, ...] = (
    Component("feature_extraction", "Feature extraction", "1",
              "every row in measurement_channel_features. A change here "
              "shifts every stored value, and without a version that is "
              "indistinguishable from the machine changing."),
    Component("processing", "Signal processing", "1",
              "the spectra and envelopes the features are computed from -- "
              "window, detrending, amplitude correction."),
    Component("quality", "Data quality", "1",
              "data_quality_assessments: whether a capture can be trusted."),
    Component("operating_mode", "Operating mode detection", "1",
              "capture_operating_modes: which band a capture was taken in."),
    Component("anomaly", "Anomaly scoring", "1",
              "feature_anomaly_scores: how unusual each reading is."),
    Component("detectors", "Joint detectors", "1",
              "capture_detector_scores: isolation forest and PCA residual."),
    Component("fault", "Fault diagnosis", "1",
              "fault_findings: the named fault, its stage and its evidence."),
)

BY_KEY: dict[str, Component] = {c.key: c for c in COMPONENTS}


def version_of(key: str) -> str:
    """The version a component stamps on its output."""
    return BY_KEY[key].version


def as_dicts() -> list[dict[str, Any]]:
    return [{"key": c.key, "name": c.name, "version": c.version,
             "stamps": c.stamps} for c in COMPONENTS]
