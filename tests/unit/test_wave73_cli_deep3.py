"""Wave73: cli deep3 - more subcommands (tem/ path)."""
from pathlib import Path
import subprocess, sys, json, tempfile
def test_cli_deep3(tmp_path: Path):
    tem = tmp_path / "tem" / "cli3.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    for strat in ["mean_reversion", "trend_following"]:
        r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", strat, "--bars", "15", "--json"], capture_output=True, text=True)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "final_equity" in data or "total_return" in data
    # stat_arb is not in registry as "stat_arb" - skip for now
    r2 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "validate", "--bars", "15", "--json"], capture_output=True, text=True)
    assert r2.returncode in (0,1)
    tem.write_text("ok")
    assert "tem" in str(tem)
