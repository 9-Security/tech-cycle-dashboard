"""Raw-data store: every downloaded byte is written to disk and hashed.

The manifest (url, sha256, size, fetched_at) is exported with each run so
any dashboard number can be traced back to the exact raw inputs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import http

log = logging.getLogger(__name__)


@dataclass
class RawStore:
    root: Path
    offline: bool = False
    timeout: float = 60.0
    retries: int = 4
    manifest: dict[str, dict] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def get(self, name: str, url: str, *, headers: dict | None = None, params: dict | None = None) -> bytes:
        path = self.root / name
        if self.offline:
            if not path.exists():
                raise http.FetchError(f"offline mode: missing cached raw file {path}")
            data = path.read_bytes()
            fetched_at = self._cached_meta(name).get("fetched_at", "cache")
        else:
            resp = http.get(url, headers=headers, params=params, timeout=self.timeout, retries=self.retries)
            data = resp.content
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
            fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        from urllib.parse import urlencode
        self.manifest[name] = {
            "url": url + ("?" + urlencode(params) if params else ""),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "fetched_at": fetched_at,
        }
        return data

    def _cached_meta(self, name: str) -> dict:
        mpath = self.root / "manifest.json"
        if mpath.exists():
            try:
                return json.loads(mpath.read_text()).get(name, {})
            except json.JSONDecodeError:
                return {}
        return {}

    def save_manifest(self) -> Path:
        mpath = self.root / "manifest.json"
        if not self.offline:
            mpath.write_text(json.dumps(self.manifest, indent=1, sort_keys=True))
        return mpath
