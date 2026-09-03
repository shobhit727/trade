"""Wave39 targeted: cli_main (tem/ path)."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone


def test_wave_cli_main(tmp_path: Path):
    from cryptobot.cli.main import build_parser
    import subprocess, sys
    tem = tmp_path / "tem" / "cli.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    p = build_parser()
    args = p.parse_args(["backtest", "--strategy", "mean_reversion", "--bars", "10"])
    assert args.strategy == "mean_reversion"
    # also test help
    import subprocess
    r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main", "--help"], capture_output=True, text=True)
    assert r.returncode == 0
    tem.write_text("ok")
    assert "tem" in str(tem)
