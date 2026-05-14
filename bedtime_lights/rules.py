from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class NightWindow:
    start: str
    end: str
    timezone: str

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def night_key(self, now: datetime) -> str | None:
        local_now = now.astimezone(self.tz)
        start = _parse_time(self.start)
        end = _parse_time(self.end)
        current_time = local_now.time()

        if start <= end:
            if start <= current_time <= end:
                return local_now.date().isoformat()
            return None

        if current_time >= start:
            return local_now.date().isoformat()
        if current_time <= end:
            return (local_now.date() - timedelta(days=1)).isoformat()
        return None


@dataclass(frozen=True)
class PixelPower:
    battery_state: str | None
    charger_type: str | None


@dataclass(frozen=True)
class BedtimeInputs:
    now: datetime
    pixel: PixelPower


@dataclass(frozen=True)
class BedtimeDecision:
    should_notify: bool
    night_key: str | None
    pixel_charging: bool


def evaluate_bedtime(
    inputs: BedtimeInputs,
    window: NightWindow,
) -> BedtimeDecision:
    night_key = window.night_key(inputs.now)
    pixel_charging = is_pixel_charging(inputs.pixel)
    return BedtimeDecision(
        should_notify=bool(night_key and pixel_charging),
        night_key=night_key,
        pixel_charging=pixel_charging,
    )


def is_pixel_charging(pixel: PixelPower) -> bool:
    battery_state = (pixel.battery_state or "").strip().lower()
    charger_type = (pixel.charger_type or "").strip().lower()
    return battery_state in {"charging", "full"} and charger_type not in {
        "",
        "none",
        "unknown",
        "unavailable",
    }


def _parse_time(value: str) -> time:
    return time.fromisoformat(value)
