from pathlib import Path

from cryptobot.utils.audit import ActionAudit


def test_audit_log_and_tail(tmp_path: Path):
    audit = ActionAudit(state_path=str(tmp_path / "audit.jsonl"))
    assert audit.tail() == []
    audit.log("alice", "breaker-reset", {"state": "state/breaker.json"})
    audit.log("bob", "gate-override", None)
    tail = audit.tail(n=10)
    assert len(tail) == 2
    assert tail[0]["actor"] == "alice"
    assert tail[0]["action"] == "breaker-reset"
    assert tail[1]["actor"] == "bob"
    assert tail[0]["ts"] and tail[0]["details"] == {"state": "state/breaker.json"}
    # tail n=1
    assert len(audit.tail(n=1)) == 1
    assert audit.tail(n=1)[0]["actor"] == "bob"
    # file exists and is JSONL
    lines = (tmp_path / "audit.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


def test_audit_log_creates_parent_dirs(tmp_path: Path):
    deep = tmp_path / "deep" / "nested" / "audit.jsonl"
    audit = ActionAudit(state_path=str(deep))
    audit.log("owner", "test", {})
    assert deep.exists()
    assert len(audit.tail()) == 1
