from __future__ import annotations

import html
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from math import sqrt
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


def equity_curve_from_trades(
    initial_capital: float,
    trades: Sequence[tuple[datetime, float]],
) -> list[tuple[datetime, float]]:
    if not trades:
        return [(_utcnow(), initial_capital)]
    series: list[tuple[datetime, float]] = [(trades[0][0], initial_capital + trades[0][1])]
    for i in range(1, len(trades)):
        ts, pnl = trades[i]
        series.append((ts, series[-1][1] + pnl))
    return series


def compute_drawdown_series(equity: Sequence[float]) -> list[float]:
    if not equity:
        return []
    peaks: list[float] = []
    peak = equity[0]
    out: list[float] = []
    for v in equity:
        peak = max(peak, v)
        peaks.append(peak)
        dd = (v - peak) / peak if peak > 0 else 0.0
        out.append(float(dd))
    return out


def sharpe_ratio(returns: Sequence[float], periods_per_year: int = 252) -> float:
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / len(returns)
    sd = sqrt(var) if var > 0 else 0.0
    if sd <= 0:
        return 0.0
    return float(mean / sd * sqrt(periods_per_year))


def render_html(
    title: str,
    start_time: datetime,
    end_time: datetime,
    initial_capital: float,
    final_equity: float,
    returns: Sequence[float],
    equity_curve: Sequence[tuple[datetime, float]],
    trades: Iterable[dict[str, Any]],
    metrics_extra: dict[str, Any] | None = None,
) -> str:
    n_trades = sum(1 for _ in trades)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    sum(1 for t in trades if t.get("pnl", 0) < 0)
    total_return = (final_equity - initial_capital) / initial_capital * 100 if initial_capital else 0.0
    equity = [v for _, v in equity_curve]
    dd_series = compute_drawdown_series(equity)
    max_dd = min(dd_series) * 100 if dd_series else 0.0
    sr = sharpe_ratio(returns)
    win_rate = (wins / n_trades * 100) if n_trades else 0.0
    rows: list[str] = []
    for t in trades:
        rows.append(
            "<tr>"
            + f"<td>{html.escape(str(t.get('timestamp', '')))}</td>"
            + f"<td>{html.escape(str(t.get('symbol', '')))}</td>"
            + f"<td>{html.escape(str(t.get('side', '')))}</td>"
            + f"<td>{html.escape(str(t.get('quantity', '')))}</td>"
            + f"<td>{html.escape(str(t.get('pnl', '')))}</td>"
            + "</tr>"
        )
    extras = ""
    if metrics_extra:
        items = "".join(
            f"<li><b>{html.escape(str(k))}</b>: {html.escape(str(v))}</li>"
            for k, v in metrics_extra.items()
        )
        extras = f"<h2>Additional metrics</h2><ul>{items}</ul>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 32px; color: #1a1a1a; }}
h1 {{ border-bottom: 1px solid #ccc; padding-bottom: 4px; }}
table {{ border-collapse: collapse; margin-top: 12px; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 6px 8px; text-align: right; }}
th {{ background: #f5f5f5; }}
.kpi-row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
.kpi {{ border: 1px solid #ddd; padding: 12px 16px; border-radius: 4px; min-width: 140px; }}
.kpi .label {{ color: #888; font-size: 12px; }}
.kpi .value {{ font-size: 18px; font-weight: 600; }}
.neg {{ color: #b00; }}
.pos {{ color: #060; }}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<p>{start_time.isoformat()} &rarr; {end_time.isoformat()}</p>
<div class="kpi-row">
  <div class="kpi"><div class="label">Initial capital</div><div class="value">{initial_capital:,.2f}</div></div>
  <div class="kpi"><div class="label">Final equity</div><div class="value">{final_equity:,.2f}</div></div>
  <div class="kpi"><div class="label">Total return</div><div class="value {'pos' if total_return>=0 else 'neg'}">{total_return:+.2f}%</div></div>
  <div class="kpi"><div class="label">Max drawdown</div><div class="value neg">{max_dd:.2f}%</div></div>
  <div class="kpi"><div class="label">Sharpe</div><div class="value">{sr:.2f}</div></div>
  <div class="kpi"><div class="label">Trades</div><div class="value">{n_trades}</div></div>
  <div class="kpi"><div class="label">Win rate</div><div class="value">{win_rate:.2f}%</div></div>
</div>
{extras}
<h2>Trades</h2>
<table>
<thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Quantity</th><th>PNL</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</body>
</html>
"""


def render_trade_distribution(trades: Sequence[dict[str, Any]]) -> str:
    pnls = [float(t.get("pnl", 0.0)) for t in trades]
    if not pnls:
        return "<p>No trades.</p>"
    bins = Counter()
    for p in pnls:
        bucket = int(p // 10) * 10
        bins[bucket] += 1
    items = "".join(
        f"<li>{k}..{k+10}: {v}</li>" for k, v in sorted(bins.items(), key=lambda kv: kv[0])
    )
    return f"<h2>PNL histogram (10-unit buckets)</h2><ul>{items}</ul>"


def generate_report(
    title: str,
    start_time: datetime,
    end_time: datetime,
    initial_capital: float,
    final_equity: float,
    equity_curve: Sequence[tuple[datetime, float]],
    trades: Sequence[dict[str, Any]],
    metrics_extra: dict[str, Any] | None = None,
) -> str:
    if not equity_curve:
        equity_curve = [(start_time, initial_capital), (end_time, final_equity)]
    returns: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1][1]
        curr = equity_curve[i][1]
        if prev > 0:
            returns.append((curr - prev) / prev)
    body = render_html(
        title,
        start_time,
        end_time,
        initial_capital,
        final_equity,
        returns,
        equity_curve,
        trades,
        metrics_extra=metrics_extra,
    )
    histogram = render_trade_distribution(trades)
    return body.replace("</body>", histogram + "</body>")


__all__ = [
    "equity_curve_from_trades",
    "compute_drawdown_series",
    "sharpe_ratio",
    "render_html",
    "render_trade_distribution",
    "generate_report",
]
