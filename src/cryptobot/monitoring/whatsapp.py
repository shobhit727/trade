"""WhatsApp sender via Meta Business Cloud API (Seed Phase reporting).

Env-configured, dedicated-number setup per the agreed plan:
  WHATSAPP_TOKEN        — permanent system-user token
  WHATSAPP_PHONE_ID     — the dedicated business phone-number ID
  WHATSAPP_TO           — recipient list, comma-separated

Messages are plain text under the 4096-char Cloud API limit. Failures never
propagate into the trading loop.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_API_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"
_MAX_LEN = 4096


@dataclass
class WhatsAppConfig:
    token: str = ""
    phone_id: str = ""
    to: list[str] | None = None

    @classmethod
    def from_env(cls) -> WhatsAppConfig:
        raw = os.getenv("WHATSAPP_TO", "")
        return cls(
            token=os.getenv("WHATSAPP_TOKEN", ""),
            phone_id=os.getenv("WHATSAPP_PHONE_ID", ""),
            to=[w.strip() for w in raw.split(",") if w.strip()],
        )

    def configured(self) -> bool:
        return bool(self.token and self.phone_id and self.to)


def format_daily_summary(stats: dict) -> str:
    """Short Hinglish-free English summary for end-of-day WhatsApp."""
    equity = stats.get("equity", "-")
    mode = stats.get("mode", "-")
    gate = stats.get("paper_gate") or {}
    breaker = stats.get("breaker") or {}
    fund = stats.get("global_fund") or {}
    lines = [
        f"Cryptobot EOD ({mode}): equity {equity}",
        f"Orders {stats.get('orders_submitted', 0)} | fills {stats.get('fills', 0)}"
        f" | rejects {stats.get('rejects', 0)}",
        f"Fund {fund.get('fund_balance', '0')}"
        + (" (FROZEN)" if fund.get("frozen") else ""),
    ]
    if gate:
        lines.append(f"Gate: {gate.get('status')} "
                     f"{gate.get('days_elapsed', 0)}/{gate.get('window_days', 60)}d")
    if breaker.get("tripped"):
        lines.append(f"ALERT: breaker tripped - {breaker.get('reason', '')}")
    return "\n".join(lines)[:_MAX_LEN]


async def send_whatsapp(text: str, cfg: WhatsAppConfig | None = None) -> bool:
    """Send to every recipient; True only if all sends succeed."""
    import aiohttp

    cfg = cfg or WhatsAppConfig.from_env()
    if not cfg.configured():
        logger.warning("whatsapp not configured (WHATSAPP_TOKEN/PHONE_ID/TO); skipped")
        return False

    url = _API_URL.format(phone_id=cfg.phone_id)
    headers = {"Authorization": f"Bearer {cfg.token}"}
    ok = True
    async with aiohttp.ClientSession() as session:
        for recipient in cfg.to or []:
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": text},
            }
            try:
                async with session.post(url, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status >= 400:
                        body = await resp.text()
                        logger.warning("whatsapp send to %s failed: %s %s",
                                       recipient, resp.status, body[:200])
                        ok = False
            except Exception as exc:  # noqa: BLE001 - alerting must never kill trading
                logger.warning("whatsapp send to %s errored: %s", recipient, exc)
                ok = False
    return ok


__all__ = ["WhatsAppConfig", "format_daily_summary", "send_whatsapp"]
