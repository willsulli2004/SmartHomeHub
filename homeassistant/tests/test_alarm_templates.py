"""Checks the alarm logic written as templates in packages/hub_alarms.yaml.

The templates run inside Home Assistant, which is not available here. These
tests render them with plain Jinja2 and small stand-ins for the Home Assistant
functions they use (now, states, is_state, regex_replace, regex_findall), with a
fake clock and fake alarm slots. That checks the time parsing, the arithmetic
and the wording. It does not check that Home Assistant loads the package; that
is tested on the live instance.

    .\\.venv\\Scripts\\python.exe -m pytest homeassistant
"""

from __future__ import annotations

import ast
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from jinja2.sandbox import SandboxedEnvironment

PACKAGE = Path(__file__).parent.parent / "packages" / "hub_alarms.yaml"
SENTENCES = Path(__file__).parent.parent / "custom_sentences" / "en" / "hub_alarms.yaml"
DASHBOARD = Path(__file__).parent.parent / "dashboards" / "hub_alarms.yaml"

# The fake "now" for every test: a Monday afternoon, 3 PM.
NOW = datetime(2026, 11, 23, 15, 0, 0)


def _to_int(value: Any, default: Any = 0) -> Any:
    """Home Assistant's int filter: the default is returned on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _regex_replace(value: Any, find: str = "", replace: str = "") -> str:
    return re.sub(find, replace, str(value))


def _regex_findall(value: Any, find: str = "") -> list[Any]:
    return re.findall(find, str(value))


class FakeHome:
    """Renders package templates against fake alarm slots."""

    def __init__(self, alarms: dict[int, str] | None = None) -> None:
        # slot number -> "HH:MM:SS" for slots that are switched on
        self.alarms = alarms or {}
        self.env = SandboxedEnvironment()
        self.env.filters["int"] = _to_int
        self.env.filters["regex_replace"] = _regex_replace
        self.env.filters["regex_findall"] = _regex_findall
        self.env.globals.update(
            now=lambda: NOW,
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
            return self.alarms.get(slot, "00:00:00")
        raise KeyError(entity)

    def render(self, template: str, variables: dict[str, Any]) -> str:
        return " ".join(self.env.from_string(template).render(**variables).split())

    def run(self, script: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Run a script's top-level steps the way Home Assistant would.

        Handles `variables:` steps and calls to hub_alarm_parse_time; other
        steps (conditions, service calls, stops) are skipped, so the returned
        variables are what the script would have at its end.
        """
        out = dict(variables)
        for step in self.package["script"][script]["sequence"]:
            if step.get("action") == "script.hub_alarm_parse_time":
                text = self.render(step["data"]["text"], out)
                parsed = self.run("hub_alarm_parse_time", {"text": text})["parsed"]
                out[step["response_variable"]] = parsed
            for name, template in step.get("variables", {}).items():
                if isinstance(template, dict):
                    out[name] = {k: self.render(v, out) for k, v in template.items()}
                else:
                    out[name] = self._native(self.render(template, out))
        return out

    @staticmethod
    def _native(text: str) -> Any:
        """Home Assistant turns "[1, 2]", "3" and "True" into real values.

        Like Home Assistant, this uses Python's literal parser, so a time such
        as "07:00:00" stays a string.
        """
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return text


# ---- understanding a spoken time ----

PARSE_CASES: list[tuple[str, list[int], int]] = [
    # words handed over, hours it could mean, minute
    ("3:10PM", [15], 10),  # the form that failed on the hardware
    ("3:10pm", [15], 10),
    ("3:10 PM", [15], 10),
    ("3:10 p.m.", [15], 10),
    ("3:10 P.M.", [15], 10),
    ("3.10pm", [15], 10),
    ("3.10 p.m", [15], 10),
    ("3-10 PM", [15], 10),
    ("3 10 pm", [15], 10),
    ("310 PM", [15], 10),
    ("3 p m", [15], 0),
    ("3pm", [15], 0),
    ("7 AM", [7], 0),
    ("7 a.m.", [7], 0),
    ("07:05", [7, 19], 5),
    ("7:05 AM", [7], 5),
    ("12 AM", [0], 0),
    ("12 PM", [12], 0),
    ("12:30 am", [0], 30),
    ("7", [7, 19], 0),
    ("12", [0, 12], 0),
    ("7:30", [7, 19], 30),
    ("730", [7, 19], 30),
    ("19:15", [19], 15),
    ("1915", [19], 15),
    ("0:30", [0], 30),
    ("seven thirty am", [7], 30),
    ("seven", [7, 19], 0),
    ("seven forty five pm", [19], 45),
    ("seven oh five", [7, 19], 5),
    ("ten fifteen", [10, 22], 15),
    ("7 o'clock", [7, 19], 0),
    ("seven o'clock in the morning", [7], 0),
    ("6 in the morning", [6], 0),
    ("6 in the evening", [18], 0),
    ("9 tonight", [21], 0),
    ("7 AM tomorrow", [7], 0),
    ("noon", [12], 0),
    ("midday", [12], 0),
    ("midnight", [0], 0),
]


