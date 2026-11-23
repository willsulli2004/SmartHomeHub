"""Checks the alarm logic written as templates in packages/alarm.yaml.

The templates run inside Home Assistant, which is not available here. These
tests render them with plain Jinja2 and small stand-ins for the Home Assistant
functions they use (now, states, is_state, strptime, timedelta), with a fake
clock and fake alarm slots. That checks the arithmetic and the wording. It does
not check that Home Assistant loads the package; that is tested on the live
instance.

    .\\.venv\\Scripts\\python.exe -m pytest homeassistant
"""

from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2.sandbox import SandboxedEnvironment

PACKAGE = Path(__file__).parent.parent / "packages" / "alarm.yaml"

# The fake "now" for every test: a Monday afternoon.
NOW = datetime(2026, 11, 23, 15, 0, 0)


def _to_int(value: Any, default: Any = 0) -> Any:
    """Home Assistant's int filter: the default is returned on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class FakeHome:
    """Renders package templates against fake alarm slots."""

    def __init__(self, alarms: dict[int, str] | None = None) -> None:
        # slot number -> "YYYY-MM-DD HH:MM:SS" for slots that are switched on
        self.alarms = alarms or {}
        self.env = SandboxedEnvironment()
        self.env.filters["int"] = _to_int
        self.env.globals.update(
            now=lambda: NOW,
            timedelta=timedelta,
            strptime=datetime.strptime,
            states=self.states,
            is_state=lambda entity, state: self.states(entity) == state,
        )
        with PACKAGE.open(encoding="utf-8") as file:
            self.package = yaml.safe_load(file)

    def states(self, entity: str) -> str:
        domain, name = entity.split(".")
        slot = int(name.rsplit("_", 1)[1]) if name[-1].isdigit() else 0
        if domain == "input_boolean":
            return "on" if slot in self.alarms else "off"
        if domain == "input_datetime":
            return self.alarms.get(slot, "2026-01-01 00:00:00")
        raise KeyError(entity)

    def render(self, template: str, variables: dict[str, Any]) -> str:
        if sys.platform == "win32":
            # "%-I" (hour without a leading zero) is the Linux spelling, which is
            # what Home Assistant runs on. Windows spells it "%#I".
            template = template.replace("%-I", "%#I")
        return " ".join(self.env.from_string(template).render(**variables).split())

    def script_variables(self, script: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Render every top-level `variables:` step of a script, in order."""
        out = dict(variables)
        for step in self.package["script"][script]["sequence"]:
            for name, template in step.get("variables", {}).items():
                if isinstance(template, dict):
                    out[name] = {k: self.render(v, out) for k, v in template.items()}
                else:
                    out[name] = self._native(self.render(template, out))
        return out

    @staticmethod
    def _native(text: str) -> Any:
        """Home Assistant turns "[1, 2]", "3" and "True" into real values.

        Like Home Assistant, this uses Python's literal parser, so a date-and-time
        string such as "2026-11-24 07:00:00" stays a string.
        """
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text


def said(hour: int = -1, minute: int = 0, ampm: str = "", named_time: str = "") -> dict[str, Any]:
    return {"hour": hour, "minute": minute, "ampm": ampm, "named_time": named_time}


# ---- setting: which moment does a spoken time mean? (now is Monday 15:00) ----

SET_CASES = [
    # said, expected moment, expected spoken form
    (said(7, ampm="am"), "2026-11-24 07:00:00", "7 AM tomorrow"),
    (said(7, 30, "pm"), "2026-11-23 19:30:00", "7:30 PM"),
    (said(2, ampm="pm"), "2026-11-24 14:00:00", "2 PM tomorrow"),  # 2 PM already passed
    (said(4, ampm="pm"), "2026-11-23 16:00:00", "4 PM"),
    (said(12, ampm="am"), "2026-11-24 00:00:00", "12 AM tomorrow"),
    (said(12, ampm="pm"), "2026-11-24 12:00:00", "12 PM tomorrow"),
    # No am/pm: the next time the clock shows it.
    (said(7), "2026-11-23 19:00:00", "7 PM"),
    (said(2), "2026-11-24 02:00:00", "2 AM tomorrow"),
    (said(3, 5), "2026-11-23 15:05:00", "3:05 PM"),
    (said(3), "2026-11-24 03:00:00", "3 AM tomorrow"),  # 15:00 exactly is not "next"
    (said(12), "2026-11-24 00:00:00", "12 AM tomorrow"),
    # 24-hour times.
    (said(19, 15), "2026-11-23 19:15:00", "7:15 PM"),
    (said(0, 30), "2026-11-24 00:30:00", "12:30 AM tomorrow"),
    # Named times.
    (said(named_time="12:00"), "2026-11-24 12:00:00", "12 PM tomorrow"),
    (said(named_time="00:00"), "2026-11-24 00:00:00", "12 AM tomorrow"),
]


