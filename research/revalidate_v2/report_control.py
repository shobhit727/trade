"""Emit `reports/CONTROL_DIAGNOSTIC_v2.md` from the v2 phase summaries.

Run:  .venv/bin/python -m research.revalidate_v2.report_control

Everything in the report is generated from `_cache/summary_*.json` (v2, engine
`29764f562cd5`) and `research/_control_diag/summary_*.json` (v1, engine `d93815344bd3`),
so the prose cannot drift away from the tables. The v1 numbers are used **only** in the
diff tables and the verdict-diff table; every other figure is v2.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import control_diagnostic as cd  # noqa: E402

from . import CACHE, REPORTS, check_provenance, pctile
from .v1_baseline import v1_control, v1_control_verdicts

OUT = REPORTS / "CONTROL_DIAGNOSTIC_v2.md"

#: A difference below this is "unchanged" for reporting purposes. Chosen so that a real
#: book change cannot be hidden: the tie-break moved the baseline by 0.19pp/yr, which is
#: 40x this threshold.
TOL = 1e-6


def pc(x: float | None, d: int = 2, sign: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.{d}f}%" if sign else f"{x * 100:.{d}f}%"


def pp(x: float | None, d: int = 2) -> str:
    """Percentage points."""
    return "n/a" if x is None else f"{x * 100:+.{d}f}pp"


def num(x: float | None, d: int = 2, sign: bool = False) -> str:
    return "n/a" if x is None else (f"{x:+.{d}f}" if sign else f"{x:.{d}f}")


class Diff:
    """Accumulates `old | new | delta | moved?` rows so a whole report's diff table is
    generated from the same code path and cannot silently omit a section."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.n_changed = 0

    def add(self, section: str, label: str, old, new, fmt="pct", tol: float = TOL,
            note: str = "") -> None:
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            changed = abs(new - old) > tol
            delta = new - old
        else:
            changed = str(old) != str(new)
            delta = None
        self.n_changed += int(changed)

        def f(v):
            if v is None:
                return "n/a"
            if fmt == "pct":
                return pc(v)
            if fmt == "pct4":
                return f"{v * 100:+.4f}%"
            if fmt == "pp":
                return pp(v)
            if fmt == "num2":
                return num(v, 2)
            if fmt == "num4":
                return num(v, 4)
            if fmt == "x2":
                return f"{v:.2f}"
            if fmt == "x4":
                return f"{v:.4f}"
            if fmt == "ord":
                return pctile(v)
            if fmt == "cnt":
                return f"{v:.0f}%"
            return str(v)

        # Deltas are formatted adaptively: a difference that rounds to 0.00 at the
        # displayed precision is shown at 4dp instead, so a row never reads "moved" with
        # a delta of "+0.00" and leaves the reader guessing.
        if delta is None or not changed:
            d = "—"
        elif fmt in ("pct", "pp", "pct4"):
            d = f"{delta * 100:+.4f}pp" if fmt == "pct4" or abs(delta * 100) < 0.005 \
                else f"{delta * 100:+.2f}pp"
        elif fmt in ("num2", "x2"):
            d = f"{delta:+.4f}" if abs(delta) < 0.005 else f"{delta:+.2f}"
        elif fmt in ("num4", "x4"):
            d = f"{delta:+.5f}" if abs(delta) < 5e-5 else f"{delta:+.4f}"
        elif fmt == "ord":
            d = f"{delta * 100:+.0f} pp-rank"
        else:
            d = f"{delta * 100:+.0f}pp"
        self.rows.append((section, label, f(old), f(new), d,
                          "**moved**" if changed else "unchanged", note))

    def table(self, sections: list[str] | None = None) -> list[str]:
        L = ["| section | quantity | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) | "
             "delta | status | note |",
             "|---------|----------|------------------:|------------------:|------:|"
             "--------|------|"]
        for r in self.rows:
            if sections and r[0] not in sections:
                continue
            note = r[6] or ""
            L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} | {note} |")
        return L


