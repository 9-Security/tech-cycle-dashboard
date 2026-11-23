"""Pre-commit validation of the published data/ directory (run by the workflow).

Checks, failing the job (nothing is committed or deployed) on any violation:
  1. every data/**/*.json parses as strict JSON (no NaN / Infinity tokens);
  2. every data/**/*.csv parses with a consistent column count;
  3. the forecast ledger is append-only against git revision --base-ref: the
     committed file must be a byte prefix of the new one;
  4. no e-mail address appears anywhere in data/ (last line of defence for the
     SEC contact secret, which must never be published).

Usage: python tools/validate_data.py --data ../data [--base-ref HEAD]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

LEDGERS = ("forecasts/stocks_ledger.csv", "forecasts/market_ledger.csv")
EMAIL = re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def _reject_constant(name: str):
    raise ValueError(f"non-standard JSON constant {name}")


def check_json(path: Path) -> str | None:
    try:
        json.loads(path.read_text(encoding="utf-8"), parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        return f"{path}: invalid JSON ({exc})"
    return None


def check_csv(path: Path) -> str | None:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
    except (csv.Error, UnicodeDecodeError) as exc:
        return f"{path}: invalid CSV ({exc})"
    if rows:
        width = len(rows[0])
        bad = [i + 1 for i, r in enumerate(rows) if len(r) != width]
        if bad:
            return f"{path}: {len(bad)} rows with a column count different from the header (first: line {bad[0]})"
    return None


def committed_bytes(repo_root: Path, ref: str, rel: str) -> bytes | None:
    r = subprocess.run(["git", "-C", str(repo_root), "show", f"{ref}:{rel}"], capture_output=True)
    return r.stdout if r.returncode == 0 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../data")
    ap.add_argument("--base-ref", default="HEAD", help="git revision holding the previously committed data")
    args = ap.parse_args()
    data = Path(args.data).resolve()
    errors: list[str] = []

    for p in sorted(data.rglob("*.json")):
        if (e := check_json(p)):
            errors.append(e)
    for p in sorted(data.rglob("*.csv")):
        if (e := check_csv(p)):
            errors.append(e)

    for name in LEDGERS:
        ledger = data / name
        rel = str(Path(data.name) / name)
        old = committed_bytes(data.parent, args.base_ref, rel)
        if old is not None and (not ledger.exists() or not ledger.read_bytes().startswith(old)):
            errors.append(f"{ledger}: not append-only against {args.base_ref} (existing rows changed or removed)")

    for p in sorted(data.rglob("*")):
        if p.is_file() and EMAIL.search(p.read_bytes()):
            errors.append(f"{p.relative_to(data.parent)}: contains an e-mail address (value not printed)")

    for e in errors:
        print("ERROR", e)
    print(f"validate_data: {len(errors)} problem(s) in {data}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
