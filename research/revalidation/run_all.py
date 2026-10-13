"""Re-run each agent's FROZEN selected variant on the old and the new engine.

For every agent the score panel is rebuilt by importing that agent's own harness library
and calling its own builder with the parameters it recorded in its own selected-variant
artifact. Nothing in `research/agent_*` is edited or executed as a script.

The comparison that decides everything is `old` vs `new` on *identical* inputs, so the
reported delta is the tie-break and nothing else. Where the `old` column disagrees with
the number in the agent's own report, that gap is a harness-fidelity finding in its own
right and is reported separately rather than hidden.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


from agentlib import load, load_json  # noqa: E402
from core import (  # noqa: E402
    TEST,
    TRAIN,
    check_provenance,
    fmt_pr,
    panel,
    probe,
)

RESULTS: list[dict] = []
PX = None


def record(pr) -> None:
    r = pr.row()
    r["strategy"] = pr.label.split("::", 1)[-1]
    RESULTS.append(r)
    print(fmt_pr(pr), flush=True)


def reg(agent: str, strategy: str):
    """Register one agent's frozen variant on TRAIN and TEST."""

    def deco(fn):
        global PX  # noqa: PLW0603
        if PX is None:
            PX = panel()
        for wname, w in (("TRAIN", TRAIN), ("TEST", TEST)):
            try:
                sc, rb = fn(agent)
                record(probe(f"{agent}::{strategy}|{wname}", PX, sc, window=w, rebalance=rb))
            except Exception:  # noqa: BLE001
                print(f"{agent}::{strategy}|{wname} FAILED: {traceback.format_exc(limit=3)}")
                flush = True
                if flush:
                    print(flush, end="")
        return fn

    return deco


# --------------------------------------------------------------------------- #
# Wave 1 + Wave 2, ordered by exposure priority (binary / gated / saturated book).
# --------------------------------------------------------------------------- #


@reg("adx_trend", "V2_mom252")
def _adx(a):  # frozen: "flag=ret1d>0, rank by 252d momentum"
    m = load(a)
    return m.build_score("V2_mom252", panel()), "M"


@reg("breakout_momentum", "V2_EXCL20 (channel=excl period=20 mom=10)")
def _bkm(a):
    m = load(a)
    u = m.load_ohlc_universe()
    sig = m.signal_long(u, period=20, mom_period=10, channel="excl", mom_floor=0.0)
    return m.score_from_signal(u, sig, rank_lookback=126), "M"


@reg("cross_sectional", "V1 (p20 t.015 rank20)")
def _cs(a):
    m = load(a)
    sc, _sig = m.build_score(panel(), 20, 0.015, 20)
    return sc, "M"


@reg("cumulative_delta", "V1_w20_delta_rank")
def _cd(a):
    m = load(a)
    close, vol = m.load_panels()[:2]
    v = [x for x in m.VARIANTS if x.name == "V1_w20_delta_rank"][0]
    return m.strategy_score(close, vol, v), "M"


@reg("dema", "V1 p20 gate+mom126")
def _dema(a):
    m = load(a, "dema_lib")
    return m.score_from_gate(panel(), 20), "M"


@reg("roc", "V3_wide (p10 t0.00 rank mom126)")
def _roc(a):
    m = load(a)
    px = panel()
    sig = m.roc_signal(px, 10, 0.0)
    return m.build_score(px, sig, "mom126"), "M"


@reg("tema", "V4 (p20 rank mom12_1)")
def _tema(a):
    m = load(a)
    return m.build_score(panel(), 20, "mom12_1"), "M"


@reg("trendvol", "tv_p20_r10")
def _tv(a):
    m = load(a)
    close, vol = m.load_panel(), m.load_vol()
    sig = m.trend_volume_signal(close, vol, 20, 1.0)
    return m.gated_momentum_score(close, sig, 126), "M"


@reg("supertrend", "st_p20_m3.0")
def _st(a):
    m = load(a)
    close, high, low = m.load_ohlc()
    sig = m.supertrend_signal(close, high, low, 20, 3.0)
    return m.momentum_score(close, sig), "M"


@reg("atr_trailing", "V4 p55 mult2.0")
def _atr(a):
    m = load(a)
    close, high, low = m.load_ohlc()
    sig = m.atr_trailing_signal(close, high, low, 55, 2.0)
    return m.momentum_score(close, sig), "M"


@reg("anchored_vwap", "V3 p200 t5.0 mom")
def _avwap(a):
    m = load(a)
    u = m.load()
    dev = m.deviation(u.close, 200)
    return m.build_score(u.close, dev, 0.05, "mom"), "M"


@reg("absolute_momentum", "V3_p126_t0.00")
def _absm(a):
    m = load(a)
    return m.strategy_score(panel(), 126, 0.0), "M"


@reg("dual_momentum", "V3_ema50_200")
def _dm(a):
    m = load(a)
    px = panel()
    return m.build_score(px, m.build_signal(px, 50, 200)), "M"


@reg("gaussian", "V1 p30 e0.8 momentum")
def _gauss(a):
    m = load(a)
    return m.build_score(panel(), 30, 0.8, "momentum"), "M"


@reg("bb_squeeze", "V1 p20 t.05 mom")
def _bb(a):
    m = load(a)
    v = m.Variant(name="V1", period=20, threshold=0.050, scorer="momentum")
    sc, _sig = m.build_score(panel(), v)
    return sc, "M"


@reg("cmf", "V2_p20_t10_flipped")
def _cmf(a):
    m = load(a, "cmflib")
    closes, highs, lows, vols = m.load_panels()
    spec = [s for s in m.SPECS if s[0] == "V2_p20_t10_flipped"][0]
    return m.build_score(closes, closes, highs, lows, vols, spec)[0], "M"


@reg("correlation_gate", "V2 p10 t0.010 (champion)")
def _cg(a):
    m = load(a)
    px = panel()
    p, t = 10, 0.010
    sig = m.signal_panel(px, p, t)
    return m.score_from_signal(sig, px, p), "M"


@reg("momvol", "V5")
def _mv(a):
    m = load(a)
    return m.build_score(panel(), 126, 0.0), "M"


@reg("rsi", "V3 p14 lower40 deepest")
def _rsi(a):
    m = load(a)
    P = m.load_panels()
    v = load_json(a, "selected_variant.json")
    return (
        m.build_score(P.close, m.rsi_panel(P.close, v["period"]), v["lower"], rank_by=v["rank_by"]),
        v["rebalance"],
    )


def main() -> None:
    """Merge this process's rows into `results.json`, last write wins per label.

    Each batch is a separate process that imports `run_all`, so `RESULTS` only ever
    holds the batches that ran in *this* process. Merging on `label` (agent|variant|set)
    makes repeated runs idempotent and lets batches accumulate instead of overwrite.
    """
    check_provenance()
    out = Path(__file__).resolve().parent / "results.json"
    merged: dict[str, dict] = {}
    if out.exists():
        for r in json.loads(out.read_text()):
            merged[r["label"]] = r
    for r in RESULTS:
        merged[r["label"]] = r
    rows = sorted(merged.values(), key=lambda r: r["label"])
    out.write_text(json.dumps(rows, indent=1))
    print(f"\nwrote {len(rows)} rows ({len({r['label'].split('|')[0] for r in rows})} agents) -> {out}")


if __name__ == "__main__":
    main()
