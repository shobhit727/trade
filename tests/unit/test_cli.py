"""Tests for cryptobot.cli.main"""

from __future__ import annotations

import argparse

import pytest

from cryptobot.cli.main import _run, build_parser
from cryptobot.cli.main import main as _main

# --- parser -------------------------------------------------------------


def test_parser_requires_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_parser_backtest_defaults():
    parser = build_parser()
    args = parser.parse_args(["backtest"])
    assert args.command == "backtest"
    assert args.strategy == "mean_reversion"
    assert args.start == "2024-01-01T00:00:00"
    assert args.end == "2024-01-02T00:00:00"
    assert args.capital == 10000.0


def test_parser_serve_args():
    args = build_parser().parse_args(["serve", "--host", "0.0.0.0", "--port", "9090"])
    assert args.host == "0.0.0.0"
    assert args.port == 9090


def test_parser_missing_subcommand():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--invalid"])


# --- happy-path commands ------------------------------------------------


@pytest.mark.asyncio
async def test_validate_returns_zero():
    # Validation on synthetic data is expected to fail (random data won't pass)
    code = await _run_async(build_parser().parse_args(["validate"]))
    assert code == 1


@pytest.mark.asyncio
async def test_paper_returns_zero():
    code = await _run_async(build_parser().parse_args(["paper"]))
    assert code == 0


@pytest.mark.asyncio
async def test_ml_command_runs_without_crash():
    # Regression for #44: the ml command previously crashed because it passed
    # a bar list to build_features and a `horizon=` kwarg to DirectionClassifier
    # (constructor expects DirectionConfig), and scored against random labels.
    code = await _run_async(build_parser().parse_args(["ml", "--bars", "200", "--horizon", "5"]))
    assert code == 0


# --- async helpers ------------------------------------------------------


async def _run_async(args: argparse.Namespace) -> int:
    """Run the async _run function directly (bypassing asyncio.run)."""
    return await _run(args)


def test_main_help_exits(monkeypatch):
    """main() with --help raises SystemExit."""
    with pytest.raises(SystemExit):
        _main(["--help"])


def test_main_unknown_command():
    """Unknown command returns exit code 2."""
    code = _main(["nonexistent"])
    assert code == 2
