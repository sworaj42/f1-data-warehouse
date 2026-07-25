"""Logging setup: writes to both a timestamped file under logs/ and the console.

Call setup_logging() once at the top of a script. Every ETL stage then logs row
counts and per-stage timings through the standard logging module.
"""
import logging
import sys
from datetime import datetime

from etl import config

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(name: str = "f1_etl", level: int = logging.INFO):
    """Configure the root logger. Returns the path of the log file created."""
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = config.LOG_DIR / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.log"

    formatter = logging.Formatter(_FMT)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()  # idempotent: avoid duplicate handlers on repeated calls

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    logging.getLogger(__name__).info("logging to %s", log_file)
    return log_file
