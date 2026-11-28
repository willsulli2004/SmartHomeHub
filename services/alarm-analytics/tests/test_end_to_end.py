"""Runs a whole alarm with the mock robot and the analytics service together.

A tiny in-memory broker passes messages between three parts:
- a stand-in for Home Assistant's alarm logic (homeassistant/packages/hub_alarms.yaml):
  it starts the alarm, stops it when the robot reports the right alarm caught,
  and can stop it for a user or a timeout
- the mock robot (tools/mock-robot)
- the analytics service

The robot and the service each have their own copy of the contract. If the two
copies drift apart, these tests fail.

    .\\.venv\\Scripts\\python.exe -m pytest services/alarm-analytics
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from alarm_analytics import contract as service_contract
from alarm_analytics.analytics import Analytics
from alarm_analytics.store import Store
from mock_robot import contract as robot_contract
from mock_robot.robot import SCENARIOS, MockRobot

T0 = 1_800_000_000.0
STEP_S = 0.05


class FakeHub:
    """The part of Home Assistant's alarm logic that touches MQTT."""

    def __init__(self) -> None:
        self.alarm_id: str | None = None
        self.stops: list[dict[str, Any]] = []

    def start(self, alarm_id: str) -> tuple[str, dict[str, Any]]:
        self.alarm_id = alarm_id
        return "hub/alarm/start", {"alarm_id": alarm_id, "ts": "2026-11-27T15:00:00Z"}

    def stop(self, reason: str) -> tuple[str, dict[str, Any]] | None:
        if self.alarm_id is None:
            return None
        payload = {"alarm_id": self.alarm_id, "reason": reason, "ts": "2026-11-27T15:00:20Z"}
        self.alarm_id = None
        self.stops.append(payload)
        return "hub/alarm/stop", payload

    def on_message(self, topic: str, payload: Any) -> tuple[str, dict[str, Any]] | None:
        # Same rule as the "Hub alarm: robot caught" automation: only the alarm
        # that is ringing counts.
        if topic == "alarmbot/caught" and self.alarm_id and payload.get("alarm_id") == self.alarm_id:
            return self.stop("caught")
        return None


class World:
    """Routes every published message to the other parts, like a broker."""

    def __init__(self, scenario: str) -> None:
        self.hub = FakeHub()
        self.robot = MockRobot(SCENARIOS[scenario], boot_time=T0)
        self.analytics = Analytics(Store(":memory:"))
        self.now = T0
        self.log: list[tuple[str, Any]] = []
        self.robot_online = True
        self._queue: list[tuple[str, Any]] = []
        self._delivering = False
        self._deliver_all(self.robot.on_connect(self.now))
        self._deliver_all(self.analytics.on_connect(self.now))

    def publish(self, topic: str, payload: Any) -> None:
        """Hand one message to the broker and deliver everything that follows from it."""
        self._enqueue(topic, payload)
        self._drain()

    def _deliver_all(self, messages: list[Any]) -> None:
        """Hand over several messages published together, then deliver.

        All of them join the queue before any is delivered, so a reply to the
        first arrives after the rest, as it would through a real broker.
        """
        for message in messages:
            text = message.encode()
            self._enqueue(message.topic, json.loads(text) if text[:1] in "{[" else text)
        self._drain()

    def _enqueue(self, topic: str, payload: Any) -> None:
        # Messages cross the broker as text, exactly as on a real network.
        self._queue.append((topic, json.loads(json.dumps(payload))))

    def _drain(self) -> None:
        if self._delivering:
            return  # already delivering; the loop below will reach the new messages
        self._delivering = True
        try:
            while self._queue:
                topic, payload = self._queue.pop(0)
                self.log.append((topic, payload))
                if self.robot_online and topic in robot_contract.SUBSCRIPTIONS:
                    self._deliver_all(self.robot.on_message(topic, payload, self.now))
                self._deliver_all(self.analytics.on_message(topic, payload, self.now))
                reply = self.hub.on_message(topic, payload)
                if reply:
                    self._enqueue(*reply)
        finally:
            self._delivering = False

    def run(self, seconds: float) -> None:
        for _ in range(round(seconds / STEP_S)):
            self.now += STEP_S
            if self.robot_online:
                self._deliver_all(self.robot.tick(self.now))
                if self.robot.wants_disconnect:
                    self.robot_online = False
                    self.publish("alarmbot/status", {"state": "offline"})  # the Last Will
            self._deliver_all(self.analytics.tick(self.now))

    def results(self) -> dict[str, Any]:
        return [p for t, p in self.log if t == service_contract.TOPIC_RESULTS][-1]

    def last(self, topic: str) -> Any:
        return [p for t, p in self.log if t == topic][-1]