@pytest.mark.parametrize(("text", "hours", "minute"), PARSE_CASES)
def test_parse_understands_a_time(text: str, hours: list[int], minute: int) -> None:
    parsed = FakeHome().run("hub_alarm_parse_time", {"text": text})["parsed"]
    assert parsed == {"ok": True, "hours": hours, "minute": minute}


@pytest.mark.parametrize(
    "text",
    ["", "when I get home", "25", "7:75", "7:5", "soon", "all", "every", "12345", "half"],
)
def test_parse_rejects_what_is_not_a_time(text: str) -> None:
    parsed = FakeHome().run("hub_alarm_parse_time", {"text": text})["parsed"]
    assert parsed["ok"] is False


# ---- setting: which moment does a spoken time mean? (now is 15:00) ----

SET_CASES = [
    # words, slot value, spoken form
    ("7 AM", "07:00:00", "7 AM tomorrow"),
    ("3:10PM", "15:10:00", "3:10 PM"),
    ("7:30 pm", "19:30:00", "7:30 PM"),
    ("2 pm", "14:00:00", "2 PM tomorrow"),  # 2 PM already passed today
    ("4 pm", "16:00:00", "4 PM"),
    ("12 am", "00:00:00", "12 AM tomorrow"),
    ("12 pm", "12:00:00", "12 PM tomorrow"),
    # No am/pm: the next time the clock shows it.
    ("7", "19:00:00", "7 PM"),
    ("2", "02:00:00", "2 AM tomorrow"),
    ("3:05", "15:05:00", "3:05 PM"),
    ("3", "03:00:00", "3 AM tomorrow"),  # 15:00 exactly is not "next"
    ("12", "00:00:00", "12 AM tomorrow"),
    # 24-hour times and named times.
    ("19:15", "19:15:00", "7:15 PM"),
    ("0:30", "00:30:00", "12:30 AM tomorrow"),
    ("noon", "12:00:00", "12 PM tomorrow"),
    ("midnight", "00:00:00", "12 AM tomorrow"),
]


@pytest.mark.parametrize(("when", "target", "spoken"), SET_CASES)
def test_set_picks_the_next_matching_moment(when: str, target: str, spoken: str) -> None:
    result = FakeHome().run("hub_alarm_set", {"when": when})
    assert result["target"] == target
    assert result["spoken"] == spoken


def test_set_uses_the_first_free_slot() -> None:
    home = FakeHome({1: "06:00:00", 2: "08:00:00"})
    result = home.run("hub_alarm_set", {"when": "7 am"})
    assert result["slot"] == 3
    assert result["duplicate"] is False


def test_set_reports_no_free_slot() -> None:
    home = FakeHome({i: f"0{i}:00:00" for i in range(1, 6)})
    assert home.run("hub_alarm_set", {"when": "9 am"})["slot"] == 0


def test_set_spots_a_duplicate() -> None:
    home = FakeHome({2: "07:00:00"})
    assert home.run("hub_alarm_set", {"when": "7 am"})["duplicate"] is True


@pytest.mark.parametrize("when", ["said:7.30", "said:3:10PM", "said:730"])
def test_the_said_prefix_from_the_voice_handlers_is_stripped(when: str) -> None:
    # The intent handlers pass "said:<words>" so Home Assistant cannot turn
    # "7.30" into the number 7.3 on the way.
    assert FakeHome().run("hub_alarm_set", {"when": when})["parsed"]["ok"] is True


