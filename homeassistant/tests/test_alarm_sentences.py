"""Checks that the alarm phrases in custom_sentences/en/hub_alarms.yaml are understood.

Uses hassil, the sentence matcher inside Home Assistant, so a phrase that passes
here is matched the same way on the live instance. Run from the repo folder:

    .\\.venv\\Scripts\\python.exe -m pytest homeassistant

These tests cover matching only: which intent a phrase triggers and which words
it hands over as the time ("when"). Turning those words into a clock time is
done by the script hub_alarm_parse_time and is checked in
test_alarm_templates.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from hassil import Intents, recognize_best

SENTENCES = Path(__file__).parent.parent / "custom_sentences" / "en" / "hub_alarms.yaml"


@pytest.fixture(scope="module")
def intents() -> Intents:
    with SENTENCES.open(encoding="utf-8") as file:
        return Intents.from_dict(yaml.safe_load(file))


def match(intents: Intents, text: str) -> tuple[str, dict[str, Any]] | None:
    """Return (intent name, slot values) for a phrase, or None if not understood."""
    result = recognize_best(text, intents)
    if result is None:
        return None
    return result.intent.name, {name: slot.value for name, slot in result.entities.items()}


# Phrases as speech-to-text tends to write them, with the words handed over as
# the time. "3:10PM" with no space is the form that failed on the hardware.
SET_CASES: list[tuple[str, str]] = [
    ("Set an alarm for 7 AM.", "7 AM"),
    ("Set an alarm for 7 a.m.", "7 a.m."),
    ("set an alarm for 3:10PM", "3:10PM"),
    ("Set an alarm for 3:10pm.", "3:10pm"),
    ("Set an alarm for 3.10pm", "3.10pm"),
    ("Set an alarm for 3:10 P.M.", "3:10 P.M."),
    ("Set an alarm for 310 PM", "310 PM"),
    ("Set an alarm for 7 30 pm", "7 30 pm"),
    ("Set an alarm for 07:05", "07:05"),
    ("Set an alarm for 19:15", "19:15"),
    ("Set an alarm for 7", "7"),
    ("Set an alarm for seven thirty am", "seven thirty am"),
    ("Set an alarm for 7 o'clock", "7 o'clock"),
    ("Set an alarm for 6 in the morning", "6 in the morning"),
    ("Set an alarm at 6:45 a.m.", "6:45 a.m."),
    ("Set another alarm for 8 AM", "8 AM"),
    ("Set alarm for 8 AM", "8 AM"),
    ("Set the alarm to 8 AM", "8 AM"),
    ("Set a 7 AM alarm", "7 AM"),
    ("Wake me up at 6:45", "6:45"),
    ("wake me at 5 am", "5 am"),
    ("Can you set an alarm for 3:10 PM?", "3:10 PM"),
    ("Please set an alarm for noon", "noon"),
    ("Set an alarm for midnight.", "midnight"),
]


@pytest.mark.parametrize(("text", "when"), SET_CASES)
def test_set_alarm(intents: Intents, text: str, when: str) -> None:
    assert match(intents, text) == ("HubSetAlarm", {"when": when})


CANCEL_CASES: list[tuple[str, dict[str, Any]]] = [
    ("Cancel my alarm.", {}),
    ("cancel the alarm", {}),
    ("Turn off the alarm", {}),
    ("Stop the alarm.", {}),
    ("Delete my alarm", {}),
    ("Please cancel my alarm", {}),
    ("Cancel my 7 AM alarm", {"when": "7 AM"}),
    ("Cancel my 7:30 a.m. alarm.", {"when": "7:30 a.m."}),
    ("Cancel my 3:10PM alarm", {"when": "3:10PM"}),
    ("Cancel the alarm for 7:30", {"when": "7:30"}),
    ("Cancel my alarm for 6 PM", {"when": "6 PM"}),
    ("Cancel my noon alarm", {"when": "noon"}),
]


@pytest.mark.parametrize(("text", "slots"), CANCEL_CASES)
def test_cancel_alarm(intents: Intents, text: str, slots: dict[str, Any]) -> None:
    assert match(intents, text) == ("HubCancelAlarm", slots)


@pytest.mark.parametrize(
    "text",
    [
        "Cancel all alarms.",
        "Cancel all my alarms",
        "Cancel all of my alarms",
        "Delete every alarm",
        "Cancel my alarms",
        "Clear the alarms",
    ],
)
def test_cancel_all_alarms(intents: Intents, text: str) -> None:
    assert match(intents, text) == ("HubCancelAllAlarms", {})


@pytest.mark.parametrize(
    "text",
    [
        "When is my alarm?",
        "When is my next alarm?",
        "What time is my alarm?",
        "What time is my alarm set for?",
        "What alarms are set?",
        "What alarms do I have?",
        "Do I have any alarms?",
        "Do I have an alarm set?",
        "List my alarms",
    ],
)
def test_query_alarm(intents: Intents, text: str) -> None:
    assert match(intents, text) == ("HubQueryAlarm", {})


@pytest.mark.parametrize(
    "text",
    [
        # Timers belong to Home Assistant's own commands.
        "Set a timer for 5 minutes",
        "Cancel my timer",
        # Device commands must not be caught by the alarm phrases.
        "Turn off the kitchen light",
        "Turn on the desk lights",
        # General questions must fall through to Claude.
        "Why is the sky blue?",
        "What is an alarm clock?",
        # No time at all.
        "Set an alarm",
    ],
)
def test_not_an_alarm_command(intents: Intents, text: str) -> None:
    assert match(intents, text) is None