@pytest.mark.parametrize(("spoken_slots", "target", "spoken"), SET_CASES)
def test_set_picks_the_next_matching_moment(
    spoken_slots: dict[str, Any], target: str, spoken: str
) -> None:
    result = FakeHome().script_variables("hub_alarm_set", spoken_slots)
    assert result["target"] == target
    assert result["spoken"] == spoken


def test_set_uses_the_first_free_slot() -> None:
    home = FakeHome({1: "2026-11-24 06:00:00", 2: "2026-11-24 08:00:00"})
    result = home.script_variables("hub_alarm_set", said(7, ampm="am"))
    assert result["slot"] == 3
    assert result["duplicate"] is False


def test_set_reports_no_free_slot() -> None:
    home = FakeHome({i: f"2026-11-24 0{i}:00:00" for i in range(1, 6)})
    assert home.script_variables("hub_alarm_set", said(9, ampm="am"))["slot"] == 0


def test_set_spots_a_duplicate() -> None:
    home = FakeHome({2: "2026-11-24 07:00:00"})
    assert home.script_variables("hub_alarm_set", said(7, ampm="am"))["duplicate"] is True


# ---- cancelling ----

THREE = {1: "2026-11-24 07:00:00", 3: "2026-11-23 19:00:00", 4: "2026-11-24 08:30:00"}

CANCEL_CASES = [
    # alarms set, what was said, slots cancelled
    ({2: "2026-11-24 07:00:00"}, said(), [2]),  # the only alarm, no time needed
    (THREE, said(), []),  # several alarms: must say which
    (THREE, said(7, ampm="am"), [1]),
    (THREE, said(7, ampm="pm"), [3]),
    (THREE, said(7), [1, 3]),  # no am/pm: both sevens
    (THREE, said(8, 30), [4]),
    (THREE, said(8), []),  # 8:00 is not 8:30
    (THREE, said(19), [3]),
    (THREE, said(named_time="12:00"), []),
    ({}, said(7, ampm="am"), []),
]


@pytest.mark.parametrize(("alarms", "spoken_slots", "expected"), CANCEL_CASES)
def test_cancel_matches_the_right_slots(
    alarms: dict[int, str], spoken_slots: dict[str, Any], expected: list[int]
) -> None:
    result = FakeHome(alarms).script_variables("hub_alarm_cancel", spoken_slots)
    assert result["matches"] == expected


# ---- wording ----


def _speech(home: FakeHome, script: str, variables: dict[str, Any]) -> str:
    """The speech of the last top-level `result` a script builds."""
    return home.script_variables(script, variables)["result"]["speech"]


@pytest.mark.parametrize(
    ("alarms", "expected"),
    [
        ({}, "You have no alarms set."),
        ({2: "2026-11-24 07:00:00"}, "Your alarm is set for 7 AM tomorrow."),
        (THREE, "You have 3 alarms: 7 PM, 7 AM tomorrow and 8:30 AM tomorrow."),
    ],
)
def test_query_lists_alarms_soonest_first(alarms: dict[int, str], expected: str) -> None:
    assert _speech(FakeHome(alarms), "hub_alarm_query", {}) == expected


def test_cancel_names_what_it_cancelled() -> None:
    speech = _speech(FakeHome(THREE), "hub_alarm_cancel", said(7))
    assert speech == "Cancelled your 7 AM and 7 PM alarms."


@pytest.mark.parametrize(
    ("alarms", "expected"),
    [
        ({}, "You have no alarms set."),
        ({2: "2026-11-24 07:00:00"}, "Cancelled your alarm."),
        (THREE, "Cancelled all 3 alarms."),
    ],
)
def test_cancel_all_wording(alarms: dict[int, str], expected: str) -> None:
    assert _speech(FakeHome(alarms), "hub_alarm_cancel_all", {}) == expected


def test_package_is_valid_yaml_with_the_expected_parts() -> None:
    package = FakeHome().package
    assert set(package) == {
        "input_datetime",
        "input_boolean",
        "input_text",
        "input_number",
        "script",
        "automation",
        "intent_script",
    }
    # Every intent in the sentences file has a handler, and the reverse.
    sentences = yaml.safe_load(
        (PACKAGE.parent.parent / "custom_sentences" / "en" / "alarm.yaml").read_text("utf-8")
    )
    assert set(package["intent_script"]) == set(sentences["intents"])
