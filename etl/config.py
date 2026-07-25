"""Central configuration, driven by environment variables (.env).

Kept import-safe and side-effect-free (beyond load_dotenv) so it can be reused
unchanged when the pipeline is later wrapped in Airflow tasks.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"          # the network boundary: JSON landed here, nothing downstream hits the API
LOG_DIR = Path(os.getenv("LOG_DIR", BASE_DIR / "logs"))

# --- API -------------------------------------------------------------------
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.jolpi.ca/ergast/f1")

# Client-side rate limits (dual token bucket). We enforce these ourselves rather
# than reacting to HTTP 429 -- a 429 means we were already rude to a free service.
BURST_RATE = 4          # requests / second
SUSTAINED_RATE = 500    # requests / hour
# NOTE: the spec claims a 1000-row page size, but the live Jolpica API caps pages at 100
# (it silently returns 100 even if you ask for more). We request 100 and paginate by the
# effective `limit` the response reports. A full 11-season backfill is ~110 requests --
# still comfortably inside the 500/hour quota, just not the ~40 the spec assumed.
PAGE_SIZE = 100

# --- Backfill scope --------------------------------------------------------
SEASON_START = int(os.getenv("SEASON_START", "2015"))
SEASON_END = int(os.getenv("SEASON_END", "2026"))  # 2026 in progress -> real new races for the incremental pipeline


def seasons():
    """Inclusive season range for the full backfill."""
    return range(SEASON_START, SEASON_END + 1)


def prod_dsn():
    """psycopg2 connection kwargs for the OLTP database (f1_prod)."""
    return dict(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("PROD_DB", "f1_prod"),
        user=os.getenv("POSTGRES_USER", "f1"),
        password=os.getenv("POSTGRES_PASSWORD", "f1"),
    )
