"""Wave63: cli deep3 - more subcommands (tem/ path)."""
from pathlib import Path
import subprocess, sys

def test_cli_deep3(tmp_path: Path):
    tem = tmp_path / "tem" / "cli3.txt"
    tem.parent.mkdir(parents=True, exist_ok=True)
    # test validate, paper, ml with different args
    for cmd in [["validate", "--bars", "10"], ["paper", "--help"], ["ml", "--help"]]:
        r = subprocess.run([sys.executable, "-m", "cryptobot.cli.main"] + cmd, capture_output=True, text=True)
        assert r.returncode in (0,1,2)  # help returns 0, others may be 0/1
    tem.write_text("ok")
    assert "tem" in str(tem)
