"""Building permits for an address, from the three City of Toronto permit datasets."""

import re
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import Permit

_COLUMNS = """
    permit_num, revision_num, permit_type, structure_type, work, status,
    application_date, issued_date, completed_date, description,
    current_use, proposed_use, dwelling_units_created, dwelling_units_lost, est_const_cost
"""

# The active and cleared sets overlap while a permit is closing; active wins.
PERMITS_SQL = f"""
SELECT DISTINCT ON (permit_num, revision_num) *
FROM (
    SELECT 1 AS priority, {_COLUMNS} FROM city.permits_active WHERE geo_id = :geo_id
    UNION ALL
    SELECT 2, {_COLUMNS} FROM city.permits_cleared WHERE geo_id = :geo_id
    UNION ALL
    SELECT 3, {_COLUMNS} FROM city.permits_cleared_2000_2016 WHERE geo_id = :geo_id
) permits
ORDER BY permit_num, revision_num, priority
"""


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return None if value in ("", "None") else value


def _date(value: Any) -> date | None:
    value = _clean(value)
    try:
        return date.fromisoformat(value[:10]) if value else None
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    """Parse "2,000" or "400000"; the city also stores notes like "DO NOT UPDATE ..." here."""
    value = (_clean(value) or "").replace(",", "")
    return float(value) if re.fullmatch(r"\d+(\.\d+)?", value) else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def permits_for(session: Session, address_point_id: int) -> list[Permit]:
    rows = session.execute(text(PERMITS_SQL), {"geo_id": str(address_point_id)}).mappings()
    permits = [
        Permit(
            permit_num=row["permit_num"],
            revision_num=_clean(row["revision_num"]),
            permit_type=_clean(row["permit_type"]),
            structure_type=_clean(row["structure_type"]),
            work=_clean(row["work"]),
            status=_clean(row["status"]),
            application_date=_date(row["application_date"]),
            issued_date=_date(row["issued_date"]),
            completed_date=_date(row["completed_date"]),
            description=_clean(row["description"]),
            current_use=_clean(row["current_use"]),
            proposed_use=_clean(row["proposed_use"]),
            dwelling_units_created=_int(row["dwelling_units_created"]),
            dwelling_units_lost=_int(row["dwelling_units_lost"]),
            est_construction_cost=_number(row["est_const_cost"]),
        )
        for row in rows
    ]
    return sorted(permits, key=lambda p: p.application_date or date.min, reverse=True)
