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


# --- reference tables ------------------------------------------------------
def parse_circuits() -> list[dict]:
    rows = {}  # keyed by circuit_ref -> deduplicated
    for mr in _read_pages("circuits"):
        for c in mr["CircuitTable"]["Circuits"]:
            ref = _ref(c["circuitId"])
            loc = c.get("Location", {})
            rows[ref] = dict(
                circuit_ref=ref,
                name=c["circuitName"].strip(),
                locality=(loc.get("locality") or "").strip() or None,
                country=(loc.get("country") or "").strip() or None,
                latitude=_num(loc.get("lat")),
                longitude=_num(loc.get("long")),
            )
    return list(rows.values())


def parse_drivers() -> list[dict]:
    rows = {}
    for mr in _read_pages("drivers"):
        for d in mr["DriverTable"]["Drivers"]:
            ref = _ref(d["driverId"])
            pn = _int(d.get("permanentNumber"))
            if pn is not None and not (0 <= pn <= 99):
                pn = None  # keep the CHECK satisfiable; a few historic values fall outside 0-99
            rows[ref] = dict(
                driver_ref=ref,
                permanent_number=pn,
                code=(d.get("code") or None),
                forename=d["givenName"].strip(),
                surname=d["familyName"].strip(),
                date_of_birth=(d.get("dateOfBirth") or None),
                nationality=(d.get("nationality") or None),
            )
    return list(rows.values())


def parse_constructors() -> list[dict]:
    rows = {}
    for mr in _read_pages("constructors"):
        for c in mr["ConstructorTable"]["Constructors"]:
            ref = _ref(c["constructorId"])
            rows[ref] = dict(
                constructor_ref=ref,
                name=c["name"].strip(),
                nationality=(c.get("nationality") or None),
            )
    return list(rows.values())


def parse_statuses() -> list[dict]:
    rows = {}  # keyed by status_text
    for mr in _read_pages("status"):
        for s in mr["StatusTable"]["Status"]:
            text = s["status"].strip()
            rows[text] = dict(status_code=_int(s.get("statusId")), status_text=text)
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
    for season in seasons:
        for mr in _read_pages(f"results/{season}"):
            for race in mr["RaceTable"]["Races"]:
                rnd = int(race["round"])
                for r in race.get("Results", []):
                    pt = r["positionText"]
                    fl = r.get("FastestLap", {})
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
    return rows


def parse_qualifying(seasons) -> list[dict]:
    rows = []
    for season in seasons:
        for mr in _read_pages(f"qualifying/{season}"):
            for race in mr["RaceTable"]["Races"]:
                rnd = int(race["round"])
                for q in race.get("QualifyingResults", []):
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
    return rows