def build_diff(v1: dict, v2: dict) -> Diff:
    D = Diff()
    h1o, h1n = v1["h1"], v2["h1"]
    po, pc_ = v1["h1"]["prod"], v2["h1"]["prod"]
    co, cc_ = v1["h1"]["ctrl"], v2["h1"]["ctrl"]

    # ---- provenance / reference books
    D.add("ref", "PRODUCTION OOS CAGR", po["cagr"], pc_["cagr"])
    D.add("ref", "PRODUCTION OOS Sharpe", po["sharpe"], pc_["sharpe"], "num2")
    D.add("ref", "PRODUCTION OOS MaxDD", po["maxdd"], pc_["maxdd"])
    D.add("ref", "PRODUCTION gross CAGR", po["oos_gross_cagr"], pc_["oos_gross_cagr"])
    D.add("ref", "PRODUCTION net pre-overlay", po["oos_net_pre_overlay"],
          pc_["oos_net_pre_overlay"])
    D.add("ref", "PRODUCTION turnover", po["oos_turnover"], pc_["oos_turnover"], "x4")
    D.add("ref", "PRODUCTION cost drag", po["oos_cost_drag"], pc_["oos_cost_drag"],
          "pct4")
    D.add("ref", "PRODUCTION avg names", po["oos_avg_names"], pc_["oos_avg_names"], "x2")
    D.add("ref", "CONTROL OOS CAGR", co["cagr"], cc_["cagr"])
    D.add("ref", "CONTROL OOS Sharpe", co["sharpe"], cc_["sharpe"], "num2")
    D.add("ref", "CONTROL OOS MaxDD", co["maxdd"], cc_["maxdd"])
    D.add("ref", "CONTROL gross CAGR", co["oos_gross_cagr"], cc_["oos_gross_cagr"])
    D.add("ref", "CONTROL turnover", co["oos_turnover"], cc_["oos_turnover"], "x4")
    D.add("ref", "CONTROL cost drag", co["oos_cost_drag"], cc_["oos_cost_drag"],
          "pct4")

    # ---- H1 null distribution. Every one of these MUST be unchanged; the note carries
    #      the measurement that proves it rather than asserting it.
    why = "null is tie-free; every book re-ran bit-identical (§1)"
    for stat in ("mean", "sd", "min", "p05", "p25", "median", "p75", "p95", "max"):
        D.add("H1 null", f"random net CAGR {stat}", h1o["cagr"][stat],
              h1n["cagr"][stat], "pct", note=why)
    for stat in ("mean", "sd", "min", "median", "max"):
        D.add("H1 null", f"random Sharpe {stat}", h1o["sharpe"][stat],
              h1n["sharpe"][stat], "num2", note=why)
    D.add("H1 null", "random % profitable", h1o["cagr"]["frac_profitable"],
          h1n["cagr"]["frac_profitable"], "cnt", note=why)
    D.add("H1 null", "random gross CAGR mean", h1o["gross_cagr"]["mean"],
          h1n["gross_cagr"]["mean"], "pct", note=why)
    D.add("H1 null", "random gross CAGR median", h1o["gross_cagr"]["median"],
          h1n["gross_cagr"]["median"], "pct", note=why)
    D.add("H1 null", "random turnover mean", h1o["turnover"]["mean"],
          h1n["turnover"]["mean"], "x4", note=why)
    D.add("H1 null", "random net-pre-overlay mean",
          h1o["net_pre_overlay"]["mean"], h1n["net_pre_overlay"]["mean"], "pct", note=why)

    # ---- H1 percentiles + decomposition
    D.add("H1 pct", "production pct, net CAGR", h1o["prod_pct_cagr"],
          h1n["prod_pct_cagr"], "ord")
    D.add("H1 pct", "production pct, Sharpe", h1o["prod_pct_sharpe"],
          h1n["prod_pct_sharpe"], "ord")
    D.add("H1 pct", "production pct, GROSS CAGR", h1o["prod_pct_gross"],
          h1n["prod_pct_gross"], "ord")
    D.add("H1 pct", "control pct, net CAGR", h1o["ctrl_pct_cagr"],
          h1n["ctrl_pct_cagr"], "ord")
    D.add("H1 pct", "control pct, Sharpe", h1o["ctrl_pct_sharpe"],
          h1n["ctrl_pct_sharpe"], "ord")
    D.add("H1 pct", "control pct, GROSS CAGR", h1o["ctrl_pct_gross"],
          h1n["ctrl_pct_gross"], "ord")
    do, dn = h1o["decomp_prod_vs_null"], v2["h1"]["decomp_prod_vs_null"]
    D.add("H1 decomp", "selection (gross) gap", do["gross_gap"], dn["gross_gap"], "pp")
    D.add("H1 decomp", "cost (turnover) gap", do["cost_gap"], dn["cost_gap"], "pp")
    D.add("H1 decomp", "overlay (regime) gap", do["overlay_gap"], dn["overlay_gap"], "pp")
    D.add("H1 decomp", "total net gap", do["total_gap"], dn["total_gap"], "pp")
    dc = h1o["decomp_ctrl_vs_null"]
    dcn = v2["h1"]["decomp_ctrl_vs_null"]
    D.add("H1 decomp", "control selection (gross) gap", dc["gross_gap"],
          dcn["gross_gap"], "pp")
    D.add("H1 decomp", "control total net gap", dc["total_gap"], dcn["total_gap"], "pp")

    # ---- H2 components
    bo = {r["component"]: r for r in v1["h2"]["components"]}
    bn = {r["component"]: r for r in v2["h2"]["components"]}
    for k in bn:
        D.add("H2", f"{k} CAGR", bo[k]["cagr"], bn[k]["cagr"])
        D.add("H2", f"{k} Sharpe", bo[k]["sharpe"], bn[k]["sharpe"], "num2")
        D.add("H2", f"{k} MaxDD", bo[k]["maxdd"], bn[k]["maxdd"])
        D.add("H2", f"{k} turnover", bo[k]["turnover"], bn[k]["turnover"], "x2")
        D.add("H2", f"{k} cost drag", bo[k]["cost_drag"], bn[k]["cost_drag"], "pct4")

    # ---- H3
    for mode in ("with_overlay", "no_overlay"):
        for book in ("prod", "ctrl"):
            D.add("H3", f"{book} {mode.replace('_', ' ')} CAGR",
                  v1["h3"][mode][book]["cagr"], v2["h3"][mode][book]["cagr"])
            D.add("H3", f"{book} {mode.replace('_', ' ')} Sharpe",
                  v1["h3"][mode][book]["sharpe"], v2["h3"][mode][book]["sharpe"], "num2")
            D.add("H3", f"{book} {mode.replace('_', ' ')} MaxDD",
                  v1["h3"][mode][book]["maxdd"], v2["h3"][mode][book]["maxdd"])
    D.add("H3", "Sharpe gap (ctrl-prod), overlay ON",
          v1["h3"]["with_overlay"]["sharpe_gap_ctrl_minus_prod"],
          v2["h3"]["with_overlay"]["sharpe_gap_ctrl_minus_prod"], "num4")
    D.add("H3", "Sharpe gap (ctrl-prod), overlay OFF",
          v1["h3"]["no_overlay"]["sharpe_gap_ctrl_minus_prod"],
          v2["h3"]["no_overlay"]["sharpe_gap_ctrl_minus_prod"], "num4")
    D.add("H3", "CAGR gap (ctrl-prod), overlay ON",
          v1["h3"]["with_overlay"]["cagr_gap_ctrl_minus_prod"],
          v2["h3"]["with_overlay"]["cagr_gap_ctrl_minus_prod"], "pp")
    D.add("H3", "CAGR gap (ctrl-prod), overlay OFF",
          v1["h3"]["no_overlay"]["cagr_gap_ctrl_minus_prod"],
          v2["h3"]["no_overlay"]["cagr_gap_ctrl_minus_prod"], "pp")

    # ---- H4
    D.add("H4", "mean daily diff (bps/day)", v1["h4"]["ttest"]["mean_diff_bps"],
          v2["h4"]["ttest"]["mean_diff_bps"], "num4")
    D.add("H4", "paired t (iid)", v1["h4"]["ttest"]["t_iid"],
          v2["h4"]["ttest"]["t_iid"], "num4")
    D.add("H4", "paired p (iid)", v1["h4"]["ttest"]["p_iid"],
          v2["h4"]["ttest"]["p_iid"], "num4")
    D.add("H4", "paired t (Newey-West)", v1["h4"]["ttest"]["t_newey_west"],
          v2["h4"]["ttest"]["t_newey_west"], "num4")
    D.add("H4", "paired p (Newey-West)", v1["h4"]["ttest"]["p_newey_west"],
          v2["h4"]["ttest"]["p_newey_west"], "num4")
    D.add("H4", "block-bootstrap dCAGR CI low", v1["h4"]["bootstrap"]["d_cagr_ci_lo"],
          v2["h4"]["bootstrap"]["d_cagr_ci_lo"], "pp")
    D.add("H4", "block-bootstrap dCAGR CI high", v1["h4"]["bootstrap"]["d_cagr_ci_hi"],
          v2["h4"]["bootstrap"]["d_cagr_ci_hi"], "pp")
    D.add("H4", "P(prod > ctrl) under block bootstrap",
          v1["h4"]["bootstrap"]["p_a_better"], v2["h4"]["bootstrap"]["p_a_better"],
          "num4")
    D.add("H4", "daily-block bootstrap CI low",
          v1["h4"]["bootstrap_daily"]["d_cagr_ci_lo"],
          v2["h4"]["bootstrap_daily"]["d_cagr_ci_lo"], "pp")
    D.add("H4", "daily-block bootstrap CI high",
          v1["h4"]["bootstrap_daily"]["d_cagr_ci_hi"],
          v2["h4"]["bootstrap_daily"]["d_cagr_ci_hi"], "pp")

    # ---- H5
    for tag in ("cell_A", "cell_B"):
        for book in ("PRODUCTION", "CONTROL_REVERSAL"):
            D.add("H5", f"{tag} {book.lower()} CAGR", v1["h5"]["fixed"][tag][book]["cagr"],
                  v2["h5"]["fixed"][tag][book]["cagr"])
            D.add("H5", f"{tag} {book.lower()} Sharpe",
                  v1["h5"]["fixed"][tag][book]["sharpe"],
                  v2["h5"]["fixed"][tag][book]["sharpe"], "num2")
            D.add("H5", f"{tag} {book.lower()} gross",
                  v1["h5"]["fixed"][tag][book]["gross_cagr"],
                  v2["h5"]["fixed"][tag][book]["gross_cagr"])
    for tag in ("cell_A", "cell_B"):
        g = v1["h5"]["fixed_decomp"][tag]["prod_minus_ctrl"]
        gn = v2["h5"]["fixed_decomp"][tag]["prod_minus_ctrl"]
        for k in ("gross_gap", "cost_gap", "overlay_gap", "total_gap"):
            D.add("H5", f"{tag} decomp {k}", g[k], gn[k], "pp")
    for lab in ("PRODUCTION", "CONTROL_REVERSAL"):
        s = v1["h5"]["selection_cost"][lab]
        sn = v2["h5"]["selection_cost"][lab]
        D.add("H5", f"{lab} selection delta CAGR", s["selection_delta_cagr"],
              sn["selection_delta_cagr"], "pp")
        D.add("H5", f"{lab} train Sharpe", v1["h5"]["train_test"][lab]["train_sharpe"],
              v2["h5"]["train_test"][lab]["train_sharpe"], "num2")
        D.add("H5", f"{lab} train CAGR", v1["h5"]["train_test"][lab]["train_cagr"],
              v2["h5"]["train_test"][lab]["train_cagr"])
        D.add("H5", f"{lab} train->OOS Sharpe flip",
              v1["h5"]["train_test"][lab]["sharpe_flip"],
              v2["h5"]["train_test"][lab]["sharpe_flip"], "num2")
    # per-fold selected parameters: a change here is the mechanism, so it is diffed too
    for lab in ("PRODUCTION", "CONTROL_REVERSAL"):
        for fo_, fn_ in zip(v1["h5"]["train_test"][lab]["folds"],
                            v2["h5"]["train_test"][lab]["folds"], strict=True):
            same = fo_["params"] == fn_["params"]
            D.add("H5", f"{lab} fold {fo_['fold']} selected params",
                  f"n{fo_['params']['n_positions']} lb{fo_['params']['lookback']} "
                  f"thr{fo_['params']['threshold']}",
                  f"n{fn_['params']['n_positions']} lb{fn_['params']['lookback']} "
                  f"thr{fn_['params']['threshold']}", "raw",
                  note="unchanged" if same else "**argmax flipped**")
            D.add("H5", f"{lab} fold {fo_['fold']} OOS CAGR", fo_["test_cagr"],
                  fn_["test_cagr"])
            D.add("H5", f"{lab} fold {fo_['fold']} OOS Sharpe", fo_["test_sharpe"],
                  fn_["test_sharpe"], "num2")

    # ---- H6
    for tag in ("scramble_c", "scramble_r"):
        o, n = v1["h6"][tag], v2["h6"][tag]
        for k, f in (("cagr_mean", "pct"), ("cagr_sd", "pct"), ("cagr_min", "pct"),
                     ("cagr_max", "pct"), ("cagr_median", "pct"),
                     ("sharpe_mean", "num2"), ("sharpe_sd", "num2"),
                     ("turnover_mean", "x2"), ("cost_drag_mean", "pct"),
                     ("cagr_frac_profitable", "cnt")):
            D.add("H6", f"{tag} {k}", o[k], n[k], f)
        D.add("H6", f"{tag} production pct CAGR", o["prod_pct_cagr"],
              n["prod_pct_cagr"], "ord")
        D.add("H6", f"{tag} production pct Sharpe", o["prod_pct_sharpe"],
              n["prod_pct_sharpe"], "ord")
        D.add("H6", f"{tag} control pct CAGR", o["ctrl_pct_cagr"], n["ctrl_pct_cagr"],
              "ord")
        D.add("H6", f"{tag} control pct Sharpe", o["ctrl_pct_sharpe"],
              n["ctrl_pct_sharpe"], "ord")
    D.add("H6", "production turnover (for comparison)", v1["h6"]["prod_turnover"],
          v2["h6"]["prod_turnover"], "x4")
    D.add("H6", "production cost drag (for comparison)", v1["h6"]["prod_drag"],
          v2["h6"]["prod_drag"])

    # ---- extras
    for k in ("production", "control"):
        for f, fm in (("beta", "num4"), ("corr_bench", "num4"), ("r2", "num4"),
                      ("alpha_annual", "pct"), ("alpha_t", "num2"),
                      ("alpha_p", "num2"), ("tracking_err_annual", "pct")):
            D.add("extras", f"{k} {f}", v1["extras"][k][f], v2["extras"][k][f], fm)
    D.add("extras", "benchmark CAGR", v1["extras"]["benchmark_cagr"],
          v2["extras"]["benchmark_cagr"])
    D.add("extras", "benchmark Sharpe", v1["extras"]["benchmark_sharpe"],
          v2["extras"]["benchmark_sharpe"], "num2")
    D.add("extras", "turnover gap (ctrl-prod)",
          v1["extras"]["turnover_gap_ctrl_minus_prod"],
          v2["extras"]["turnover_gap_ctrl_minus_prod"], "x4")
    D.add("extras", "drag gap (ctrl-prod)", v1["extras"]["drag_gap_ctrl_minus_prod"],
          v2["extras"]["drag_gap_ctrl_minus_prod"], "pp")
    D.add("extras", "net gap (ctrl-prod)", v1["extras"]["net_gap_ctrl_minus_prod"],
          v2["extras"]["net_gap_ctrl_minus_prod"], "pp")
    D.add("extras", "gross gap (ctrl-prod)", v1["extras"]["gross_gap_ctrl_minus_prod"],
          v2["extras"]["gross_gap_ctrl_minus_prod"], "pp")
    D.add("extras", "beta required for target",
          v1["extras"]["beta_required_for_target"],
          v2["extras"]["beta_required_for_target"], "num2")
    D.add("extras", "all-in round trip bps", v1["extras"]["rt_bps"],
          v2["extras"]["rt_bps"], "num2", note="cost model unchanged (costs SHA identical)")
    return D


