"""Daily P&L email digest via Gmail SMTP (Seed Phase reporting).

Credentials come from env (never hardcoded):
  EMAIL_SMTP_USER / EMAIL_SMTP_PASS  — Gmail app-password
  EMAIL_TO                           — recipient list, comma-separated
"""

from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    user: str = ""
    password: str = ""
    to: list[str] | None = None

    @classmethod
    def from_env(cls) -> EmailConfig:
        to_raw = os.getenv("EMAIL_TO", "")
        return cls(
            user=os.getenv("EMAIL_SMTP_USER", ""),
            password=os.getenv("EMAIL_SMTP_PASS", ""),
            to=[addr.strip() for addr in to_raw.split(",") if addr.strip()],
        )

    def configured(self) -> bool:
        return bool(self.user and self.password and self.to)


def format_digest(stats: dict) -> str:
    """Plain-text daily digest body from trader stats_snapshot()."""
    lines = [
        "Daily trading digest",
        "====================",
        f"Status      : {stats.get('status')}",
        f"Strategy    : {stats.get('strategy')} {stats.get('symbol')} {stats.get('timeframe')}",
        f"Mode        : {stats.get('mode')}",
        f"Equity      : {stats.get('equity')}",
        f"Bars fed    : {stats.get('bars_fed')} (seen {stats.get('bars_seen')})",
        f"Orders      : {stats.get('orders_submitted')} submitted, "
        f"{stats.get('fills')} fills, {stats.get('rejects')} rejects",
    ]
    fund = stats.get("global_fund") or {}
    lines.append(f"Global fund : {fund.get('fund_balance', '0')} "
                 f"(frozen={fund.get('frozen', False)})")
    gate = stats.get("paper_gate")
    if gate:
        lines.append(f"Paper gate  : {gate.get('status')} "
                     f"({gate.get('days_elapsed')}/{gate.get('window_days')} days)")
    breaker = stats.get("breaker") or {}
    lines.append(f"Breaker     : {'TRIPPED - ' + breaker.get('reason', '') if breaker.get('tripped') else 'ok'}")
    tax = stats.get("tax_summary") or {}
    if tax:
        lines.append(f"Tax est.    : {tax.get('estimated_tax', '0')} "
                         f"(net payable {tax.get('net_tax_payable', '0')})")
    return "\n".join(lines)


def send_digest(stats: dict, cfg: EmailConfig | None = None,
                subject_prefix: str = "[cryptobot]") -> bool:
    """Send the digest; returns True on success. Never raises."""
    cfg = cfg or EmailConfig.from_env()
    if not cfg.configured():
        logger.warning("email not configured (EMAIL_SMTP_USER/PASS/TO); digest skipped")
        return False
    msg = EmailMessage()
    msg["Subject"] = f"{subject_prefix} daily digest"
    msg["From"] = cfg.user
    msg["To"] = ", ".join(cfg.to or [])
    msg.set_content(format_digest(stats))
    try:
        with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=30) as smtp:
            smtp.login(cfg.user, cfg.password)
            smtp.send_message(msg)
        logger.info("digest emailed to %s", cfg.to)
        return True
    except Exception as exc:  # noqa: BLE001 - alerting must never kill trading
        logger.warning("digest email failed: %s", exc)
        return False


__all__ = ["EmailConfig", "format_digest", "send_digest"]
