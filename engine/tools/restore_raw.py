"""Rebuild a raw cache directory from an R2 archive index (see archive_raw.py).

    python tools/restore_raw.py --index runs/123-1-full.json --out /tmp/raw
    python -m tcd refresh --offline --allow-stale --cache /tmp/raw --out /tmp/out

Every file is checked against its SHA-256 before it is written. Needs the same
R2_* environment variables as archive_raw.py (read access is enough).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from archive_raw import REQUIRED, aws_env, s3api  # noqa: E402


def get(bucket: str, key: str, dest: Path, env: dict) -> None:
    r = s3api(["get-object", "--bucket", bucket, "--key", key, str(dest)], env)
    if r.returncode != 0:
        raise RuntimeError(f"get-object {key} failed (exit {r.returncode})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, help="runs/<run_id>-<attempt>-<scope>.json (health.json -> raw_archive.index)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    if missing:
        print(f"missing settings: {', '.join(missing)}", file=sys.stderr)
        return 2
    bucket, env, out = os.environ["R2_BUCKET"], aws_env(), Path(args.out)
    with tempfile.TemporaryDirectory() as tmp:
        ip = Path(tmp) / "index.json"
        get(bucket, args.index, ip, env)
        index = json.loads(ip.read_text())
        for rel, meta in index["files"].items():
            gz = Path(tmp) / "blob.gz"
            get(bucket, f"blobs/{meta['sha256']}.gz", gz, env)
            data = gzip.decompress(gz.read_bytes())
            if hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise RuntimeError(f"hash mismatch for {rel}")
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    print(f"restored {len(index['files'])} files to {out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"restore failed: {exc}", file=sys.stderr)
        sys.exit(1)
