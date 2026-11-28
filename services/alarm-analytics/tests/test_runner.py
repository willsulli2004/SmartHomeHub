"""Checks that broker events are handled on the main thread.

Found on the first real run (November 27th, 2026): the MQTT library calls back
on its own thread, and SQLite refuses a connection used from a thread other
than the one that opened it, so the service crashed as soon as it connected.
The earlier tests called the analytics directly and never crossed threads.

    .\\.venv\\Scripts\\python.exe -m pytest services/alarm-analytics
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

from alarm_analytics import contract
from alarm_analytics.analytics import Analytics
from alarm_analytics.contract import Message
from alarm_analytics.runner import Runner, decode
from alarm_analytics.store import Store


def on_another_thread(work) -> None:
    """Run `work` the way the MQTT library does: on a thread of its own."""
    errors: list[BaseException] = []

    def target() -> None:
        try:
            work()
        except BaseException as error:  # noqa: BLE001 - reported to the test below
            errors.append(error)

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Runner, Analytics, list[Message]]:
    published: list[Message] = []
    analytics = Analytics(Store(str(tmp_path / "history.db")))
    return Runner(analytics, published.extend), analytics, published


def test_the_crash_it_prevents(setup: tuple[Runner, Analytics, list[Message]]) -> None:
    # Calling the analytics straight from the library's thread is what crashed.
    _, analytics, _ = setup
    with pytest.raises(sqlite3.ProgrammingError):
        on_another_thread(lambda: analytics.on_connect(0.0))


def test_connect_from_the_library_thread_is_handled_on_the_main_thread(
    setup: tuple[Runner, Analytics, list[Message]]
) -> None:
    runner, _, published = setup
    on_another_thread(runner.connected)
    assert published == []  # nothing happens on the library's thread
    runner.run_once(0)
    assert published[-1].topic == contract.TOPIC_RESULTS
    assert Message(contract.TOPIC_AVAILABILITY, "online", qos=1, retain=True) in published


def test_a_whole_alarm_arriving_on_the_library_thread(
    setup: tuple[Runner, Analytics, list[Message]]
) -> None:
    runner, _, published = setup

    def alarm() -> None:
        runner.connected()
        runner.received(contract.TOPIC_START, b'{"alarm_id":"alarm-1","ts":"x"}')
        runner.received(contract.TOPIC_TELEMETRY, b'{"alarm_id":"alarm-1","ts_ms":100,"lifted":false,"battery_v":7.9}')
        runner.received(contract.TOPIC_STOP, b'{"alarm_id":"alarm-1","reason":"user","ts":"x"}')

    on_another_thread(alarm)
    runner.run_once(0)
    results = published[-1].payload
    assert isinstance(results, dict)
    assert results["last_alarm_id"] == "alarm-1"
    assert results["last_reason"] == "user"
    assert results["alarms_7d"] == 1


def test_run_once_returns_after_the_wait_when_nothing_arrives(
    setup: tuple[Runner, Analytics, list[Message]]
) -> None:
    runner, _, published = setup
    runner.run_once(0.01)
    assert published == []


def test_a_setting_sent_as_plain_text_is_understood(
    setup: tuple[Runner, Analytics, list[Message]]
) -> None:
    # Home Assistant sends a number's new value as text such as "0.5".
    runner, _, published = setup
    on_another_thread(lambda: runner.received(contract.TOPIC_SET_PREFIX + "min_lift_s", b"0.5"))
    runner.run_once(0)
    assert isinstance(published[-1].payload, dict)
    assert published[-1].payload["min_lift_s"] == 0.5


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b'{"a":1}', {"a": 1}),
        (b"0.5", 0.5),
        (b"online", "online"),
        (b"", ""),
        (b"\xff\xfe", None),  # not text at all
    ],
)
def test_decode(raw: bytes, expected: object) -> None:
    assert decode(raw) == expected
    if isinstance(expected, dict):
        assert json.loads(raw) == expected
