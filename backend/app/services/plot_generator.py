import json
from pathlib import Path
from typing import Any
from uuid import UUID

from app.schemas.measurement import PLOT_TYPES, PLOT_TYPE_ALIASES, PlotSeriesOut
from app.services.signal_processing import (
    compute_circular_time_waveform,
    compute_envelope_spectrum,
    compute_fft_spectrum,
    compute_time_waveform,
    compute_trend_plot,
)

PLOT_COMPUTERS = {
    "time_waveform": lambda ts, samples, cfg: compute_time_waveform(
        ts, samples, float(cfg["sampling_rate_hz"])
    ),
    "circular_time_waveform": lambda ts, samples, cfg: compute_circular_time_waveform(ts, samples),
    "fft_spectrum": lambda ts, samples, cfg: compute_fft_spectrum(
        samples,
        float(cfg["sampling_rate_hz"]),
        fft_lines=cfg.get("fft_lines"),
        frequency_max_hz=cfg.get("frequency_max_hz"),
    ),
    "envelope_spectrum": lambda ts, samples, cfg: compute_envelope_spectrum(
        samples,
        float(cfg["sampling_rate_hz"]),
        fft_lines=cfg.get("fft_lines"),
        frequency_max_hz=cfg.get("frequency_max_hz"),
    ),
    "trend_plot": lambda ts, samples, cfg: compute_trend_plot(
        ts, samples, float(cfg["sampling_rate_hz"])
    ),
}


def normalize_plot_types(enabled: list[str] | None) -> list[str]:
    if not enabled:
        return list(PLOT_TYPES)
    result: list[str] = []
    for plot_type in enabled:
        canonical = PLOT_TYPE_ALIASES.get(plot_type, plot_type)
        if canonical in PLOT_COMPUTERS and canonical not in result:
            result.append(canonical)
    return result or list(PLOT_TYPES)


def load_parsed_data(parsed_data_path: str) -> dict[str, Any]:
    with open(parsed_data_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_active_channel(parsed_data: dict[str, Any], active_channel: int) -> int:
    """Clamp to a channel that exists in parsed data (ch0 .. chN-1)."""
    channels = parsed_data.get("channels", {})
    if not channels:
        return 0
    available = sorted(
        int(k[2:]) for k in channels if k.startswith("ch") and k[2:].isdigit()
    )
    if not available:
        return 0
    if active_channel in available and f"ch{active_channel}" in channels:
        return active_channel
    return available[0]


def generate_plot(
    parsed_data: dict[str, Any],
    plot_type: str,
    active_channel: int,
    config: dict[str, Any],
) -> PlotSeriesOut:
    plot_type = PLOT_TYPE_ALIASES.get(plot_type, plot_type)
    if plot_type not in PLOT_TYPES:
        raise ValueError(f"Unknown plot type: {plot_type}")

    active_channel = resolve_active_channel(parsed_data, active_channel)
    channel_key = f"ch{active_channel}"
    channels = parsed_data.get("channels", {})
    if channel_key not in channels:
        raise ValueError(f"Channel {channel_key} not found in parsed data")

    timestamps = parsed_data["timestamps"]
    samples = channels[channel_key]
    computer = PLOT_COMPUTERS[plot_type]
    result = computer(timestamps, samples, config)

    return PlotSeriesOut(
        plot_type=plot_type,
        title=result["title"],
        x_label=result["x_label"],
        y_label=result["y_label"],
        x=result["x"],
        y=result["y"],
        channel=active_channel,
        metadata=result.get("metadata", {}),
    )


def generate_all_plots(
    upload_id: UUID,
    sensor_id: UUID,
    parsed_data_path: str,
    config: dict[str, Any],
) -> list[PlotSeriesOut]:
    parsed = load_parsed_data(parsed_data_path)
    enabled = normalize_plot_types(config.get("enabled_plots"))
    active_channel = resolve_active_channel(parsed, int(config.get("active_channel", 0)))

    plots: list[PlotSeriesOut] = []
    for plot_type in enabled:
        if plot_type in PLOT_COMPUTERS:
            plots.append(
                generate_plot(parsed, plot_type, active_channel, config)
            )
    return plots


def save_parsed_data(parsed_data_path: str, data: dict[str, Any]) -> None:
    Path(parsed_data_path).parent.mkdir(parents=True, exist_ok=True)
    with open(parsed_data_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
