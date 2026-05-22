from __future__ import annotations

from bedtime_lights.config import parse_bedtime_config


def test_parse_bedtime_config_requires_only_phone_and_action_entities() -> None:
    config = parse_bedtime_config(
        {
            "timezone": "America/New_York",
            "night_window": {"start": "21:45", "end": "04:00"},
            "delayed_action_minutes": 30,
            "pixel": {
                "battery_state_entity": "sensor.phone_battery_state",
                "charger_type_entity": "sensor.phone_charger_type",
            },
            "action": {"script_entity": "script.turn_off_all_lights"},
            "notification": {
                "title": "Bedtime lights",
                "message": "Turn off the lights?",
            },
            "morning_prompt_time": "08:30",
            "history_retention_days": 180,
            "morning_prompt": {
                "title": "Bedtime follow-up",
                "message": "Why did you skip the lights alert?",
                "reply_button_title": "Send",
                "reply_placeholder": "Why didn't you use it?",
            },
        }
    )

    assert config.delayed_action_minutes == 30
    assert config.morning_prompt_time == "08:30"
    assert config.history_retention_days == 180
    assert config.morning_prompt.reply_placeholder == "Why didn't you use it?"
    assert config.watched_entities == {
        "sensor.phone_battery_state",
        "sensor.phone_charger_type",
        "script.turn_off_all_lights",
    }
