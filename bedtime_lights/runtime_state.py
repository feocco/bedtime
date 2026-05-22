from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class NotificationToken:
    night_key: str
    token: str


@dataclass
class NightHistory:
    night_key: str
    notification_sent_at: datetime | None = None
    action_used: bool = False
    action_type: str | None = None
    action_clicked_at: datetime | None = None
    delayed_action_ran_at: datetime | None = None
    morning_prompt_sent_at: datetime | None = None
    feedback_reply_at: datetime | None = None
    feedback_text: str | None = None
    feedback_token: str | None = None

    @classmethod
    def from_payload(cls, night_key: str, raw: dict[str, object]) -> NightHistory:
        return cls(
            night_key=night_key,
            notification_sent_at=_datetime_or_none(raw.get("notification_sent_at")),
            action_used=bool(raw.get("action_used")),
            action_type=_string_or_none(raw.get("action_type")),
            action_clicked_at=_datetime_or_none(raw.get("action_clicked_at")),
            delayed_action_ran_at=_datetime_or_none(raw.get("delayed_action_ran_at")),
            morning_prompt_sent_at=_datetime_or_none(raw.get("morning_prompt_sent_at")),
            feedback_reply_at=_datetime_or_none(raw.get("feedback_reply_at")),
            feedback_text=_string_or_none(raw.get("feedback_text")),
            feedback_token=_string_or_none(raw.get("feedback_token")),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "notification_sent_at": _datetime_payload(self.notification_sent_at),
            "action_used": self.action_used,
            "action_type": self.action_type,
            "action_clicked_at": _datetime_payload(self.action_clicked_at),
            "delayed_action_ran_at": _datetime_payload(self.delayed_action_ran_at),
            "morning_prompt_sent_at": _datetime_payload(self.morning_prompt_sent_at),
            "feedback_reply_at": _datetime_payload(self.feedback_reply_at),
            "feedback_text": self.feedback_text,
            "feedback_token": self.feedback_token,
        }


@dataclass
class RuntimeState:
    last_notification_night_key: str | None = None
    pending_action_night_key: str | None = None
    pending_action_token: str | None = None
    last_action_night_key: str | None = None
    delayed_action_night_key: str | None = None
    delayed_action_due_at: datetime | None = None
    history: dict[str, NightHistory] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> RuntimeState:
        state_path = Path(path)
        if not state_path.exists():
            return cls()
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        history_raw = raw.get("history")
        return cls(
            last_notification_night_key=raw.get("last_notification_night_key"),
            pending_action_night_key=raw.get("pending_action_night_key"),
            pending_action_token=raw.get("pending_action_token"),
            last_action_night_key=raw.get("last_action_night_key"),
            delayed_action_night_key=raw.get("delayed_action_night_key"),
            delayed_action_due_at=_datetime_or_none(raw.get("delayed_action_due_at")),
            history=_history_from_payload(history_raw),
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
            "history": {
                night_key: record.to_payload()
                for night_key, record in sorted(self.history.items())
            },
        }
        tmp_path = state_path.with_name(f".{state_path.name}.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(state_path)

    def mark_notification_sent(
        self,
        night_key: str,
        *,
        sent_at: datetime | None = None,
    ) -> NotificationToken | None:
        if self.last_notification_night_key == night_key:
            return None
        token = secrets.token_urlsafe(18)
        self.last_notification_night_key = night_key
        self.pending_action_night_key = night_key
        self.pending_action_token = token
        self._record(night_key).notification_sent_at = sent_at
        return NotificationToken(night_key=night_key, token=token)

    def mark_action_handled(
        self,
        token: str,
        *,
        clicked_at: datetime | None = None,
    ) -> bool:
        if not self.pending_action_token or token != self.pending_action_token:
            return False
        night_key = self.pending_action_night_key
        self.last_action_night_key = night_key
        self.pending_action_night_key = None
        self.pending_action_token = None
        if night_key is not None:
            record = self._record(night_key)
            record.action_used = True
            record.action_type = "immediate"
            record.action_clicked_at = clicked_at
        return True

    def schedule_delayed_action(
        self,
        token: str,
        *,
        due_at: datetime,
        clicked_at: datetime | None = None,
    ) -> bool:
        if not self.pending_action_token or token != self.pending_action_token:
            return False
        self.delayed_action_night_key = self.pending_action_night_key
        self.delayed_action_due_at = due_at
        self.pending_action_night_key = None
        self.pending_action_token = None
        if self.delayed_action_night_key is not None:
            record = self._record(self.delayed_action_night_key)
            record.action_used = True
            record.action_type = "delayed"
            record.action_clicked_at = clicked_at
        return True

    def pop_due_delayed_action(self, now: datetime) -> bool:
        if self.delayed_action_due_at is None:
            return False
        if now < self.delayed_action_due_at:
            return False
        night_key = self.delayed_action_night_key
        self.last_action_night_key = night_key
        self.delayed_action_night_key = None
        self.delayed_action_due_at = None
        if night_key is not None:
            self._record(night_key).delayed_action_ran_at = now
        return True

    def mark_morning_prompt_sent(
        self,
        night_key: str,
        *,
        sent_at: datetime,
    ) -> NotificationToken | None:
        record = self.history.get(night_key)
        if record is None or record.notification_sent_at is None:
            return None
        if record.action_used or record.morning_prompt_sent_at is not None:
            return None
        token = secrets.token_urlsafe(18)
        record.morning_prompt_sent_at = sent_at
        record.feedback_token = token
        return NotificationToken(night_key=night_key, token=token)

    def record_feedback(self, token: str, text: str, *, replied_at: datetime) -> bool:
        for record in self.history.values():
            if record.feedback_token != token:
                continue
            record.feedback_reply_at = replied_at
            record.feedback_text = text.strip()
            record.feedback_token = None
            return True
        return False

    def prune_history(self, *, now: datetime, retention_days: int) -> None:
        cutoff = now.date().toordinal() - retention_days
        for night_key in list(self.history):
            night_date = _date_ordinal_or_none(night_key)
            if night_date is not None and night_date < cutoff:
                del self.history[night_key]

    def _record(self, night_key: str) -> NightHistory:
        record = self.history.get(night_key)
        if record is None:
            record = NightHistory(night_key=night_key)
            self.history[night_key] = record
        return record


def _datetime_or_none(value: object) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value else None


def _datetime_payload(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _string_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def _history_from_payload(value: object) -> dict[str, NightHistory]:
    if not isinstance(value, dict):
        return {}
    history: dict[str, NightHistory] = {}
    for night_key, raw_record in value.items():
        if not isinstance(raw_record, dict):
            continue
        history[str(night_key)] = NightHistory.from_payload(str(night_key), raw_record)
    return history


def _date_ordinal_or_none(value: str) -> int | None:
    try:
        return datetime.fromisoformat(value).date().toordinal()
    except ValueError:
        return None
