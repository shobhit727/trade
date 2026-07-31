"""
Alerting System for Cryptobot.

Supports Telegram, Discord, Email, and PagerDuty notifications
with alert routing, deduplication, and escalation.
"""

from __future__ import annotations

import asyncio
import smtplib
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import StrEnum
from typing import Any

from cryptobot.config import settings
from cryptobot.utils.logging import get_logger

logger = get_logger(__name__)


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertCategory(StrEnum):
    SYSTEM = "system"
    TRADING = "trading"
    RISK = "risk"
    EXECUTION = "execution"
    ML = "ml"
    DATA = "data"


@dataclass
class Alert:
    """Alert message with metadata."""
    id: str = field(default_factory=lambda: f"alert_{datetime.utcnow().timestamp()}")
    title: str = ""
    message: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    category: AlertCategory = AlertCategory.SYSTEM
    source: str = ""
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    fingerprint: str = ""
    resolved: bool = False
    resolved_at: datetime | None = None

    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = f"{self.category}:{self.source}:{self.title}"


@dataclass
class AlertRule:
    """Alert routing and notification rules."""
    name: str
    category: AlertCategory | None = None
    severity: AlertSeverity | None = None
    labels: dict[str, str] = field(default_factory=dict)
    channels: list[str] = field(default_factory=list)
    cooldown: timedelta = field(default_factory=lambda: timedelta(minutes=15))
    auto_resolve: bool = True
    resolve_after: timedelta = field(default_factory=lambda: timedelta(hours=1))
    escalation: dict[AlertSeverity, list[str]] | None = None


class NotificationChannel(ABC):
    """Abstract notification channel."""

    @abstractmethod
    async def send(self, alert: Alert) -> bool:
        """Send alert notification. Returns True if successful."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get channel name."""
        pass


class TelegramChannel(NotificationChannel):
    """Telegram bot notification channel."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def get_name(self) -> str:
        return "telegram"

    async def send(self, alert: Alert) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram not configured")
            return False

        emoji_map = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.EMERGENCY: "🆘",
        }

        text = (
            f"{emoji_map.get(alert.severity, '📢')} <b>{alert.title}</b>\n\n"
            f"{alert.message}\n\n"
            f"<b>Severity:</b> {alert.severity.value.upper()}\n"
            f"<b>Category:</b> {alert.category.value}\n"
            f"<b>Source:</b> {alert.source}\n"
            f"<b>Time:</b> {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )

        if alert.labels:
            text += "\n<b>Labels:</b> " + ", ".join(f"{k}={v}" for k, v in alert.labels.items())

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"Telegram alert sent: {alert.id}")
                        return True
                    else:
                        logger.error(f"Telegram send failed: {resp.status} - {await resp.text()}")
                        return False
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False


class DiscordChannel(NotificationChannel):
    """Discord webhook notification channel."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def get_name(self) -> str:
        return "discord"

    async def send(self, alert: Alert) -> bool:
        if not self.webhook_url:
            logger.warning("Discord not configured")
            return False

        color_map = {
            AlertSeverity.INFO: 0x3498db,      # Blue
            AlertSeverity.WARNING: 0xf39c12,   # Orange
            AlertSeverity.CRITICAL: 0xe74c3c,  # Red
            AlertSeverity.EMERGENCY: 0x8e44ad, # Purple
        }

        embed = {
            "title": alert.title,
            "description": alert.message,
            "color": color_map.get(alert.severity, 0x95a5a6),
            "timestamp": alert.timestamp.isoformat(),
            "fields": [
                {"name": "Severity", "value": alert.severity.value.upper(), "inline": True},
                {"name": "Category", "value": alert.category.value, "inline": True},
                {"name": "Source", "value": alert.source, "inline": True},
            ],
            "footer": {"text": f"Alert ID: {alert.id}"},
        }

        if alert.labels:
            embed["fields"].append({
                "name": "Labels",
                "value": "\n".join(f"{k}: {v}" for k, v in alert.labels.items()),
                "inline": False,
            })

        payload = {"embeds": [embed]}

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=10) as resp:
                    if resp.status in (200, 204):
                        logger.info(f"Discord alert sent: {alert.id}")
                        return True
                    else:
                        logger.error(f"Discord send failed: {resp.status} - {await resp.text()}")
                        return False
        except Exception as e:
            logger.error(f"Discord error: {e}")
            return False


