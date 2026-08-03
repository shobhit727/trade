from __future__ import annotations

__all__ = ["main"]


def __getattr__(name: str):
    if name == "main":
        from cryptobot.cli.main import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
