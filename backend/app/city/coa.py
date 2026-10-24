"""Committee of Adjustment applications: a typed, geocoded table from the raw open data.

`./start.sh city-data` has the importer merge the city's "Committee of Adjustment
Applications" files (active, closed since 2017, one file per year back to 2001)
into `city.coa_raw`, all text. This module turns that into `city.coa_applications`:

1. One row per application (SYS_ID), dates parsed, decision and appeal outcome
   normalized to a short vocabulary (`decision`, `appeal`, `outcome`).
2. A point: the city address point with the same street number, name, type and
   direction. The open data has no coordinates, so this is how an application
   becomes "near this lot".

Run with `python -m app.city.coa` (the start script does it after the importer,
and the backend does it on start with --if-needed). The open data has no
variance table; the hearing agenda PDFs are item lists only, and the per-file
notices on the Application Information Centre stay up for about 90 days.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import Connection, text

from app.city.address import AP_NAME, normalize_name

TABLE = "city.coa_applications"

DDL = f"""
CREATE TABLE {TABLE} (
    sys_id            text PRIMARY KEY,
    source            text NOT NULL,           -- active | closed (which open-data file)
    application_type  text,                    -- MV (minor variance) | CO (consent)
    reference_file    text,                    -- e.g. A0498/26TEY
    planning_district text,
    ward              text,
    street_num        text,
    street_name       text,
    street_type       text,
    street_direction  text,
    postal            text,
    street_num_norm   text,                    -- "12 A" -> "12A", for the address point join
    street_num_int    integer,                 -- leading digits of the street number
    street_name_norm  text,                    -- app.city.address.normalize_name
    sub_type          text,
    work_type         text,                    -- R Addition | New R Building | Sever Lot | ...
    zoning_review     text,
    zoning_designation text,
    description       text,
    in_date           date,
    hearing_date      date,
    final_date        date,
    decision_raw      text,
    decision          text NOT NULL,           -- see normalize_decision
    appeal_raw        text,
    appeal            text,                    -- see normalize_appeal
    appeal_body       text,                    -- OMB | TLAB | NULL
    status            text,
    outcome           text NOT NULL,           -- approved | refused | withdrawn | deferred | pending | unknown
    lots_created      text,
    address_point_id  bigint,
    address_full      text,
    geom              geometry(Point, 4326)
)
"""

INDEXES = [
    f"CREATE INDEX coa_applications_geog ON {TABLE} USING GIST ((geom::geography))",
    f"CREATE INDEX coa_applications_work_type ON {TABLE} (work_type)",
    f"CREATE INDEX coa_applications_hearing_date ON {TABLE} (hearing_date)",
    # Name-only index for the range match on lo_num/hi_num (the number+name index
    # from app.city.match serves the exact match).
    f"CREATE INDEX IF NOT EXISTS address_points_name ON city.address_points (({AP_NAME}))",
]

INSERT = text(f"""
INSERT INTO {TABLE} (
    sys_id, source, application_type, reference_file, planning_district, ward,
    street_num, street_name, street_type, street_direction, postal,
    street_num_norm, street_num_int, street_name_norm,
    sub_type, work_type, zoning_review, zoning_designation, description,
    in_date, hearing_date, final_date,
    decision_raw, decision, appeal_raw, appeal, appeal_body, status, outcome, lots_created
) VALUES (
    :sys_id, :source, :application_type, :reference_file, :planning_district, :ward,
    :street_num, :street_name, :street_type, :street_direction, :postal,
    :street_num_norm, :street_num_int, :street_name_norm,
    :sub_type, :work_type, :zoning_review, :zoning_designation, :description,
    :in_date, :hearing_date, :final_date,
    :decision_raw, :decision, :appeal_raw, :appeal, :appeal_body, :status, :outcome, :lots_created
)
""")

# Pass 1: the exact street number ("12A", "3345-3347"). Pass 2, for the rest: the
# leading number falls in an address point's lo_num..hi_num range. Both require
# the street name, and the type and direction when both sides have one. There is
# no pin to break ties with, so a candidate on a different street is never taken.
_GEOCODE = """
WITH cand AS (
    -- The importer promotes every layer to multi-geometry; an address point has 1 part.
    SELECT DISTINCT ON (c.sys_id) c.sys_id, a.address_point_id, a.address_full, ST_GeometryN(a.geom, 1) AS geom
    FROM {table} c
    JOIN city.address_points a
      ON {ap_name} = c.street_name_norm
     AND {number_match}
     AND (c.street_type IS NULL OR a.linear_name_type IS NULL OR upper(a.linear_name_type) = c.street_type)
     AND (c.street_direction IS NULL OR a.linear_name_dir IS NULL OR a.linear_name_dir = c.street_direction)
    WHERE c.geom IS NULL AND c.street_name_norm IS NOT NULL
    ORDER BY c.sys_id,
             (upper(a.linear_name_type) = c.street_type) DESC NULLS LAST,
             (a.linear_name_dir = c.street_direction) DESC NULLS LAST,
             a.address_point_id
)
UPDATE {table} c
   SET address_point_id = cand.address_point_id, address_full = cand.address_full, geom = cand.geom
  FROM cand
 WHERE cand.sys_id = c.sys_id
