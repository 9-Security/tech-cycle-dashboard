"""Archive this run's raw inputs to a PRIVATE Cloudflare R2 bucket.

Content-addressed: every raw file is stored once as blobs/<sha256>.gz, where
<sha256> is the hash of the raw bytes - the same hash the published manifests
(health.json -> raw_manifest, stocks.json, ...) already record. Each run also
writes an index runs/<run_id>-<attempt>-<scope>.json listing the
files it used. tools/restore_raw.py rebuilds a cache directory from an index.

Uses the AWS CLI (preinstalled on GitHub runners) against R2's S3 API.
Credentials come only from the environment of the workflow step:
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET.
If they are missing the script prints a notice and exits 0 (not configured).

Usage: python tools/archive_raw.py --cache .cache/raw --scope full [--run-id N --attempt N] [--feed FILE]

--feed FILE (full scope): the PRIVATE range feed (schema range-feed/2, full price
series) is uploaded as feeds/latest.json and feeds/<generated_at>.json. The
private agent range reads it to settle; the public data/feed.json has summaries only.
Exit code 1 on any upload error (the workflow step is continue-on-error and
reported by the notify job).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REQUIRED = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


def aws_env() -> dict:
    env = dict(os.environ)
    env.update({
        "AWS_ACCESS_KEY_ID": os.environ["R2_ACCESS_KEY_ID"],
        "AWS_SECRET_ACCESS_KEY": os.environ["R2_SECRET_ACCESS_KEY"],
        "AWS_DEFAULT_REGION": "auto",
        # R2 does not need the newer default integrity headers of the AWS CLI.
        "AWS_REQUEST_CHECKSUM_CALCULATION": "when_required",
        "AWS_RESPONSE_CHECKSUM_VALIDATION": "when_required",
        "AWS_PAGER": "",
    })
    return env


def endpoint() -> str:
    return f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"


def s3api(args: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(["aws", "s3api", *args, "--endpoint-url", endpoint()],
                          capture_output=True, text=True, env=env)


def exists(bucket: str, key: str, env: dict) -> bool:
    r = s3api(["head-object", "--bucket", bucket, "--key", key], env)
    if r.returncode == 0:
        return True
    if "404" in r.stderr or "Not Found" in r.stderr or "NoSuchKey" in r.stderr:
        return False
    raise RuntimeError(f"head-object {key} failed (exit {r.returncode})")


def put(bucket: str, key: str, body: Path, content_type: str, env: dict) -> None:
    r = s3api(["put-object", "--bucket", bucket, "--key", key, "--body", str(body),
               "--content-type", content_type], env)
    if r.returncode != 0:
        raise RuntimeError(f"put-object {key} failed (exit {r.returncode})")


def index_name(run_id: str, attempt: str, scope: str) -> str:
    """Deterministic, so the engine can publish it before the upload."""
    return f"runs/{run_id}-{attempt}-{scope}.json"


def collect(cache: Path) -> dict[str, dict]:
    files = {}
    for p in sorted(cache.rglob("*")):
        if p.is_file() and not p.name.endswith(".tmp"):
            data = p.read_bytes()
            files[str(p.relative_to(cache))] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    return files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=".cache/raw")
    ap.add_argument("--scope", required=True)
    ap.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", "local"))
    ap.add_argument("--attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    ap.add_argument("--feed", default=None, help="private range feed to upload (full scope)")
    args = ap.parse_args()
    missing = [k for k in REQUIRED if not os.environ.get(k)]
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if missing:
        print(f"R2 archive not configured ({len(missing)} setting(s) missing): skipped")
        if gh_out:
            with open(gh_out, "a") as fh:
                fh.write("ran=no\n")
        return 0
    if gh_out:
        with open(gh_out, "a") as fh:
            fh.write("ran=yes\n")
    bucket, env, cache = os.environ["R2_BUCKET"], aws_env(), Path(args.cache)
    files = collect(cache)
    uploaded = reused = 0
    with tempfile.TemporaryDirectory() as tmp:
        for rel, meta in files.items():
            key = f"blobs/{meta['sha256']}.gz"
            if exists(bucket, key, env):
                reused += 1
                continue
            gz = Path(tmp) / "blob.gz"
            gz.write_bytes(gzip.compress((cache / rel).read_bytes(), mtime=0))
            put(bucket, key, gz, "application/gzip", env)
            uploaded += 1
        now = datetime.now(timezone.utc)
        index_key = index_name(args.run_id, args.attempt, args.scope)
        index = {"created": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "scope": args.scope, "run_id": args.run_id,
                 "attempt": args.attempt, "blob_key": "blobs/<sha256>.gz (gzip of the raw bytes)", "files": files}
        ip = Path(tmp) / "index.json"
        ip.write_text(json.dumps(index, indent=1, sort_keys=True))
        put(bucket, index_key, ip, "application/json", env)
        if args.feed and Path(args.feed).is_file():
            fb = Path(args.feed)
            stamp = json.loads(fb.read_text()).get("generated_at", "unknown")
            put(bucket, f"feeds/{stamp}.json", fb, "application/json", env)
            put(bucket, "feeds/latest.json", fb, "application/json", env)
            print(f"R2 archive: private range feed {stamp} uploaded (feeds/latest.json)")
    print(f"R2 archive: {len(files)} files, {uploaded} uploaded, {reused} already stored; index {index_key}")
    if gh_out:
        with open(gh_out, "a") as fh:
            fh.write(f"index={index_key}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:  # message names keys only, never credentials
        print(f"R2 archive failed: {exc}", file=sys.stderr)
        sys.exit(1)