class EmailChannel(NotificationChannel):
    """Email notification channel via SMTP."""

    _executor: ThreadPoolExecutor | None = None
    _executor_lock = asyncio.Lock()

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_email: str,
        to_emails: list[str],
        use_tls: bool = True,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.to_emails = to_emails
        self.use_tls = use_tls

    def get_name(self) -> str:
        return "email"

    @classmethod
    async def _get_executor(cls) -> ThreadPoolExecutor:
        async with cls._executor_lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="email-sender")
            return cls._executor

    @classmethod
    async def shutdown_executor(cls):
        async with cls._executor_lock:
            if cls._executor is not None:
                cls._executor.shutdown(wait=True)
                cls._executor = None

    async def send(self, alert: Alert) -> bool:
        if not all([self.smtp_host, self.username, self.password, self.to_emails]):
            logger.warning("Email not configured")
            return False

        subject = f"[{alert.severity.value.upper()}] {alert.title}"
        body = f"""
{alert.message}

---
Severity: {alert.severity.value.upper()}
Category: {alert.category.value}
Source: {alert.source}
Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
Alert ID: {alert.id}
"""

        if alert.labels:
            body += "\nLabels:\n" + "\n".join(f"  {k}: {v}" for k, v in alert.labels.items())

        msg = MIMEMultipart()
        msg["From"] = self.from_email
        msg["To"] = ", ".join(self.to_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            # Run in shared executor to avoid blocking
            executor = await self._get_executor()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(executor, self._send_sync, msg)
            logger.info(f"Email alert sent: {alert.id}")
            return True
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False

    def _send_sync(self, msg: MIMEMultipart):
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            server.login(self.username, self.password)
            server.send_message(msg)


class PagerDutyChannel(NotificationChannel):
    """PagerDuty notification channel."""

    def __init__(self, integration_key: str):
        self.integration_key = integration_key
        self.api_url = "https://events.pagerduty.com/v2/enqueue"

    def get_name(self) -> str:
        return "pagerduty"

    async def send(self, alert: Alert) -> bool:
        if not self.integration_key:
            logger.warning("PagerDuty not configured")
            return False

        severity_map = {
            AlertSeverity.INFO: "info",
            AlertSeverity.WARNING: "warning",
            AlertSeverity.CRITICAL: "critical",
            AlertSeverity.EMERGENCY: "critical",
        }

        payload = {
            "routing_key": self.integration_key,
            "event_action": "trigger" if not alert.resolved else "resolve",
            "dedup_key": alert.fingerprint,
            "payload": {
                "summary": alert.title,
                "source": alert.source,
                "severity": severity_map.get(alert.severity, "info"),
                "component": alert.category.value,
                "custom_details": {
                    "message": alert.message,
                    "labels": alert.labels,
                    "annotations": alert.annotations,
                },
            },
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, json=payload, timeout=10) as resp:
                    if resp.status == 202:
                        logger.info(f"PagerDuty alert sent: {alert.id}")
                        return True
                    else:
                        logger.error(f"PagerDuty send failed: {resp.status} - {await resp.text()}")
                        return False
        except Exception as e:
            logger.error(f"PagerDuty error: {e}")
            return False


class AlertManager:
    """
    Central alert management with deduplication, routing, and escalation.
    """

    def __init__(self):
        self.channels: dict[str, NotificationChannel] = {}
        self.rules: list[AlertRule] = []
        self.active_alerts: dict[str, Alert] = {}
        self.alert_history: list[Alert] = []
        self._cooldowns: dict[str, datetime] = {}
        self._running = False
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def add_channel(self, channel: NotificationChannel):
        """Register a notification channel."""
        self.channels[channel.get_name()] = channel
        logger.info(f"Registered alert channel: {channel.get_name()}")

    def add_rule(self, rule: AlertRule):
        """Add alert routing rule."""
        self.rules.append(rule)
        logger.info(f"Added alert rule: {rule.name}")

    def _match_rule(self, alert: Alert, rule: AlertRule) -> bool:
        """Check if alert matches rule."""
        if rule.category and alert.category != rule.category:
            return False
        if rule.severity and alert.severity != rule.severity:
            return False
        for key, value in rule.labels.items():
            if alert.labels.get(key) != value:
                return False
        return True

    def _get_channels_for_alert(self, alert: Alert) -> list[NotificationChannel]:
        """Determine which channels to use for an alert."""
        channels = set()
        for rule in self.rules:
            if self._match_rule(alert, rule):
                for ch_name in rule.channels:
                    if ch_name in self.channels:
                        channels.add(self.channels[ch_name])
        # Default to all channels if no rules match
        if not channels:
            channels = set(self.channels.values())
        return list(channels)

    def _is_cooldown(self, alert: Alert) -> bool:
        """Check if alert is in cooldown period."""
        last_sent = self._cooldowns.get(alert.fingerprint)
        if last_sent:
            for rule in self.rules:
                if self._match_rule(alert, rule):
                    if datetime.utcnow() - last_sent < rule.cooldown:
                        return True
        return False

    async def fire(self, alert: Alert) -> int:
        """
        Fire an alert.

        Returns:
            Number of channels successfully notified
        """
        async with self._lock:
            # Check cooldown
            if self._is_cooldown(alert):
                logger.debug(f"Alert in cooldown: {alert.fingerprint}")
                return 0

            # Check if already active
            if alert.fingerprint in self.active_alerts:
                existing = self.active_alerts[alert.fingerprint]
                existing.timestamp = alert.timestamp
                existing.message = alert.message
                existing.annotations.update(alert.annotations)
                return 0  # Don't re-notify for same active alert

            # Store active alert
            self.active_alerts[alert.fingerprint] = alert
            self.alert_history.append(alert)

        # Send notifications
        channels = self._get_channels_for_alert(alert)
        sent_count = 0

        for channel in channels:
            try:
                success = await channel.send(alert)
                if success:
                    sent_count += 1
            except Exception as e:
                logger.error(f"Channel {channel.get_name()} error: {e}")

        if sent_count > 0:
            self._cooldowns[alert.fingerprint] = datetime.utcnow()

        return sent_count

    async def resolve(self, alert: Alert) -> int:
        """Resolve an active alert."""
        async with self._lock:
            existing = self.active_alerts.pop(alert.fingerprint, None)
            if not existing:
                return 0
            existing.resolved = True
            existing.resolved_at = datetime.utcnow()
            alert = existing

        # Send resolution notifications
        channels = self._get_channels_for_alert(alert)
        sent_count = 0

        for channel in channels:
            try:
                success = await channel.send(alert)
                if success:
                    sent_count += 1
            except Exception as e:
                logger.error(f"Channel {channel.get_name()} resolve error: {e}")

        return sent_count

    async def resolve_all(self, category: AlertCategory | None = None):
        """Resolve all active alerts, optionally filtered by category."""
        alerts_to_resolve = list(self.active_alerts.values())
        for alert in alerts_to_resolve:
            if category is None or alert.category == category:
                await self.resolve(alert)

    async def start(self):
        """Start alert manager background tasks."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop alert manager."""
        if not self._running:
            return
        self._running = False
        task = self._cleanup_task
        self._cleanup_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error awaiting cleanup task: {e}")

        # Shutdown email executor
        from cryptobot.monitoring.alerting import EmailChannel
        await EmailChannel.shutdown_executor()

    async def _cleanup_loop(self):
        """Periodic cleanup of old alerts and cooldowns."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self._cleanup()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert cleanup error: {e}")

    async def _cleanup(self):
        """Clean up old cooldowns and auto-resolve stale alerts."""
        now = datetime.utcnow()

        # Clean cooldowns older than 1 hour
        self._cooldowns = {
            k: v for k, v in self._cooldowns.items()
            if now - v < timedelta(hours=1)
        }

        # Auto-resolve stale alerts
        async with self._lock:
            to_resolve = []
            for _fingerprint, alert in self.active_alerts.items():
                for rule in self.rules:
                    if self._match_rule(alert, rule) and rule.auto_resolve:
                        if now - alert.timestamp > rule.resolve_after:
                            to_resolve.append(alert)
                            break

        for alert in to_resolve:
            await self.resolve(alert)

    def get_active_alerts(self) -> list[Alert]:
        """Get all active alerts."""
        return list(self.active_alerts.values())

    def get_alert_history(self, limit: int = 100) -> list[Alert]:
        """Get recent alert history."""
        return self.alert_history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get alert manager statistics."""
        return {
            "active_alerts": len(self.active_alerts),
            "total_history": len(self.alert_history),
            "channels": list(self.channels.keys()),
            "rules": len(self.rules),
        }


# Default alert rules
DEFAULT_RULES = [
    AlertRule(
        name="risk_critical",
        category=AlertCategory.RISK,
        severity=AlertSeverity.CRITICAL,
        channels=["telegram", "discord", "email"],
        cooldown=timedelta(minutes=5),
    ),
    AlertRule(
        name="risk_emergency",
        category=AlertCategory.RISK,
        severity=AlertSeverity.EMERGENCY,
        channels=["telegram", "discord", "email", "pagerduty"],
        cooldown=timedelta(minutes=1),
    ),
    AlertRule(
        name="system_down",
        category=AlertCategory.SYSTEM,
        severity=AlertSeverity.CRITICAL,
        channels=["telegram", "pagerduty"],
        cooldown=timedelta(minutes=15),
    ),
    AlertRule(
        name="execution_failure",
        category=AlertCategory.EXECUTION,
        severity=AlertSeverity.WARNING,
        channels=["telegram", "discord"],
        cooldown=timedelta(minutes=10),
    ),
    AlertRule(
        name="ml_drift",
        category=AlertCategory.ML,
        severity=AlertSeverity.WARNING,
        channels=["telegram", "discord"],
        cooldown=timedelta(hours=1),
    ),
    AlertRule(
        name="data_gaps",
        category=AlertCategory.DATA,
        severity=AlertSeverity.WARNING,
        channels=["telegram"],
        cooldown=timedelta(minutes=30),
    ),
    AlertRule(
        name="trading_signals",
        category=AlertCategory.TRADING,
        channels=["telegram"],
        cooldown=timedelta(minutes=1),
    ),
]


# Global alert manager
_alert_manager: AlertManager | None = None


def get_alert_manager() -> AlertManager:
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()

        # Configure channels from settings
        if settings.monitoring.telegram_enabled and settings.monitoring.telegram_bot_token:
            _alert_manager.add_channel(TelegramChannel(
                settings.monitoring.telegram_bot_token,
                settings.monitoring.telegram_chat_id,
            ))

        if settings.monitoring.discord_webhook:
            _alert_manager.add_channel(DiscordChannel(settings.monitoring.discord_webhook))

        if settings.monitoring.email_enabled and settings.monitoring.email_smtp_host:
            _alert_manager.add_channel(EmailChannel(
                settings.monitoring.email_smtp_host,
                settings.monitoring.email_smtp_port,
                settings.monitoring.email_username,
                settings.monitoring.email_password,
                settings.monitoring.email_from,
                settings.monitoring.email_to,
            ))

        # Add default rules
        for rule in DEFAULT_RULES:
            _alert_manager.add_rule(rule)

    return _alert_manager


async def init_alerting() -> AlertManager:
    """Initialize and start alert manager."""
    manager = get_alert_manager()
    if manager.channels:
        await manager.start()
    return manager


async def shutdown_alerting():
    """Shutdown alert manager."""
    global _alert_manager
    if _alert_manager:
        await _alert_manager.stop()
        _alert_manager = None


# Convenience functions
async def alert(
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.INFO,
    category: AlertCategory = AlertCategory.SYSTEM,
    source: str = "",
    labels: dict[str, str] | None = None,
) -> int:
    """Fire an alert."""
    manager = get_alert_manager()
    alert = Alert(
        title=title,
        message=message,
        severity=severity,
        category=category,
        source=source,
        labels=labels or {},
    )
    return await manager.fire(alert)


async def alert_critical(
    title: str,
    message: str,
    category: AlertCategory = AlertCategory.SYSTEM,
    source: str = "",
    labels: dict[str, str] | None = None,
) -> int:
    """Fire a critical alert."""
    return await alert(title, message, AlertSeverity.CRITICAL, category, source, labels)


async def alert_emergency(
    title: str,
    message: str,
    category: AlertCategory = AlertCategory.RISK,
    source: str = "",
    labels: dict[str, str] | None = None,
) -> int:
    """Fire an emergency alert."""
    return await alert(title, message, AlertSeverity.EMERGENCY, category, source, labels)


async def resolve_alert(fingerprint: str) -> int:
    """Resolve an alert by fingerprint."""
    manager = get_alert_manager()
    alert = manager.active_alerts.get(fingerprint)
    if alert:
        return await manager.resolve(alert)
    return 0
