"""Sensor SQL agent — backend-only access to measurement data for other agents.

Not a service and not a UI. Import it, call it, get a fixed envelope back:

    from sql_agent import SensorDataAgent

    agent = SensorDataAgent()
    result = agent.get_sensor_data("cooling water pump")
    if result.ok:
        rows = result.data                  # one row per capture x channel x feature
        csv_text = result.meta["csv"]
        caveats = result.meta["caveats"]    # units, no_baseline, ordering
    else:
        handle(result.error)                # failures are values, not exceptions

The package imports without the chatbot's retrieval stack, so a downstream agent
can depend on it without pulling in faiss, docling or sentence-transformers.
"""

from sql_agent.agent import (  # noqa: F401
    CAVEATS,
    AgentResult,
    SensorDataAgent,
    sensor_agent,
)
from sql_agent.client import (  # noqa: F401
    PlatformAuthError,
    PlatformClient,
    PlatformError,
    platform_client,
)
from sql_agent.dataset import (  # noqa: F401
    CSV_COLUMNS,
    SensorDataset,
    build_sensor_index,
    collect_sensor_dataset,
    dataset_to_rows,
    resolve_sensor,
    rows_to_csv,
    summarize,
)

__all__ = [
    "AgentResult",
    "SensorDataAgent",
    "sensor_agent",
    "CAVEATS",
    "CSV_COLUMNS",
    "PlatformClient",
    "PlatformError",
    "PlatformAuthError",
    "platform_client",
    "SensorDataset",
    "build_sensor_index",
    "collect_sensor_dataset",
    "dataset_to_rows",
    "resolve_sensor",
    "rows_to_csv",
    "summarize",
]
