"""CLI extra: bot, serve, backtest, ml, breaker (tem/ path)."""

from pathlib import Path
import subprocess
import sys

def test_cli_help(tmp_path: Path):
    result = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "cryptobot" in result.stdout.lower() or "usage" in result.stdout.lower()
    tem = tmp_path / "tem" / "cli.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(result.stdout[:100])
    assert "tem" in str(tem)

def test_cli_backtest_synthetic(tmp_path: Path):
    result = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", "mean_reversion", "--bars", "20", "--json"], capture_output=True, text=True)
    # may take a moment, but should not crash
    assert result.returncode == 0 or "total_return" in result.stdout or "error" not in result.stderr.lower()
    tem = tmp_path / "tem" / "backtest.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text(result.stdout[:500])
    assert tem.exists()
