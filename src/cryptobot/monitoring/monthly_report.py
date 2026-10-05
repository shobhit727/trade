"""Monthly family report — PDF generator (Seed Phase reporting).

One page per month: equity curve, headline stats, global-fund status, paper
gate progress, breaker state, and the India VDA tax estimate. Built on fpdf2
(pure Python) so it renders anywhere without system fonts or browsers.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

logger = logging.getLogger(__name__)


def _equity_series(stats_history: list[dict]) -> list[tuple[str, float]]:
    """(date_iso, equity) pairs from gate snapshots or caller-supplied history."""
    return [
        (row["date"], float(row["equity"]))
        for row in stats_history
        if row.get("equity") not in (None, "")
    ]


class _ReportPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("helvetica", "I", 8)
        self.cell(0, 10, f"cryptobot seed-phase report - page {self.page_no()}/{{nb}}", align="C")


def build_monthly_report(
    out_path: str | Path,
    month_label: str,
    stats: dict,
    equity_history: list[dict],
    tax_summary: dict,
) -> Path:
    """Render the PDF; returns the written path."""
    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, f"Cryptobot Monthly Report - {month_label}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 6, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}",
             new_x="LMARGIN", new_y="NEXT")

    # --- headline stats table ---
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "Performance", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    rows = [
        ("Strategy", f"{stats.get('strategy', '-')} ({stats.get('symbol', '-')}, {stats.get('timeframe', '-')})"),
        ("Mode", str(stats.get("mode", "-"))),
        ("Equity (current)", str(stats.get("equity", "-"))),
        ("Orders / fills / rejects",
         f"{stats.get('orders_submitted', 0)} / {stats.get('fills', 0)} / {stats.get('rejects', 0)}"),
        ("Risk profile", str(stats.get("risk_profile", "realistic"))),
    ]
    for label, value in rows:
        pdf.cell(60, 7, label)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")

    # --- equity curve ---
    series = _equity_series(equity_history)
    if len(series) >= 2:
        pdf.ln(2)
        values = [v for _d, v in series]
        vmin, vmax = min(values), max(values)
        span = (vmax - vmin) or 1.0
        w, h = 180, 60
        x0 = pdf.l_margin
        y0 = pdf.get_y() + 4
        pdf.set_draw_color(200)
        pdf.rect(x0, y0, w, h)
        step = w / (len(series) - 1)
        pdf.set_draw_color(20, 90, 170)
        pdf.set_line_width(0.5)
        prev = None
        for i, (_d, v) in enumerate(series):
            px = x0 + i * step
            py = y0 + h - ((v - vmin) / span) * (h - 6) - 3
            if prev:
                pdf.line(prev[0], prev[1], px, py)
            prev = (px, py)
        pdf.set_xy(x0, y0 + h + 1)
        pdf.set_font("helvetica", "I", 8)
        pdf.cell(0, 5, f"Equity curve ({series[0][0]} to {series[-1][0]}; "
                       f"low {vmin:.2f} / high {vmax:.2f})", new_x="LMARGIN", new_y="NEXT")

    # --- safety systems ---
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "Safety systems", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    fund = stats.get("global_fund") or {}
    gate = stats.get("paper_gate") or {}
    breaker = stats.get("breaker") or {}
    safety = [
        ("Global fund balance", str(fund.get("fund_balance", "0"))),
        ("Fund frozen", str(fund.get("frozen", False))),
        ("Paper gate", f"{gate.get('status', '-')} "
                       f"({gate.get('days_elapsed', 0)}/{gate.get('window_days', 60)} days)"),
        ("Circuit breaker", "TRIPPED: " + breaker.get("reason", "") if breaker.get("tripped") else "ok"),
    ]
    for label, value in safety:
        pdf.cell(60, 7, label)
        pdf.cell(0, 7, value, new_x="LMARGIN", new_y="NEXT")

    # --- tax estimate ---
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(0, 8, "India VDA tax estimate (Section 115BBH)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 10)
    for key in ("total_proceeds", "taxable_income", "estimated_tax", "tds_credits", "net_tax_payable"):
        pdf.cell(60, 7, key.replace("_", " "))
        pdf.cell(0, 7, str(tax_summary.get(key, "0")), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font("helvetica", "I", 8)
    pdf.multi_cell(0, 5,
                   "Estimate only - losses are never offset per Section 115BBH(2). "
                   "Your CA verifies and files using the Schedule VDA CSV export.")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    logger.info("monthly report written: %s", out)
    return out


__all__ = ["build_monthly_report"]
