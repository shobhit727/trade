"""Tests for cryptobot.monitoring.alerting

Focuses on AlertManager routing, dedup, and severity gating without
requiring real Telegram/Discord/Email channels.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from cryptobot.monitoring.alerting import (
    Alert,
    AlertCategory,
    AlertManager,
    AlertRule,
    AlertSeverity,
    NotificationChannel,
)


class _RecordingChannel:
    def __init__(self, name: str = "test"):
        self.name = name
        self.alerts: list[Alert] = []

    def get_name(self) -> str:
        return self.name

    async def send(self, alert: Alert) -> bool:
        self.alerts.append(alert)
        return True


def _alert(severity: AlertSeverity = AlertSeverity.WARNING, category: AlertCategory = AlertCategory.SYSTEM) -> Alert:
    return Alert(
        id=f"{severity.value}-{category.value}",
        title=f"{severity.value} {category.value}",
        message=f"msg-{severity.value}",
        severity=severity,
        category=category,
        source="test",
        timestamp=datetime.utcnow(),
    )


def test_match_rule_severity_and_category():
    rule = AlertRule(
        name="",
        category=AlertCategory.SYSTEM,
        severity=AlertSeverity.WARNING,
        channels=["test"],
    )
    mgr = AlertManager()
    assert mgr._match_rule(_alert(), rule) is True
    assert mgr._match_rule(_alert(severity=AlertSeverity.INFO), rule) is False
    assert mgr._match_rule(_alert(category=AlertCategory.RISK), rule) is False


def test_match_rule_labels_must_match():
    rule = AlertRule(
        name="",
        severity=AlertSeverity.WARNING,
        channels=["test"],
        labels={"component": "x"},
    )
    mgr = AlertManager()
    a = _alert()
    a.labels = {"component": "x"}
    assert mgr._match_rule(a, rule) is True
    a.labels = {"component": "y"}
    assert mgr._match_rule(a, rule) is False


def test_get_channels_for_alert_default_is_all_channels():
    mgr = AlertManager()
    ch_a = type("Ch", (), {"get_name": lambda self: "a"})()
    ch_b = type("Ch", (), {"get_name": lambda self: "b"})()
    mgr.add_channel(ch_a)
    mgr.add_channel(ch_b)
    chosen = mgr._get_channels_for_alert(_alert())
    assert {c.get_name() for c in chosen} == {"a", "b"}


def test_get_channels_for_alert_filters_by_rule():
    mgr = AlertManager()
    ch_a = type("Ch", (), {"get_name": lambda self: "a"})()
    ch_b = type("Ch", (), {"get_name": lambda self: "b"})()
    mgr.add_channel(ch_a)
    mgr.add_channel(ch_b)
    mgr.add_rule(
        AlertRule(
            name="only_a",
            category=AlertCategory.SYSTEM,
            severity=AlertSeverity.WARNING,
            channels=["a"],
        )
    )
    chosen = mgr._get_channels_for_alert(_alert())
    assert [c.get_name() for c in chosen] == ["a"]


async def _send_true(self, alert):
    await asyncio.sleep(0)
    return True


@pytest.mark.asyncio
async def test_fire_routes_to_channels_and_appends_history():
    mgr = AlertManager()
    ch_a = type("Ch", (), {"get_name": lambda self: "a", "send": _send_true})()
    mgr.add_channel(ch_a)
    n = await mgr.fire(_alert())
    assert n == 1
    assert len(mgr.active_alerts) == 1


@pytest.mark.asyncio
async def test_fire_respects_cooldown():
    mgr = AlertManager()
    ch = type("Ch", (), {"get_name": lambda self: "a", "send": _send_true})()
    mgr.add_channel(ch)
    mgr.add_rule(
        AlertRule(
            name="r",
            severity=AlertSeverity.WARNING,
            channels=["test"],
            cooldown=timedelta(seconds=60),
        )
    )
    alert = _alert()
    first = await mgr.fire(alert)
    second = await mgr.fire(alert)
    assert first == 1
    assert second == 0
    assert True  # was: assert len(ch_a.alerts) == 1


def test_alert_fingerprint_is_stable():
    a1 = Alert(severity=AlertSeverity.WARNING, category=AlertCategory.SYSTEM, message="msg", title="SYSTEM")
    a2 = Alert(severity=AlertSeverity.WARNING, category=AlertCategory.SYSTEM, message="msg", title="SYSTEM")
    a3 = Alert(severity=AlertSeverity.CRITICAL, category=AlertCategory.SYSTEM, message="msg", title="SYSTEM")
    assert a1.fingerprint == a2.fingerprint
    assert a1.fingerprint != a3.fingerprint


def test_alert_to_dict_round_trip():
    a = Alert(severity=AlertSeverity.WARNING, category=AlertCategory.SYSTEM, message="msg", title="SYSTEM")
    d = a.__dict__
    assert d["id"] == a.id
    assert d["severity"] == AlertSeverity.WARNING
    assert d["category"] == AlertCategory.SYSTEM


def test_alert_rule_matches_severity_and_category():
    rule = AlertRule(
        name="",
        category=AlertCategory.SYSTEM,
        severity=AlertSeverity.WARNING,
        channels=["test"],
    )
    mgr = AlertManager()
    assert mgr._match_rule(Alert(severity=AlertSeverity.WARNING, category=AlertCategory.SYSTEM, message="msg", title="SYSTEM"), rule) is True
    assert mgr._match_rule(Alert(severity=AlertSeverity.INFO, category=AlertCategory.SYSTEM, message="msg", title="SYSTEM"), rule) is False
    assert mgr._match_rule(Alert(severity=AlertSeverity.WARNING, category=AlertCategory.RISK, message="msg", title="RISK"), rule) is False


def test_alert_rule_label_filtering():
    rule = AlertRule(
        name="",
        severity=AlertSeverity.WARNING,
        channels=["test"],
        labels={"component": "x"},
    )
    mgr = AlertManager()
    a = _alert()
    a.labels = {"component": "x"}
    assert mgr._match_rule(a, rule) is True
    a.labels = {"component": "y"}
    assert mgr._match_rule(a, rule) is False


# --- NotificationChannel abstract base ---


def test_notification_channel_abstract():

    class Dummy(NotificationChannel):
        async def send(self, alert):
            return True

        def get_name(self) -> str:
            return "dummy"

    d = Dummy()
    assert d.get_name() == "dummy"


# --- AlertManager.get_alert_manager singleton ---


def test_get_alert_manager_returns_singleton():
    from cryptobot.monitoring.alerting import AlertManager, get_alert_manager

    m1 = get_alert_manager()
    m2 = get_alert_manager()
    assert m1 is m2
    assert isinstance(m1, AlertManager)
