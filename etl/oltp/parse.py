"""Parse raw landed JSON into normalized row dicts (1NF -> 3NF).

Reads only from the raw landing zone on disk -- never the network. This is where
the flattening, string cleaning, deduplication and time parsing happen. Each
parse_* function returns rows carrying *natural* keys; surrogate FK resolution is
done later, in load.py.
"""
import json
import logging

from etl import config

log = logging.getLogger(__name__)


# --- scalar coercion helpers ----------------------------------------------
def _int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _lap_ms(v):
    """Parse a lap/session time string ('1:32.847' or '58.231') to milliseconds."""
    if not v:
        return None
    v = str(v).strip()
    if not v:
        return None
    try:
        if ":" in v:
            minutes, seconds = v.split(":")
            return int((int(minutes) * 60 + float(seconds)) * 1000)
        return int(float(v) * 1000)
    except (ValueError, TypeError):
        return None


def _ref(v):
    """Normalize a natural key: TRIM + consistent (lower) casing."""
    return v.strip().lower() if v else v


def _read_pages(cache_key: str):
    """Yield the MRData dict from every landed page file for an endpoint."""
    directory = config.RAW_DIR / cache_key
    if not directory.exists():
        log.warning("no raw data landed at %s", directory)
        return
    for page_file in sorted(directory.glob("page_*.json")):
        yield json.loads(page_file.read_text())["MRData"]


# --- cleaning helpers ------------------------------------------------------
def _clean_ref(raw, counter):
    """Normalize a natural key (TRIM + lowercase) and count when it changed."""
    ref = _ref(raw)
    if raw is not None and ref != raw:
        counter["refs_normalized"] += 1
    return ref


def _clean_text(raw, counter):
    """Trim a free-text value and count when trailing/leading whitespace was removed."""
    if raw is None:
        return None
    stripped = raw.strip()
    if stripped != raw:
        counter["text_trimmed"] += 1
    return stripped


def _log_clean(entity, raw_count, kept, counter):
    log.info("clean[%s]: %d raw -> %d unique (%d duplicate rows removed) | "
             "refs normalized %d | text trimmed %d",
             entity, raw_count, kept, raw_count - kept,
             counter["refs_normalized"], counter["text_trimmed"])


# --- reference tables ------------------------------------------------------
def parse_circuits() -> list[dict]:
    rows = {}  # keyed by circuit_ref -> deduplicated
    raw = 0
    c9n = {"refs_normalized": 0, "text_trimmed": 0}
    for mr in _read_pages("circuits"):
        for c in mr["CircuitTable"]["Circuits"]:
            raw += 1
            ref = _clean_ref(c["circuitId"], c9n)
            loc = c.get("Location", {})
            rows[ref] = dict(
                circuit_ref=ref,
                name=_clean_text(c["circuitName"], c9n),
                locality=(_clean_text(loc.get("locality"), c9n) or None),
                country=(_clean_text(loc.get("country"), c9n) or None),
                latitude=_num(loc.get("lat")),
                longitude=_num(loc.get("long")),
            )
    _log_clean("circuits", raw, len(rows), c9n)
    return list(rows.values())


def parse_drivers() -> list[dict]:
    rows = {}
    raw = 0
    c9n = {"refs_normalized": 0, "text_trimmed": 0}
    for mr in _read_pages("drivers"):
        for d in mr["DriverTable"]["Drivers"]:
            raw += 1
            ref = _clean_ref(d["driverId"], c9n)
            pn = _int(d.get("permanentNumber"))
            if pn is not None and not (0 <= pn <= 99):
                pn = None  # keep the CHECK satisfiable; a few historic values fall outside 0-99
            rows[ref] = dict(
                driver_ref=ref,
                permanent_number=pn,
                code=(d.get("code") or None),
                forename=_clean_text(d["givenName"], c9n),
                surname=_clean_text(d["familyName"], c9n),
                date_of_birth=(d.get("dateOfBirth") or None),
                nationality=(d.get("nationality") or None),
            )
    _log_clean("drivers", raw, len(rows), c9n)
    return list(rows.values())


def parse_constructors() -> list[dict]:
    rows = {}
    raw = 0
    c9n = {"refs_normalized": 0, "text_trimmed": 0}
    for mr in _read_pages("constructors"):
        for c in mr["ConstructorTable"]["Constructors"]:
            raw += 1
            ref = _clean_ref(c["constructorId"], c9n)
            rows[ref] = dict(
                constructor_ref=ref,
                name=_clean_text(c["name"], c9n),
                nationality=(c.get("nationality") or None),
            )
    _log_clean("constructors", raw, len(rows), c9n)
    return list(rows.values())


