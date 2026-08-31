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
from dataclasses import dataclass

from cryptobot.config import settings

logger = logging.getLogger(__name__)


def _get_whatsapp_api_url() -> str:
    return settings.external_services.whatsapp_api_url

_MAX_LEN = 4096


@dataclass
class WhatsAppConfig:
    token: str = ""
    phone_id: str = ""
    to: list[str] | None = None

    @classmethod
    def from_env(cls) -> WhatsAppConfig:
        m = settings.monitoring
        to_raw = m.whatsapp_to
        return cls(
            token=m.whatsapp_token,
            phone_id=m.whatsapp_phone_id,
            to=list(to_raw) if to_raw else [],
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
    from cryptobot.config import get_settings

    cfg = cfg or WhatsAppConfig.from_env()
    if not cfg.configured():
        logger.warning("whatsapp not configured (WHATSAPP_TOKEN/PHONE_ID/TO); skipped")
        return False

    url = _get_whatsapp_api_url().format(phone_id=cfg.phone_id)
    headers = {"Authorization": f"Bearer {cfg.token}"}
    timeout = get_settings().timeouts.http_long_timeout
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
                                        timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
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
