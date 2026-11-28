"""Checks the mock robot's behaviour without a broker.

    .\\.venv\\Scripts\\python.exe -m pytest tools/mock-robot
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mock_robot import contract
from mock_robot.contract import Message
from mock_robot.envfile import BrokerSettings, load_env_file
from mock_robot.robot import SCENARIOS, MockRobot

T0 = 1_800_000_000.0  # an arbitrary start time, in seconds


def run(robot: MockRobot, start: float, seconds: float, step: float = 0.05) -> list[Message]:
    """Tick the robot from `start` for `seconds` and collect what it publishes."""
    out: list[Message] = []
    steps = round(seconds / step)
    for i in range(1, steps + 1):
        out.extend(robot.tick(start + i * step))
    return out


def start_alarm(robot: MockRobot, alarm_id: str = "alarm-1") -> list[Message]:
    return robot.on_message(contract.TOPIC_START, {"alarm_id": alarm_id, "ts": "x"}, T0)


def topics(messages: list[Message]) -> list[str]:
    return [m.topic for m in messages]


def test_connect_announces_online_and_idle() -> None:
    robot = MockRobot(SCENARIOS["catch"], boot_time=T0)
    status, state = robot.on_connect(T0)
    assert (status.topic, status.payload, status.retain) == (contract.TOPIC_STATUS, {"state": "online"}, True)
    assert state.topic == contract.TOPIC_STATE
    assert state.payload["state"] == "idle"
    assert state.retain is True


def test_idle_robot_sends_slow_telemetry_for_the_battery() -> None:
    robot = MockRobot(SCENARIOS["catch"], boot_time=T0)
    messages = run(robot, T0, 25.0)
    assert topics(messages) == [contract.TOPIC_TELEMETRY] * 3  # at 0, 10 and 20 seconds
    assert messages[0].payload["state"] == "idle"
    assert messages[0].payload["alarm_id"] is None
    assert messages[0].payload["battery_v"] == 7.9
    assert messages[0].qos == 0


def test_start_makes_it_flee_and_send_fast_telemetry() -> None:
    robot = MockRobot(SCENARIOS["never"], boot_time=T0)
    (state,) = start_alarm(robot)
    assert state.payload == {"state": "fleeing", "ts": contract.iso_utc(T0), "alarm_id": "alarm-1"}

    messages = run(robot, T0, 2.0)
    telemetry = [m.payload for m in messages if m.topic == contract.TOPIC_TELEMETRY]
    assert 9 <= len(telemetry) <= 11  # about 5 a second
    assert all(t["alarm_id"] == "alarm-1" and t["state"] == "fleeing" for t in telemetry)
    assert telemetry[-1]["odom_m"] > telemetry[0]["odom_m"]  # it is driving
    assert telemetry[-1]["lifted"] is False
    assert telemetry[-1]["nearest_cm"] is not None


def test_battery_sags_when_the_motors_start() -> None:
    robot = MockRobot(SCENARIOS["never"], boot_time=T0)
    start_alarm(robot)
    telemetry = [m.payload for m in run(robot, T0, 2.0) if m.topic == contract.TOPIC_TELEMETRY]
    assert telemetry[0]["battery_v"] == pytest.approx(7.7, abs=0.01)  # 0.2 V dip
    assert telemetry[-1]["battery_v"] == pytest.approx(7.9, abs=0.01)


def test_catch_scenario_lifts_then_reports_caught() -> None:
    robot = MockRobot(SCENARIOS["catch"], boot_time=T0)
    start_alarm(robot)
    messages = run(robot, T0, 16.0)

    caught = [m for m in messages if m.topic == contract.TOPIC_CAUGHT]
    assert len(caught) == 1
    assert caught[0].payload["alarm_id"] == "alarm-1"
    assert caught[0].payload["chase_ms"] == pytest.approx(15_000, abs=100)
    assert caught[0].payload["distance_m"] == pytest.approx(0.45 * 13.5, abs=0.2)
    assert caught[0].qos == 1

    # Held off the ground for about 1.5 seconds before it reported.
    lifted = [m.payload for m in messages if m.topic == contract.TOPIC_TELEMETRY and m.payload["lifted"]]
    assert 6 <= len(lifted) <= 9
    assert all(t["speed_mps"] == 0.0 for t in lifted)

    assert robot.state == "caught"
    assert messages[-1].topic == contract.TOPIC_STATE
    assert messages[-1].payload["state"] == "caught"


def test_stop_returns_it_to_idle() -> None:
    robot = MockRobot(SCENARIOS["catch"], boot_time=T0)
    start_alarm(robot)
    run(robot, T0, 16.0)
    (state,) = robot.on_message(
        contract.TOPIC_STOP, {"alarm_id": "alarm-1", "reason": "caught", "ts": "x"}, T0 + 16
    )
    assert state.payload["state"] == "idle"
    assert "alarm_id" not in state.payload
    assert robot.state == "idle"


def test_stop_for_another_alarm_is_ignored() -> None:
    robot = MockRobot(SCENARIOS["never"], boot_time=T0)
    start_alarm(robot)
    assert robot.on_message(contract.TOPIC_STOP, {"alarm_id": "alarm-other", "reason": "user"}, T0 + 1) == []
    assert robot.state == "fleeing"


def test_user_stop_mid_chase_ends_it_without_a_catch() -> None:
    robot = MockRobot(SCENARIOS["catch"], boot_time=T0)
    start_alarm(robot)
    run(robot, T0, 5.0)
    robot.on_message(contract.TOPIC_STOP, {"alarm_id": "alarm-1", "reason": "user"}, T0 + 5)
    later = run(robot, T0 + 5, 20.0)
    assert contract.TOPIC_CAUGHT not in topics(later)
    assert robot.state == "idle"


def test_never_scenario_keeps_fleeing() -> None:
    robot = MockRobot(SCENARIOS["never"], boot_time=T0)
    start_alarm(robot)
    messages = run(robot, T0, 60.0)
    assert contract.TOPIC_CAUGHT not in topics(messages)
    assert robot.state == "fleeing"


def test_bump_scenario_reports_caught_with_almost_no_lift() -> None:
    robot = MockRobot(SCENARIOS["bump"], boot_time=T0)
    start_alarm(robot)
    messages = run(robot, T0, 9.0)
    assert contract.TOPIC_CAUGHT in topics(messages)
    lifted = [m for m in messages if m.topic == contract.TOPIC_TELEMETRY and m.payload["lifted"]]
    assert len(lifted) <= 2  # a fraction of a second, not a sustained lift


def test_low_battery_scenario_starts_under_the_warning_level() -> None:
    robot = MockRobot(SCENARIOS["low-battery"], boot_time=T0)
    start_alarm(robot)
    telemetry = [m.payload for m in run(robot, T0, 10.0) if m.topic == contract.TOPIC_TELEMETRY]
    assert all(t["battery_v"] < 6.8 for t in telemetry)
    assert telemetry[-1]["battery_v"] < telemetry[5]["battery_v"]  # and falling


def test_offline_scenario_asks_to_disconnect_mid_chase() -> None:
    robot = MockRobot(SCENARIOS["offline"], boot_time=T0)
    start_alarm(robot)
    messages = run(robot, T0, 10.0)
    assert robot.wants_disconnect is True
    assert contract.TOPIC_CAUGHT not in topics(messages)


def test_second_start_while_fleeing_is_ignored() -> None:
    robot = MockRobot(SCENARIOS["never"], boot_time=T0)
    start_alarm(robot, "alarm-1")
    assert start_alarm(robot, "alarm-2") == []
    assert robot.alarm_id == "alarm-1"


def test_schedule_is_remembered() -> None:
    robot = MockRobot(SCENARIOS["catch"], boot_time=T0)
    schedule = {"alarms": ["07:00"], "next": "2026-11-28T15:00:00Z", "next_epoch": 1795618800}
    assert robot.on_message(contract.TOPIC_SCHEDULE, schedule, T0) == []
    assert robot.schedule == schedule


def test_messages_encode_as_compact_json() -> None:
    assert contract.online().encode() == '{"state":"online"}'
    assert contract.iso_utc(0) == "1970-01-01T00:00:00Z"


def test_env_file_is_read_without_overriding_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "# comment\nMQTT_HOST=broker.test\nMQTT_USERNAME=alarmbot\nMQTT_PASSWORD='not-a-real-password'\n",
        encoding="utf-8",
    )
    for key in ("MQTT_HOST", "MQTT_PORT", "MQTT_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MQTT_USERNAME", "from-environment")
    load_env_file(env)
    settings = BrokerSettings.from_env()
    assert settings.host == "broker.test"
    assert settings.port == 1883
    assert settings.username == "from-environment"  # the environment wins
    assert settings.password == "not-a-real-password"  # quotes removed


def test_missing_settings_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("MQTT_HOST", "MQTT_USERNAME", "MQTT_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SystemExit) as error:
        BrokerSettings.from_env()
    assert "MQTT_HOST" in str(error.value)
