"""Step 4 — sanity check 2 (weight count) and how much of the book is actually
being driven by the gaussian signal vs carried over by the turnover budget."""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_gaussian")

from harness import TEST, TRAIN, build_score, run_window, signal_panel  # noqa: E402

from nsealgo.backtest.engine import PortfolioConfig  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    per, ent, con = 30, 0.8, "equalw"
    score = build_score(panel, per, ent, con)
    sig = signal_panel(panel, per, ent)

    for name, window in (("TRAIN", TRAIN), ("TEST", TEST)):
        res = run_window(panel, score, window, PortfolioConfig())
        w = res.weights
        s = sig.loc[w.index]
        signalled_w = w.where(s).sum(axis=1)
        held = (w > 0).sum(axis=1)
        n_sig = s.sum(axis=1)
        print(f"=== {name} ({window[0]} -> {window[1]}) ===")
        print(f"  days                        : {len(w)}")
        print(f"  avg names held              : {held.mean():>6.2f}   (n_positions=22, max_names=30)")
        print(f"  max names held              : {held.max():>6d}")
        print(f"  days where held > 30        : {int((held > 30).sum())}")
        print(f"  avg names signalled that day: {n_sig.mean():>6.2f}")
        print(f"  avg weight in signalled names:{signalled_w.mean() * 100:>6.2f}%  "
              f"(vs {(1 - 0.10) * 100:.0f}% invested, 10% cash buffer)")
        print(f"  -> carried-over (non-signalled) weight: {(1 - 0.10 - signalled_w.mean()) * 100:.2f}%"
              " of book")
        print(f"  avg single-name weight      : "
              f"{(w.sum(axis=1) / held.clip(lower=1)).mean() * 100:>6.2f}%")
        print(f"  max single-name weight      : {float(w.max().iloc[0]) * 100 if False else float(w.max().max()) * 100:>6.2f}%  (cap 12%)")
        print(f"  invested (sum of weights)   : {w.sum(axis=1).mean() * 100:>6.2f}%")
        print()


if __name__ == "__main__":
    main()