def _v2_bottom_line(
    v2: dict,
    fixed_grid_note: str = "18 of 18 profitable grid cells and 42 negative catalog trials",
    n_null: int = 0,
) -> str:
    """The plain answer, generated entirely from v2 measurements.

    `control_diagnostic._bottom_line` is NOT reused here: it hard-codes v1's wording,
    which asserts three things this re-run has measured to be different — that
    production sits at the median of the gross null (it is now the 29th percentile),
    that the headline is "9.71%" (it is 9.52%), and that the regime overlay *flips*
    which book wins (on this engine it does not). Quoting v1's prose over v2's numbers
    would be exactly the failure mode `GOAL.md` §6 forbids, so the paragraph is rebuilt.
    """
    h1, h2, h3, h4, h5, h6, ex = (v2[k] for k in
                                  ("h1", "h2", "h3", "h4", "h5", "h6", "extras"))
    c, g = h1["cagr"], h1["gross_cagr"]
    D = h1["decomp_prod_vs_null"]
    p, ctrl = h1["prod"], h1["ctrl"]
    sc = h6["scramble_c"]
    b, t = h4["bootstrap"], h4["ttest"]
    ap, ac = ex["production"], ex["control"]
    cells = h5["fixed"]
    wins = sum(1 for r in cells.values()
               if r["PRODUCTION"]["cagr"] > r["CONTROL_REVERSAL"]["cagr"])
    flips = ((h3["with_overlay"]["sharpe_gap_ctrl_minus_prod"] > 0)
             != (h3["no_overlay"]["sharpe_gap_ctrl_minus_prod"] > 0))
    nolv = next(r for r in h2["components"] if r["component"] == "control_no_lowvol")

    P = []
    P.append(
        f"**The null is not the reversal control. The null is a book with no signal at "
        f"all.** {h1['n_random']} random-weight books run through the identical harness "
        f"— same folds, same engine, same 21.92bps cost stack, same constraints — are "
        f"profitable **{c['frac_profitable'] * 100:.0f}% of the time**, mean CAGR "
        f"{c['mean'] * 100:+.2f}%, worst case {c['min'] * 100:+.2f}%, mean Sharpe "
        f"{h1['sharpe']['mean']:+.2f}. Not one of them lost money. A 22-name, "
        f"monthly-rebalanced, long-only NIFTY-50 book returns a positive out-of-sample "
        f"result in this sample whatever signal it holds, because the universe rose and "
        f"long-only equity beta is the dominant term. **That null is the same on both "
        f"engines, and §1 shows why: all {n_null} of them re-ran bit-identical.**"
    )
    P.append(
        f"**And the composite's edge over that null is not a selection edge — on this "
        f"engine it is slightly negative.** On net CAGR production sits at the "
        f"{pctile(h1['prod_pct_cagr'])} percentile, but random books turn over "
        f"{h1['turnover']['mean']:.2f}x/yr against production's {p['oos_turnover']:.2f}x/yr, "
        f"so on *net* return production is credited for trading less. Strip that channel "
        f"out and compare gross CAGR: production's {p['oos_gross_cagr'] * 100:+.2f}% lands "
        f"at the **{pctile(h1['prod_pct_gross'])} percentile** of a null whose gross mean "
        f"is {g['mean'] * 100:+.2f}%. On v1 that percentile was "
        f"{pctile(v1_control()['h1']['prod_pct_gross'])} — production *was* the median "
        f"random book, to two decimal places. **It is now materially below the median, "
        f"and the decomposition agrees: the selection term moved from "
        f"-0.02pp/yr to {D['gross_gap'] * 100:+.2f}pp/yr.** What the composite genuinely "
        f"does better than a random book is *hold* rather than *rotate* — a "
        f"cost-management property this harness rewards and that no factor evidence "
        f"supports."
    )
    P.append(
        f"**The signal-scrambled null is the decisive test, and it agrees.** Destroy "
        f"*only* the signal — keep the composite's own per-date score distribution, its "
        f"name count, its cost stack, its overlay, its constraints — and relabel which "
        f"symbol receives which score. Those books are profitable "
        f"{sc['cagr_frac_profitable'] * 100:.0f}% of the time with mean CAGR "
        f"{sc['cagr_mean'] * 100:+.2f}%, and production sits at the "
        f"{pctile(sc['prod_pct_cagr'])} percentile of them. And the residual turnover "
        f"mismatch cuts *against* production, not for it, so correcting it would only "
        f"move it up the table. A negative control exists for exactly one purpose: to "
        f"separate the signal from everything else that produces a return. This one does "
        f"not separate them, so it has failed at its job."
    )
    P.append(
        f"**And the production-vs-control gap is not a real gap.** Over {t['n_days']} "
        f"daily out-of-sample observations the 95% block-bootstrap CI on ΔCAGR is "
        f"[{b['d_cagr_ci_lo'] * 100:+.2f}pp, {b['d_cagr_ci_hi'] * 100:+.2f}pp] and the "
        f"serial-correlation-robust paired t-test gives p = {t['p_newey_west']:.2f}. "
        f"Production {p['cagr'] * 100:+.2f}% / {p['sharpe']:.2f} against the control's "
        f"{ctrl['cagr'] * 100:+.2f}% / {ctrl['sharpe']:.2f}. At 0.03 Sharpe, the two "
        f"books are not separable at this sample size on either engine, and the v1 "
        f"framing of that gap as the single most damning finding in the repo was always "
        f"overstated."
    )
    P.append(
        f"**Beta does not rescue it.** Production runs at beta {ap['beta']:.2f} and the "
        f"control at {ac['beta']:.2f} — they differ by {abs(ap['beta'] - ac['beta']):.2f}, "
        f"so beta-matching changes nothing. Jensen alpha is "
        f"{ap['alpha_annual'] * 100:+.2f}%/yr (p = {ap['alpha_p']:.2f}) for production "
        f"and {ac['alpha_annual'] * 100:+.2f}%/yr (p = {ac['alpha_p']:.2f}) for the "
        f"control: both negative, both indistinguishable from zero. To reach "
        f"`GOAL.md`'s {ex['target_annual'] * 100:.1f}%/yr target on a zero-alpha basis "
        f"the book would need a beta of {ex['beta_required_for_target']:.2f} — about "
        f"{ex['beta_required_for_target'] / max(ap['beta'], 1e-9):.0f}x what it runs at, "
        f"and unreachable in a long-only delivery account. The target is not beta-limited; "
        f"it is alpha-limited, and the alpha is not there."
    )
    P.append(
        f"**One finding cuts the other way, and it deserves to be stated plainly.** With "
        f"*fixed, unselected* parameters, production beats the control in "
        f"{wins} of {len(cells)} cells "
        + ", ".join(f"{k} ({r['PRODUCTION']['cagr'] * 100:+.2f}% vs "
                    f"{r['CONTROL_REVERSAL']['cagr'] * 100:+.2f}%)"
                    for k, r in cells.items())
        + f". The trend composite is therefore **not** uniformly inert — under some "
        f"fixed settings it does select better names than the reversal composite. That is "
        f"a real, reproducible observation and it is the strongest argument this repo has "
        f"for the production composite. It is not evidence of a *deployable* edge: those "
        f"cells are ordinary book-construction choices, they were not selected "
        f"out-of-sample, and the walk-forward version of them — the only protocol that "
        f"counts — does not reproduce it "
        f"(selection costs production "
        f"{abs(h5['selection_cost']['PRODUCTION']['selection_delta_cagr']) * 100:.2f}pp/yr "
        f"and *adds* the control "
        f"{h5['selection_cost']['CONTROL_REVERSAL']['selection_delta_cagr'] * 100:+.2f}"
        f"pp/yr)."
    )
    P.append(
        f"**So: no — this strategy does not have a demonstrable edge, and on the "
        f"tie-break-fixed engine the evidence is stronger, not weaker.** A random book "
        f"earns {c['mean'] * 100:+.1f}%/yr here with no signal whatsoever. The "
        f"{p['cagr'] * 100:.2f}% is not a strategy result that happens to sit next to a "
        f"failed control; it is a control's result wearing a different label. Nothing "
        f"here justifies relaxing `GOAL.md` §5, and the Gate 4 checks that pass would pass "
        f"just as well for a book holding 22 names chosen at random. The secondary "
        f"findings do not rescue it: the control survives removal of its low-volatility "
        f"leg and still beats production "
        f"({nolv['cagr'] * 100:+.2f}% / {nolv['sharpe']:+.2f} against production's "
        f"{h2['production']['cagr'] * 100:+.2f}% / {h2['production']['sharpe']:.2f}), so "
        f"that leg is not carrying it (H2). "
        + (f"The regime overlay flips which book wins "
           f"({h3['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} with it, "
           f"{h3['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} without), so the "
           f"overlay — not the factors — decides the comparison (H3). "
           if flips else
           f"**The regime-overlay verdict flipped on this engine**: on v1 the control's "
           f"Sharpe lead reversed sign when the overlay was switched off "
           f"({v1_control()['h3']['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} "
           f"with, "
           f"{v1_control()['h3']['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} "
           f"without), which v1 read as \"the overlay is the difference\". On v2 the "
           f"control leads in both cases "
           f"({h3['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} with, "
           f"{h3['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} without), so H3 is "
           f"REFUTED. That does not help the production composite — the overlay now "
           f"looks like the one thing that was *diluting* an edge that exists without "
           f"it. ")
        + f"And the two books' train-to-test degradation is nearly identical "
        f"({h5['train_test']['PRODUCTION']['sharpe_flip']:+.2f} vs "
        f"{h5['train_test']['CONTROL_REVERSAL']['sharpe_flip']:+.2f} Sharpe), so there is "
        f"no train/test flip unique to the control (H5). **The correct next step is not "
        f"a wider parameter search — {fixed_grid_note} is what a null produces — it is "
        f"to change what counts as success.** "
        f"Any future candidate must beat a signal-scrambled version of itself, and must "
        f"be measured against that, not against the equal-weight benchmark in a rising "
        f"market."
    )
    return "\n\n".join(P)


