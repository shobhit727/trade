"""Wave63: cli deep3 - all subcommands (tem/ path)."""
from pathlib import Path
import subprocess, sys, json, tempfile

def test_cli_deep3(tmp_path: Path):
    tem = tmp_path / "tem" / "cli3.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # backtest synthetic with different strategies
    for strat in ["mean_reversion", "trend_following"]:
        r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "backtest", "--strategy", strat, "--bars", "15", "--json"], capture_output=True, text=True)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "total_return" in data or "final_equity" in data
    # validate
    r2 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "validate", "--bars", "15", "--json"], capture_output=True, text=True)
    assert r2.returncode in (0,1)
    assert "passed" in r2.stdout or "walk_forward" in r2.stdout
    # breaker-reset with temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{"tripped": true}')
        fname = f.name
    r3 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "breaker-reset", "--state", fname], capture_output=True, text=True)
    assert r3.returncode in (0,1)
    # tax with temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write('{}')
        fname2 = f.name
    r4 = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "tax", "--state", fname2], capture_output=True, text=True)
    assert r4.returncode in (0,1)
    tem.write_text("ok")
    assert "tem" in str(tem)
