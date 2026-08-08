"""Rate-limited Jolpica-F1 API client that lands raw JSON to disk.

The raw landing zone is the network boundary. Every response is written to
data/raw/ before anything parses it, so:
  * the parse/load stages run fully offline (the demo works with wifi off);
  * re-running never re-hits the API (a cached page is served from disk).

The cache is keyed on page *identity*, never on content: it answers "have I fetched
offset N of this endpoint before?", not "is what I fetched still correct?". That is
right for a closed season, which is immutable, and wrong for anything that grows --
the reference endpoints and the season currently being run. Callers say so with
`refresh=True`, which refetches a page it already holds and degrades to the cached
copy when the network is unavailable.

Rate limiting is enforced client-side with a dual token bucket (burst + sustained)
rather than reacting to HTTP 429. Transient failures (429 / 5xx / network) retry
with exponential backoff.
"""
import json
import logging
import time
from collections import deque
from pathlib import Path

import requests

from etl import config

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RateLimiter:
    """Dual token bucket: at most `burst` req/sec AND `sustained` req/hour."""

    def __init__(self, burst: int = config.BURST_RATE, sustained: int = config.SUSTAINED_RATE):
        self.burst = burst
        self.sustained = sustained
        self._sec: deque[float] = deque()    # request timestamps in the last 1s
        self._hour: deque[float] = deque()   # request timestamps in the last 3600s

    def acquire(self) -> None:
        """Block until a request slot is free in both buckets, then reserve it."""
        while True:
            now = time.monotonic()
            while self._sec and now - self._sec[0] >= 1.0:
                self._sec.popleft()
            while self._hour and now - self._hour[0] >= 3600.0:
                self._hour.popleft()

            if len(self._sec) < self.burst and len(self._hour) < self.sustained:
                self._sec.append(now)
                self._hour.append(now)
                return

            waits = []
            if len(self._sec) >= self.burst:
                waits.append(1.0 - (now - self._sec[0]))
            if len(self._hour) >= self.sustained:
                waits.append(3600.0 - (now - self._hour[0]))
            time.sleep(max(0.01, min(waits)))


class JolpicaClient:
    def __init__(
        self,
        base_url: str = config.API_BASE_URL,
        raw_dir: Path = config.RAW_DIR,
        page_size: int = config.PAGE_SIZE,
        max_retries: int = 5,
    ):
        self.base_url = base_url.rstrip("/")
        self.raw_dir = Path(raw_dir)
        self.page_size = page_size
        self.max_retries = max_retries
        self.limiter = RateLimiter()
        self.session = requests.Session()

    # -- low level ----------------------------------------------------------
    def _request_with_retry(self, url: str, params: dict) -> dict:
        backoff = 1.0
        for attempt in range(1, self.max_retries + 1):
            self.limiter.acquire()
            resp = None
            try:
                resp = self.session.get(url, params=params, timeout=30)
            except requests.RequestException as exc:
                log.warning("network error on %s (%s), attempt %d/%d", url, exc, attempt, self.max_retries)

            if resp is not None:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code not in _RETRYABLE_STATUS:
                    resp.raise_for_status()
                log.warning("HTTP %s on %s, attempt %d/%d", resp.status_code, url, attempt, self.max_retries)

            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        raise RuntimeError(f"exhausted retries for {url} params={params}")

    def _fetch_page(self, path: str, offset: int, cache_key: str, refresh: bool = False) -> dict:
        """Return one page's MRData, landing it to disk first (or serving the cache).

        `refresh` refetches a page already on disk and overwrites it. If that request
        fails we fall back to the cached copy rather than raising, so an offline run
        still succeeds -- refreshing is best-effort, and the warning says which it was.
        """
        cache_file = self.raw_dir / cache_key / f"page_{offset}.json"
        cached = cache_file.exists()
        if cached and not refresh:
            log.debug("cache hit: %s", cache_file)
            return json.loads(cache_file.read_text())["MRData"]

        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            payload = self._request_with_retry(url, {"limit": self.page_size, "offset": offset})
        except (requests.RequestException, RuntimeError):
            if not cached:
                raise
            log.warning("refresh failed for %s, serving the cached page", cache_file)
            return json.loads(cache_file.read_text())["MRData"]

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload))
        return payload["MRData"]

    # -- public -------------------------------------------------------------
    def paginate(self, path: str, cache_key: str, refresh: bool = False):
        """Yield every MRData page for an endpoint, following the `total` field.

        Advances the offset by the *effective* page size the API reports (`limit`),
        not by the requested size -- Jolpica caps pages at 100 regardless of the
        requested limit, so stepping by the request size would skip rows.

        `refresh` matters most here, because `total` is read off page 0: served from
        cache it is frozen at whatever it was when that page was first landed, so the
        loop stops short of any row added since and never even requests the page that
        would hold it. Refetching page 0 is what lets the loop see the new total.
        """
        offset = 0
        while True:
            mrdata = self._fetch_page(path, offset, cache_key, refresh=refresh)
            yield mrdata
            total = int(mrdata.get("total", 0))
            step = int(mrdata.get("limit") or self.page_size) or self.page_size
            offset += step
            if offset >= total:
                break

    def land(self, path: str, cache_key: str, refresh: bool = False) -> int:
        """Land all pages of an endpoint to disk. Returns the page count."""
        pages = sum(1 for _ in self.paginate(path, cache_key, refresh=refresh))
        log.info("landed %-22s -> data/raw/%s (%d page[s])%s", path, cache_key, pages,
                 " [refreshed]" if refresh else "")
        return pages