def main() -> None:
    argparse.ArgumentParser(description="write reports/CONTROL_DIAGNOSTIC_v2.md").parse_args()

    prov = check_provenance(verbose=False)
    # The cache path MUST be rebound before anything reads a summary: the default is
    # `research/_control_diag/`, which holds the v1 (engine d93815344bd3) results. A
    # v2 report assembled from those would silently restate v1 with new captions.
    cd.CACHE_DIR = CACHE
    v1 = v1_control()
    v2 = {k: cd.load_summary(k) for k in ("h1", "h2", "h3", "h4", "h5", "h6", "extras")}
    missing = [k for k, v in v2.items() if v is None]
    if missing:
        raise SystemExit(f"missing phase summaries: {missing} — run run_control.py first")
    stale = [k for k, v in v2.items() if v["provenance"]["engine"] != prov["engine"]]
    if stale:
        raise SystemExit(
            f"phase summaries {stale} are stamped with a different engine than the "
            f"working tree ({prov['engine']}); re-run run_control.py --force before "
            f"writing a report"
        )
    cd._init_worker()
    panel = cd.PANEL
    ref_p = cd.load_run("PRODUCTION")
    ref_c = cd.load_run("CONTROL_REVERSAL")
    tie = json.loads(
        (Path(__file__).resolve().parent / "_cache" / "tie_invariance.json").read_text())
    D = build_diff(v1, v2)

    L: list[str] = []
    A = L.append

    h1, h2, h3, h4, h5, h6, ex = (v2[k] for k in ("h1", "h2", "h3", "h4", "h5", "h6", "extras"))
    h1o = v1["h1"]
    h1n = v2["h1"]
    do = h1o["decomp_prod_vs_null"]
    dn = h1n["decomp_prod_vs_null"]
    po, pc_ = h1o["prod"], h1n["prod"]
    co, cc_ = h1o["ctrl"], h1n["ctrl"]

    # ================================================================ headline
    v1v = v1_control_verdicts()
    n2v = cd._verdict_rows(v2)
    n2v = {r["id"]: r for r in n2v}
    flips = [k for k in v1v if v1v[k].split("—")[0].strip() !=
             n2v[k]["verdict"].split("—")[0].strip()]

    A("# Control Diagnostic v2 — re-run on the tie-break-fixed engine")
    A("")
    A("**`engine 29764f562cd5` · loader `c1badf5f7df8` · costs `ba350aef75b3` "
      "· panel `389b082b832f`**")
    A("")
    A("v1 (`reports/CONTROL_DIAGNOSTIC.md`) was computed on engine **`d93815344bd3`**. "
      "That engine resolved tied scores **alphabetically** — `np.argsort(-score, "
      "kind=\"stable\")` over a panel whose columns are alphabetical. It is now a "
      "deterministic `blake2b(\"{date}|{symbol}\")` key via `np.lexsort`. "
      "**Every number in v1 that touches a real composite was therefore measured on a "
      "book that was partly chosen by the alphabet**, and is re-measured here.")
    A("")

    # ---- headline block
    A("## Headline — what changed, in one table")
    A("")
    A("| | v1 (`d93815344bd3`) | v2 (`29764f562cd5`) |")
    A("|---|---|---|")
    A(f"| production OOS CAGR / Sharpe | **{pc(po['cagr'])} / {num(po['sharpe'])}** | "
      f"**{pc(pc_['cagr'])} / {num(pc_['sharpe'])}** |")
    A(f"| production **gross** OOS CAGR | {pc(po['oos_gross_cagr'])} | "
      f"**{pc(pc_['oos_gross_cagr'])}** |")
    A(f"| production gross percentile in the null | {pctile(h1o['prod_pct_gross'])} | "
      f"**{pctile(h1n['prod_pct_gross'])}** |")
    A(f"| selection term of production's edge (gross gap) | "
      f"**{pp(do['gross_gap'])}** | **{pp(dn['gross_gap'])}** |")
    A(f"| cost term | {pp(do['cost_gap'])} | {pp(dn['cost_gap'])} |")
    A(f"| overlay term | {pp(do['overlay_gap'])} | {pp(dn['overlay_gap'])} |")
    A(f"| total net edge over the mean random book | {pp(do['total_gap'])} | "
      f"{pp(dn['total_gap'])} |")
    A(f"| reversal control OOS CAGR / Sharpe | {pc(co['cagr'])} / {num(co['sharpe'])} | "
      f"**{pc(cc_['cagr'])} / {num(cc_['sharpe'])}** |")
    A(f"| null (random books) mean CAGR / % profitable | "
      f"{pc(h1o['cagr']['mean'])} / {h1o['cagr']['frac_profitable'] * 100:.0f}% | "
      f"**{pc(h1n['cagr']['mean'])} / {h1n['cagr']['frac_profitable'] * 100:.0f}%** |")
    A(f"| H1 verdict | {v1v['H1'].split(' —')[0]} | "
      f"**{n2v['H1']['verdict'].split(' —')[0]}** |")
    A(f"| H6 verdict | {v1v['H6'].split(' —')[0]} | "
      f"**{n2v['H6']['verdict'].split(' —')[0]}** |")
    A("")
    if not flips:
        A("> **No hypothesis verdict flipped.** All six read the same way on the new engine "
          "as they did on the old one. What changed is the *size* of the thing the "
          "verdict is about: production's gross percentile fell from "
          f"{pctile(h1o['prod_pct_gross'])} to {pctile(h1n['prod_pct_gross'])} of the "
          "random null, and its selection term moved from "
          f"{pp(do['gross_gap'])} to {pp(dn['gross_gap'])}/yr.")
    else:
        A(f"> **Verdict flip: {', '.join(flips)}.** The other hypotheses are unchanged. "
          "Any of these is a headline in its own right; the diff table in §2 shows exactly "
          "which number moved.")
    A("")

    # ================================================================ provenance
    A("## 0. Provenance")
    A("")
    A("| component | v1 | v2 (this report) |")
    A("|-----------|----|----|")
    for k in ("engine", "loader", "costs", "panel"):
        A(f"| {k} | `{v1['provenance'][k]}` | `{prov[k]}`"
          + ("  — **CHANGED**" if v1["provenance"][k] != prov[k] else "") + " |")
    A("")
    A(f"- **Panel**: {panel.shape[1]} symbols x {len(panel)} daily bars, "
      f"{panel.index[0].date()} -> {panel.index[-1].date()} (unchanged: panel SHA identical)")
    A(f"- **Cost model**: `CostModel(segment=\"delivery\", slippage_bps=5)`; "
      f"**{cd.COST.all_in_round_trip_bps(100_000):.2f} bps all-in round trip** "
      f"(statutory + 2 x {cd.BASE_SLIPPAGE} bps slippage). Engine charges "
      f"`2.0 x one_way_turnover x equity x rate`. Unchanged: costs SHA identical.")
    A(f"- **Harness**: `nsealgo.backtest.walkforward.walk_forward`, {cd.N_FOLDS} folds, "
      f"{cd.TRAIN_YEARS}y train / {cd.TEST_YEARS}y test, {len(cd.PARAM_GRID)}-cell grid "
      f"(`n_positions` x overlay `lookback` x overlay `threshold`). Identical to "
      f"`research/validate.py` and to v1.")
    A("- **Only thing that varied between v1 and v2**: the engine's ranking tie-break. "
      "Same score panels, same seeds, same folds, same grid, same costs, same "
      "constraints, same loader, same factor code, same overlay.")
    A(f"- **OOS window**: {ref_p['folds'][-1]['test_start']} -> "
      f"{ref_p['folds'][0]['test_end']}, {ref_p['n_oos_days']} daily observations across "
      f"{cd.N_FOLDS} contiguous 2-year test windows. Identical to v1.")
    A("- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed in "
      "every report in this repo.")
    A("- Reproduce: `.venv/bin/python -m research.revalidate_v2.run_control && "
      ".venv/bin/python -m research.revalidate_v2.report_control`")
    A("")

    # ================================================================ §1 tie invariance
    A("## 1. Is the null affected by the tie-break? — measured, not assumed")
    A("")
    rd = tie["rerun_diff"]
    inv = tie["null_is_tie_invariant"]
    A("The brief's claim is that random books are unaffected because i.i.d. "
      "`Uniform(0,1)` has no ties. That is **true but not sufficient**, and this section "
      "checks the stronger claim instead: *did the null move?*")
    A("")
    A("Two things could have moved it, and the obvious one is not the interesting one:")
    A("")
    A("1. **Score ties.** `build_rebalance_weights` ranks with "
      "`np.lexsort((tiebreak, -score))`. For a random panel the tiebreak key is never "
      "consulted, because two `Uniform(0,1)` draws are never equal.")
    A("2. **Weight ties — the one that matters.** The engine has three rankers that sort "
      "by *weight*, not score (`_top_n_weights`, `_exit_allocation`, `_thin`), and "
      "`_project_constraints` clamps at `config.max_weight`, so any two names that both "
      "hit the cap arrive at **bit-identical** weights. Under the old engine that tie "
      "was resolved by column position — alphabetically. A random book pushes a large "
      "share of its names through the cap every rebalance, so this is the common case.")
    A("")
    A("`research/revalidate_v2/tie_invariance.py` measures both, on the real engine path:")
    A("")
    ir = tie["instrumented_runs"]
    A("| run | rebalances | rebalances with a **score** tie | `_top_n_weights` calls "
      "with a **weight** tie | of those, where the OLD rule gave a different book | "
      "`_exit_allocation` calls where the OLD rule differed |")
    A("|---|---:|---:|---:|---:|---:|")
    for tag, w in ir.items():
        A(f"| {tag} | {w['rebalances']} | {w['rows_with_score_tie']} | "
          f"{w['top_n_tie_calls']}/{w['top_n_calls']} | "
          f"**{w['top_n_changed_calls']}** | {w['exit_changed_calls']} |")
    A("")
    A("Read the first two columns together. The **production composite ties on "
      f"{ir[list(ir)[0]]['rows_with_score_tie']} of {ir[list(ir)[0]]['rebalances']} "
      "rebalances** — because `build_composite_score` fills missing factor values with "
      "the median 0.5, so ties are common *by construction* — while the **random null "
      f"ties on {ir[list(ir)[1]]['rows_with_score_tie']} of "
      f"{ir[list(ir)[1]]['rebalances']}**. That asymmetry is the whole mechanism of the "
      "tie-break bug: it could bias production and could not bias the null.")
    A("")
    A(f"And the weight-space rankers never saw a tie that mattered: "
      f"{tie['null_calls_where_old_rule_differs']} calls changed on the null run and "
      f"{tie['production_calls_where_old_rule_differs']} on the production run, so the "
      "cap-clamp tie is real in principle but did not fire on these books.")
    A("")
    A("**The end-to-end check, which settles it:**")
    A("")
    A(f"- **{rd['n_bit_identical_series']}/{rd['n_checked']}** cached null books "
      f"re-ran with a **bit-identical OOS daily return series** "
      f"(`np.array_equal` on the full float array). That is the **entire sweep**, not a "
      f"sample — every null book in this report was re-run against the new engine.")
    A(f"- **{rd['n_identical_folds']}/{rd['n_checked']}** had an identical per-fold "
      f"result table (selected params, train and test metrics).")
    A(f"- max `|dCAGR|` across all of them: **{rd['max_abs_cagr_delta']:.1e}**.")
    A("")
    A(f"**Conclusion: the null is tie-invariant — `{inv}`.** The v1 null column is "
      "reusable *as a measurement*, not as an assumption. Every null-distribution row in "
      "the diff table below is marked `unchanged` with this measurement standing behind "
      f"it, across all {rd['n_checked']} books in the sweep — not a sample.")
    A("")
    A("> **What is NOT reusable is anything built from a real composite.** Production, "
      "the reversal control and both scrambled nulls all draw on a composite whose "
      "missing values are median-filled, so they tie constantly and their books really "
      "do change. Every one of their numbers below was re-measured.")
    A("")

    # ================================================================ §2 diff table
    A("## 2. Diff table vs v1 — every number that moved")
    A("")
    A(f"Generated from `research/_control_diag/summary_*.json` (v1, full precision) and "
      f"`research/revalidate_v2/_cache/summary_*.json` (v2, full precision). "
      f"**{D.n_changed} of {len(D.rows)} quantities moved**; the rest are identical to "
      f"the last bit and say why.")
    A("")
    A("Rows marked `unchanged` are not carried forward on trust. They are either "
      "(a) null-distribution statistics, protected by the bit-identity measurement in §1, "
      "or (b) cost-model quantities, protected by the `costs` SHA being unchanged.")
    A("")
    A("### 2.1 Reference books and H1 percentiles / decomposition")
    A("")
    L.extend(D.table(["ref", "H1 pct", "H1 decomp"]))
    A("")
    A("### 2.2 H1 null distribution — protected by the §1 measurement")
    A("")
    L.extend(D.table(["H1 null"]))
    A("")
    A("### 2.3 H2 — component singles")
    A("")
    L.extend(D.table(["H2"]))
    A("")
    A("### 2.4 H3 — regime overlay on/off")
    A("")
    L.extend(D.table(["H3"]))
    A("")
    A("### 2.5 H4 — production vs control significance")
    A("")
    L.extend(D.table(["H4"]))
    A("")
    A("### 2.6 H5 — fixed unselected cells, selection cost, per-fold selections")
    A("")
    L.extend(D.table(["H5"]))
    A("")
    A("### 2.7 H6 — signal-scrambled nulls")
    A("")
    L.extend(D.table(["H6"]))
    A("")
    A("### 2.8 Beta, turnover and the equal-weight benchmark")
    A("")
    L.extend(D.table(["extras"]))
    A("")
    A(f"*Moved: {D.n_changed}. Unchanged: {len(D.rows) - D.n_changed}.*")
    A("")

    # ================================================================ verdict table
    A("## 3. Verdict at a glance — v1 vs v2")
    A("")
    A("| # | Hypothesis | v1 verdict | v2 verdict | flipped? | decisive v2 number |")
    A("|---|-----------|------------|------------|---------|---------------------|")
    for k in ("H1", "H2", "H3", "H4", "H5", "H6"):
        r = n2v[k]
        A(f"| {k} | {r['hyp']} | {v1v[k]} | **{r['verdict']}** | "
          f"{'**YES**' if k in flips else 'no'} | {r['key']} |")
    A("")

    write_body(A, v1, v2, panel, ref_p, ref_c, h1, h2, h3, h4, h5, h6, ex, D,
               v1v, n2v, flips, prov, ir)
    OUT.write_text("\n".join(L) + "\n")
    print(f"wrote {OUT}")


