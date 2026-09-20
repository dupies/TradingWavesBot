import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSV = """time,open,high,low,close,volume
2025-01-06T07:00:00,1.10000,1.10300,1.10000,1.10200,100
2025-01-06T08:00:00,1.10200,1.10500,1.10250,1.10450,120
2025-01-06T09:00:00,1.10450,1.11500,1.10400,1.11450,150
"""


def test_backtest_script_runs_and_reports(tmp_path):
    csv_path = tmp_path / "EURUSD_H1.csv"
    csv_path.write_text(CSV)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "backtest.py"),
            "--csv",
            str(csv_path),
            "--symbol",
            "EURUSD",
            "--rejections",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Trades" in result.stdout
    assert "Skipped setups" in result.stdout


def test_unknown_symbol_exits_with_error(tmp_path):
    csv_path = tmp_path / "X.csv"
    csv_path.write_text(CSV)

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "backtest.py"), "--csv", str(csv_path), "--symbol", "NOPE"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "not defined" in result.stderr
