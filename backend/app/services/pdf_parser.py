"""
Parse sensor measurement files (CSV / PDF) into timestamp + channel columns.

Supported formats:
  timestamp_,ch0,ch1,ch2,...     (Excel export — header may be timestamp or timestamp_)
  timestamp,ch0,ch1,...
  Tab- or space-separated rows with Unix epoch or float timestamps
"""
import re
from typing import Any

CH_COLUMN_RE = re.compile(r"^ch(\d+)$", re.IGNORECASE)
TIMESTAMP_HEADERS = {"timestamp", "timestamp_", "time", "t", "index", "sample", "datetime", "date_time"}


def _clean_cell(value: str) -> str:
    return value.strip().strip('"').strip("'").strip("\ufeff")


def _parse_numeric_row(parts: list[str], channel_count: int) -> tuple[float, list[float]] | None:
    try:
        timestamp = float(_clean_cell(parts[0]))
        values = [float(_clean_cell(p)) for p in parts[1 : 1 + channel_count]]
        if not values:
            return None
        while len(values) < channel_count:
            values.append(0.0)
        return timestamp, values[:channel_count]
    except (ValueError, IndexError):
        return None


def _split_line(line: str) -> list[str]:
    line = line.strip()
    if not line:
        return []
    if "\t" in line:
        parts = line.split("\t")
    elif ";" in line and "," not in line:
        parts = line.split(";")
    elif "," in line:
        parts = line.split(",")
    else:
        parts = re.split(r"\s+", line)
    return [_clean_cell(p) for p in parts if _clean_cell(p)]


def _is_timestamp_header(cell: str) -> bool:
    normalized = _clean_cell(cell).lower().rstrip("_")
    return normalized in {"timestamp", "time", "t", "index", "sample", "datetime", "date", "time"} or cell.lower().startswith("timestamp")


def _is_header_row(parts: list[str]) -> bool:
    if not parts:
        return False
    if _is_timestamp_header(parts[0]):
        return True
    return any(CH_COLUMN_RE.match(p.lower()) for p in parts[1:])


def _detect_channel_count_from_header(parts: list[str]) -> int:
    count = 0
    for p in parts[1:]:
        if CH_COLUMN_RE.match(_clean_cell(p).lower()):
            count += 1
    return count


def _detect_channel_count_from_text(text: str) -> int | None:
    for raw_line in text.splitlines():
        parts = _split_line(raw_line)
        if _is_header_row(parts):
            detected = _detect_channel_count_from_header(parts)
            if detected > 0:
                return detected
    return None


def parse_measurement_text(text: str, channel_count: int) -> dict[str, Any]:
    detected = _detect_channel_count_from_text(text)
    effective_count = detected if detected else channel_count
    if detected and detected != channel_count:
        # Prefer columns present in the file (e.g. ch0–ch6 = 7, not user-supplied 8)
        effective_count = detected

    timestamps: list[float] = []
    channels: dict[str, list[float]] = {f"ch{i}": [] for i in range(effective_count)}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = _split_line(line)
        if not parts:
            continue
        if _is_header_row(parts):
            continue

        # Accept row if at least 1 channel value is present
        available_channels = len(parts) - 1
        if available_channels < 1:
            continue

        row_channels = min(effective_count, available_channels)
        parsed = _parse_numeric_row(parts, row_channels)
        if parsed is None:
            continue

        ts, values = parsed
        timestamps.append(ts)
        for i in range(effective_count):
            if i < len(values):
                channels[f"ch{i}"].append(values[i])
            else:
                channels[f"ch{i}"].append(0.0)

    if not timestamps:
        raise ValueError(
            "No valid measurement rows found. "
            "Expected header like timestamp_,ch0,ch1,... and numeric data rows. "
            f"Configured channel_count={channel_count}, detected={detected}."
        )

    return {
        "timestamps": timestamps,
        "channels": channels,
        "sample_count": len(timestamps),
        "channel_count": effective_count,
        "detected_channel_count": detected,
    }


def parse_sensor_pdf(pdf_path: str, channel_count: int) -> dict[str, Any]:
    import pdfplumber

    text_parts: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Prefer structured table extraction (Excel → PDF preserves tables)
            tables = page.extract_tables() or []
            if tables:
                for table in tables:
                    for row in table:
                        if row and any(c is not None and str(c).strip() for c in row):
                            text_parts.append(
                                ",".join(_clean_cell(str(c)) if c is not None else "" for c in row)
                            )
            else:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(page_text)

    combined = "\n".join(text_parts)
    if not combined.strip():
        raise ValueError("PDF contains no extractable text or table data")

    return parse_measurement_text(combined, channel_count)


def parse_sensor_csv(csv_path: str, channel_count: int) -> dict[str, Any]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(csv_path, "r", encoding=encoding, errors="replace") as f:
                return parse_measurement_text(f.read(), channel_count)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV file")


def parse_sensor_file(file_path: str, channel_count: int) -> dict[str, Any]:
    lower = file_path.lower()
    if lower.endswith(".csv"):
        return parse_sensor_csv(file_path, channel_count)
    if lower.endswith(".pdf"):
        return parse_sensor_pdf(file_path, channel_count)
    raise ValueError("Unsupported file type. Upload a .csv or .pdf file.")


# Backward-compatible alias
parse_pdf_text = parse_measurement_text