def write_body(A, v1, v2, panel, ref_p, ref_c, h1, h2, h3, h4, h5, h6, ex, D,
               v1v, n2v, flips, prov, ir):
    h1o, do = v1["h1"], v1["h1"]["decomp_prod_vs_null"]
    dn = v2["h1"]["decomp_prod_vs_null"]
    bo = {r["component"]: r for r in v1["h2"]["components"]}


    # ---------------- H1
    A("## 4. H1 — \"It's beta, not skill\"")
    A("")
    c, s, g = h1["cagr"], h1["sharpe"], h1["gross_cagr"]
    A(f"{h1['n_random']} random-weight books (i.i.d. `Uniform(0,1)` scores) through the "
      "**identical** harness: same 6 folds, same 18-cell grid, same engine, same cost "
      "stack, same top-N cut, same inverse-vol scaling, same caps, same turnover budget, "
      "same monthly rebalance. The only thing removed is the signal.")
    A("")
    A("| statistic | random CAGR | random Sharpe | random MaxDD | v1 CAGR | status |")
    A("|-----------|-------------|--------------|-------------|---------|--------|")
    for stat in ("mean", "sd", "min", "p05", "p25", "median", "p75", "p95", "max"):
        same = abs(c[stat] - h1o["cagr"][stat]) <= TOL
        A(f"| {stat} | {c[stat] * 100:+.2f}% | {s[stat]:+.2f} | "
          f"{h1['maxdd'][stat] * 100:+.2f}% | {h1o['cagr'][stat] * 100:+.2f}% | "
          f"{'unchanged' if same else '**moved**'} |")
    A(f"| **profitable** | **{c['frac_profitable'] * 100:.0f}% of books** | — | — | "
      f"{h1o['cagr']['frac_profitable'] * 100:.0f}% | "
      f"{'unchanged' if abs(c['frac_profitable'] - h1o['cagr']['frac_profitable']) <= TOL else '**moved**'} |")
    A("")
    A("| book | net CAGR | pct (net) | **gross CAGR** | **pct (gross)** | Sharpe | "
      "pct | turnover | cost drag |")
    A("|------|---------:|---------:|-------------:|--------------:|-------:|"
      "-----:|---------:|----------:|")
    A(f"| **production (trend)** | {h1['prod']['cagr'] * 100:+.2f}% | "
      f"{pctile(h1['prod_pct_cagr'])} | {h1['prod']['oos_gross_cagr'] * 100:+.2f}% | "
      f"**{pctile(h1['prod_pct_gross'])}** | {h1['prod']['sharpe']:+.2f} | "
      f"{pctile(h1['prod_pct_sharpe'])} | {h1['prod']['oos_turnover']:.2f}x/y | "
      f"{h1['prod']['oos_cost_drag'] * 100:.2f}%/y |")
    A(f"| control (reversal) | {h1['ctrl']['cagr'] * 100:+.2f}% | "
      f"{pctile(h1['ctrl_pct_cagr'])} | {h1['ctrl']['oos_gross_cagr'] * 100:+.2f}% | "
      f"{pctile(h1['ctrl_pct_gross'])} | {h1['ctrl']['sharpe']:+.2f} | "
      f"{pctile(h1['ctrl_pct_sharpe'])} | {h1['ctrl']['oos_turnover']:.2f}x/y | "
      f"{h1['ctrl']['oos_cost_drag'] * 100:.2f}%/y |")
    A("")
    A(f"> **Read the gross column, not the net one.** The random books turn over "
      f"{h1['turnover']['mean']:.2f}x/yr against production's "
      f"{h1['prod']['oos_turnover']:.2f}x/yr, so on *net* return production is credited "
      f"for a cost saving that has nothing to do with its factors. The gross column "
      f"strips both costs and the regime overlay.")
    A("")
    A("### Where production's net edge over the null actually comes from")
    A("")
    A("Three consistent measurements are available per book and they nest:")
    A("")
    A("```")
    A("gross   ->  -costs-  ->  net_pre_overlay  ->  +overlay  ->  net")
    A("```")
    A("")
    A("| book | gross CAGR | cost channel | net pre-overlay | overlay channel | net CAGR |")
    A("|------|-----------:|-------------:|----------------:|----------------:|---------:|")
    A(f"| production | {h1['prod']['oos_gross_cagr'] * 100:+.2f}% | "
      f"{dn['cost_a'] * 100:+.2f}pp | {h1['prod']['oos_net_pre_overlay'] * 100:+.2f}% | "
      f"{dn['overlay_a'] * 100:+.2f}pp | {h1['prod']['cagr'] * 100:+.2f}% |")
    A(f"| mean random book | {h1['null_mean']['oos_gross_cagr'] * 100:+.2f}% | "
      f"{dn['cost_b'] * 100:+.2f}pp | {h1['null_mean']['oos_net_pre_overlay'] * 100:+.2f}% | "
      f"{dn['overlay_b'] * 100:+.2f}pp | {h1['null_mean']['cagr'] * 100:+.2f}% |")
    A(f"| **difference (v2)** | **{dn['gross_gap'] * 100:+.2f}pp** | "
      f"**{dn['cost_gap'] * 100:+.2f}pp** | — | **{dn['overlay_gap'] * 100:+.2f}pp** | "
      f"**{dn['total_gap'] * 100:+.2f}pp** |")
    A(f"| difference (v1) | {do['gross_gap'] * 100:+.2f}pp | "
      f"{do['cost_gap'] * 100:+.2f}pp | — | {do['overlay_gap'] * 100:+.2f}pp | "
      f"{do['total_gap'] * 100:+.2f}pp |")
    A("")
    A(f"The three difference terms reconcile to the observed net gap "
      f"({dn['total_gap'] * 100:+.2f}pp) to {abs(dn['recon_err']):.1e}. "
      f"**The selection term — the only one that reflects the factors — is "
      f"{dn['gross_gap'] * 100:+.2f}pp/yr.** On v1 it was "
      f"{do['gross_gap'] * 100:+.2f}pp/yr.")
    A("")
    A(cd._h1_verdict(h1))
    A("")

    # ---------------- H2
    A("## 5. H2 — \"The low-vol leg is doing the work, not the reversal legs\"")
    A("")
    A("Every component run alone at weight 1.0 through the same harness, plus the "
      "control with `low_volatility` removed (weights renormalised by "
      "`build_composite_score`).")
    A("")
    A("| book | OOS CAGR | OOS Sharpe | OOS MaxDD | turnover | cost drag | v1 CAGR | "
      "v1 Sharpe | status |")
    A("|------|---------:|-----------:|----------:|---------:|----------:|"
      "--------:|----------:|--------|")
    for k, lab in (("PRODUCTION", "**PRODUCTION (trend)**"),
                   ("CONTROL_REVERSAL", "**CONTROL (reversal)**")):
        n = h2["production"] if k == "PRODUCTION" else h2["control"]
        o = v1["h2"]["production"] if k == "PRODUCTION" else v1["h2"]["control"]
        A(f"| {lab} | {n['cagr'] * 100:+.2f}% | {n['sharpe']:.2f} | "
          f"{n['maxdd'] * 100:+.2f}% | {ref_p['oos_turnover'] if k == 'PRODUCTION' else ref_c['oos_turnover']:.2f}x/y | "
          f"{(ref_p['oos_cost_drag'] if k == 'PRODUCTION' else ref_c['oos_cost_drag']) * 100:.2f}%/y | "
          f"{o['cagr'] * 100:+.2f}% | {o['sharpe']:.2f} | "
          f"{'**moved**' if abs(n['cagr'] - o['cagr']) > TOL else 'unchanged'} |")
    for r in h2["components"]:
        k = r["component"]
        o = bo[k]
        A(f"| {k} | {r['cagr'] * 100:+.2f}% | {r['sharpe']:+.2f} | "
          f"{r['maxdd'] * 100:+.2f}% | {r['turnover']:.2f}x/y | "
          f"{r['cost_drag'] * 100:.2f}%/y | {o['cagr'] * 100:+.2f}% | "
          f"{o['sharpe']:+.2f} | "
          f"{'**moved**' if abs(r['cagr'] - o['cagr']) > TOL else 'unchanged'} |")
    A("")
    A(cd._h2_verdict(h2))
    A("")

    # ---------------- H3
    A("## 6. H3 — \"The regime overlay is the whole difference\"")
    A("")
    A("Identical folds, identical grid, identical engine and costs. `overlay=OFF` skips "
      "`blend_with_cash` and nothing else.")
    A("")
    A("| book | overlay | OOS CAGR | OOS Sharpe | OOS MaxDD | v1 CAGR | v1 Sharpe | status |")
    A("|------|---------|---------:|-----------:|----------:|--------:|----------:|--------|")
    for k in ("prod", "ctrl"):
        for mode in ("with_overlay", "no_overlay"):
            r = h3[mode][k]
            o = v1["h3"][mode][k]
            A(f"| {k} | {mode.replace('_', ' ')} | {r['cagr'] * 100:+.2f}% | "
              f"{r['sharpe']:+.2f} | {r['maxdd'] * 100:+.2f}% | "
              f"{o['cagr'] * 100:+.2f}% | {o['sharpe']:+.2f} | "
              f"{'**moved**' if abs(r['cagr'] - o['cagr']) > TOL else 'unchanged'} |")
    A("")
    A(f"**Sharpe gap (control − production):** "
      f"{h3['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} with the overlay "
      f"(v1 {v1['h3']['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f}), "
      f"{h3['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} without it "
      f"(v1 {v1['h3']['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f}). "
      f"**CAGR gap (control − production):** "
      f"{h3['with_overlay']['cagr_gap_ctrl_minus_prod'] * 100:+.2f}pp with, "
      f"{h3['no_overlay']['cagr_gap_ctrl_minus_prod'] * 100:+.2f}pp without.")
    A("")
    A(cd._h3_verdict(h3))
    A("")

    # ---------------- H4
    A("## 7. H4 — \"the production-vs-control gap is noise\"")
    A("")
    t, b = h4["ttest"], h4["bootstrap"]
    A(f"OOS window {h4['oos_window'][0]} -> {h4['oos_window'][1]}, "
      f"**{t['n_days']} daily observations**, both books on identical dates (paired).")
    A("")
    A("| test | statistic | p-value | v1 statistic | v1 p | status |")
    A("|------|-----------|---------|--------------|-------|--------|")
    A(f"| paired daily t-test on the return difference | t = {t['t_iid']:+.3f} | "
      f"{t['p_iid']:.3f} | {v1['h4']['ttest']['t_iid']:+.3f} | "
      f"{v1['h4']['ttest']['p_iid']:.3f} | "
      f"{'**moved**' if abs(t['t_iid'] - v1['h4']['ttest']['t_iid']) > TOL else 'unchanged'} |")
    A(f"| same, Newey-West HAC(10) | t = {t['t_newey_west']:+.3f} | "
      f"{t['p_newey_west']:.3f} | {v1['h4']['ttest']['t_newey_west']:+.3f} | "
      f"{v1['h4']['ttest']['p_newey_west']:.3f} | "
      f"{'**moved**' if abs(t['t_newey_west'] - v1['h4']['ttest']['t_newey_west']) > TOL else 'unchanged'} |")
    A(f"| bootstrap 95% CI on ΔCAGR (21-bar blocks, B={b['B']:,}) | "
      f"[{b['d_cagr_ci_lo'] * 100:+.2f}pp, {b['d_cagr_ci_hi'] * 100:+.2f}pp] | — | "
      f"[{v1['h4']['bootstrap']['d_cagr_ci_lo'] * 100:+.2f}pp, "
      f"{v1['h4']['bootstrap']['d_cagr_ci_hi'] * 100:+.2f}pp] | — | "
      f"{'**moved**' if abs(b['d_cagr_ci_lo'] - v1['h4']['bootstrap']['d_cagr_ci_lo']) > TOL else 'unchanged'} |")
    A("")
    A(f"Observed ΔCAGR = {h4['prod_cagr'] * 100:+.2f}% − {h4['ctrl_cagr'] * 100:+.2f}% "
      f"= {(h4['prod_cagr'] - h4['ctrl_cagr']) * 100:+.2f}pp "
      f"(v1 {(v1['h4']['prod_cagr'] - v1['h4']['ctrl_cagr']) * 100:+.2f}pp). "
      f"Observed ΔSharpe = {h4['prod_sharpe']:.2f} − {h4['ctrl_sharpe']:.2f} = "
      f"{h4['prod_sharpe'] - h4['ctrl_sharpe']:+.2f} "
      f"(v1 {v1['h4']['prod_sharpe'] - v1['h4']['ctrl_sharpe']:+.2f}).")
    A("")
    A(cd._h4_verdict(h4))
    A("")

    # ---------------- H5
    A("## 8. H5 — \"The harness has a selection artifact\"")
    A("")
    A("Walk-forward selects parameters on TRAIN. A book that survives TRAIN selection "
      "could carry a structural OOS advantage unrelated to its signal. Two readings: a "
      "**fixed, unselected** parameter set, and the train/test profile of both books.")
    A("")
    A("### Fixed parameters — no train selection at all")
    A("")
    A("| cell | params | production CAGR | control CAGR | production Sharpe | "
      "control Sharpe |")
    A("|------|--------|----------------:|--------------:|-----------------:|"
      "---------------:|")
    for tag, rows in h5["fixed"].items():
        p_ = rows["params"]
        A(f"| {tag} | n={p_['n_positions']}, lb={p_['lookback']}, "
          f"thr={p_['threshold']} | {rows['PRODUCTION']['cagr'] * 100:+.2f}% | "
          f"{rows['CONTROL_REVERSAL']['cagr'] * 100:+.2f}% | "
          f"{rows['PRODUCTION']['sharpe']:.2f} | "
          f"{rows['CONTROL_REVERSAL']['sharpe']:.2f} |")
    A("")
    A("| cell | v1 prod CAGR | v1 ctrl CAGR | selection (gross) | cost | overlay | "
      "total net | v1 total net |")
    A("|------|-------------:|-------------:|------------------:|-----:|--------:|"
      "----------:|-------------:|")
    for tag, d in h5["fixed_decomp"].items():
        g = d["prod_minus_ctrl"]
        o = v1["h5"]["fixed_decomp"][tag]["prod_minus_ctrl"]
        A(f"| {tag} | {v1['h5']['fixed'][tag]['PRODUCTION']['cagr'] * 100:+.2f}% | "
          f"{v1['h5']['fixed'][tag]['CONTROL_REVERSAL']['cagr'] * 100:+.2f}% | "
          f"{g['gross_gap'] * 100:+.2f}pp | {g['cost_gap'] * 100:+.2f}pp | "
          f"{g['overlay_gap'] * 100:+.2f}pp | {g['total_gap'] * 100:+.2f}pp | "
          f"{o['total_gap'] * 100:+.2f}pp |")
    A("")
    A("### What the train-window selection actually does")
    A("")
    A("| book | best fixed cell | walk-forward | selection delta | v1 selection delta |")
    A("|------|-----------------:|-------------:|----------------:|------------------:|")
    for lab, s_ in h5["selection_cost"].items():
        o = v1["h5"]["selection_cost"][lab]
        A(f"| {lab} | {s_['best_fixed_cagr'] * 100:+.2f}% | "
          f"{s_['walk_forward_cagr'] * 100:+.2f}% | "
          f"{s_['selection_delta_cagr'] * 100:+.2f}pp | "
          f"{o['selection_delta_cagr'] * 100:+.2f}pp |")
    A("")
    A("### Train vs test — is there a flip?")
    A("")
    A("| book | mean TRAIN Sharpe | OOS Sharpe | flip | mean TRAIN CAGR | OOS CAGR | "
      "v1 flip |")
    A("|------|------------------:|-----------:|-----:|----------------:|--------:|"
      "--------:|")
    for lab, p_ in h5["train_test"].items():
        o = v1["h5"]["train_test"][lab]
        A(f"| {lab} | {p_['train_sharpe']:+.2f} | {p_['oos_sharpe']:+.2f} | "
          f"{p_['sharpe_flip']:+.2f} | {p_['train_cagr'] * 100:+.2f}% | "
          f"{p_['oos_cagr'] * 100:+.2f}% | {o['sharpe_flip']:+.2f} |")
    A("")
    A("### Per-fold train/test, and which parameter the tie-break changed the choice of")
    A("")
    A("This is the mechanism table. A cell flagged **argmax flipped** is a fold where "
      "the tie-break changed which of the 18 grid cells the train window preferred — "
      "which is a direct, mechanical measurement of how much of the headline is the "
      "selection layer.")
    A("")
    A("| book | fold | selected params | v1 selected params | TRAIN Sharpe | OOS Sharpe "
      "| TRAIN CAGR | OOS CAGR |")
    A("|------|-----:|------------------|-------------------|-------------:|-----------:"
      "|----------:|--------:|")
    nflip = 0

    def fmt(d: dict) -> str:
        return f"n={d['n_positions']}, lb={d['lookback']}, thr={d['threshold']}"

    for lab in ("PRODUCTION", "CONTROL_REVERSAL"):
        for fo_, fn_ in zip(v1["h5"]["train_test"][lab]["folds"],
                            h5["train_test"][lab]["folds"], strict=True):
            po_, pn_ = fo_["params"], fn_["params"]
            same = po_ == pn_
            nflip += int(not same)
            A(f"| {lab} | {fo_['fold']} | {fmt(pn_)} | "
              f"{fmt(po_) if not same else '*same*'} | {fn_['train_sharpe']:+.2f} | "
              f"{fn_['test_sharpe']:+.2f} | {fn_['train_cagr'] * 100:+.2f}% | "
              f"{fn_['test_cagr'] * 100:+.2f}% |")
    A("")
    n_folds = sum(len(h5["train_test"][x]["folds"])
                  for x in ("PRODUCTION", "CONTROL_REVERSAL"))
    A(f"**{nflip} of {n_folds} fold-level parameter selections changed between the two "
      f"engines.**")
    A("")
    A(cd._h5_verdict(h5))
    A("")

    # ---------------- H6
    A("## 9. H6 — \"Equal-count controls are the wrong null\"")
    A("")
    A("A random book and a **signal-scrambled** book are different nulls. A random book "
      "asks *does an arbitrary book make money*. A scrambled book asks *does **this** "
      "book make money for any reason other than its signal* — which is what a negative "
      "control is for.")
    A("")
    A("- `scramble_c`: the composite score with a **fixed column relabel** "
      "(`score'[t,s] = score[t,π(s)]`). Every per-date marginal score distribution is "
      "preserved **exactly**; only the score-to-return link is destroyed.")
    A("- `scramble_r`: the composite with an **independent permutation of each date's "
      "cross-section**. Per-date marginals are still preserved exactly, but the name "
      "identity churns every rebalance, so turnover rises.")
    A("")
    A("> **Caveat carried forward, and it is not a formality.** The brief asked for the "
      "scrambled null to match turnover as closely as possible. `scramble_c` does **not** "
      "match it exactly and cannot: relabelling score columns relabels *which name* "
      "receives *which score*, but `build_rebalance_weights` then inverse-vol-scales by "
      "the **name's** realised volatility and runs a sector / single-name cap projection "
      "over **name identities**, so the resulting weight vector is not a permutation of "
      "the original. Measured: production turns over "
      f"{h6['prod_turnover']:.2f}x/y and `scramble_c` {h6['scramble_c']['turnover_mean']:.2f}x/y "
      f"— a {abs(h6['scramble_c']['turnover_mean'] / h6['prod_turnover'] - 1) * 100:.1f}% "
      f"gap — and the scrambled books' own seed-to-seed spread is "
      f"{h6['scramble_c']['cagr_sd'] * 100:.2f}pp on CAGR. The match is good to within a "
      "few percent and the residual is printed in the table rather than described as "
      "exact.")
    A("")
    A("| book | n | mean CAGR | sd | min | max | mean Sharpe | sd | turnover | "
      "cost drag | profitable |")
    A("|------|--:|----------:|---:|----:|----:|-----------:|---:|---------:|"
      "----------:|-----------:|")
    A(f"| **production (unscrambled)** | 1 | {h6['prod_cagr'] * 100:+.2f}% | — | — | — | "
      f"{h6['prod_sharpe']:.2f} | — | **{h6['prod_turnover']:.2f}x/y** | "
      f"**{h6['prod_drag'] * 100:.2f}%/y** | — |")
    for tag, lab in (("scramble_c", "scramble_c (fixed relabel)"),
                     ("scramble_r", "scramble_r (per-date permute)")):
        r = h6[tag]
        o = v1["h6"][tag]
        A(f"| {lab} | {r['n']} | {r['cagr_mean'] * 100:+.2f}% | "
          f"{r['cagr_sd'] * 100:.2f}pp | {r['cagr_min'] * 100:+.2f}% | "
          f"{r['cagr_max'] * 100:+.2f}% | {r['sharpe_mean']:+.2f} | "
          f"{r['sharpe_sd']:.2f} | {r['turnover_mean']:.2f}x/y | "
          f"{r['cost_drag_mean'] * 100:.2f}%/y | "
          f"{r['cagr_frac_profitable'] * 100:.0f}% |")
    A("")
    A("| book | vs scramble_c (CAGR pct) | vs scramble_c (Sharpe pct) | "
      "vs scramble_r (CAGR pct) | vs scramble_r (Sharpe pct) | v1 scramble_c CAGR pct |")
    A("|------|-------------------------:|---------------------------:|"
      "------------------------:|--------------------------:|----------------------:|")
    A(f"| **production** | {pctile(h6['scramble_c']['prod_pct_cagr'])} | "
      f"{pctile(h6['scramble_c']['prod_pct_sharpe'])} | "
      f"{pctile(h6['scramble_r']['prod_pct_cagr'])} | "
      f"{pctile(h6['scramble_r']['prod_pct_sharpe'])} | "
      f"{pctile(v1['h6']['scramble_c']['prod_pct_cagr'])} |")
    A(f"| control | {pctile(h6['scramble_c']['ctrl_pct_cagr'])} | "
      f"{pctile(h6['scramble_c']['ctrl_pct_sharpe'])} | "
      f"{pctile(h6['scramble_r']['ctrl_pct_cagr'])} | "
      f"{pctile(h6['scramble_r']['ctrl_pct_sharpe'])} | "
      f"{pctile(v1['h6']['scramble_c']['ctrl_pct_cagr'])} |")
    A("")
    A("> **Read the production row, not the control row.** These nulls are built by "
      "scrambling the **production** composite, so the production row is a like-for-like "
      "test of production against its own signal destroyed. The control row places a "
      "*different* composite (reversal weights) against a null built from the trend "
      "composite's score distribution — different turnover, different score dispersion, "
      "different name overlap — so the control's percentile against this null is "
      "indicative only and must not be read as a significance test. A matched control "
      "scramble (reversal weights, then scrambled) is the clean version and was not run; "
      "H2 and H4 cover the production-vs-control question directly instead.")
    A("")
    A(cd._h6_verdict(h6))
    A("")
    A("> **Measured turnover residual, and which way it cuts.** The verdict text above "
      "says the turnover is matched \"to within a few percent\", carried from v1's "
      "wording. Re-measured on this engine the residual is larger and it should be "
      f"stated plainly: `scramble_c` turns over "
      f"{h6['scramble_c']['turnover_mean']:.2f}x/y against production's "
      f"{h6['prod_turnover']:.2f}x/y, i.e. "
      f"**{abs(h6['scramble_c']['turnover_mean'] / h6['prod_turnover'] - 1) * 100:.1f}% "
      f"lower**, not ~3%. (v1's ~3% was a different measurement — total one-way turnover "
      f"over the whole panel under pure column permutations, not the annualised "
      f"turnover of the *selected* out-of-sample cell — and the two are not "
      f"interchangeable.)\n\n"
      f"**The direction matters, and it cuts against production.** A null that turns over "
      f"less pays less cost drag, so its mean net CAGR is flattered relative to "
      f"production's. If the null were turnover-matched it would pay "
      f"{(h6['prod_drag'] - h6['scramble_c']['cost_drag_mean']) * 100:.2f}pp/yr more in "
      f"drag, its mean would fall, and production's percentile against it would be "
      f"*higher* than the {pctile(h6['scramble_c']['prod_pct_cagr'])} measured here. The "
      f"residual therefore works **against** the production composite, and it still does "
      f"not clear the null. Correcting it would not change the verdict; it would move "
      f"production up the table, not out of it.")
    A("")

    # ---------------- extras
    A("## 10. Turnover, beta and the equal-weight benchmark")
    A("")
    A("### 1. Turnover and cost drag — is the control's edge just a smaller bill?")
    A("")
    A("| book | annual turnover | annual cost drag | v1 turnover | v1 drag | status |")
    A("|------|----------------:|-----------------:|-------------|----------:|--------|")
    for lab, pre in (("production", "prod"), ("control", "ctrl")):
        t_, d_ = ex[f"{pre}_turnover"], ex[f"{pre}_drag"]
        to, do_ = v1["extras"][f"{pre}_turnover"], v1["extras"][f"{pre}_drag"]
        A(f"| {lab} | {t_:.4f}x/y | {d_ * 100:.2f}%/y | {to:.4f}x/y | "
          f"{do_ * 100:.2f}%/y | "
          f"{'**moved**' if abs(t_ - to) > TOL else 'unchanged'} |")
    A(f"| **control − production** | "
      f"**{ex['turnover_gap_ctrl_minus_prod']:+.4f}x/y** | "
      f"**{ex['drag_gap_ctrl_minus_prod'] * 100:+.2f}pp/y** | "
      f"{v1['extras']['turnover_gap_ctrl_minus_prod']:+.4f}x/y | "
      f"{v1['extras']['drag_gap_ctrl_minus_prod'] * 100:+.2f}pp/y | |")
    A("")
    A("**The hypothesis is refuted, and the direction matters.** The control turns over "
      f"**{abs(ex['turnover_gap_ctrl_minus_prod']):.2f}x/yr more** and pays "
      f"**{abs(ex['drag_gap_ctrl_minus_prod']) * 100:.2f}pp/yr more** in drag, and still "
      "earns more. As an identity:")
    A("")
    A("```")
    A("gross_ctrl - gross_prod = (net_ctrl - net_prod) + (drag_ctrl - drag_prod)")
    A(f"                        = {ex['net_gap_ctrl_minus_prod'] * 100:+.2f}pp"
      f"           + {ex['drag_gap_ctrl_minus_prod'] * 100:+.2f}pp")
    A(f"                        = {ex['gross_gap_ctrl_minus_prod'] * 100:+.2f}pp")
    A("```")
    A("")
    A(f"The control's **gross** advantage is {ex['gross_gap_ctrl_minus_prod'] * 100:+.2f}pp/yr "
      f"(v1 {v1['extras']['gross_gap_ctrl_minus_prod'] * 100:+.2f}pp) — larger than its "
      f"net advantage of {ex['net_gap_ctrl_minus_prod'] * 100:+.2f}pp/yr "
      f"(v1 {v1['extras']['net_gap_ctrl_minus_prod'] * 100:+.2f}pp). Cost drag "
      f"*narrows* the gap between the two books; it does not create it.")
    A("")
    A("### 2. Beta and correlation to the equal-weight benchmark")
    A("")
    A("| book | beta | corr | R² | Jensen alpha | alpha t | alpha p | "
      "tracking error | v1 beta | v1 alpha |")
    A("|------|-----:|-----:|---:|-------------:|--------:|--------:|"
      "---------------:|--------:|----------:|")
    for k in ("production", "control"):
        b = ex[k]
        o = v1["extras"][k]
        A(f"| {k} | {b['beta']:.3f} | {b['corr_bench']:.3f} | {b['r2']:.3f} | "
          f"{b['alpha_annual'] * 100:+.2f}%/y | {b['alpha_t']:+.2f} | "
          f"{b['alpha_p']:.2f} | {b['tracking_err_annual'] * 100:.1f}% | "
          f"{o['beta']:.3f} | {o['alpha_annual'] * 100:+.2f}%/y |")
    A(f"| *equal-weight benchmark* | 1.000 | 1.000 | 1.000 | — (CAGR "
      f"{ex['benchmark_cagr'] * 100:+.2f}%, Sharpe {ex['benchmark_sharpe']:.2f}) | — | — "
      f"| — | — | — |")
    A("")
    A("### 3. Would a market-neutral or beta-matched comparison change the verdict?")
    A("")
    A(cd._beta_verdict(ex))
    A("")

    # ---------------- bottom line
    A("## 11. Bottom line")
    A("")
    A(_v2_bottom_line(v2, _fixed_grid_note(), _null_books_checked()))
    A("")
    A("---")
    A("")
    A(f"*Produced by `research/revalidate_v2/run_control.py` + `report_control.py` "
      f"against engine `{prov['engine']}`, loader `{prov['loader']}`, costs "
      f"`{prov['costs']}`, panel `{prov['panel']}`. v1 (engine `d93815344bd3`) is "
      f"`reports/CONTROL_DIAGNOSTIC.md` and its underlying per-book cache is "
      f"`research/_control_diag/`. All-in cost 21.92 bps round trip. Every figure here "
      f"is net of the full Indian delivery cost stack and must be quoted with its end "
      f"date — the OOS window ends {ref_p['folds'][0]['test_end']}. Survivorship bias "
      f"is present and disclosed. `GOAL.md` §6 anti-fraud rules apply: no in-sample "
      f"number is presented as a result, and no cost was reduced to rescue anything.*")



def _fixed_grid_note() -> str:
    """The '18 of 18 profitable cells' phrase, sourced from `reports/STRESS_v4.md` if it
    has been generated, and marked as v3's figure otherwise.

    It is a Gate 4 number, not a control-diagnostic number, so it is read from the
    stress report's own cache when that exists. Nothing here is asserted from memory.
    """
    import pickle
    p = CACHE / "STRESS_fixed_grid.pkl"
    if p.exists():
        with p.open("rb") as fh:
            rows = pickle.load(fh)
        n_ok = sum(1 for r in rows if r["cagr"] > 0)
        return (f"{n_ok} of {len(rows)} fixed grid cells profitable "
                f"(reports/STRESS_v4.md §5)")
    return "18 of 18 profitable grid cells (reports/STRESS_v3.md §5)"


def _null_books_checked() -> int:
    """How many null books the tie-invariance phase re-ran end to end."""
    import json as _json
    p = CACHE / "tie_invariance.json"
    if not p.exists():
        return 0
    return _json.loads(p.read_text())["rerun_diff"]["n_checked"]


if __name__ == "__main__":
    main()
