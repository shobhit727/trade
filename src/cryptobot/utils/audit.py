"""Owner-action audit log (Seed Phase ops).

Every manual intervention — breaker resets, gate overrides, config changes —
appends an immutable JSONL record. The no-touch pact is only enforceable if
touches are *recorded*.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ActionAudit:
    def __init__(self, state_path: str = "state/audit_log.jsonl"):
        self.state_path = Path(state_path)

    def log(self, actor: str, action: str, details: dict[str, Any] | None = None) -> None:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "actor": actor,
            "action": action,
            "details": details or {},
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        logger.info("audit: %s %s", actor, action)

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        if not self.state_path.exists():
            return []
        lines = self.state_path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines[-n:] if line.strip()]


__all__ = ["ActionAudit"]