def test_both_copies_of_the_contract_agree() -> None:
    assert robot_contract.TOPIC_START == service_contract.TOPIC_START
    assert robot_contract.TOPIC_STOP == service_contract.TOPIC_STOP
    assert robot_contract.TOPIC_TELEMETRY == service_contract.TOPIC_TELEMETRY
    assert robot_contract.TOPIC_CAUGHT == service_contract.TOPIC_CAUGHT


def test_alarm_chase_caught_stop() -> None:
    world = World("catch")
    world.publish(*world.hub.start("alarm-100"))
    world.run(20.0)

    # The robot fled, was caught, and the hub stopped the alarm for that reason.
    assert world.hub.stops == [{"alarm_id": "alarm-100", "reason": "caught", "ts": "2026-11-27T15:00:20Z"}]
    assert world.robot.state == "idle"
    assert world.last("alarmbot/state")["state"] == "idle"

    results = world.results()
    assert results["last_alarm_id"] == "alarm-100"
    assert results["last_reason"] == "caught"
    assert results["last_catch"] == "real"
    assert results["last_time_to_catch_s"] == pytest.approx(15.0, abs=0.2)
    assert results["last_distance_m"] == pytest.approx(6.1, abs=0.3)
    assert results["last_lift_ms"] >= 1000
    assert results["catches_7d"] == 1
    assert results["battery_low"] is False


def test_a_bump_stops_the_alarm_but_is_flagged() -> None:
    world = World("bump")
    world.publish(*world.hub.start("alarm-101"))
    world.run(12.0)
    # Home Assistant trusts the robot's report straight away (the agreed design)...
    assert world.hub.stops[0]["reason"] == "caught"
    # ...and the service marks it afterwards.
    results = world.results()
    assert results["last_catch"] == "suspicious"
    assert results["suspicious_catches_7d"] == 1
    assert results["catches_7d"] == 0


def test_never_caught_ends_on_the_timeout() -> None:
    world = World("never")
    world.publish(*world.hub.start("alarm-102"))
    world.run(30.0)
    assert world.hub.stops == []
    world.publish(*world.hub.stop("timeout"))
    world.run(1.0)
    assert world.robot.state == "idle"
    results = world.results()
    assert results["last_reason"] == "timeout"
    assert results["last_wake_delay_s"] == pytest.approx(30.0, abs=0.2)
    assert results["last_catch"] == "not caught"


def test_user_stops_it_at_the_hub() -> None:
    world = World("catch")
    world.publish(*world.hub.start("alarm-103"))
    world.run(5.0)
    world.publish(*world.hub.stop("user"))
    world.run(20.0)
    assert world.robot.state == "idle"
    assert [t for t, _ in world.log].count("alarmbot/caught") == 0
    assert world.results()["last_reason"] == "user"


def test_low_battery_is_flagged_during_the_chase() -> None:
    world = World("low-battery")
    world.publish(*world.hub.start("alarm-104"))
    world.run(20.0)
    results = world.results()
    assert results["battery_low"] is True
    assert results["battery_v"] < 6.8
    assert results["last_catch"] == "real"


def test_robot_going_offline_leaves_the_alarm_to_the_hub() -> None:
    world = World("offline")
    world.publish(*world.hub.start("alarm-105"))
    world.run(15.0)
    assert world.last("alarmbot/status") == {"state": "offline"}
    assert world.hub.stops == []  # the alarm keeps ringing; the robot is not needed to stop it
    world.publish(*world.hub.stop("user"))
    world.run(1.0)
    assert world.results()["last_reason"] == "user"


def test_two_alarms_in_a_row_are_averaged() -> None:
    world = World("catch")
    world.publish(*world.hub.start("alarm-106"))
    world.run(20.0)
    world.publish(*world.hub.start("alarm-107"))
    world.run(5.0)
    world.publish(*world.hub.stop("user"))
    world.run(1.0)
    results = world.results()
    assert results["alarms_7d"] == 2
    assert results["avg_wake_delay_7d_s"] == pytest.approx(10.0, abs=0.2)  # (15 + 5) / 2
    assert results["avg_time_to_catch_7d_s"] == pytest.approx(15.0, abs=0.2)
