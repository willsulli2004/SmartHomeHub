"""Checks the analytics logic without a broker.

    .\\.venv\\Scripts\\python.exe -m pytest services/alarm-analytics
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from alarm_analytics import contract, discovery
from alarm_analytics.analytics import Analytics
from alarm_analytics.contract import Message
from alarm_analytics.store import SEVEN_DAYS_S, AlarmRecord, Store

T0 = 1_800_000_000.0


@pytest.fixture
def analytics() -> Analytics:
    return Analytics(Store(":memory:"))


def telemetry(alarm_id: str | None, ts_ms: int, lifted: bool = False, **extra: Any) -> dict[str, Any]:
    return {"alarm_id": alarm_id, "ts_ms": ts_ms, "lifted": lifted, "battery_v": 7.9, "odom_m": 0.0, **extra}


def run_alarm(
    analytics: Analytics,
    alarm_id: str,
    start: float,
    seconds: float,
    reason: str,
    lift_ms: int = 0,
    distance_m: float | None = None,
) -> dict[str, Any]:
    """Play one alarm through the service and return the results it publishes."""
    analytics.on_message(contract.TOPIC_START, {"alarm_id": alarm_id, "ts": "x"}, start)
    total_ms = round(seconds * 1000)
    for ts_ms in range(0, total_ms + 1, 200):
        lifted = reason == "caught" and ts_ms >= total_ms - lift_ms
        analytics.on_message(
            contract.TOPIC_TELEMETRY,
            telemetry(alarm_id, ts_ms, lifted, odom_m=round(ts_ms / 1000 * 0.4, 2)),
            start + ts_ms / 1000,
        )
    if reason == "caught":
        caught = {"alarm_id": alarm_id, "ts": "x", "chase_ms": total_ms}
        if distance_m is not None:
            caught["distance_m"] = distance_m
        analytics.on_message(contract.TOPIC_CAUGHT, caught, start + seconds)
    (results,) = analytics.on_message(
        contract.TOPIC_STOP, {"alarm_id": alarm_id, "reason": reason, "ts": "x"}, start + seconds
    )
    assert results.topic == contract.TOPIC_RESULTS
    assert results.retain is True
    assert isinstance(results.payload, dict)
    return results.payload


# ---- one alarm ----


def test_a_real_catch_is_timed_and_marked_real(analytics: Analytics) -> None:
    results = run_alarm(analytics, "alarm-1", T0, 20.0, "caught", lift_ms=1400, distance_m=7.5)
    assert results["last_alarm_id"] == "alarm-1"
    assert results["last_reason"] == "caught"
    assert results["last_wake_delay_s"] == 20.0
    assert results["last_time_to_catch_s"] == 20.0
    assert results["last_distance_m"] == 7.5
    assert results["last_lift_ms"] == 1400
    assert results["last_catch"] == "real"
    assert (results["alarms_7d"], results["catches_7d"], results["suspicious_catches_7d"]) == (1, 1, 0)


def test_a_bump_is_marked_suspicious_and_not_counted_as_a_catch(analytics: Analytics) -> None:
    results = run_alarm(analytics, "alarm-1", T0, 8.0, "caught", lift_ms=200)
    assert results["last_catch"] == "suspicious"
    assert results["last_lift_ms"] == 200
    assert results["last_wake_delay_s"] == 8.0
    assert results["last_time_to_catch_s"] is None  # only real catches have a time to catch
    assert (results["catches_7d"], results["suspicious_catches_7d"]) == (0, 1)
    assert results["avg_time_to_catch_7d_s"] is None


def test_a_caught_report_with_no_lift_readings_is_suspicious(analytics: Analytics) -> None:
    analytics.on_message(contract.TOPIC_START, {"alarm_id": "a"}, T0)
    analytics.on_message(contract.TOPIC_CAUGHT, {"alarm_id": "a"}, T0 + 5)
    (results,) = analytics.on_message(contract.TOPIC_STOP, {"alarm_id": "a", "reason": "caught"}, T0 + 5)
    assert results.payload["last_catch"] == "suspicious"
    assert results.payload["last_lift_ms"] == 0


def test_a_user_stop_has_a_delay_but_no_catch(analytics: Analytics) -> None:
    results = run_alarm(analytics, "alarm-1", T0, 12.0, "user")
    assert results["last_reason"] == "user"
    assert results["last_wake_delay_s"] == 12.0
    assert results["last_time_to_catch_s"] is None
    assert results["last_catch"] == "not caught"
    assert results["last_distance_m"] == pytest.approx(4.8)  # from the last odometry reading


def test_a_timeout_is_recorded(analytics: Analytics) -> None:
    results = run_alarm(analytics, "alarm-1", T0, 600.0, "timeout")
    assert results["last_reason"] == "timeout"
    assert results["last_wake_delay_s"] == 600.0


def test_an_alarm_works_with_no_robot_at_all(analytics: Analytics) -> None:
    analytics.on_message(contract.TOPIC_START, {"alarm_id": "a"}, T0)
    (results,) = analytics.on_message(contract.TOPIC_STOP, {"alarm_id": "a", "reason": "user"}, T0 + 30)
    assert results.payload["last_wake_delay_s"] == 30.0
    assert results.payload["last_distance_m"] is None


def test_the_lift_threshold_can_be_changed(analytics: Analytics) -> None:
    analytics.on_message(contract.TOPIC_SET_PREFIX + "min_lift_s", 0.2, T0)
    results = run_alarm(analytics, "alarm-1", T0, 8.0, "caught", lift_ms=400)
    assert results["last_catch"] == "real"


# ---- messages that must be ignored ----


def test_a_stop_for_an_alarm_it_never_saw_start_is_ignored(analytics: Analytics) -> None:
    assert analytics.on_message(contract.TOPIC_STOP, {"alarm_id": "x", "reason": "user"}, T0) == []


def test_telemetry_and_caught_for_another_alarm_are_ignored(analytics: Analytics) -> None:
    analytics.on_message(contract.TOPIC_START, {"alarm_id": "a"}, T0)
    analytics.on_message(contract.TOPIC_TELEMETRY, telemetry("other", 100, lifted=True, odom_m=99.0), T0 + 1)
    analytics.on_message(contract.TOPIC_CAUGHT, {"alarm_id": "other", "distance_m": 99.0}, T0 + 2)
    (results,) = analytics.on_message(contract.TOPIC_STOP, {"alarm_id": "a", "reason": "user"}, T0 + 3)
    assert results.payload["last_distance_m"] is None


@pytest.mark.parametrize("payload", [None, "hello", 5, [1, 2], {"no": "alarm_id"}])
def test_bad_payloads_do_not_break_it(analytics: Analytics, payload: Any) -> None:
    for topic in (contract.TOPIC_START, contract.TOPIC_TELEMETRY, contract.TOPIC_CAUGHT, contract.TOPIC_STOP):
        assert analytics.on_message(topic, payload, T0) == []


# ---- seven-day figures ----


def test_seven_day_averages_drop_old_alarms(analytics: Analytics) -> None:
    eight_days_ago = T0 - 8 * 24 * 3600
    run_alarm(analytics, "old", eight_days_ago, 500.0, "user")
    run_alarm(analytics, "a", T0 - 3600, 10.0, "caught", lift_ms=1400)
    run_alarm(analytics, "b", T0 - 1800, 30.0, "caught", lift_ms=1400)
    results = run_alarm(analytics, "c", T0, 50.0, "user")
    assert results["alarms_7d"] == 3
    assert results["avg_wake_delay_7d_s"] == 30.0  # (10 + 30 + 50) / 3, without the old one
    assert results["avg_time_to_catch_7d_s"] == 20.0  # (10 + 30) / 2
    assert results["catches_7d"] == 2


def test_history_survives_a_restart(tmp_path: Any) -> None:
    path = str(tmp_path / "history.db")
    first = Analytics(Store(path))
    run_alarm(first, "a", T0, 10.0, "caught", lift_ms=1400)
    first.on_message(contract.TOPIC_SET_PREFIX + "battery_warn_v", "7.0", T0)
    first.store.close()

    second = Analytics(Store(path))
    results = second.on_connect(T0 + 60)[-1].payload
    assert isinstance(results, dict)
    assert results["last_alarm_id"] == "a"
    assert results["battery_warn_v"] == 7.0


def test_week_summary_with_no_history() -> None:
    summary = Store(":memory:").week_summary(T0)
    assert (summary.alarms, summary.catches, summary.avg_wake_delay_s) == (0, 0, None)


def test_a_repeated_alarm_id_replaces_the_row() -> None:
    store = Store(":memory:")
    for stopped in (T0 + 5, T0 + 9):
        store.add_alarm(AlarmRecord("a", T0, stopped, "user", None, None, None))
    assert store.week_summary(T0 + SEVEN_DAYS_S).alarms == 1
    assert store.last_alarm() is not None and store.last_alarm().duration_s == 9.0


# ---- battery ----


def feed_battery(analytics: Analytics, volts: list[float], start: float = T0) -> dict[str, Any]:
    for i, v in enumerate(volts):
        analytics.on_message(contract.TOPIC_TELEMETRY, {"alarm_id": None, "ts_ms": i, "battery_v": v}, start + i)
    (results,) = analytics.tick(start + len(volts) + 60)
    assert isinstance(results.payload, dict)
    return results.payload


def test_battery_is_healthy_at_a_normal_voltage(analytics: Analytics) -> None:
    results = feed_battery(analytics, [7.9] * 15)
    assert results["battery_v"] == 7.9
    assert results["battery_pct"] == 75
    assert results["battery_low"] is False
    assert results["battery_critical"] is False


def test_a_brief_sag_does_not_raise_the_low_warning(analytics: Analytics) -> None:
    # The pack dips 0.2 V for a moment when the motors start.
    results = feed_battery(analytics, [6.95] * 7 + [6.75, 6.75] + [6.95] * 6)
    assert results["battery_v"] == 6.95
    assert results["battery_low"] is False


def test_a_sustained_low_voltage_raises_the_warning(analytics: Analytics) -> None:
    results = feed_battery(analytics, [6.75] * 15)
    assert results["battery_low"] is True
    assert results["battery_critical"] is False


def test_critical_at_the_robots_cut_off(analytics: Analytics) -> None:
    results = feed_battery(analytics, [6.4] * 15)
    assert results["battery_critical"] is True
    assert results["battery_pct"] == 0


def test_the_battery_warning_level_can_be_changed(analytics: Analytics) -> None:
    analytics.on_message(contract.TOPIC_SET_PREFIX + "battery_warn_v", 7.2, T0)
    assert feed_battery(analytics, [7.0] * 15)["battery_low"] is True


@pytest.mark.parametrize("bad", [None, "7.9", True, -1, 0, 55.0])
def test_nonsense_battery_readings_are_ignored(analytics: Analytics, bad: Any) -> None:
    analytics.on_message(contract.TOPIC_TELEMETRY, {"alarm_id": None, "ts_ms": 1, "battery_v": bad}, T0)
    assert analytics.tick(T0 + 100) == []


def test_battery_updates_are_not_sent_more_than_every_ten_seconds(analytics: Analytics) -> None:
    analytics.on_connect(T0)
    analytics.on_message(contract.TOPIC_TELEMETRY, {"alarm_id": None, "ts_ms": 1, "battery_v": 7.9}, T0 + 1)
    assert analytics.tick(T0 + 2) == []
    assert len(analytics.tick(T0 + 11)) == 1
    assert analytics.tick(T0 + 30) == []  # nothing new to report


# ---- settings ----


def test_settings_are_clamped_to_their_range(analytics: Analytics) -> None:
    (results,) = analytics.on_message(contract.TOPIC_SET_PREFIX + "min_lift_s", 99, T0)
    assert results.payload["min_lift_s"] == 3.0
    (results,) = analytics.on_message(contract.TOPIC_SET_PREFIX + "min_lift_s", "0.01", T0)
    assert results.payload["min_lift_s"] == 0.2


@pytest.mark.parametrize("payload", ["abc", None, True, {"v": 1}, [1]])
def test_bad_setting_values_are_ignored(analytics: Analytics, payload: Any) -> None:
    assert analytics.on_message(contract.TOPIC_SET_PREFIX + "min_lift_s", payload, T0) == []


def test_unknown_settings_are_ignored(analytics: Analytics) -> None:
    assert analytics.on_message(contract.TOPIC_SET_PREFIX + "nope", 1, T0) == []


# ---- what Home Assistant is told ----


def test_connect_announces_entities_then_online_then_results(analytics: Analytics) -> None:
    messages = analytics.on_connect(T0)
    configs = [m for m in messages if m.topic.startswith("homeassistant/")]
    assert len(configs) == len(messages) - 2
    assert all(m.retain for m in messages)
    assert messages[-2] == Message(contract.TOPIC_AVAILABILITY, "online", qos=1, retain=True)
    assert messages[-1].topic == contract.TOPIC_RESULTS


def test_every_discovered_entity_reads_a_field_the_results_contain(analytics: Analytics) -> None:
    results = analytics.on_connect(T0)[-1].payload
    assert isinstance(results, dict)
    for message in discovery.messages():
        config = message.payload
        assert isinstance(config, dict)
        key = config["unique_id"].removeprefix("hub_robot_")
        assert key in results, key
        assert "value_json." + key in config["value_template"]
        domain = message.topic.split("/")[1]
        assert message.topic == f"homeassistant/{domain}/hub_robot/{key}/config"
        assert config["device"]["name"] == "Hub Robot"
        json.loads(message.encode())  # valid JSON


def test_settings_are_offered_as_numbers_with_a_command_topic() -> None:
    numbers = [m.payload for m in discovery.messages() if "/number/" in m.topic]
    assert {n["command_topic"] for n in numbers if isinstance(n, dict)} == {
        "hub/analytics/set/min_lift_s",
        "hub/analytics/set/battery_warn_v",
    }


def test_results_are_empty_but_valid_before_any_alarm(analytics: Analytics) -> None:
    results = analytics.on_connect(T0)[-1].payload
    assert isinstance(results, dict)
    assert results["last_alarm_id"] is None
    assert results["last_catch"] is None
    assert results["alarms_7d"] == 0
    assert results["battery_v"] is None
    assert results["battery_low"] is False
    assert (results["min_lift_s"], results["battery_warn_v"]) == (0.5, 6.8)


def test_entity_ids_follow_the_device_and_entity_names() -> None:
    assert discovery.entity_id("sensor", "Last wake-up delay") == "sensor.hub_robot_last_wake_up_delay"
    assert discovery.entity_id("number", "Shortest real lift") == "number.hub_robot_shortest_real_lift"
    assert len(discovery.entity_ids()) == len(discovery.messages())


def test_the_dashboard_only_names_robot_entities_that_exist() -> None:
    import yaml  # PyYAML, installed with the development tools

    repo = Path(__file__).resolve().parents[3]
    dashboard = yaml.safe_load((repo / "homeassistant" / "dashboards" / "hub_alarms.yaml").read_text("utf-8"))

    def entities(node: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("entity", "entity_id") and isinstance(value, str):
                    found.add(value)
                else:
                    found |= entities(value)
        elif isinstance(node, list):
            for item in node:
                found |= entities(item)
        return found

    # The two status entities come from homeassistant/packages/hub_robot.yaml.
    known = discovery.entity_ids() | {"binary_sensor.hub_robot_online", "sensor.hub_robot_state"}
    used = {e for e in entities(dashboard) if e.split(".", 1)[1].startswith("hub_robot_")}
    assert used, "the dashboard should show the robot"
    assert used <= known, sorted(used - known)
