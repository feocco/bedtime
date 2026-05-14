from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class NotificationToken:
    night_key: str
    token: str


@dataclass
class RuntimeState:
    last_notification_night_key: str | None = None
    pending_action_night_key: str | None = None
    pending_action_token: str | None = None
    last_action_night_key: str | None = None
    delayed_action_night_key: str | None = None
    delayed_action_due_at: datetime | None = None

    @classmethod
    def load(cls, path: str | Path) -> RuntimeState:
        state_path = Path(path)
        if not state_path.exists():
            return cls()
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        return cls(
            last_notification_night_key=raw.get("last_notification_night_key"),
            pending_action_night_key=raw.get("pending_action_night_key"),
            pending_action_token=raw.get("pending_action_token"),
            last_action_night_key=raw.get("last_action_night_key"),
            delayed_action_night_key=raw.get("delayed_action_night_key"),
            delayed_action_due_at=_datetime_or_none(raw.get("delayed_action_due_at")),
        )

    def save(self, path: str | Path) -> None:
        state_path = Path(path)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_notification_night_key": self.last_notification_night_key,
            "pending_action_night_key": self.pending_action_night_key,
            "pending_action_token": self.pending_action_token,
            "last_action_night_key": self.last_action_night_key,
            "delayed_action_night_key": self.delayed_action_night_key,
            "delayed_action_due_at": self.delayed_action_due_at.isoformat()
            if self.delayed_action_due_at
            else None,
        }
        tmp_path = state_path.with_name(f".{state_path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(state_path)

    def mark_notification_sent(self, night_key: str) -> NotificationToken | None:
        if self.last_notification_night_key == night_key:
            return None
        token = secrets.token_urlsafe(18)
        self.last_notification_night_key = night_key
        self.pending_action_night_key = night_key
        self.pending_action_token = token
        return NotificationToken(night_key=night_key, token=token)

    def mark_action_handled(self, token: str) -> bool:
        if not self.pending_action_token or token != self.pending_action_token:
            return False
        self.last_action_night_key = self.pending_action_night_key
        self.pending_action_night_key = None
        self.pending_action_token = None
        return True

    def schedule_delayed_action(self, token: str, *, due_at: datetime) -> bool:
        if not self.pending_action_token or token != self.pending_action_token:
            return False
        self.delayed_action_night_key = self.pending_action_night_key
        self.delayed_action_due_at = due_at
        self.pending_action_night_key = None
        self.pending_action_token = None
        return True

    def pop_due_delayed_action(self, now: datetime) -> bool:
        if self.delayed_action_due_at is None:
            return False
        if now < self.delayed_action_due_at:
            return False
        self.last_action_night_key = self.delayed_action_night_key
        self.delayed_action_night_key = None
        self.delayed_action_due_at = None
        return True


def _datetime_or_none(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None
