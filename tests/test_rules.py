from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bedtime_lights.rules import (
    NightWindow,
    PersonPresence,
    PixelPower,
    BedtimeInputs,
    evaluate_bedtime,
    is_pixel_charging,
)


NY = ZoneInfo("America/New_York")


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=NY)


def test_night_window_crosses_midnight() -> None:
    window = NightWindow(start="21:45", end="04:00", timezone="America/New_York")

    before_start = dt("2026-05-11T21:44:59")
    after_start = dt("2026-05-11T21:45:00")
    after_midnight = dt("2026-05-12T00:15:00")
    after_end = dt("2026-05-12T04:00:01")

    assert window.night_key(before_start) is None
    assert window.night_key(after_start) == "2026-05-11"
    assert window.night_key(after_midnight) == "2026-05-11"
    assert window.night_key(after_end) is None


def test_presence_counts_when_start_is_for_current_night_and_end_is_fresh() -> None:
    window = NightWindow(start="21:45", end="04:00", timezone="America/New_York")
    now = dt("2026-05-12T00:15:00")
    person = PersonPresence(
        name="Sleeper A",
        presence_start=datetime.fromisoformat("2026-05-12T02:05:00+00:00"),
        presence_end=datetime.fromisoformat("2026-05-12T04:28:30+00:00"),
    )

    assert person.is_in_bed(now, window, fresh_minutes=20)


def test_presence_rejects_stale_or_previous_night_timestamps() -> None:
    window = NightWindow(start="21:45", end="04:00", timezone="America/New_York")
    now = dt("2026-05-12T00:15:00")

    stale_end = PersonPresence(
        name="Sleeper A",
        presence_start=datetime.fromisoformat("2026-05-12T02:05:00+00:00"),
        presence_end=datetime.fromisoformat("2026-05-12T03:40:00+00:00"),
    )
    previous_night = PersonPresence(
        name="Sleeper B",
        presence_start=datetime.fromisoformat("2026-05-11T01:58:00+00:00"),
        presence_end=datetime.fromisoformat("2026-05-12T04:28:30+00:00"),
    )

    assert not stale_end.is_in_bed(now, window, fresh_minutes=20)
    assert not previous_night.is_in_bed(now, window, fresh_minutes=20)


def test_pixel_charging_requires_charging_state_and_real_charger() -> None:
    assert is_pixel_charging(PixelPower(battery_state="charging", charger_type="ac"))
    assert is_pixel_charging(PixelPower(battery_state="full", charger_type="wireless"))
    assert not is_pixel_charging(PixelPower(battery_state="charging", charger_type="none"))
    assert not is_pixel_charging(PixelPower(battery_state="discharging", charger_type="ac"))
    assert not is_pixel_charging(PixelPower(battery_state="not_charging", charger_type="none"))


def test_evaluate_bedtime_requires_window_presence_and_phone_charging() -> None:
    window = NightWindow(start="21:45", end="04:00", timezone="America/New_York")
    now = dt("2026-05-12T00:15:00")
    inputs = BedtimeInputs(
        now=now,
        people=[
            PersonPresence(
                name="Sleeper A",
                presence_start=datetime.fromisoformat("2026-05-12T02:05:00+00:00"),
                presence_end=datetime.fromisoformat("2026-05-12T04:28:30+00:00"),
            )
        ],
        pixel=PixelPower(battery_state="charging", charger_type="ac"),
    )

    decision = evaluate_bedtime(inputs, window, fresh_minutes=20)

    assert decision.should_notify
    assert decision.night_key == "2026-05-11"
    assert decision.in_bed_people == ["Sleeper A"]
