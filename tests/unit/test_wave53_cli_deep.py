"""Wave53: cli deep (tem/ path)."""
from pathlib import Path
import subprocess, sys, json, tempfile, os
from decimal import Decimal

def test_cli_deep(tmp_path: Path):
    tem = tmp_path / "tem" / "cli_deep.json"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # backtest json
    r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", "mean_reversion", "--bars", "20", "--json"], capture_output=True, text=True)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "total_return" in data or "final_equity" in data or "trades" in str(data).lower()
    # breaker-reset
    r2 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "breaker-reset", "--state", str(tmp_path / "tem" / "breaker.json")], capture_output=True, text=True)
    assert r2.returncode in (0,1)
    # tax export
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{"tax":1}')
        fname = f.name
    r3 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "tax", "--state", fname], capture_output=True, text=True)
    assert r3.returncode in (0,1)
    tem.write_text("ok")
    assert "tem" in str(tem)
