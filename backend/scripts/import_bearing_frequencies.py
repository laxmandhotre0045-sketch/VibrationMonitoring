"""Load the bearing fault frequency catalogue into `bearing_fault_frequencies`.

Usage (from the backend directory, or inside the backend container):

    python scripts/import_bearing_frequencies.py "Bearing Fault Frequencies-Index.xlsx"
    python scripts/import_bearing_frequencies.py <file> --dry-run
    python scripts/import_bearing_frequencies.py <file> --truncate

The source is an .xlsx, which is a zip of XML — it is read here with the
standard library rather than openpyxl, so importing an 88k-row reference sheet
once does not add a dependency to the service that runs in production.

Two quirks of the sheet are handled deliberately:

1. Rows 1-3 are a VLOOKUP scratch area. The real header is row 4 and the data
   starts at row 5.

2. 8,406 designations were stored by Excel as *numbers*, and it mangled the ones
   that look like scientific notation: the part "2E+32" comes back as
   "2.0000000000000001E+32". The sheet's CONC column (manufacturer +
   designation, as text) survived intact, so the designation is always
   recovered from CONC by stripping the manufacturer prefix. That rule was
   checked against the whole sheet: it recovers all 8,406 numeric cells, and
   agrees with all 80,328 string cells.

The load is idempotent — it keys on the catalogue's own Bearing ID, so a rerun
updates rather than duplicates.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal
from pathlib import Path
from typing import Iterator

# Allow running as `python scripts/import_bearing_frequencies.py` from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SHEET = "xl/worksheets/sheet1.xml"

#: Row 4 is the header; everything below it is data.
FIRST_DATA_ROW = 5

#: Column letters in the source sheet.
COL_ID = "A"
COL_MANUFACTURER = "B"
COL_DESIGNATION = "C"
COL_ROLLING_ELEMENTS = "D"
COL_FTF = "E"
COL_BSF = "F"
COL_BPFO = "G"
COL_BPFI = "H"
COL_CONC = "I"

#: The catalogue carries 3 decimal places; the rest is float representation
#: noise ("0.40200000000000002"), so values are quantised on the way in.
QUANTUM = Decimal("0.0001")

#: BPFO + BPFI == rolling elements, for a stationary outer race. Allow the
#: larger of a rounding-sized absolute slack and 2% for big-diameter bearings.
CONSISTENCY_ABS = Decimal("0.05")
CONSISTENCY_REL = Decimal("0.02")

BATCH = 2000

_PUNCT = re.compile(r"[^A-Z0-9]+")


def normalise_key(manufacturer: str, designation: str) -> str:
    """Uppercase, punctuation-free key so a part number can be typed loosely."""
    return _PUNCT.sub("", f"{manufacturer}{designation}".upper())


def _column_of(ref: str) -> str:
    return "".join(ch for ch in ref if ch.isalpha())


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{NS}t")) for si in root.iter(f"{NS}si")]


def iter_sheet_rows(zf: zipfile.ZipFile, shared: list[str]) -> Iterator[tuple[int, dict[str, str]]]:
    """Stream the sheet as (row number, {column letter: cell text}).

    Streamed rather than loaded: the sheet is 41 MB of XML uncompressed.
    """
    with zf.open(SHEET) as handle:
        for _, element in ET.iterparse(handle, events=("end",)):
            if element.tag != f"{NS}row":
                continue
            cells: dict[str, str] = {}
            for cell in element.iter(f"{NS}c"):
                value = cell.find(f"{NS}v")
                if value is None or value.text is None:
                    continue
                if cell.get("t") == "s":
                    cells[_column_of(cell.get("r", ""))] = shared[int(value.text)]
                else:
                    cells[_column_of(cell.get("r", ""))] = value.text
            yield int(element.get("r") or 0), cells
            element.clear()


def _decimal(raw: str) -> Decimal:
    return Decimal(raw).quantize(QUANTUM)


class ImportStats:
    def __init__(self) -> None:
        self.read = 0
        self.skipped_blank = 0
        self.skipped_bad = 0
        self.loaded = 0
        self.inconsistent = 0
        self.recovered_designations = 0
        self.problems: list[str] = []

    def note(self, message: str) -> None:
        if len(self.problems) < 20:
            self.problems.append(message)


def parse_rows(path: Path, stats: ImportStats) -> Iterator[dict]:
    zf = zipfile.ZipFile(path)
    shared = _shared_strings(zf)

    for row_number, cells in iter_sheet_rows(zf, shared):
        if row_number < FIRST_DATA_ROW:
            continue
        if not any((cells.get(c) or "").strip() for c in cells):
            stats.skipped_blank += 1
            continue

        stats.read += 1
        # Manufacturer codes arrive in mixed case — the sheet carries both "FAG"
        # and "fag", "NTN" and "ntn", for six makers across ~17k rows. They are
        # abbreviations, so uppercase is the canonical form; left alone, the
        # same maker appears twice in every manufacturer list.
        raw_manufacturer = (cells.get(COL_MANUFACTURER) or "").strip()
        manufacturer = raw_manufacturer.upper()
        conc = (cells.get(COL_CONC) or "").strip()
        raw_designation = (cells.get(COL_DESIGNATION) or "").strip()

        # CONC is the only field Excel could not turn into a float. Prefer it,
        # and fall back to the cell itself if it does not carry the prefix.
        # Compared case-insensitively against the *raw* code, since CONC was
        # built from the manufacturer cell as it was written.
        if conc.upper().startswith(manufacturer) and len(conc) > len(raw_manufacturer):
            designation = conc[len(raw_manufacturer):]
            if designation != raw_designation:
                stats.recovered_designations += 1
        else:
            designation = raw_designation

        try:
            source_id = int(float(cells.get(COL_ID) or ""))
            rolling_elements = int(float(cells.get(COL_ROLLING_ELEMENTS) or ""))
            ftf = _decimal(cells.get(COL_FTF) or "")
            bsf = _decimal(cells.get(COL_BSF) or "")
            bpfo = _decimal(cells.get(COL_BPFO) or "")
            bpfi = _decimal(cells.get(COL_BPFI) or "")
        except (ValueError, ArithmeticError) as exc:
            stats.skipped_bad += 1
            stats.note(f"row {row_number}: unreadable number ({exc})")
            continue

        if not manufacturer or not designation:
            stats.skipped_bad += 1
            stats.note(f"row {row_number}: missing manufacturer or designation")
            continue

        tolerance = max(CONSISTENCY_ABS, Decimal(rolling_elements) * CONSISTENCY_REL)
        is_consistent = abs((bpfo + bpfi) - Decimal(rolling_elements)) <= tolerance
        if not is_consistent:
            stats.inconsistent += 1

        yield {
            "source_bearing_id": source_id,
            "manufacturer": manufacturer,
            "designation": designation,
            "search_key": normalise_key(manufacturer, designation),
            "rolling_elements": rolling_elements,
            "ftf": ftf,
            "bsf": bsf,
            "bpfo": bpfo,
            "bpfi": bpfi,
            "is_consistent": is_consistent,
        }


UPSERT = text(
    """
    INSERT INTO bearing_fault_frequencies (
        id, source_bearing_id, manufacturer, designation, search_key,
        rolling_elements, ftf, bsf, bpfo, bpfi, is_consistent
    )
    VALUES (
        gen_random_uuid(), :source_bearing_id, :manufacturer, :designation, :search_key,
        :rolling_elements, :ftf, :bsf, :bpfo, :bpfi, :is_consistent
    )
    ON CONFLICT (source_bearing_id) DO UPDATE SET
        manufacturer = EXCLUDED.manufacturer,
        designation = EXCLUDED.designation,
        search_key = EXCLUDED.search_key,
        rolling_elements = EXCLUDED.rolling_elements,
        ftf = EXCLUDED.ftf,
        bsf = EXCLUDED.bsf,
        bpfo = EXCLUDED.bpfo,
        bpfi = EXCLUDED.bpfi,
        is_consistent = EXCLUDED.is_consistent
    """
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Path to the .xlsx catalogue")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing anything.",
    )
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Empty the table first, for a clean reload.",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"No such file: {args.source}", file=sys.stderr)
        return 1

    stats = ImportStats()
    session = SessionLocal()
    batch: list[dict] = []

    try:
        if args.truncate and not args.dry_run:
            session.execute(text("TRUNCATE TABLE bearing_fault_frequencies"))
            session.commit()
            print("Table truncated.")

        for record in parse_rows(args.source, stats):
            stats.loaded += 1
            if args.dry_run:
                continue
            batch.append(record)
            if len(batch) >= BATCH:
                session.execute(UPSERT, batch)
                session.commit()
                batch.clear()
                print(f"  ... {stats.loaded:,} rows", end="\r", flush=True)

        if batch and not args.dry_run:
            session.execute(UPSERT, batch)
            session.commit()

        total = None
        if not args.dry_run:
            total = session.execute(
                text("SELECT count(*) FROM bearing_fault_frequencies")
            ).scalar()
    finally:
        session.close()

    print(" " * 40, end="\r")
    print(f"read            : {stats.read:,}")
    print(f"blank skipped   : {stats.skipped_blank:,}")
    print(f"bad skipped     : {stats.skipped_bad:,}")
    print(f"designations fixed from CONC: {stats.recovered_designations:,}")
    print(f"flagged inconsistent (BPFO+BPFI != rolling elements): {stats.inconsistent:,}")
    print(f"{'would load' if args.dry_run else 'loaded'}      : {stats.loaded:,}")
    if total is not None:
        print(f"table now holds : {total:,}")
    for problem in stats.problems:
        print(f"  ! {problem}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
