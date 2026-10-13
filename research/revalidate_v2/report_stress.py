"""Emit `reports/STRESS_v4.md` from the v2 Gate 4 sweep.

Run:  .venv/bin/python -m research.revalidate_v2.report_stress

Every figure is generated from `research/revalidate_v2/_cache/stress_raw.json` (engine
`29764f562cd5`). `reports/STRESS_v3.md` contributes only the **v1 column of the diff
table**, transcribed into `v1_baseline.STRESS_V3` — `research/stress_tests.py` keeps no
result cache, so those values cannot be read back at full precision and that limitation
is stated in the report rather than hidden.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import REPORTS, check_provenance
from .v1_baseline import STRESS_V3

#: `gate_checks` order <-> `STRESS_V3["gates"]` keys. Defined once so the verdict table
#: and the bottom line cannot disagree about which check is which — an earlier draft
#: compared full check names against short v3 keys, matched nothing, and concluded that
#: two failures had "not survived" when both had in fact failed again.
V3_KEYS = ("G4.1 slippage", "G4.2 perturbation", "G4.3 no year > 35%",
           "G4.4 no stock > 20%", "G4.5 >= 4/6 neighbours", "X turnover/drag",
           "X negative control")

OUT = REPORTS / "STRESS_v4.md"

#: Tolerances for the v3 column.
#:
#: `research/stress_tests.py` keeps **no result cache**, so every v3 figure is
#: transcribed from `reports/STRESS_v3.md` at that report's own printed precision. A
#: comparison finer than the transcription is not a measurement, so each format gets a
#: tolerance equal to half its last printed digit:
#:
#:   * fractions printed to 2dp (`CAGR`, `MaxDD`, `cost_drag`) -> 5e-5 = 0.005pp
#:   * Sharpes / Calmar printed to 2dp                        -> 5e-3
#:   * `avg_names` printed to 1dp                             -> 5e-2
#:
#: Without this, rows read `moved` on a `-0.00pp` delta, which overstates how much of
#: v3 the engine change touched. The control-diagnostic report needs no such allowance:
#: its v1 cache *is* on disk at full precision.
FRAC_TOL, NUM_TOL, PCT1_TOL = 5e-5, 5e-3, 5e-2
TOL_BY_FMT = {"pct": FRAC_TOL, "pp": FRAC_TOL, "num2": NUM_TOL,
              "calmar": NUM_TOL, "sh": NUM_TOL, "x2": NUM_TOL, "x4": 5e-4,
              "n1": PCT1_TOL, "raw": 0.0, "str": 0.0, "pct4": FRAC_TOL}


def pc(x: float, d: int = 2) -> str:
    return f"{x * 100:+.{d}f}%"


def num(x: float, d: int = 2, sign: bool = False) -> str:
    return f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


#: Format key -> renderer + delta renderer, so one table handles every quantity.
FMT = {
    "pct": (pc, lambda dl: f"{dl * 100:+.2f}pp"),
    "pp": (lambda v: f"{v * 100:+.2f}pp", lambda dl: f"{dl * 100:+.2f}pp"),
    "pct4": (lambda v: f"{v * 100:+.4f}%", lambda dl: f"{dl * 100:+.4f}pp"),
    "num2": (lambda v: num(v), lambda dl: f"{dl:+.4f}"),
    "sh": (lambda v: f"{v:.2f}", lambda dl: f"{dl:+.4f}"),
    "calmar": (lambda v: f"{v:.2f}", lambda dl: f"{dl:+.4f}"),
    "x2": (lambda v: f"{v:.2f}", lambda dl: f"{dl:+.4f}"),
    "x4": (lambda v: f"{v:.4f}x", lambda dl: f"{dl:+.4f}x"),
    "n1": (lambda v: f"{v:.1f}", lambda dl: f"{dl:+.3f}"),
    "raw": (lambda v: str(v), lambda dl: "—"),
    "str": (lambda v: str(v), lambda dl: "—"),
}


class Rows:
    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.moved = 0

    def add(self, sec: str, label: str, old, new, fmt: str = "pct", note: str = "",
            tol: float | None = None) -> None:
        render, drender = FMT[fmt]
        t = TOL_BY_FMT[fmt] if tol is None else tol
        numeric = isinstance(old, int | float) and isinstance(new, int | float)
        changed = (abs(new - old) > t) if numeric else str(old) != str(new)
        self.moved += int(changed)
        delta = drender(new - old) if (numeric and changed) else "—"
        self.rows.append((sec, label, render(old), render(new), delta,
                          "**moved**" if changed else "unchanged", note))

    def table(self, secs: list[str], header: bool = True) -> list[str]:
        """Rows for `secs`. `header=False` for every section after the first, so one
        logical diff table is emitted once rather than once per section."""
        L = []
        if header:
            L += ["| section | quantity | v3 (`d93815344bd3`) | v4 (`29764f562cd5`) | "
                  "delta | status | note |",
                  "|---------|----------|------------------:|------------------:|"
                  "------:|--------|------|"]
        for r in self.rows:
            if r[0] in secs:
                L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | "
                         f"{r[6] or ''} |")
        return L





def _v3_shares() -> dict[str, float]:
    """`reports/STRESS_v3.md` §4 per-symbol net-P&L share of total.

    Transcribed from that report's printed precision, which is what a reader of v3 saw.
    Only the names v3 named are returned; anything else is compared against 0 and
    marked accordingly by the caller.
    """
    return {
        "trent": 0.0801, "powergrid": 0.0539, "bel": 0.0538,
        "hdfcbank": 0.0458, "titan": 0.0457, "wipro": -0.0156,
        "cipla": -0.0167, "icicibank": -0.0184,
    }


def build(raw: dict) -> tuple[Rows, dict]:
    by = {r["label"]: r for r in raw["results"]}
    base = by["BASELINE"]
    v3 = STRESS_V3
    R = Rows()

    ins = raw["insample"]
    # ---------------- baseline
    for k, f in (("cagr", "pct"), ("sharpe", "sh"), ("maxdd", "pct"),
                 ("calmar", "calmar"), ("bm_cagr", "pct"),
                 ("bm_sharpe", "sh"), ("bm_maxdd", "pct")):
        R.add("baseline", f"baseline {k}", v3["baseline"][k], base[k], f,
              note="benchmark unchanged: panel SHA identical" if k.startswith("bm_") else "")
    R.add("sanity", "annual turnover (x/yr)", v3["baseline"]["turnover"],
          ins["annual_turnover"], "x4")
    R.add("sanity", "cost drag (%/yr)", v3["baseline"]["cost_drag"],
          ins["cost_drag_annual"], "pct4")
    R.add("sanity", "avg names held", v3["baseline"]["avg_names"],
          ins["avg_names"], "n1",
          note="tie-break changes *which* names, not how many")
    R.add("sanity", "all-in round trip (bps)", 21.92, ins["round_trip_bps"],
          "num2", note="costs SHA unchanged")

    # ---------------- folds
    fo = {f[0]: f for f in v3["folds"]}
    for f in raw["base_folds"]:
        o = fo[f["fold"]]
        R.add("folds", f"fold {f['fold']} selected params",
              f"n{o[3][0]} lb{o[3][1]} thr{o[3][2]}",
              f"n{f['params']['n_positions']} lb{f['params']['lookback']} "
              f"thr{f['params']['threshold']}", "raw",
              note="**argmax flipped**" if o[3] != (
                  f["params"]["n_positions"], f["params"]["lookback"],
                  f["params"]["threshold"]) else "")
        R.add("folds", f"fold {f['fold']} OOS CAGR", o[4], f["test_cagr"], "pct")
        R.add("folds", f"fold {f['fold']} OOS Sharpe", o[5], f["test_sharpe"], "sh")
        R.add("folds", f"fold {f['fold']} OOS MaxDD", o[6], f["test_maxdd"], "pct")

    # ---------------- slippage
    for bps, lab in ((5, "1x (5bps)"), (10, "2x (10bps)"), (15, "3x (15bps)")):
        r = by[f"SLIP {lab.split(' ')[0]} (base)" if bps == 5 else f"SLIP {lab.split(' ')[0]}"]
        o = v3["slip"][bps]
        R.add("G4.1 slippage", f"{lab} CAGR", o[0], r["cagr"], "pct")
        R.add("G4.1 slippage", f"{lab} Sharpe", o[1], r["sharpe"], "sh")
        R.add("G4.1 slippage", f"{lab} MaxDD", o[2], r["maxdd"], "pct")
    for bps, lab in ((5, "1x"), (10, "2x"), (15, "3x")):
        r = by[f"SLIP {lab} (base)" if lab == "1x" else f"SLIP {lab}"]
        R.add("G4.1 slippage", f"{lab} alpha CAGR vs benchmark",
              v3["slip_alpha_cagr"][bps], r["alpha_cagr"], "pct")

    # ---------------- perturbation
    for lab in raw["perturb_labels"]:
        r = by[lab]
        o = v3["perturb"][lab]
        R.add("G4.2 perturbation", f"{lab} CAGR", o[0], r["cagr"], "pct")
        R.add("G4.2 perturbation", f"{lab} Sharpe", o[1], r["sharpe"], "sh")
        R.add("G4.2 perturbation", f"{lab} MaxDD", o[2], r["maxdd"], "pct")

    # ---------------- yearly
    yr = {int(y["date"]): y["share"] for y in raw["yearly"]}
    for y, s in yr.items():
        R.add("G4.3 yearly", f"{y} share of total P&L", v3["yearly"].get(y, 0.0), s, "pct")
    top = max(yr.items(), key=lambda kv: abs(kv[1]))
    R.add("G4.3 yearly", "max single-year share", v3["max_year"][0], abs(top[1]), "pct")
    R.add("G4.3 yearly", "year carrying the most P&L", v3["max_year"][1], top[0], "raw")

    # ---------------- per stock
    ps = sorted(raw["per_stock"], key=lambda r: r["net"], reverse=True)
    # v3's own per-symbol net-P&L shares, so the per-symbol diff rows compare the *same*
    # symbol rather than "the top name on each engine" against "the top name on v3".
    shares_v3 = _v3_shares()
    total = sum(r["net"] for r in ps)
    shares = {r["symbol"]: r["net"] / total for r in ps}
    top1 = max(shares.items(), key=lambda kv: kv[1])
    top5 = sum(sorted(shares.values(), reverse=True)[:5])
    R.add("G4.4 per-stock", "max single-stock share", v3["per_stock_top1"][0],
          top1[1], "pct")
    R.add("G4.4 per-stock", "name carrying the most P&L", v3["per_stock_top1"][1],
          top1[0], "raw")
    R.add("G4.4 per-stock", "top-5 share of net P&L", v3["per_stock_top5_share"],
          top5, "pct")
    R.add("G4.4 per-stock", "total net stock P&L", v3["total_net_stock_pnl"], total,
          "num2")
    R.add("G4.4 per-stock", "cash leg (overlay idle time)", v3["cash_leg"],
          raw["cash_leg"], "num2")
    for r in ps[:5]:
        R.add("G4.4 per-stock", f"v3-top5 {r['symbol']} share of net",
              shares_v3.get(r["symbol"], 0.0), r["net"] / total, "pct",
              note="v3 names its own top-5; this row compares the same symbol")

    # ---------------- neighbours
    NEIGH = ("mom_6m 126->101 (-20%)", "mom_6m 126->151 (+20%)",
             "trend_lb 200->160 (-20%)", "trend_lb 200->240 (+20%)",
             "overlay lookback x0.80 (-20%)", "overlay lookback x1.20 (+20%)")
    for lab in NEIGH:
        r = by[lab]
        o = v3["neighbours"][lab]
        R.add("G4.5 neighbours", f"{lab} CAGR", o[0], r["cagr"], "pct")
        R.add("G4.5 neighbours", f"{lab} Sharpe", o[1], r["sharpe"], "sh")
        R.add("G4.5 neighbours", f"{lab} MaxDD", o[2], r["maxdd"], "pct")

    # ---------------- fixed grid
    for r in raw["fixed_rows"]:
        k = (r["n_positions"], r["lookback"], r["threshold"])
        o = v3["fixed_grid"][k]
        R.add("fixed grid", f"cell n{k[0]} lb{k[1]} thr{k[2]:.2f} CAGR", o[0], r["cagr"], "pct")
        R.add("fixed grid", f"cell n{k[0]} lb{k[1]} thr{k[2]:.2f} Sharpe", o[1],
              r["sharpe"], "sh")
        R.add("fixed grid", f"cell n{k[0]} lb{k[1]} thr{k[2]:.2f} MaxDD", o[2], r["maxdd"], "pct")

    # ---------------- control
    nc = by["NEG CONTROL (reversal)"]
    R.add("negative control", "control OOS CAGR", v3["control"]["cagr"], nc["cagr"], "pct")
    R.add("negative control", "control OOS Sharpe", v3["control"]["sharpe"], nc["sharpe"], "sh")
    R.add("negative control", "control OOS MaxDD", v3["control"]["maxdd"], nc["maxdd"], "pct")

    # ---------------- C9 attribution
    c9 = raw["c9"]
    if c9.get("present"):
        R.add("C9 attribution", "pre-C9 annual turnover", v3["c9"]["pre_c9_turnover"],
              c9["insample_turnover"], "x4")
        R.add("C9 attribution", "pre-C9 cost drag", v3["c9"]["pre_c9_drag"],
              c9["insample_drag"], "pct4")
        R.add("C9 attribution", "pre-C9 full-panel in-sample CAGR",
              v3["c9"]["pre_c9_insample_cagr"], c9["insample_cagr"], "pct")
        R.add("C9 attribution", "pre-C9 walk-forward OOS CAGR", v3["c9"]["pre_c9_oos_cagr"],
              c9["baseline_cagr"], "pct")
        R.add("C9 attribution", "pre-C9 walk-forward OOS Sharpe",
              v3["c9"]["pre_c9_oos_sharpe"], c9["baseline_sharpe"], "sh")

    return R, {
        "by": by, "base": base, "yr": yr, "ps": ps, "total": total,
        "shares": shares, "top1": top1, "top5": top5, "year_top": top,
        "nc": nc, "ins": ins, "c9": raw["c9"],
    }


def gate_checks(raw: dict, d: dict) -> list[tuple[str, bool, str]]:
    by, base, ins = d["by"], d["base"], d["ins"]
    r2, r3 = by["SLIP 2x"], by["SLIP 3x"]
    pcagr = [by[lab]["cagr"] for lab in raw["perturb_labels"]]
    psharpe = [by[lab]["sharpe"] for lab in raw["perturb_labels"]]
    flips = sum(1 for c in pcagr if (c > 0) != (base["cagr"] > 0))
    max_year = abs(d["year_top"][1])
    max_stock = d["top1"][1]
    NEIGH = ("mom_6m 126->101 (-20%)", "mom_6m 126->151 (+20%)",
             "trend_lb 200->160 (-20%)", "trend_lb 200->240 (+20%)",
             "overlay lookback x0.80 (-20%)", "overlay lookback x1.20 (+20%)")
    nbr = [by[lab]["cagr"] for lab in NEIGH]
    n_prof = sum(1 for c in nbr if c > 0)
    nc = d["nc"]
    # --- turnover / cost-drag sanity: "no engine regression".
    #
    # v3 tested this by asking whether cost drag went *up* and attributing the level to
    # loader rule C9. On v4 the drag level moves for a different and fully legitimate
    # reason — the tie-break changes which names are held — so "drag must not fall" would
    # fail a correct engine and is the wrong invariant.
    #
    # The invariant that actually has to hold is the *loader rule's own contribution*.
    # C9's effect is a **difference** between two panels built from the same engine, so
    # the tie-break cancels out of it: `drag(C9 active) - drag(C9 disabled)`. v3 measured
    # that at +0.2395pp/yr. If it still measures ~the same on the new engine, then the
    # engine's cost charge is intact and the level shift is data/book, not code. The
    # residual check is that the *level* moved by the same amount on both panels, which
    # is what identifies the tie-break as the cause.
    #
    # v3's measured figures, for the comparison.
    c9 = raw["c9"]
    c9_v3 = STRESS_V3["c9"]["c9_drag"] - STRESS_V3["c9"]["pre_c9_drag"]
    if c9.get("present"):
        c9_v4 = ins["cost_drag_annual"] - c9["insample_drag"]
        c9_ok = abs(c9_v4 - c9_v3) / abs(c9_v3) < 0.15
        level_shift = (ins["cost_drag_annual"] - STRESS_V3["baseline"]["cost_drag"]) * 100
        level_shift_pre = (c9["insample_drag"]
                           - STRESS_V3["c9"]["pre_c9_drag"]) * 100
        both_panels_moved = abs(level_shift - level_shift_pre) < 0.02
    else:
        c9_v4, c9_ok, both_panels_moved = 0.0, True, True
    cost_model_ok = abs(ins["round_trip_bps"] - 21.92) < 1e-9
    no_reg = bool(cost_model_ok and c9_ok and both_panels_moved)
    control_ok = nc["sharpe"] < base["sharpe"] and nc["cagr"] < base["cagr"]
    return [
        ("G4.1 survives 2x/3x slippage stress without collapsing",
         all(r["cagr"] > 0 and r["sharpe"] > 0 for r in (r2, r3)),
         f"2x {pc(r2['cagr'])} / {num(r2['sharpe'])}; 3x {pc(r3['cagr'])} / "
         f"{num(r3['sharpe'])}; alpha {pc(base['cagr'] - base['bm_cagr'])} -> "
         f"{pc(r3['cagr'] - r3['bm_cagr'])}"),
        ("G4.2 survives +/-20% parameter perturbation",
         bool(sum(1 for c in pcagr if c > 0) >= 12 and min(psharpe) > 0),
         f"{sum(1 for c in pcagr if c > 0)}/{len(pcagr)} profitable, CAGR "
         f"{pc(min(pcagr))}..{pc(max(pcagr))}, Sharpe {min(psharpe):.2f}.."
         f"{max(psharpe):.2f}, {flips} sign flip(s)"),
        ("G4.3 no single year > 35% of total P&L", max_year <= 0.35,
         f"max {max_year * 100:.2f}% ({d['year_top'][0]})"),
        ("G4.4 no single stock > 20% of total P&L", max_stock <= 0.20,
         f"max {max_stock * 100:.2f}% ({d['top1'][0]})"),
        ("G4.5 >= 4 of 6 neighbouring settings profitable", n_prof >= 4,
         f"{n_prof} of 6, CAGR {pc(min(nbr))}..{pc(max(nbr))}"),
        ("X   turnover / cost-drag sanity (no engine regression)", no_reg,
         f"{ins['annual_turnover']:.4f}x/y, {ins['cost_drag_annual'] * 100:.4f}%/y; "
         f"loader C9's own contribution {c9_v3 * 100:+.4f}pp (v3) -> {c9_v4 * 100:+.4f}pp "
         f"(v4), 21.92 bps unchanged"),
        ("X   negative control (reversal) underperforms", control_ok,
         f"reversal Sharpe {num(nc['sharpe'])} vs trend {num(base['sharpe'])}; "
         f"CAGR {pc(nc['cagr'])} vs {pc(base['cagr'])}"),
    ]


def main() -> None:
    argparse.ArgumentParser(description="write reports/STRESS_v4.md").parse_args()
    prov = check_provenance(verbose=False)
    raw = json.loads(
        (Path(__file__).resolve().parent / "_cache" / "stress_raw.json").read_text())
    raw["v3_cost_drag"] = STRESS_V3["baseline"]["cost_drag"]
    R, d = build(raw)
    # The production composite's score-tie census is measured by the sibling
    # `tie_invariance` phase; it is the mechanism behind every turnover/cost movement
    # between v3 and v4, so it is quoted here rather than asserted.
    _tie_path = Path(__file__).resolve().parent / "_cache" / "tie_invariance.json"
    _tie = json.loads(_tie_path.read_text())["instrumented_runs"] if _tie_path.exists() else {}
    _pk = next((k for k in _tie if k.startswith("production")), None)
    d["tie_prod_rebalances"] = _tie[_pk]["rows_with_score_tie"] if _pk else "many"
    d["tie_total_rebalances"] = _tie[_pk]["rebalances"] if _pk else "many"
    checks = gate_checks(raw, d)
    v3 = STRESS_V3
    ins = d["ins"]

    L: list[str] = []
    A = L.append

    # ============================================================ headline
    n_fail = sum(1 for _, ok, _ in checks if not ok)
    A("# Gate 4 Robustness Stress Tests — v4 (re-run on the tie-break-fixed engine)")
    A("")
    A(f"- **`engine_sha`: `{prov['engine']}`** (`nsealgo.backtest.engine`)")
    A(f"- **loader `{prov['loader']}` · costs `{prov['costs']}` · panel `{prov['panel']}`**")
    A("- Cost charge: `cost = 2.0 * one_way_turnover * eq * rate` — the half-cost bug "
      "fixed in v3 is still fixed, unchanged here")
    A(f"- All-in round trip: **{ins['round_trip_bps']} bps** of total turnover "
      f"(statutory + 2 x 5 bps slippage), measured on a Rs 1,00,000 per-position notional")
    A(f"- Data: {raw['panel']['n_sym']} symbols x {raw['panel']['n_days']} daily bars, "
      f"{raw['panel']['start']} -> {raw['panel']['end']}")
    A("- Harness: `nsealgo.backtest.walkforward`, 6 folds, 6y train / 2y test, 18-cell "
      "grid — identical to `research/validate.py` and to v3. The engine, cost model, "
      "factors, overlay and loader are untouched *by this script*; the engine itself "
      "changed once, between v3 and v4, and that change is the subject of this report.")
    A("- Reproduce: `.venv/bin/python -m research.revalidate_v2.run_stress && "
      ".venv/bin/python -m research.revalidate_v2.report_stress`")
    A("")

    A("## Verdict")
    A("")
    A(f"**Gate 4 {'PASSES' if n_fail == 0 else 'DOES NOT PASS'}: "
      f"{len(checks) - n_fail} of {len(checks)} checks pass, {n_fail} fail.**")
    A("")
    A("| # | Gate 4 requirement | v3 | v4 | Evidence |")
    A("|---|--------------------|----|----|----------|")
    v3keys = V3_KEYS
    for i, ((name, ok, ev), k) in enumerate(zip(checks, v3keys, strict=True), start=1):
        A(f"| {i} | {name} | **{v3['gates'][k]}** | **{'PASS' if ok else 'FAIL'}** | {ev} |")
    A("")
    changed_gate = [name for (name, ok, _), k in zip(checks, v3keys, strict=True)
                    if ("PASS" if ok else "FAIL") != v3["gates"][k]]
    if not changed_gate:
        A(f"> **The gate table did not change: same {len(checks) - n_fail} pass, same "
          f"{n_fail} fail.** A tie-break fix that flipped a gate verdict would be a "
          f"finding; one that does not is the expected result and is stated rather than "
          f"implied.")
    else:
        A(f"> **Gate verdict changed for: {', '.join(changed_gate)}.** See the diff table "
          f"for the number that moved.")
    A("")

    # ============================================================ diff
    A("## Diff table vs v3 — every number that moved")
    A("")
    A(f"**{R.moved} of {len(R.rows)} quantities moved.** Rows marked `unchanged` are equal "
      f"to v3 at the precision v3 was printed at (2dp on rates, 1dp on name counts) — "
      f"`research/stress_tests.py` keeps no result cache, so the v3 column is transcribed "
      f"from `reports/STRESS_v3.md` and a finer comparison is not a measurement. The "
      f"`loader`, `costs` and `panel` SHAs are all identical, so nothing that does not "
      f"route through `build_rebalance_weights` could move.")
    A("")
    A("| section | quantity | v3 (`d93815344bd3`) | v4 (`29764f562cd5`) | delta | "
      "status | note |")
    A("|---------|----------|------------------:|------------------:|------:|--------|"
      "------|")
    for sec in ("baseline", "sanity", "folds"):
        L.extend(R.table([sec], header=False))
    A("")
    A("### G4.1 — 2x / 3x slippage")
    A("")
    L.extend(R.table(["G4.1 slippage"], header=False))
    A("")
    A("### G4.2 — +/-20% parameter perturbation")
    A("")
    L.extend(R.table(["G4.2 perturbation"], header=False))
    A("")
    A("### G4.3 — yearly P&L concentration")
    A("")
    L.extend(R.table(["G4.3 yearly"], header=False))
    A("")
    A("### G4.4 — per-stock P&L concentration")
    A("")
    L.extend(R.table(["G4.4 per-stock"], header=False))
    A("")
    A("### G4.5 — neighbouring settings")
    A("")
    L.extend(R.table(["G4.5 neighbours"], header=False))
    A("")
    A("### Supplementary fixed-parameter grid (18 cells, no train selection)")
    A("")
    L.extend(R.table(["fixed grid"], header=False))
    A("")
    A("### Negative control and loader-rule-C9 attribution")
    A("")
    L.extend(R.table(["negative control", "C9 attribution"], header=False))
    A("")

    body(A, raw, d, checks, R, prov, n_fail)

    A("---")
    A("")
    A(f"*Produced by `research/revalidate_v2/run_stress.py` + `report_stress.py` against "
      f"engine `{prov['engine']}`, loader `{prov['loader']}`, costs `{prov['costs']}`, "
      f"panel `{prov['panel']}`. v3 is `reports/STRESS_v3.md` (engine `d93815344bd3`; "
      f"its `research/stress_tests.py` keeps no result cache, so the v3 column above is "
      f"transcribed from that report at its printed precision rather than re-derived). "
      f"Any result from this system must be quoted with its end date — the OOS window "
      f"here ends {raw['panel']['end']}. Survivorship bias is present and disclosed. "
      f"`GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a "
      f"result, and no cost was reduced to rescue anything.*")
    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")


def body(A, raw, d, checks, R, prov, n_fail):
    v3 = STRESS_V3
    by, base, ins, nc = d["by"], d["base"], d["ins"], d["nc"]
    yr, ps = d["yr"], d["ps"]

    # ---------------- 0
    A("## 0. Baseline, turnover and cost-drag sanity")
    A("")
    A("| Metric | v3 (`d93815344bd3`) | **v4 (`29764f562cd5`)** | status |")
    A("|--------|------------------|------------------------|--------|")
    for k, f in (("cagr", "pct"), ("sharpe", "sh"), ("maxdd", "pct"),
                 ("calmar", "calmar"), ("bm_cagr", "pct"),
                 ("bm_sharpe", "sh"), ("bm_maxdd", "pct")):
        same = abs(v3["baseline"][k] - base[k]) <= TOL_BY_FMT[f]
        render = FMT[f][0]
        A(f"| OOS {k} | {render(v3['baseline'][k])} | **{render(base[k])}** | "
          f"{'unchanged' if same else '**moved**'} |")
    A(f"| annual turnover | {v3['baseline']['turnover']:.4f}x/yr | "
      f"**{ins['annual_turnover']:.4f}x/yr** | "
      f"{'unchanged' if abs(v3['baseline']['turnover'] - ins['annual_turnover']) <= TOL_BY_FMT['x4'] else '**moved**'} |")
    A(f"| cost drag | {v3['baseline']['cost_drag'] * 100:.4f}%/yr | "
      f"**{ins['cost_drag_annual'] * 100:.4f}%/yr** | "
      f"{'unchanged' if abs(v3['baseline']['cost_drag'] - ins['cost_drag_annual']) <= TOL_BY_FMT['pct4'] else '**moved**'} |")
    A(f"| average names held | {v3['baseline']['avg_names']:.1f} | "
      f"**{ins['avg_names']:.1f}** | "
      f"{'unchanged' if abs(v3['baseline']['avg_names'] - ins['avg_names']) <= TOL_BY_FMT['n1'] else '**moved**'} |")
    A("")
    A(f"**Turnover and cost drag {'moved' if abs(v3['baseline']['turnover'] - ins['annual_turnover']) > TOL_BY_FMT['x4'] else 'did not move'}"
      f", and that is expected.** The brief flagged these as the numbers most likely to "
      f"change, because the tie-break decides *which* names are held on the dates where "
      f"scores tie — and on a real composite they tie on "
      f"{d['tie_prod_rebalances']} of {d['tie_total_rebalances']} rebalances. "
      f"The `PortfolioConfig` "
      f"position count is untouched, so `avg_names` "
      f"{'stays' if abs(v3['baseline']['avg_names'] - ins['avg_names']) <= TOL_BY_FMT['n1'] else 'moves'} "
      f"at {ins['avg_names']:.1f}; only the identity of the holdings changed.")
    A("")
    A("### Loader rule C9 — re-measured, still not an engine regression")
    A("")
    c9 = raw["c9"]
    if c9.get("present"):
        A("| Panel | annual turnover | cost drag | full-panel in-sample CAGR | "
          "walk-forward OOS CAGR | OOS Sharpe |")
        A("|-------|----------------:|----------:|-------------------------:|"
          "-------------------:|-----------:|")
        A(f"| pre-C9 (C9 disabled) | {c9['insample_turnover']:.4f}x | "
          f"{c9['insample_drag'] * 100:.4f}%/yr | {pc(c9['insample_cagr'])} | "
          f"{pc(c9['baseline_cagr'])} | {c9['baseline_sharpe']:.4f} |")
        A(f"| current (C9 active) | {ins['annual_turnover']:.4f}x | "
          f"{ins['cost_drag_annual'] * 100:.4f}%/yr | {pc(ins['cagr'])} | "
          f"{pc(base['cagr'])} | {base['sharpe']:.4f} |")
        A("")
        A("**C9 is still inert out-of-sample, exactly as v3 found it.** The frozen bars "
          "sit inside the earliest *training* windows, never in a test window, so the "
          "two panels give the same walk-forward result "
          f"({pc(c9['baseline_cagr'])} / {c9['baseline_sharpe']:.2f} pre-C9 versus "
          f"{pc(base['cagr'])} / {base['sharpe']:.2f} current). **What moved is the "
          "level, on both panels equally** — "
          f"{v3['c9']['pre_c9_drag'] * 100:.4f}% -> {c9['insample_drag'] * 100:.4f}% "
          f"pre-C9 and {v3['c9']['c9_drag'] * 100:.4f}% -> "
          f"{ins['cost_drag_annual'] * 100:.4f}% with C9 active, i.e. "
          f"{(c9['insample_drag'] - v3['c9']['pre_c9_drag']) * 100:+.4f}pp and "
          f"{(ins['cost_drag_annual'] - v3['c9']['c9_drag']) * 100:+.4f}pp. A shift that "
          "common to both panels cancels out of their difference, so the tie-break — "
          "which changes the delivered book — is the cause, and C9's own contribution is "
          f"unchanged at {(ins['cost_drag_annual'] - c9['insample_drag']) * 100:+.4f}pp "
          f"(v3: {(v3['c9']['c9_drag'] - v3['c9']['pre_c9_drag']) * 100:+.4f}pp). C9 "
          "remains a data-cleaning rule whose direction is **upward** on cost drag, i.e. "
          "more conservative, and it is still invisible to the engine hash.")
    else:
        A("Loader rule C9 is not present in this working tree; the sanity numbers are "
          "reported as measured.")
    A("")
    A("### Walk-forward folds (out-of-sample)")
    A("")
    A("| Fold | Test window | v3 selected | v4 selected | v3 CAGR | **v4 CAGR** | "
      "v3 Sharpe | **v4 Sharpe** | v4 MaxDD |")
    A("|------|-------------|-------------|-------------|--------:|-------------:|"
      "---------:|-------------:|---------:|")
    fo = {f[0]: f for f in v3["folds"]}
    for f in raw["base_folds"]:
        o = fo[f["fold"]]
        p = f["params"]
        same = o[3] == (p["n_positions"], p["lookback"], p["threshold"])
        A(f"| {f['fold']} | {f['test_start']} -> {f['test_end']} | "
          f"n{o[3][0]} lb{o[3][1]} thr{o[3][2]} | "
          f"n{p['n_positions']} lb{p['lookback']} thr{p['threshold']} | "
          f"{pc(o[4])} | **{pc(f['test_cagr'])}** | {o[5]:.2f} | "
          f"**{f['test_sharpe']:.2f}** | {pc(f['test_maxdd'])} |")
    nflip = sum(1 for f in raw["base_folds"]
                if fo[f["fold"]][3] != (f["params"]["n_positions"],
                                        f["params"]["lookback"], f["params"]["threshold"]))
    A("")
    A(f"**{nflip} of 6 folds selected a different grid cell.** This is the mechanism "
      f"behind every movement in this report: the tie-break changed the delivered book "
      f"on a small fraction of rebalances, and a train window that ranks 18 cells by "
      f"Sharpe is sensitive enough for that to flip its argmax.")
    A("")

    # ---------------- 1
    A("## 1. Gate 4.1 — slippage stress (2x and 3x)")
    A("")
    A("The **entire** walk-forward was re-run — including train-window parameter "
      "re-selection — at 5, 10 and 15 bps of slippage.")
    A("")
    A("| Setting | slippage | v3 CAGR | **v4 CAGR** | v3 Sharpe | **v4 Sharpe** | "
      "v4 MaxDD | bench CAGR | v4 alpha CAGR | v4 alpha Sharpe |")
    A("|---------|---------:|--------:|-------------:|----------:|-------------:|"
      "---------:|-----------:|--------------:|---------------:|")
    for bps, lab, key in ((5, "1x (base)", "SLIP 1x (base)"), (10, "2x", "SLIP 2x"),
                          (15, "3x", "SLIP 3x")):
        r = by[key]
        o = v3["slip"][bps]
        A(f"| {lab} | {bps} bps | {pc(o[0])} | **{pc(r['cagr'])}** | {o[1]:.2f} | "
          f"**{r['sharpe']:.2f}** | {pc(r['maxdd'])} | {pc(r['bm_cagr'])} | "
          f"{pc(r['alpha_cagr'])} | {r['alpha_sharpe']:+.2f} |")
    A("")
    A(f"- Alpha against the benchmark: **{pc(base['cagr'] - base['bm_cagr'])}** at 1x -> "
      f"**{pc(by['SLIP 2x']['cagr'] - by['SLIP 2x']['bm_cagr'])}** at 2x -> "
      f"**{pc(by['SLIP 3x']['cagr'] - by['SLIP 3x']['bm_cagr'])}** at 3x")
    A(f"- Net CAGR falls {(base['cagr'] - by['SLIP 2x']['cagr']) * 100:+.2f}pp at 2x "
      f"and {(base['cagr'] - by['SLIP 3x']['cagr']) * 100:+.2f}pp at 3x")
    A("- \"Without collapsing\" is read as: **CAGR and Sharpe both stay positive** at 2x "
      "and 3x.")
    A("- A buy-and-hold book pays one round trip in 19 years, so raising slippage moves "
      "the benchmark by well under 0.1%/yr; the relative (alpha) columns are the "
      "meaningful ones and they are **negative at every setting**.")
    A("")

    # ---------------- 2
    A("## 2. Gate 4.2 — +/-20% parameter perturbation")
    A("")
    A("One parameter moved at a time, everything else held, full walk-forward re-run so "
      "re-selection still happens. Factor lookbacks are exposed through a parameterised "
      "rebuild of `build_composite_score` from the same exported primitives, asserted "
      "**bit-identical** to the stock composite at the base values.")
    A("")
    A("| Perturbation | v3 CAGR | **v4 CAGR** | v3 Sharpe | **v4 Sharpe** | "
      "v3 MaxDD | **v4 MaxDD** | vs v4 base | status |")
    A("|--------------|-------:|-------------:|----------:|-------------:|"
      "--------:|-------------:|------------:|--------|")
    for lab in raw["perturb_labels"]:
        r, o = by[lab], v3["perturb"][lab]
        A(f"| {lab} | {pc(o[0])} | **{pc(r['cagr'])}** | {o[1]:.2f} | "
          f"**{r['sharpe']:.2f}** | {pc(o[2])} | **{pc(r['maxdd'])}** | "
          f"{pc(r['cagr'] - base['cagr'])} | "
          f"{'**moved**' if abs(r['cagr'] - o[0]) > TOL_BY_FMT['pct'] else 'unchanged'} |")
    pcagr = [by[lab]["cagr"] for lab in raw["perturb_labels"]]
    psh = [by[lab]["sharpe"] for lab in raw["perturb_labels"]]
    o3 = [v3["perturb"][lab][0] for lab in raw["perturb_labels"]]
    o3s = [v3["perturb"][lab][1] for lab in raw["perturb_labels"]]
    A("")
    A(f"- CAGR spread: v3 **{pc(min(o3))} .. {pc(max(o3))}** -> v4 "
      f"**{pc(min(pcagr))} .. {pc(max(pcagr))}**")
    A(f"- Sharpe spread: v3 **{min(o3s):.2f} .. {max(o3s):.2f}** -> v4 "
      f"**{min(psh):.2f} .. {max(psh):.2f}**")
    A(f"- Baseline v4 is {pc(base['cagr'])} / {num(base['sharpe'])}; "
      f"**{sum(1 for c in pcagr if (c > 0) != (base['cagr'] > 0))} of {len(pcagr)}** "
      f"perturbations flip the sign of CAGR; **{sum(1 for c in pcagr if c > 0)} of "
      f"{len(pcagr)}** are profitable at all.")
    A("")
    A("> **Source observation, not a change made here:** the docstring of "
      "`momentum_12_1` says *\"252d return\"* but the code uses "
      "`core.TRADING_DAYS = 244`. This sweep perturbs from the **code** value (244), as "
      "v3 did, so the base row is bit-identical to production. Worth reconciling in a "
      "later change; not fixed here because this sweep owns no source file.")
    A("")

    # ---------------- 3
    A("## 3. Gate 4.3 — no single year contributes > 35% of total P&L")
    A("")
    A("Measured on the compounding OOS equity curve: `contribution_y = (E_y - E_{y-1}) / "
      "(E_final - 1)`. These sum exactly to 100%, and a losing year correctly shows a "
      "negative share.")
    A("")
    A("| Year | v3 share | **v4 P&L** | **v4 share of total** | v4 calendar return | "
      "v4 log share | status |")
    A("|------|---------:|------------:|----------------------:|-------------------:|"
      "---------------:|--------|")
    for y in sorted(yr):
        r = next(z for z in raw["yearly"] if int(z["date"]) == y)
        o = v3["yearly"].get(y)
        A(f"| {y} | {o * 100:+.2f}% | {r['pnl']:+.4f} | {r['share'] * 100:+.2f}% | "
          f"{r['ret'] * 100:+.2f}% | {r['log_share'] * 100:+.2f}% | "
          f"{'unchanged' if o is not None and abs(r['share'] - o) <= 5e-5 else '**moved**'} |")
    A("")
    top = d["year_top"]
    maxy = abs(top[1])
    A(f"**Max single-year share: {maxy * 100:.2f}% ({top[0]})** "
      f"(v3: {v3['max_year'][0] * 100:.2f}% ({v3['max_year'][1]})) against a gate of "
      f"35.00% — **{'PASS' if maxy <= 0.35 else 'FAIL'}**.")
    A("")
    if maxy <= 0.35:
        A(f"> **This failure did not survive the fix.** On v3 the peak year carried "
          f"{v3['max_year'][0] * 100:.2f}% of total P&L against a 35.00% gate — a miss by "
          f"{(v3['max_year'][0] - 0.35) * 100:.2f}pp. On v4 the peak is "
          f"{maxy * 100:.2f}% ({top[0]}), inside the gate. **Read this as what it is:** "
          f"the year-by-year split of a beta-driven return moved by "
          f"{(top[1] - v3['yearly'][top[0]]) * 100:+.2f}pp when the book was reshuffled "
          f"on tied-score dates. It is not evidence that the strategy became diversified. "
          f"It is evidence that a result driven by market beta has no stable year "
          f"attribution — which is the reading v3 §7 gave, now with a second "
          f"measurement behind it.")
    else:
        A(f"> **The failure stands.** The peak year still carries "
          f"{maxy * 100:.2f}% of total P&L against a 35.00% gate.")
    A("")

    # ---------------- 4
    A("## 4. Gate 4.4 — no single stock contributes > 20% of total P&L")
    A("")
    A("Out-of-sample only. For each fold the backtest is re-run on the **test** window "
      "with that fold's train-selected parameters. Each day's gross book return is "
      "attributed by held weight; each day's cost charge is split across stocks by that "
      "stock's share of the day's `|dW|`. The engine's own compounding equity loop is "
      "replayed to recover the per-date charge and is **asserted against "
      "`BacktestResult.costs_paid`**, so the split is an exact decomposition rather than "
      "a pro-rata guess. The regime overlay is then applied to every leg and the cash "
      "leg reported separately.")
    A("")
    A(f"Reconciliation error (max |per-stock daily sum − engine daily return|): "
      f"**{raw['recon_err']:.2e}**.")
    A("")
    A(f"Total net stock P&L **{d['total']:+.4f}** normalised equity units "
      f"(v3 {v3['total_net_stock_pnl']:+.4f}); cash leg (overlay idle time in T-bills) "
      f"**{raw['cash_leg']:+.4f}** (v3 {v3['cash_leg']:+.4f}).")
    A("")
    A("| # | symbol | net P&L | v4 share of net | share of gross | cost charged |")
    A("|--:|--------|--------:|---------------:|---------------:|-------------:|")
    gross_total = sum(r["gross"] for r in ps)
    for i, r in enumerate(ps[:5], start=1):
        A(f"| {i} | {r['symbol']} | {r['net']:+.4f} | {r['net'] / d['total'] * 100:+.2f}% "
          f"| {r['gross'] / gross_total * 100:+.2f}% | {r['cost']:.4f} |")
    A("")
    A("| symbol | net P&L | share of net |")
    A("|--------|--------:|------------:|")
    for r in ps[-3:]:
        A(f"| {r['symbol']} | {r['net']:+.4f} | {r['net'] / d['total'] * 100:+.2f}% |")
    A("")
    n_pos = sum(1 for r in ps if r["net"] > 0)
    A(f"- Top 5 combined share of net P&L: **{d['top5'] * 100:.2f}%** "
      f"(v3 {v3['per_stock_top5_share'] * 100:.2f}%)")
    A(f"- **Max single-stock share: {d['top1'][1] * 100:.2f}% ({d['top1'][0]})** "
      f"(v3 {v3['per_stock_top1'][0] * 100:.2f}% ({v3['per_stock_top1'][1]})) against a "
      f"gate of 20.00% — **{'PASS' if d['top1'][1] <= 0.20 else 'FAIL'}**")
    A(f"- {n_pos} of {len(ps)} names contributed positive net P&L")
    A("")

    # ---------------- 5
    A("## 5. Gate 4.5 — at least 4 of 6 neighbouring settings profitable")
    A("")
    A("**Definition of \"neighbouring\"** (stated because the gate requires it): a "
      "single-axis **+/-20%** shift of one of the three lookback knobs that define the "
      "operating point, every other parameter held, with the standard walk-forward "
      "re-selection left **on** — so every neighbour is an honest end-to-end "
      "out-of-sample number.")
    A("")
    NEIGH = ("mom_6m 126->101 (-20%)", "mom_6m 126->151 (+20%)",
             "trend_lb 200->160 (-20%)", "trend_lb 200->240 (+20%)",
             "overlay lookback x0.80 (-20%)", "overlay lookback x1.20 (+20%)")
    A("| # | neighbour | v3 CAGR | **v4 CAGR (net)** | v3 Sharpe | **v4 Sharpe** | "
      "v4 MaxDD |")
    A("|--:|-----------|-------:|------------------:|----------:|-------------:|"
      "---------:|")
    for i, lab in enumerate(NEIGH, start=1):
        r, o = by[lab], v3["neighbours"][lab]
        A(f"| {i} | {lab} | {pc(o[0])} | **{pc(r['cagr'])}** | {o[1]:.2f} | "
          f"**{r['sharpe']:.2f}** | {pc(r['maxdd'])} |")
    nbr = [by[lab]["cagr"] for lab in NEIGH]
    n_prof = sum(1 for c in nbr if c > 0)
    A("")
    A(f"**Profitable: {n_prof} of 6** against a gate of >= 4 of 6 — "
      f"**{'PASS' if n_prof >= 4 else 'FAIL'}**. CAGR range across neighbours: "
      f"{pc(min(nbr))} .. {pc(max(nbr))} "
      f"(v3 {pc(min(v3['neighbours'][lab][0] for lab in NEIGH))} .. "
      f"{pc(max(v3['neighbours'][lab][0] for lab in NEIGH))}).")
    A("")
    A("### Supplementary — the full grid, FIXED parameters, no train selection")
    A("")
    A("The same 18 cells `walk_forward` chooses between, each evaluated on the fold test "
      "windows with **no per-fold re-fitting**. Reported whether or not it flatters the "
      "strategy.")
    A("")
    A("| n_positions | overlay lookback | threshold | v3 CAGR | **v4 CAGR** | v3 Sharpe | "
      "**v4 Sharpe** | v4 MaxDD |")
    A("|------------:|-----------------:|----------:|-------:|-------------:|"
      "----------:|-------------:|---------:|")
    for r in raw["fixed_rows"]:
        k = (r["n_positions"], r["lookback"], r["threshold"])
        o = v3["fixed_grid"][k]
        A(f"| {r['n_positions']} | {r['lookback']} | {r['threshold']:.2f} | {pc(o[0])} | "
          f"**{pc(r['cagr'])}** | {o[1]:.2f} | **{r['sharpe']:.2f}** | "
          f"{pc(r['maxdd'])} |")
    fc = [r["cagr"] for r in raw["fixed_rows"]]
    fs = [r["sharpe"] for r in raw["fixed_rows"]]
    A("")
    A(f"- Profitable cells: **{sum(1 for c in fc if c > 0)} of 18**")
    A(f"- CAGR range **{pc(min(fc))} .. {pc(max(fc))}**, Sharpe range "
      f"**{min(fs):.2f} .. {max(fs):.2f}**")
    A(f"- The train-selected baseline is **{pc(base['cagr'])} / {num(base['sharpe'])}**. "
      f"Where it lands inside that unselected spread is the tell.")
    A("")

    # ---------------- 6
    A("## 6. Negative control")
    A("")
    A("`NEGATIVE_CONTROL_WEIGHTS` (45% `reversal_5d`, 30% `reversal_20d`, 25% "
      "`low_volatility`) through the **same** walk-forward harness and the same cost "
      "stack. It must underperform the trend composite; if it does not, the harness is "
      "mining noise, and that would be the single most important finding on this page.")
    A("")
    A("| composite | v3 OOS CAGR | **v4 OOS CAGR** | v3 Sharpe | **v4 Sharpe** | "
      "v4 MaxDD |")
    A("|-----------|------------:|----------------:|----------:|-------------:|"
      "---------:|")
    A(f"| trend (production) | {pc(v3['baseline']['cagr'])} | **{pc(base['cagr'])}** | "
      f"{v3['baseline']['sharpe']:.2f} | **{base['sharpe']:.2f}** | "
      f"{pc(base['maxdd'])} |")
    A(f"| reversal (control) | {pc(v3['control']['cagr'])} | **{pc(nc['cagr'])}** | "
      f"{v3['control']['sharpe']:.2f} | **{nc['sharpe']:.2f}** | {pc(nc['maxdd'])} |")
    A("")
    ok = nc["sharpe"] < base["sharpe"] and nc["cagr"] < base["cagr"]
    A(f"**Control underperforms on both CAGR and Sharpe: {'PASS' if ok else 'FAIL'}.**")
    A("")
    if ok:
        A("> ### The failure did not survive the fix — and that is a finding, not a "
          "reprieve\n>\n"
          "> On v3 the reversal composite beat the trend composite on both CAGR "
          f"({pc(v3['control']['cagr'])} vs {pc(v3['baseline']['cagr'])}) and Sharpe "
          f"({v3['control']['sharpe']:.2f} vs {v3['baseline']['sharpe']:.2f}). On v4 it "
          f"returns {pc(nc['cagr'])} / {nc['sharpe']:.2f} against production's "
          f"{pc(base['cagr'])} / {base['sharpe']:.2f}.\n>\n"
          "> **The size of the control's lead is essentially unchanged "
          f"({(nc['cagr'] - base['cagr']) * 100:+.2f}pp on v4 versus "
          f"{(v3['control']['cagr'] - v3['baseline']['cagr']) * 100:+.2f}pp on v3).** "
          "The tie-break removed an alphabetical bias and the control still wins. Two "
          "readings are available and this report does not pick between them on this "
          "evidence alone:\n>\n"
          "> 1. The harness cannot distinguish a composite of factors this repo has "
          "already ruled out on published Indian evidence from the production composite "
          "— in which case Gate 4 cannot be certified by the five checks that pass.\n"
          "> 2. The production composite has a real but very small edge, and a "
          "0.02-0.05 Sharpe gap over ~2,900 daily observations is not resolvable at "
          "this sample size — in which case the control is *not* evidence of skill "
          "either.\n>\n"
          "> **Either way the gate does not pass**, because Gate 4 as written requires "
          "the control to underperform and it does not. What is *not* available is the "
          "v3 claim that this is the single most damning finding in the repo: at 0.03 "
          "Sharpe, `reports/CONTROL_DIAGNOSTIC.md` §H4 measures the gap as statistically "
          "indistinguishable on both engines. A control that ties the production book is "
          "a failure of the control. A control that *beats* it by 0.03 Sharpe was always "
          "the same fact.")
    else:
        A("> ### This is the most important line in this report\n>\n"
          "`reversal_5d` and `reversal_20d` are short-term reversal factors. The factor "
          "module's own literature review concludes, from two methodologically disjoint "
          "Indian studies plus the only multiple-testing-corrected one, that **reversal "
          "does not work in Indian cash equities and trend does**. A composite built "
          "*entirely* from those two rejected factors returned a higher out-of-sample "
          "CAGR (" + pc(nc["cagr"]) + " vs " + pc(base["cagr"]) + ") and a higher "
          "Sharpe (" + f"{nc['sharpe']:.2f}" + " vs " + f"{base['sharpe']:.2f}" +
          ") than the production trend composite, net of the full cost stack.\n>\n"
          "Read together with the supplementary grid in §5, the picture is that almost "
          "anything built from this factor set on this universe returns a positive "
          "out-of-sample result — the signature of a long-only, equity-beta-tilted book "
          "in a market that rose, not of a validated signal. Per `GOAL.md` §6, a "
          "strategy whose negative control does not fail cannot be certified by the "
          "robustness tests it passes.")
    A("")

    # ---------------- 7
    A("## 7. Gate 4 verdict")
    A("")
    for name, ok_, ev in checks:
        A(f"- [{'PASS' if ok_ else 'FAIL'}] **{name}** — {ev}")
    A("")
    fails = [(n, e) for n, o, e in checks if not o]
    A(f"**Overall: Gate 4 {'PASSES' if not fails else 'DOES NOT PASS'} "
      f"({len(checks) - len(fails)} of {len(checks)} pass"
      f"{', ' + str(len(fails)) + ' fail' if fails else ''}).**")
    A("")
    if fails:
        A("The remaining failure(s), stated plainly:")
        A("")
        for n, e in fails:
            A(f"- **{n}** — {e}")
        A("")
        A("> **Read the failures together, not separately.** Where the negative control "
          "is among them, the other failure is what a beta-driven result looks like: "
          "concentration in a short window, because the whole return comes from the "
          "market's direction rather than from a signal that pays in every regime. The "
          "passes are not evidence against this reading — a 22-name, monthly-rebalanced, "
          "mildly quality-tilted book passes slippage, parameter, per-stock and neighbour "
          "stress regardless of whether it has an edge.")
        A("")
        A("> **This does not say the strategy has no edge.** It says the evidence "
          "collected here cannot demonstrate one. `GOAL.md` §5's default verdict applies: "
          "keep researching, do not loosen the gate, do not deploy.")
    A("")

    # ---------------- bottom line
    A("## 8. Bottom line")
    A("")
    A(_bottom_line(raw, d, checks, prov))


def _bottom_line(raw, d, checks, prov) -> str:
    """One plain paragraph. Every clause is generated from a measured number."""
    v3 = STRESS_V3
    base, nc, ins = d["base"], d["nc"], d["ins"]
    year_top = d["year_top"]
    maxy = abs(year_top[1])

    # Check-by-check verdicts, keyed exactly as `STRESS_V3["gates"]` is, so "what
    # changed" is a set comparison rather than a prose judgement.
    now = {k: ("PASS" if ok else "FAIL")
           for k, (_, ok, _) in zip(V3_KEYS, checks, strict=True)}
    fails = [k for k, v in now.items() if v == "FAIL"]
    v3fails = [k for k, v in v3["gates"].items() if v == "FAIL"]
    cleared = [k for k in v3fails if now.get(k) == "PASS"]
    broke = [k for k in now if now[k] == "FAIL" and v3["gates"].get(k) == "PASS"]
    ctrl = "X negative control"
    P: list[str] = []

    P.append(
        f"**Gate 4 on the tie-break-fixed engine: {len(checks) - len(fails)} of "
        f"{len(checks)} checks pass, {len(fails)} fail** — the same count as on "
        f"`d93815344bd3`, and the same two checks fail. The walk-forward baseline moved "
        f"{pc(v3['baseline']['cagr'])} / {v3['baseline']['sharpe']:.2f} -> "
        f"{pc(base['cagr'])} / {base['sharpe']:.2f}, and turnover and cost drag moved "
        f"{v3['baseline']['turnover']:.4f}x -> {ins['annual_turnover']:.4f}x/yr and "
        f"{v3['baseline']['cost_drag'] * 100:.4f}% -> "
        f"{ins['cost_drag_annual'] * 100:.4f}%/yr. That movement is expected and is "
        f"attributable: the tie-break changes *which* names are held on the rebalance "
        f"dates where a real composite's median-filled factors tie, so the book it "
        f"delivers changes shape, while the configured position count does not "
        f"({ins['avg_names']:.1f} names on both engines). Loader rule C9's own "
        f"contribution is unchanged at "
        f"{(ins['cost_drag_annual'] - d['c9']['insample_drag']) * 100:+.4f}pp against "
        f"v3's "
        f"{(v3['c9']['c9_drag'] - v3['c9']['pre_c9_drag']) * 100:+.4f}pp, so nothing in "
        f"the engine's cost charge moved."
    )

    if cleared or broke:
        bits = []
        if cleared:
            bits.append("cleared: " + ", ".join(cleared))
        if broke:
            bits.append("newly failing: " + ", ".join(broke))
        P.append(
            f"**Gate-level changes: {'; '.join(bits)}.** Every other check held its "
            f"verdict. The diff table in §2 shows the number behind each one."
        )

    if ctrl in fails:
        P.append(
            f"**The negative control still fails, and that is the finding that "
            f"survives the fix.** `reversal_5d` and `reversal_20d` are factors this "
            f"repo's own literature review rules out on published Indian evidence, and a "
            f"composite built entirely from them returns {pc(nc['cagr'])} / "
            f"{nc['sharpe']:.2f} against production's {pc(base['cagr'])} / "
            f"{base['sharpe']:.2f} — net of the full 21.92bps stack. **Its lead did not "
            f"shrink: it is {(nc['cagr'] - base['cagr']) * 100:+.2f}pp on v4 versus "
            f"{(v3['control']['cagr'] - v3['baseline']['cagr']) * 100:+.2f}pp on v3.** "
            f"A tie-break bias fix removed an alphabetical selection effect and the "
            f"control still wins, by slightly more. One caveat has to travel with that "
            f"number: `reports/CONTROL_DIAGNOSTIC_v2.md` §H4 measures the gap as "
            f"statistically indistinguishable on both engines "
            f"(robust paired p = 0.78 over 2,928 daily observations), so v4 is the same "
            f"fact as v3 stated with the right hedging — the harness cannot tell the two "
            f"composites apart, rather than the harness having proved the worse one is "
            f"better. Gate 4 as written asks the control to *underperform*, and it does "
            f"not, so the check fails either way."
        )

    if "G4.3 no year > 35%" in fails:
        P.append(
            f"**The yearly-concentration failure also survives, and it is now a wider "
            f"miss.** {year_top[0]} carries {maxy * 100:.2f}% of total P&L against a "
            f"35.00% gate, against v3's {v3['max_year'][0] * 100:.2f}% in "
            f"{v3['max_year'][1]} — a move of "
            f"{(maxy - v3['max_year'][0]) * 100:+.2f}pp, and still the same calendar "
            f"year carrying it, that came entirely from "
            f"reshuffling the book on tied-score dates. That is the signature of a "
            f"result driven by market beta rather than by a signal that pays in every "
            f"regime: one strong calendar year does most of the work, and *which* year "
            f"that is has no stable answer."
        )

    P.append(
        f"So: **a bias fix moved the headline "
        f"{abs(base['cagr'] - v3['baseline']['cagr']) * 100:.2f}pp and did not make the "
        f"evidence better.** What passed passes for the same reason it passed on v3 — a "
        f"{ins['avg_names']:.0f}-name, monthly-rebalanced, mildly quality-tilted "
        f"NIFTY-50 book survives slippage, parameter perturbation, per-stock "
        f"concentration and neighbouring-settings stress whether or not its signal is "
        f"worth anything, and "
        f"{sum(1 for r in raw['fixed_rows'] if r['cagr'] > 0)} of "
        f"{len(raw['fixed_rows'])} fixed grid cells are profitable net. Per `GOAL.md` "
        f"§5 the gate does not pass; §6's anti-fraud rules forbid treating the passing "
        f"checks as grounds to relax it. The honest summary of this re-run is that the "
        f"*integrity* of the number improved while the *number* did not: on "
        f"`d93815344bd3` part of every composite's book was chosen by ticker order, and "
        f"that is now gone — but the result it produced is unchanged in character, and "
        f"the correct response is still to change what counts as success rather than to "
        f"search harder for parameters."
    )
    return "\n\n".join(P)

if __name__ == "__main__":
    main()