"""
GEOCODE_EXACT = _GEOCODE.format(table=TABLE, ap_name=AP_NAME, number_match="upper(a.address_number) = c.street_num_norm")
GEOCODE_RANGE = _GEOCODE.format(
    table=TABLE,
    ap_name=AP_NAME,
    number_match="c.street_num_int IS NOT NULL AND a.lo_num <= c.street_num_int AND COALESCE(a.hi_num, a.lo_num) >= c.street_num_int",
)


# -- normalization (pure) -----------------------------------------------------

APPEAL_STATUSES = {"TLAB APPEAL", "OMB APPEAL", "APPEALED"}
CLOSED_STATUSES = {"CLOSED", "FINAL AND BINDING"}
DROPPED_STATUSES = {"CANCELLED", "APPLICATION WITHDRAWN"}


def clean(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return None if s in ("", "None") else s


MIN_YEAR, MAX_YEAR = 1990, date.today().year + 2  # the data has typos like 0227-11-21 and 3008-12-03


def parse_date(value: object) -> date | None:
    """'2026-09-02', '2026-07-08T00:00:00' or 'Jun 12, 2009' (the pre-2010 files); None for a typo year."""
    s = clean(value)
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
        return parsed if MIN_YEAR <= parsed.year <= MAX_YEAR else None
    return None


def normalize_decision(raw: str | None, status: str | None) -> str:
    """The committee's decision as one of a short vocabulary.

    approved | approved_with_conditions | approved_in_part | refused | withdrawn |
    deferred | pending | unknown. The raw text has 40+ spellings ("Approved wih
    Conditions", "conditional approval", "Not Granted"); the status column fills in
    when the decision is blank.
    """
    d = (raw or "").strip().lower()
    st = (status or "").strip().upper()
    if d:
        if "partial" in d or "in part" in d:
            return "approved_in_part"
        if "condition" in d:
            return "approved_with_conditions"
        if d.startswith(("approved", "granted", "approve", "allowed")):
            return "approved"
        if d.startswith(("refused", "not granted", "denied", "not approved")):
            return "refused"
        if "withdraw" in d or "cancel" in d:
            return "withdrawn"
        if "defer" in d or "postpone" in d or "adjourn" in d:
            return "deferred"
        return "unknown"
    if st in DROPPED_STATUSES:
        return "withdrawn"
    if st in CLOSED_STATUSES:
        return "unknown"
    if st == "DEFERRED" or st == "POSTPONED":
        return "deferred"
    if st == "REFUSED":
        return "refused"
    if st.startswith("APPROVED") or st == "CONDITIONAL CONSENT":
        return "approved_with_conditions" if "CONDITION" in st else "approved"
    return "pending"


def normalize_appeal(raw: str | None, status: str | None) -> tuple[str | None, str | None]:
    """(appeal result, appeal body).

    approved | refused: the board decided the application itself.
    dismissed: the appeal failed or was withdrawn, so the committee's decision stands.
    pending: the status says an appeal is open. unknown: text we cannot read.
    None: no appeal on record.
    """
    a = (raw or "").strip().lower()
    st = (status or "").strip().upper()
    body = "TLAB" if "tlab" in a or "TLAB" in st else "OMB" if "omb" in a or "OMB" in st else None
    if a:
        if "dismiss" in a or "withdraw" in a or "upheld" in a:
            return "dismissed", body
        if "approved" in a or "allowed" in a or "granted" in a:
            return "approved", body
        if "refused" in a or "denied" in a:
            return "refused", body
        return "unknown", body
    if st in APPEAL_STATUSES:
        return "pending", body
    return None, None


def outcome_of(decision: str, appeal: str | None) -> str:
    """What finally happened to the application, in 6 words."""
    if appeal in ("approved", "refused"):
        return appeal
    if appeal == "pending":
        return "pending"
    if decision.startswith("approved"):
        return "approved"
    return decision


_LEADING_INT = re.compile(r"^\s*(\d+)")


def normalize_number(raw: str | None) -> tuple[str | None, int | None]:
    """'12 A' -> ('12A', 12); '3345-3347' -> ('3345-3347', 3345); '' -> (None, None)."""
    s = clean(raw)
    if not s:
        return None, None
    norm = re.sub(r"\s+", "", s.upper())
    m = _LEADING_INT.match(s)
    return norm, int(m.group(1)) if m else None


@dataclass
class Application:
    sys_id: str
    source: str
    application_type: str | None
    reference_file: str | None
    planning_district: str | None
    ward: str | None
    street_num: str | None
    street_name: str | None
    street_type: str | None
    street_direction: str | None
    postal: str | None
    street_num_norm: str | None
    street_num_int: int | None
    street_name_norm: str | None
    sub_type: str | None
    work_type: str | None
    zoning_review: str | None
    zoning_designation: str | None
    description: str | None
    in_date: date | None
    hearing_date: date | None
    final_date: date | None
    decision_raw: str | None
    decision: str
    appeal_raw: str | None
    appeal: str | None
    appeal_body: str | None
    status: str | None
    outcome: str
    lots_created: str | None


def normalize_row(row: dict[str, object]) -> Application | None:
    """One `city.coa_raw` row (lower snake case columns) -> Application, or None without a SYS_ID."""
    sys_id = clean(row.get("sys_id"))
    if not sys_id:
        return None
    status = clean(row.get("statusdesc"))
    decision_raw = clean(row.get("c_of_a_descision"))
    appeal_raw = clean(row.get("omb_descision"))
    decision = normalize_decision(decision_raw, status)
    appeal, body = normalize_appeal(appeal_raw, status)
    num_norm, num_int = normalize_number(clean(row.get("street_num")))
    name = clean(row.get("street_name"))
    street_type = clean(row.get("street_type"))
    direction = clean(row.get("street_direction"))
    # The yearly files have WARD; the newer files have WARD_NAME and WARD_NUMBER.
    ward = clean(row.get("ward"))
    if not ward:
        ward_name, ward_number = clean(row.get("ward_name")), clean(row.get("ward_number"))
        ward = f"{ward_name} ({ward_number})" if ward_name and ward_number else ward_name or ward_number
    return Application(
        sys_id=sys_id,
        source=clean(row.get("source")) or "closed",
        application_type=clean(row.get("application_type")),
        reference_file=clean(row.get("reference_file")),
        planning_district=clean(row.get("planning_district")),
        ward=ward,
        street_num=clean(row.get("street_num")),
        street_name=name,
        street_type=street_type.upper() if street_type else None,
        street_direction=direction.upper() if direction else None,
        postal=clean(row.get("postal")),
        street_num_norm=num_norm,
        street_num_int=num_int,
        street_name_norm=normalize_name(name) if name else None,
        sub_type=clean(row.get("sub_type")),
        work_type=clean(row.get("work_type")),
        zoning_review=clean(row.get("zoning_review")),
        zoning_designation=clean(row.get("zoning_designation")),
        description=clean(row.get("description")),
        in_date=parse_date(row.get("in_date")),
        hearing_date=parse_date(row.get("hearing_date")),
        final_date=parse_date(row.get("finaldate")),
        decision_raw=decision_raw,
        decision=decision,
        appeal_raw=appeal_raw,
        appeal=appeal,
        appeal_body=body,
        status=status,
        outcome=outcome_of(decision, appeal),
        lots_created=clean(row.get("number_of_lots_created")),
    )


def dedupe(apps: list[Application]) -> list[Application]:
    """One row per SYS_ID; a decided row beats an undecided one, then the later final date."""
    best: dict[str, Application] = {}
    for app in apps:
        cur = best.get(app.sys_id)
        if cur is None or _rank(app) > _rank(cur):
            best[app.sys_id] = app
    return list(best.values())


def _rank(app: Application) -> tuple[int, date]:
    return (0 if app.outcome in ("pending", "unknown") else 1, app.final_date or app.hearing_date or date.min)


# -- database -----------------------------------------------------------------


def raw_loaded(conn: Connection) -> bool:
    return bool(conn.scalar(text("SELECT to_regclass('city.coa_raw') IS NOT NULL")))


def loaded(conn: Connection) -> bool:
    return bool(conn.scalar(text(f"SELECT to_regclass('{TABLE}') IS NOT NULL")))


def rebuild(conn: Connection) -> dict[str, int]:
    rows = conn.execute(text("SELECT * FROM city.coa_raw")).mappings()
    apps = dedupe([a for r in rows if (a := normalize_row(dict(r)))])

    conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
    conn.execute(text(DDL))
    for start in range(0, len(apps), 2000):
        conn.execute(INSERT, [vars(a) for a in apps[start : start + 2000]])
    for statement in INDEXES:
        conn.execute(text(statement))

    exact = conn.execute(text(GEOCODE_EXACT)).rowcount
    ranged = conn.execute(text(GEOCODE_RANGE)).rowcount
    return {"applications": len(apps), "geocoded_exact": exact, "geocoded_range": ranged}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--if-needed",
        action="store_true",
        help="only run when city.coa_raw is loaded and city.coa_applications does not exist yet",
    )
    args = parser.parse_args()

    from app.db import engine

    with engine.begin() as conn:
        if not raw_loaded(conn):
            print("coa: no Committee of Adjustment data loaded, skipping (run ./start.sh city-data)")
            return
        if args.if_needed and loaded(conn):
            return
        stats = rebuild(conn)
        geocoded = stats["geocoded_exact"] + stats["geocoded_range"]
        print(
            f"coa: {stats['applications']} applications, {geocoded} placed on a city address point "
            f"({stats['geocoded_exact']} exact, {stats['geocoded_range']} by number range)"
        )


if __name__ == "__main__":
    main()
