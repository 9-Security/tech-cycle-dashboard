"""Small HTTP helper with retry/backoff. Read-only GETs only."""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched after retries."""


def get(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    timeout: float = 60.0,
    retries: int = 4,
) -> requests.Response:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp
            # 4xx other than 429 will not get better by retrying.
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                raise FetchError(f"GET {url} -> HTTP {resp.status_code}")
            last = FetchError(f"GET {url} -> HTTP {resp.status_code}")
        except requests.RequestException as exc:
            last = exc
        if attempt < retries:
            wait = 2 ** attempt
            log.warning("retry %d/%d for %s in %ss (%s)", attempt + 1, retries, url, wait, last)
            time.sleep(wait)
    raise FetchError(f"GET {url} failed after {retries + 1} attempts: {last}")
