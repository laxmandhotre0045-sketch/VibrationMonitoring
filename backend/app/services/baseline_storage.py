"""Persist and load baseline plot series in PostgreSQL."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud import baseline as baseline_crud
from app.models.measurement import BaselinePlotResult, SensorBaseline
from app.schemas.measurement import PlotSeriesOut
from app.services.plot_generator import (
    PLOT_COMPUTERS,
    generate_plot,
    normalize_plot_types,
)
from app.services.plot_storage import compute_config_fingerprint


def _available_channels(parsed_data: dict[str, Any], channel_count: int) -> list[int]:
    channels = parsed_data.get("channels", {})
    available = sorted(
        int(k[2:]) for k in channels if k.startswith("ch") and k[2:].isdigit()
    )
    if not available:
        return list(range(channel_count))
    return [ch for ch in available if ch < channel_count] or available


def persist_baseline_plot_results(
    db: Session,
    baseline: SensorBaseline,
    parsed_data: dict[str, Any],
    config: dict[str, Any],
) -> int:
    fingerprint = compute_config_fingerprint(config)
    enabled = normalize_plot_types(config.get("enabled_plots"))
    baseline_crud.delete_baseline_plot_results(db, baseline.id, fingerprint)

    rows: list[BaselinePlotResult] = []
    for channel in _available_channels(parsed_data, baseline.channel_count):
        channel_key = f"ch{channel}"
        if channel_key not in parsed_data.get("channels", {}):
            continue
        for plot_type in enabled:
            if plot_type not in PLOT_COMPUTERS:
                continue
            series = generate_plot(parsed_data, plot_type, channel, config)
            rows.append(
                BaselinePlotResult(
                    baseline_id=baseline.id,
                    sensor_id=baseline.sensor_id,
                    plot_type=series.plot_type,
                    channel=series.channel,
                    title=series.title,
                    x_label=series.x_label,
                    y_label=series.y_label,
                    x_data=series.x,
                    y_data=series.y,
                    metadata_=series.metadata,
                    point_count=len(series.x),
                    sampling_rate_hz=float(config["sampling_rate_hz"]),
                    fft_lines=config.get("fft_lines"),
                    frequency_max_hz=config.get("frequency_max_hz"),
                    config_fingerprint=fingerprint,
                    computed_at=datetime.utcnow(),
                    status="ready",
                )
            )

    if rows:
        db.add_all(rows)
    db.commit()
    return len(rows)


def baseline_plot_to_series(row: BaselinePlotResult) -> PlotSeriesOut:
    return PlotSeriesOut(
        plot_type=row.plot_type,
        title=row.title,
        x_label=row.x_label,
        y_label=row.y_label,
        x=row.x_data,
        y=row.y_data,
        channel=row.channel,
        metadata=row.metadata_ or {},
    )
