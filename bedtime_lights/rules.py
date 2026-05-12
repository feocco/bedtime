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

    def night_start_at(self, now: datetime) -> datetime | None:
        key = self.night_key(now)
        if key is None:
            return None
        return datetime.combine(datetime.fromisoformat(key).date(), _parse_time(self.start), self.tz)


@dataclass(frozen=True)
class PersonPresence:
    name: str
    presence_start: datetime | None
    presence_end: datetime | None

    def is_in_bed(self, now: datetime, window: NightWindow, *, fresh_minutes: int) -> bool:
        if self.presence_start is None or self.presence_end is None:
            return False
        night_start = window.night_start_at(now)
        if night_start is None:
            return False
        local_start = self.presence_start.astimezone(window.tz)
        local_end = self.presence_end.astimezone(window.tz)
        local_now = now.astimezone(window.tz)
        return local_start >= night_start and local_end >= local_now - timedelta(minutes=fresh_minutes)


@dataclass(frozen=True)
class PixelPower:
    battery_state: str | None
    charger_type: str | None


@dataclass(frozen=True)
class BedtimeInputs:
    now: datetime
    people: list[PersonPresence]
    pixel: PixelPower


@dataclass(frozen=True)
class BedtimeDecision:
    should_notify: bool
    night_key: str | None
    in_bed_people: list[str]
    pixel_charging: bool


def evaluate_bedtime(
    inputs: BedtimeInputs,
    window: NightWindow,
    *,
    fresh_minutes: int,
) -> BedtimeDecision:
    night_key = window.night_key(inputs.now)
    in_bed_people = [
        person.name
        for person in inputs.people
        if person.is_in_bed(inputs.now, window, fresh_minutes=fresh_minutes)
    ]
    pixel_charging = is_pixel_charging(inputs.pixel)
    return BedtimeDecision(
        should_notify=bool(night_key and in_bed_people and pixel_charging),
        night_key=night_key,
        in_bed_people=in_bed_people,
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

