from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class NightWindowConfig:
    start: str
    end: str


@dataclass(frozen=True)
class PixelConfig:
    battery_state_entity: str
    charger_type_entity: str


@dataclass(frozen=True)
class ActionConfig:
    script_entity: str


@dataclass(frozen=True)
class NotificationConfig:
    title: str
    message: str


@dataclass(frozen=True)
class BedtimeConfig:
    timezone: str
    night_window: NightWindowConfig
    pixel: PixelConfig
    action: ActionConfig
    delayed_action_minutes: int
    notification: NotificationConfig

    @property
    def watched_entities(self) -> set[str]:
        return {
            self.pixel.battery_state_entity,
            self.pixel.charger_type_entity,
            self.action.script_entity,
        }


@dataclass(frozen=True)
class ServiceConfig:
    config_path: str
    state_path: str
    log_level: str
    dry_run: bool
    reconcile_seconds: int


def load_bedtime_config(path: str | Path) -> BedtimeConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("config must be a mapping")
    return parse_bedtime_config(raw)


def parse_bedtime_config(raw: dict[str, Any]) -> BedtimeConfig:
    night_window = _mapping(raw, "night_window")
    pixel = _mapping(raw, "pixel")
    action = _mapping(raw, "action")
    notification = _mapping(raw, "notification")
    return BedtimeConfig(
        timezone=_string(raw, "timezone"),
        night_window=NightWindowConfig(
            start=_string(night_window, "start"),
            end=_string(night_window, "end"),
        ),
        pixel=PixelConfig(
            battery_state_entity=_string(pixel, "battery_state_entity"),
            charger_type_entity=_string(pixel, "charger_type_entity"),
        ),
        action=ActionConfig(script_entity=_string(action, "script_entity")),
        delayed_action_minutes=int(raw.get("delayed_action_minutes", 30)),
        notification=NotificationConfig(
            title=_string(notification, "title"),
            message=_string(notification, "message"),
        ),
    )


def load_service_config() -> ServiceConfig:
    return ServiceConfig(
        config_path=os.environ.get("CONFIG_PATH", "config.yaml"),
        state_path=os.environ.get("STATE_PATH", "data/state.json"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        dry_run=_env_bool("DRY_RUN", default=False),
        reconcile_seconds=int(os.environ.get("RECONCILE_SECONDS", "60")),
    )


def _mapping(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return value


def _string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
