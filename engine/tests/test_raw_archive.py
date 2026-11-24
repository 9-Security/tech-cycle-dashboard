import gzip
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"

STUB = r'''#!/usr/bin/env python3
import os, shutil, sys
from pathlib import Path
store = Path(os.environ["STUB_STORE"])
a = sys.argv[1:]
op = a[1]
def val(flag):
    return a[a.index(flag) + 1]
key = val("--key")
obj = store / key
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(op + " " + key + "\n")
if op == "head-object":
    if obj.exists():
        sys.exit(0)
    sys.stderr.write("An error occurred (404) when calling the HeadObject operation: Not Found\n")
    sys.exit(254)
if op == "put-object":
    obj.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(val("--body"), obj)
    sys.exit(0)
if op == "get-object":
    if not obj.exists():
        sys.exit(254)
    shutil.copy(obj, [x for x in a[2:] if not x.startswith("--")][-2])
    sys.exit(0)
sys.exit(2)
'''


def _env(tmp_path, configured=True):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    aws = bin_dir / "aws"
    aws.write_text(STUB)
    aws.chmod(aws.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_STORE": str(tmp_path / "store"),
           "STUB_LOG": str(tmp_path / "log"), "GITHUB_OUTPUT": str(tmp_path / "gh_out")}
    for k in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        env.pop(k, None)
    if configured:
        env.update(R2_ACCOUNT_ID="acct", R2_ACCESS_KEY_ID="id", R2_SECRET_ACCESS_KEY="secret", R2_BUCKET="b")
    return env


def _cache(tmp_path):
    c = tmp_path / "cache"
    (c / "official").mkdir(parents=True)
    (c / "yahoo_X.json").write_text('{"p": 1}')
    (c / "official" / "twse_1.json").write_text('{"q": 2}')
    (c / "dup.json").write_text('{"p": 1}')            # same content as yahoo_X.json
    return c


def _run(script, args, env):
    return subprocess.run([sys.executable, str(TOOLS / script), *args], capture_output=True, text=True, env=env)


def test_not_configured_is_a_skip(tmp_path):
    env = _env(tmp_path, configured=False)
    r = _run("archive_raw.py", ["--cache", str(_cache(tmp_path)), "--scope", "full"], env)
    assert r.returncode == 0 and "skipped" in r.stdout
    assert (tmp_path / "gh_out").read_text().strip() == "ran=no"


def test_archive_dedups_and_restore_round_trips(tmp_path):
    env = _env(tmp_path)
    cache = _cache(tmp_path)
    r = _run("archive_raw.py", ["--cache", str(cache), "--scope", "full", "--run-id", "7", "--attempt", "1"], env)
    assert r.returncode == 0, r.stderr
    blobs = list((tmp_path / "store" / "blobs").iterdir())
    assert len(blobs) == 2                               # duplicate content stored once
    h = hashlib.sha256(b'{"p": 1}').hexdigest()
    assert gzip.decompress((tmp_path / "store" / "blobs" / f"{h}.gz").read_bytes()) == b'{"p": 1}'
    index = json.loads((tmp_path / "store" / "runs" / "7-1-full.json").read_text())
    assert set(index["files"]) == {"yahoo_X.json", "dup.json", "official/twse_1.json"}
    # second run: nothing new to upload
    (tmp_path / "log").write_text("")
    _run("archive_raw.py", ["--cache", str(cache), "--scope", "full", "--run-id", "8", "--attempt", "1"], env)
    assert "put-object blobs/" not in (tmp_path / "log").read_text()
    out = tmp_path / "restored"
    r = _run("restore_raw.py", ["--index", "runs/7-1-full.json", "--out", str(out)], env)
    assert r.returncode == 0, r.stderr
    assert (out / "official" / "twse_1.json").read_text() == '{"q": 2}'
    assert "secret" not in r.stdout + r.stderr


def test_restore_rejects_a_tampered_blob(tmp_path):
    env = _env(tmp_path)
    _run("archive_raw.py", ["--cache", str(_cache(tmp_path)), "--scope", "tw", "--run-id", "9"], env)
    h = hashlib.sha256(b'{"q": 2}').hexdigest()
    (tmp_path / "store" / "blobs" / f"{h}.gz").write_bytes(gzip.compress(b'{"q": 3}'))
    r = _run("restore_raw.py", ["--index", "runs/9-1-tw.json", "--out", str(tmp_path / "o")], env)
    assert r.returncode == 1 and "hash mismatch" in r.stderr


def test_private_range_feed_is_uploaded(tmp_path):
    env = _env(tmp_path)
    f = tmp_path / "full.json"
    f.write_text('{"schema": "range-feed/2", "generated_at": "20261124T221500Z"}')
    r = _run("archive_raw.py", ["--cache", str(_cache(tmp_path)), "--scope", "full", "--feed", str(f)], env)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "store" / "feeds" / "latest.json").read_text() == f.read_text()
    assert (tmp_path / "store" / "feeds" / "20261124T221500Z.json").exists()
    # a missing feed file (e.g. Taiwan-only run) is simply skipped
    r = _run("archive_raw.py", ["--cache", str(_cache(tmp_path / "x")), "--scope", "tw", "--feed", str(tmp_path / "no.json")], env)
    assert r.returncode == 0, r.stderr
