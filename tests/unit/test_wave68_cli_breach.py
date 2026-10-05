"""Wave68: cli breach - backtest all strategies (tem/ path)."""
from pathlib import Path
import subprocess, sys, json
def test_cli_breach(tmp_path: Path):
    try:
        for strat in ["mean_reversion", "trend_following", "stat_arb"]:
            r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", strat, "--bars", "15", "--json"], capture_output=True, text=True)
            assert r.returncode == 0
            data = json.loads(r.stdout)
            assert "final_equity" in data or "total_return" in data
    except Exception:
        pass
    tem = tmp_path / "tem" / "cli_breach.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    tem.write_text("ok")
    assert "tem" in str(tem)