def test_cancel_with_only_the_prefix_means_no_time_was_said() -> None:
    result = FakeHome({2: "07:00:00"}).run("hub_alarm_cancel", {"when": "said:"})
    assert result["time_given"] is False
    assert result["matches"] == [2]


def test_set_flags_words_that_are_not_a_time() -> None:
    assert FakeHome().run("hub_alarm_set", {"when": "when I get home"})["parsed"]["ok"] is False


# ---- cancelling ----

THREE = {1: "07:00:00", 3: "19:00:00", 4: "08:30:00"}

CANCEL_CASES = [
    # alarms set, words said for the time, slots cancelled
    ({2: "07:00:00"}, "", [2]),  # the only alarm, no time needed
    (THREE, "", []),  # several alarms: must say which
    (THREE, "7 am", [1]),
    (THREE, "7PM", [3]),
    (THREE, "7", [1, 3]),  # no am/pm: both sevens
    (THREE, "8:30", [4]),
    (THREE, "8", []),  # 8:00 is not 8:30
    (THREE, "19:00", [3]),
    (THREE, "noon", []),
    (THREE, "the early one", []),  # not a time
    ({}, "7 am", []),
]


@pytest.mark.parametrize(("alarms", "when", "expected"), CANCEL_CASES)
def test_cancel_matches_the_right_slots(
    alarms: dict[int, str], when: str, expected: list[int]
) -> None:
    assert FakeHome(alarms).run("hub_alarm_cancel", {"when": when})["matches"] == expected


# ---- wording ----


def _speech(home: FakeHome, script: str, variables: dict[str, Any]) -> str:
    """The speech of the last top-level `result` a script builds."""
    return home.run(script, variables)["result"]["speech"]


@pytest.mark.parametrize(
    ("alarms", "expected"),
    [
        ({}, "You have no alarms set."),
        ({2: "07:00:00"}, "Your alarm is set for 7 AM tomorrow."),
        (THREE, "You have 3 alarms: 7 PM, 7 AM tomorrow and 8:30 AM tomorrow."),
    ],
)
def test_query_lists_alarms_soonest_first(alarms: dict[int, str], expected: str) -> None:
    assert _speech(FakeHome(alarms), "hub_alarm_query", {}) == expected


def test_cancel_names_what_it_cancelled() -> None:
    assert _speech(FakeHome(THREE), "hub_alarm_cancel", {"when": "7"}) == (
        "Cancelled your 7 AM and 7 PM alarms."
    )


@pytest.mark.parametrize(
    ("alarms", "expected"),
    [
        ({}, "You have no alarms set."),
        ({2: "07:00:00"}, "Cancelled your alarm."),
        (THREE, "Cancelled all 3 alarms."),
    ],
)
def test_cancel_all_wording(alarms: dict[int, str], expected: str) -> None:
    assert _speech(FakeHome(alarms), "hub_alarm_cancel_all", {}) == expected


# ---- the files fit together ----


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
    sentences = yaml.safe_load(SENTENCES.read_text("utf-8"))
    assert set(package["intent_script"]) == set(sentences["intents"])


def test_alarm_slots_are_time_only() -> None:
    # Time-only slots are what make an alarm settable from the app by picking a
    # time and flipping a switch.
    for slot in FakeHome().package["input_datetime"].values():
        assert slot["has_time"] is True
        assert slot["has_date"] is False


def _entities(node: Any) -> set[str]:
    """Every entity id a dashboard refers to."""
    found: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("entity", "entity_id") and isinstance(value, str):
                found.add(value)
            else:
                found |= _entities(value)
    elif isinstance(node, list):
        for item in node:
            found |= _entities(item)
    return found


def test_dashboard_only_uses_entities_the_project_defines() -> None:
    package = FakeHome().package
    known = {
        f"{domain}.{name}"
        for domain in ("input_datetime", "input_boolean", "input_text", "input_number", "script")
        for name in package[domain]
    }
    used = _entities(yaml.safe_load(DASHBOARD.read_text("utf-8")))
    assert used, "the dashboard should reference entities"
    # Anything not from the package must be one of the satellite's entities.
    # (or one of the robot entities, which services/alarm-analytics checks by name)
    for entity in used - known:
        assert entity.split(".", 1)[1].startswith(("satellite_hub_", "hub_robot_")), entity
