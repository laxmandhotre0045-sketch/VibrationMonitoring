"""Report columns the database has that the application does not know about.

The declarative models are the application's definition of its own data, and
Alembic generates migrations by diffing them against the database. That is the
right arrangement and this module does not change it: the models stay the
source of truth, and nothing here alters a query, a response or a mapping.

What it adds is a smoke alarm.

In the intended workflow a column is added to a model, Alembic writes the
migration, the migration adds it to the database, and the two stay in step. But
they can come apart -- a migration applied only on one machine, a column added
by hand while debugging, a branch merged without its migration. When that
happens the application simply cannot see the column, and there is no error to
say so: queries succeed, responses look complete, and the value is silently
absent.

That is not hypothetical here. The shaft speed the platform had computed sat in
a field nothing downstream could read, and it took weeks to notice, because
every layer between it and the report quietly dropped what it had not been told
to expect. Two of those layers now carry everything they receive. This one
reports what it cannot carry, so the same failure is loud rather than silent.

Read-only, and deliberately advisory: it logs and returns, never raises. A
schema check that can stop the API from starting is a worse problem than the
drift it detects.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.database import Base

logger = logging.getLogger(__name__)


def find_undeclared_columns(engine: Engine) -> dict[str, list[str]]:
    """Columns present in the database but absent from the mapped models.

    Returns ``{table_name: [column, ...]}`` for tables the application maps.
    Tables it does not map at all are ignored -- alembic_version and anything
    another service owns are not this application's business.
    """
    drift: dict[str, list[str]] = {}
    try:
        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names())
    except Exception as exc:  # pragma: no cover - a dead database is reported elsewhere
        logger.warning("Schema drift check skipped: %s", exc)
        return drift

    for table_name, table in Base.metadata.tables.items():
        if table_name not in actual_tables:
            # The model expects a table that is not there. That is a missing
            # migration, and it will announce itself on the first query.
            continue
        try:
            in_database = {c["name"] for c in inspector.get_columns(table_name)}
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not inspect %s: %s", table_name, exc)
            continue
        declared = {c.name for c in table.columns}
        extra = sorted(in_database - declared)
        if extra:
            drift[table_name] = extra
    return drift


def report_schema_drift(engine: Engine) -> dict[str, Any]:
    """Run the check and log the result. Never raises."""
    try:
        drift = find_undeclared_columns(engine)
    except Exception as exc:  # pragma: no cover - advisory only, never fatal
        logger.warning("Schema drift check failed: %s", exc)
        return {"checked": False, "error": str(exc), "tables": {}}

    if drift:
        total = sum(len(v) for v in drift.values())
        logger.warning(
            "SCHEMA DRIFT: %d column(s) exist in the database but are not mapped, "
            "so nothing can read them. Add them to the model, or drop them.",
            total,
        )
        for table_name, columns in sorted(drift.items()):
            logger.warning("  %s: %s", table_name, ", ".join(columns))
    else:
        logger.info(
            "Schema check: every database column in %d mapped table(s) is declared.",
            len(Base.metadata.tables),
        )

    return {
        "checked": True,
        "tables": drift,
        "undeclared_total": sum(len(v) for v in drift.values()),
        "tables_checked": len(Base.metadata.tables),
    }
