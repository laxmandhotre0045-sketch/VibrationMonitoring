"""Persist and load computed plot series in PostgreSQL (JSONB)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.crud import measurement as measurement_crud
from app.models.measurement import PlotResult, SensorDataUpload
from app.schemas.measurement import AllPlotsOut, PlotSeriesOut
from app.services.plot_generator import (
    PLOT_COMPUTERS,
    generate_plot,
    load_parsed_data,
    normalize_plot_types,
    resolve_active_channel,
)

# Bumped to v2 when compute_fft_spectrum was corrected: Hann scaling moved to
# the window's coherent gain and fft_lines became a line count. The fingerprint
# covers this constant, so every cached plot recomputes instead of serving the
# old, roughly-halved amplitudes.
ALGORITHM_VERSION = "v2"


def compute_config_fingerprint(config: dict[str, Any]) -> str:
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "sampling_rate_hz": float(config["sampling_rate_hz"]),
        "fft_lines": config.get("fft_lines"),
        "frequency_max_hz": config.get("frequency_max_hz"),
        "data_type": config.get("data_type", "acceleration"),
        "enabled_plots": sorted(normalize_plot_types(config.get("enabled_plots"))),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _available_channels(parsed_data: dict[str, Any], channel_count: int) -> list[int]:
    channels = parsed_data.get("channels", {})
    available = sorted(
        int(k[2:]) for k in channels if k.startswith("ch") and k[2:].isdigit()
    )
    if not available:
        return list(range(channel_count))
    return [ch for ch in available if ch < channel_count] or available


def plot_result_to_series(row: PlotResult) -> PlotSeriesOut:
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


def persist_all_plot_results(
    db: Session,
    upload: SensorDataUpload,
    parsed_data_path: str,
    config: dict[str, Any],
) -> int:
    """Compute all enabled plots for every channel and store in plot_results."""
    parsed = load_parsed_data(parsed_data_path)
    fingerprint = compute_config_fingerprint(config)
    enabled = normalize_plot_types(config.get("enabled_plots"))

    measurement_crud.delete_plot_results(db, upload.id, fingerprint)

    rows: list[PlotResult] = []
    for channel in _available_channels(parsed, upload.channel_count):
        channel_key = f"ch{channel}"
        if channel_key not in parsed.get("channels", {}):
            continue
        for plot_type in enabled:
            if plot_type not in PLOT_COMPUTERS:
                continue
            series = generate_plot(parsed, plot_type, channel, config)
            rows.append(
                PlotResult(
                    upload_id=upload.id,
                    sensor_id=upload.sensor_id,
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


def get_stored_plots_for_channel(
    db: Session,
    upload_id: UUID,
    config_fingerprint: str,
    channel: int,
) -> list[PlotResult]:
    return measurement_crud.get_plot_results(
        db,
        upload_id=upload_id,
        config_fingerprint=config_fingerprint,
        channel=channel,
    )


def get_or_load_all_plots(
    db: Session,
    upload: SensorDataUpload,
    config: dict[str, Any],
    channel: int | None = None,
) -> AllPlotsOut:
    """Return plots for the requested channel, loading from DB or computing if missing."""
    if not upload.parsed_data_path:
        raise ValueError("Upload has no parsed data")

    fingerprint = compute_config_fingerprint(config)
    parsed = load_parsed_data(upload.parsed_data_path)
    requested = channel if channel is not None else int(config.get("active_channel", 0))
    resolved_channel = resolve_active_channel(parsed, requested)

    stored = get_stored_plots_for_channel(db, upload.id, fingerprint, resolved_channel)
    enabled = normalize_plot_types(config.get("enabled_plots"))
    expected_types = {p for p in enabled if p in PLOT_COMPUTERS}

    if not stored or {r.plot_type for r in stored} != expected_types:
        persist_all_plot_results(db, upload, upload.parsed_data_path, config)
        measurement_crud.mark_upload_plots_ready(db, upload.id)
        db.refresh(upload)
        resolved_channel = resolve_active_channel(parsed, requested)
        stored = get_stored_plots_for_channel(db, upload.id, fingerprint, resolved_channel)

    all_stored = measurement_crud.get_plot_results(db, upload.id, fingerprint)
    available_channels = sorted({r.channel for r in all_stored})
    if not available_channels:
        available_channels = _available_channels(parsed, upload.channel_count)

    plots = [plot_result_to_series(r) for r in stored]
    plot_order = {p: i for i, p in enumerate(enabled)}
    plots.sort(key=lambda p: plot_order.get(p.plot_type, 999))

    return AllPlotsOut(
        upload_id=upload.id,
        sensor_id=upload.sensor_id,
        channel=resolved_channel,
        available_channels=available_channels,
        plots=plots,
    )


def get_or_load_single_plot(
    db: Session,
    upload: SensorDataUpload,
    config: dict[str, Any],
    plot_type: str,
    channel: int | None = None,
) -> PlotSeriesOut:
    all_plots = get_or_load_all_plots(db, upload, config, channel=channel)
    for plot in all_plots.plots:
        if plot.plot_type == plot_type:
            return plot
    raise ValueError(f"Plot type {plot_type} not found for channel {all_plots.channel}")
