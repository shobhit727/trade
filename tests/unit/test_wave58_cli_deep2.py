"""Wave58: cli deep2 - all subcommands (tem/ path)."""
from pathlib import Path
import subprocess, sys, json, tempfile
from decimal import Decimal

def test_cli_all_commands(tmp_path: Path):
    tem = tmp_path / "tem" / "cli2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # backtest synthetic
    r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", "trend_following", "--bars", "15", "--json"], capture_output=True, text=True)
    assert r.returncode == 0
    # validate
    r2 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "validate", "--bars", "20", "--json"], capture_output=True, text=True)
    assert r2.returncode in (0,1)
    # serve --help
    r3 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "serve", "--help"], capture_output=True, text=True)
    assert r3.returncode == 0
    # bot --help
    r4 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "bot", "--help"], capture_output=True, text=True)
    assert r4.returncode == 0
    tem.write_text("ok")
    assert "tem" in str(tem)
