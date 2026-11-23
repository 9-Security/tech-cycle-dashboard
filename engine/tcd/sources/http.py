"""Small HTTP helper with retry/backoff. Read-only GETs only."""

from __future__ import annotations

import logging
import re
import time

import requests

log = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """Raised when a source cannot be fetched after retries."""


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def redact(text: str) -> str:
    """Remove e-mail addresses from text bound for logs or outputs."""
    return _EMAIL.sub("<redacted>", str(text))


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
        except requests.exceptions.InvalidHeader:
            # The message quotes the header value (may hold the SEC contact secret).
            raise FetchError(f"GET {url}: invalid request header (value not shown)") from None
        except requests.RequestException as exc:
            last = FetchError(redact(f"{type(exc).__name__}: {exc}"))
        if attempt < retries:
            wait = 2 ** attempt
            log.warning("retry %d/%d for %s in %ss (%s)", attempt + 1, retries, url, wait, last)
            time.sleep(wait)
    raise FetchError(redact(f"GET {url} failed after {retries + 1} attempts: {last}"))
