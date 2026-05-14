from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bedtime_lights.rules import (
    BedtimeInputs,
    NightWindow,
    PixelPower,
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


def test_pixel_charging_requires_charging_state_and_real_charger() -> None:
    assert is_pixel_charging(PixelPower(battery_state="charging", charger_type="ac"))
    assert is_pixel_charging(PixelPower(battery_state="full", charger_type="wireless"))
    assert not is_pixel_charging(PixelPower(battery_state="charging", charger_type="none"))
    assert not is_pixel_charging(PixelPower(battery_state="discharging", charger_type="ac"))
    assert not is_pixel_charging(PixelPower(battery_state="not_charging", charger_type="none"))


def test_evaluate_bedtime_requires_only_window_and_phone_charging() -> None:
    window = NightWindow(start="21:45", end="04:00", timezone="America/New_York")
    now = dt("2026-05-12T00:15:00")
    inputs = BedtimeInputs(
        now=now,
        pixel=PixelPower(battery_state="charging", charger_type="ac"),
    )

    decision = evaluate_bedtime(inputs, window)

    assert decision.should_notify
    assert decision.night_key == "2026-05-11"
