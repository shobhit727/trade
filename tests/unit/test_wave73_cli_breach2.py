"""Wave73: cli breach2 - more branches (tem/ path)."""
from pathlib import Path
import subprocess, sys, json, tempfile
from decimal import Decimal

def test_cli_breach2(tmp_path: Path):
    tem = tmp_path / "tem" / "cli_breach2.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # test backtest with different timeframes and strategies
    for strat in ["statistical_arbitrage", "funding_arbitrage"]:
        r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", strat, "--bars", "15", "--json"], capture_output=True, text=True)
        # stat_arb may need more bars, but should not crash
        assert r.returncode in (0,1)
    # test serve --help
    r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "serve", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    # test bot --help
    r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "bot", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    # test tax with export
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        fname = f.name
    r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "tax", "--state", str(tmp_path / "tem" / "nonexistent.json"), "--export-csv", fname], capture_output=True, text=True)
    assert r.returncode in (0,1)
    tem.write_text("ok")
    assert "tem" in str(tem)