def parse_statuses() -> list[dict]:
    rows = {}  # keyed by status_text
    raw = 0
    c9n = {"refs_normalized": 0, "text_trimmed": 0}
    for mr in _read_pages("status"):
        for s in mr["StatusTable"]["Status"]:
            raw += 1
            text = _clean_text(s["status"], c9n)
            rows[text] = dict(status_code=_int(s.get("statusId")), status_text=text)
    _log_clean("statuses", raw, len(rows), c9n)
    return list(rows.values())


# --- event / transaction tables -------------------------------------------
def parse_races(seasons) -> list[dict]:
    rows = []
    for season in seasons:
        for mr in _read_pages(f"races/{season}"):
            for r in mr["RaceTable"]["Races"]:
                race_time = r.get("time")
                if race_time and race_time.endswith("Z"):
                    race_time = race_time[:-1]  # '13:00:00Z' -> '13:00:00' for a TIME column
                rows.append(dict(
                    season=int(r["season"]),
                    round=int(r["round"]),
                    race_name=r["raceName"].strip(),
                    race_date=r["date"],
                    race_time=(race_time or None),
                    # qualifying runs the day before the race; present for recent seasons only
                    qualifying_date=(r.get("Qualifying") or {}).get("date") or None,
                    circuit_ref=_ref(r["Circuit"]["circuitId"]),
                ))
    return rows


def parse_results(seasons) -> list[dict]:
    rows = []
    dnf_to_null = 0      # non-numeric position_text cleaned to a NULL finish_position
    lap_times_parsed = 0  # fastest-lap time strings converted to milliseconds
    for season in seasons:
        for mr in _read_pages(f"results/{season}"):
            for race in mr["RaceTable"]["Races"]:
                rnd = int(race["round"])
                for r in race.get("Results", []):
                    pt = r["positionText"]
                    fl = r.get("FastestLap", {})
                    if not pt.isdigit():
                        dnf_to_null += 1
                    if (fl.get("Time") or {}).get("time"):
                        lap_times_parsed += 1
                    rows.append(dict(
                        season=int(race["season"]),
                        round=rnd,
                        driver_ref=_ref(r["Driver"]["driverId"]),
                        constructor_ref=_ref(r["Constructor"]["constructorId"]),
                        status_text=r["status"].strip(),
                        car_number=_int(r.get("number")),
                        grid_position=(_int(r.get("grid")) or 0),
                        finish_position=(int(pt) if pt.isdigit() else None),  # NULL for R/D/W/E/...
                        position_text=pt,
                        position_order=_int(r.get("position")),
                        points=(_num(r.get("points")) or 0),
                        laps_completed=(_int(r.get("laps")) or 0),
                        race_time_ms=_int((r.get("Time") or {}).get("millis")),
                        fastest_lap_number=_int(fl.get("lap")),
                        fastest_lap_rank=_int(fl.get("rank")),
                        fastest_lap_time_ms=_lap_ms((fl.get("Time") or {}).get("time")),
                        fastest_lap_speed_kph=_num((fl.get("AverageSpeed") or {}).get("speed")),
                    ))
    log.info("clean[results]: %d rows | %d non-classified -> NULL finish_position | "
             "%d fastest-lap times parsed to ms", len(rows), dnf_to_null, lap_times_parsed)
    return rows


def parse_qualifying(seasons) -> list[dict]:
    rows = []
    q_times_parsed = 0  # Q1/Q2/Q3 time strings ('1:23.456') converted to milliseconds
    for season in seasons:
        for mr in _read_pages(f"qualifying/{season}"):
            for race in mr["RaceTable"]["Races"]:
                rnd = int(race["round"])
                for q in race.get("QualifyingResults", []):
                    q_times_parsed += sum(1 for k in ("Q1", "Q2", "Q3") if q.get(k))
                    rows.append(dict(
                        season=int(race["season"]),
                        round=rnd,
                        driver_ref=_ref(q["Driver"]["driverId"]),
                        constructor_ref=_ref(q["Constructor"]["constructorId"]),
                        car_number=_int(q.get("number")),
                        quali_position=_int(q.get("position")),
                        q1_ms=_lap_ms(q.get("Q1")),
                        q2_ms=_lap_ms(q.get("Q2")),
                        q3_ms=_lap_ms(q.get("Q3")),
                    ))
    log.info("clean[qualifying]: %d rows | %d Q1/Q2/Q3 time strings parsed to ms",
             len(rows), q_times_parsed)
    return rows
