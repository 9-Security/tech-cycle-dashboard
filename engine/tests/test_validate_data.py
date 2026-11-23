import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "tools" / "validate_data.py"


def _run(data: Path, ref: str = "HEAD") -> int:
    return subprocess.run([sys.executable, str(TOOL), "--data", str(data), "--base-ref", ref], capture_output=True).returncode


def _repo(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    (data / "forecasts").mkdir(parents=True)
    (data / "a.json").write_text('{"x": 1}')
    (data / "forecasts" / "stocks_ledger.csv").write_text("k,v\n1,a\n")
    for cmd in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t.invalid", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", "-C", str(tmp_path), *cmd], check=True, capture_output=True)
    return data


def test_valid_data_and_append_pass(tmp_path):
    data = _repo(tmp_path)
    (data / "forecasts" / "stocks_ledger.csv").write_text("k,v\n1,a\n2,b\n")
    assert _run(data) == 0


def test_rewritten_ledger_row_fails(tmp_path):
    data = _repo(tmp_path)
    (data / "forecasts" / "stocks_ledger.csv").write_text("k,v\n1,CHANGED\n2,b\n")
    assert _run(data) == 1


def test_nan_json_and_email_fail(tmp_path):
    data = _repo(tmp_path)
    (data / "a.json").write_text('{"x": NaN}')
    assert _run(data) == 1
    (data / "a.json").write_text('{"ua": "Org someone@example.com"}')
    assert _run(data) == 1


def test_unresolvable_base_ref_fails(tmp_path):
    data = _repo(tmp_path)
    assert _run(data, "NOSUCHREF") == 1
