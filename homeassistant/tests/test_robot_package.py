"""Checks packages/hub_robot.yaml: the robot status entities and the alarm schedule.

The schedule message is built by a Home Assistant template. As in
test_alarm_templates.py, it is rendered here with plain Jinja2 and stand-ins for
the Home Assistant functions it uses.

    .\\.venv\\Scripts\\python.exe -m pytest homeassistant
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jinja2.sandbox import SandboxedEnvironment

PACKAGE = Path(__file__).parent.parent / "packages" / "hub_robot.yaml"

# The fake "now": 3 PM local time, with some seconds on the clock.
NOW = datetime(2026, 11, 27, 15, 0, 42)
THIS_MINUTE = int(NOW.replace(second=0).timestamp())


def _load() -> dict[str, Any]:
    return yaml.safe_load(PACKAGE.read_text("utf-8"))


def _schedule(alarms: dict[int, str]) -> dict[str, Any]:
    """Render the schedule message for the given slots (slot -> "HH:MM:SS", all on)."""

    def states(entity: str) -> str:
        domain, name = entity.split(".")
        slot = int(name.rsplit("_", 1)[1])
        if domain == "input_boolean":
            return "on" if slot in alarms else "off"
        return alarms.get(slot, "00:00:00")

    def to_int(value: Any, default: Any = 0) -> Any:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def timestamp_custom(value: Any, fmt: str, local: bool = True) -> str:
        assert local is False, "the schedule must be written in UTC"
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime(fmt)

    env = SandboxedEnvironment()
    env.filters.update(int=to_int, timestamp_custom=timestamp_custom, to_json=json.dumps)
    env.globals.update(
        now=lambda: NOW,
        utcnow=lambda: datetime(2026, 11, 27, 23, 0, 42),
        states=states,
        is_state=lambda entity, state: states(entity) == state,
    )
    (automation,) = _load()["automation"]
    template = automation["action"][0]["data"]["payload"]
    return json.loads(env.from_string(template).render())


def test_schedule_with_no_alarms() -> None:
    assert _schedule({}) == {
        "alarms": [],
        "next_epoch": None,
        "next": None,
        "ts": "2026-11-27T23:00:42Z",
    }


def test_schedule_lists_alarms_soonest_first_and_names_the_next() -> None:
    schedule = _schedule({1: "07:00:00", 3: "19:30:00", 4: "15:05:00"})
    assert schedule["alarms"] == ["15:05", "19:30", "07:00"]
    assert schedule["next_epoch"] == THIS_MINUTE + 5 * 60
    expected = datetime.fromtimestamp(THIS_MINUTE + 5 * 60, tz=timezone.utc)
    assert schedule["next"] == expected.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_an_alarm_for_the_current_minute_means_tomorrow() -> None:
    schedule = _schedule({2: "15:00:00"})
    assert schedule["next_epoch"] == THIS_MINUTE + 24 * 3600


def test_an_alarm_earlier_than_now_is_tomorrow() -> None:
    schedule = _schedule({2: "07:00:00"})
    assert schedule["next_epoch"] == THIS_MINUTE + 16 * 3600


def test_schedule_is_retained_and_republished_when_any_slot_changes() -> None:
    (automation,) = _load()["automation"]
    data = automation["action"][0]["data"]
    assert (data["topic"], data["qos"], data["retain"]) == ("hub/alarm/schedule", 1, True)
    watched = set(automation["trigger"][0]["entity_id"])
    assert watched == {f"input_boolean.hub_alarm_{i}" for i in range(1, 6)} | {
        f"input_datetime.hub_alarm_{i}" for i in range(1, 6)
    }
    assert {"trigger": "homeassistant", "event": "start"} in automation["trigger"]


def test_robot_status_entities_read_the_contract_topics() -> None:
    mqtt = _load()["mqtt"]
    (online,) = mqtt["binary_sensor"]
    (state,) = mqtt["sensor"]
    assert (online["name"], online["state_topic"]) == ("Hub Robot online", "alarmbot/status")
    assert (state["name"], state["state_topic"]) == ("Hub Robot state", "alarmbot/state")
    assert online["unique_id"] != state["unique_id"]
