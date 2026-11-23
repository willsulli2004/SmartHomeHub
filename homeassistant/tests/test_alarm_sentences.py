"""Checks that the alarm phrases in custom_sentences/en/hub_alarms.yaml are understood.

Uses hassil, the sentence matcher inside Home Assistant, so a phrase that passes
here is matched the same way on the live instance. Run from the repo folder:

    .\\.venv\\Scripts\\python.exe -m pytest homeassistant

These tests cover matching only: which intent a phrase triggers and the hour,
minute and am/pm it carries. Turning those into a clock time is done by Home
Assistant templates in packages/hub_alarms.yaml and is tested on the live instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from hassil import Intents, recognize

SENTENCES = Path(__file__).parent.parent / "custom_sentences" / "en" / "hub_alarms.yaml"


@pytest.fixture(scope="module")
def intents() -> Intents:
    with SENTENCES.open(encoding="utf-8") as file:
        return Intents.from_dict(yaml.safe_load(file))


def match(intents: Intents, text: str) -> tuple[str, dict[str, Any]] | None:
    """Return (intent name, slot values) for a phrase, or None if not understood."""
    result = recognize(text, intents)
    if result is None:
        return None
    return result.intent.name, {name: slot.value for name, slot in result.entities.items()}


# Phrases as speech-to-text tends to write them, with the slots they must carry.
SET_CASES: list[tuple[str, dict[str, Any]]] = [
    ("Set an alarm for 7 AM.", {"hour": 7, "ampm": "am"}),
    ("Set an alarm for 7 a.m.", {"hour": 7, "ampm": "am"}),
    ("set an alarm for 7:30 PM", {"hour": 7, "minute": 30, "ampm": "pm"}),
    ("Set an alarm for 7:30 p.m.", {"hour": 7, "minute": 30, "ampm": "pm"}),
    ("Set an alarm for 7 30 pm", {"hour": 7, "minute": 30, "ampm": "pm"}),
    ("Set an alarm for 07:05", {"hour": 7, "minute": 5}),
    ("Set an alarm for 7:05 AM", {"hour": 7, "minute": 5, "ampm": "am"}),
    ("Set an alarm for 19:15", {"hour": 19, "minute": 15}),
    ("Set an alarm for 7", {"hour": 7}),
    ("Set an alarm for 12 AM", {"hour": 12, "ampm": "am"}),
    ("Set an alarm for seven thirty am", {"hour": 7, "minute": 30, "ampm": "am"}),
    ("Set an alarm for seven", {"hour": 7}),
    ("Set an alarm for 7 o'clock", {"hour": 7, "minute": 0}),
    ("Set an alarm for 6 in the morning", {"hour": 6, "ampm": "am"}),
    ("Set an alarm at 6:45 a.m.", {"hour": 6, "minute": 45, "ampm": "am"}),
    ("Set another alarm for 8 AM", {"hour": 8, "ampm": "am"}),
    ("Set a 7 AM alarm", {"hour": 7, "ampm": "am"}),
    ("Wake me up at 6:45", {"hour": 6, "minute": 45}),
    ("wake me at 5 am", {"hour": 5, "ampm": "am"}),
    ("Set an alarm for noon", {"named_time": "12:00"}),
    ("Set an alarm for midnight.", {"named_time": "00:00"}),
]


@pytest.mark.parametrize(("text", "slots"), SET_CASES)
def test_set_alarm(intents: Intents, text: str, slots: dict[str, Any]) -> None:
    assert match(intents, text) == ("HubSetAlarm", slots)


CANCEL_CASES: list[tuple[str, dict[str, Any]]] = [
    ("Cancel my alarm.", {}),
    ("cancel the alarm", {}),
    ("Turn off the alarm", {}),
    ("Stop the alarm.", {}),
    ("Delete my alarm", {}),
    ("Cancel my 7 AM alarm", {"hour": 7, "ampm": "am"}),
    ("Cancel my 7:30 a.m. alarm.", {"hour": 7, "minute": 30, "ampm": "am"}),
    ("Cancel the alarm for 7:30", {"hour": 7, "minute": 30}),
    ("Cancel my alarm for 6 PM", {"hour": 6, "ampm": "pm"}),
    ("Cancel my noon alarm", {"named_time": "12:00"}),
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
        # General questions must fall through to Claude.
        "Why is the sky blue?",
        "What is an alarm clock?",
        # Not a time.
        "Set an alarm for 25",
        "Set an alarm for 7:75",
        "Set an alarm",
    ],
)
def test_not_an_alarm_command(intents: Intents, text: str) -> None:
    assert match(intents, text) is None
