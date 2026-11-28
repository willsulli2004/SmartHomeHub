"""What the service works out from the robot's reports, with no network code.

Analytics is told the time and what arrived, and returns the messages to
publish. __main__.py connects it to the broker; the tests drive it directly.

It only listens and reports. The alarm itself is run by Home Assistant and does
not wait for this service, so an alarm works the same with the service stopped.

What it works out:
- wake-up delay: seconds from hub/alarm/start to hub/alarm/stop, whatever the
  reason. Measured on this machine's clock when each message arrives, so it
  does not depend on the robot's clock.
- time to catch: the same span, for alarms stopped by a catch that looked real.
- distance travelled: from the robot's "caught" report, or its last odometry.
- whether a catch looked real: the robot must have reported being held off the
  ground for at least "Shortest real lift" before it said "caught". A knock
  that trips the robot's catch detection shows almost no lift.
- battery: the middle value of the last readings, so the brief dip when the
  motors start does not raise a false warning.
- seven-day averages and counts, from the history in store.py.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import contract, discovery
from .contract import Message
from .store import AlarmRecord, Store

# 2S Li-ion pack (docs/robot-integration.md): full, and the robot's own cut-off.
BATTERY_FULL_V = 8.4
BATTERY_EMPTY_V = 6.4
BATTERY_WINDOW = 15  # readings: 3 seconds during a chase, 2.5 minutes when idle
BATTERY_PUBLISH_PERIOD_S = 10.0  # at most one results message this often for battery alone
# A chase's readings are kept in memory until it ends. 5 a second for an hour.
MAX_SAMPLES = 18_000


@dataclass
class _Chase:
    """The alarm that is going off now."""

    alarm_id: str
    started: float
    samples: list[tuple[int, bool]] = field(default_factory=list)  # (ts_ms, lifted)
    last_odom_m: float | None = None
    caught_distance_m: float | None = None
    lift_ms: int | None = None
    caught: bool = False


class Analytics:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._chase: _Chase | None = None
        self._battery: deque[float] = deque(maxlen=BATTERY_WINDOW)
        self._last_battery_publish = 0.0
        self._battery_dirty = False

    # ---- events ----

    def on_connect(self, now: float) -> list[Message]:
        """Connected: announce the entities, mark the service online, send the results."""
        return [
            *discovery.messages(),
            Message(contract.TOPIC_AVAILABILITY, "online", qos=1, retain=True),
            self._results(now),
        ]

    def on_message(self, topic: str, payload: Any, now: float) -> list[Message]:
        if topic.startswith(contract.TOPIC_SET_PREFIX):
            return self._change_setting(topic[len(contract.TOPIC_SET_PREFIX) :], payload, now)
        if not isinstance(payload, dict):
            return []
        if topic == contract.TOPIC_START:
            return self._alarm_started(payload, now)
        if topic == contract.TOPIC_TELEMETRY:
            return self._telemetry(payload, now)
        if topic == contract.TOPIC_CAUGHT:
            return self._caught(payload)
        if topic == contract.TOPIC_STOP:
            return self._alarm_stopped(payload, now)
        return []

    def tick(self, now: float) -> list[Message]:
        """Call about once a second: sends a battery update if one is waiting."""
        if self._battery_dirty and now - self._last_battery_publish >= BATTERY_PUBLISH_PERIOD_S:
            return [self._results(now)]
        return []

    # ---- alarms ----

    def _alarm_started(self, payload: dict[str, Any], now: float) -> list[Message]:
        alarm_id = payload.get("alarm_id")
        if isinstance(alarm_id, str):
            self._chase = _Chase(alarm_id=alarm_id, started=now)
        return []

    def _telemetry(self, payload: dict[str, Any], now: float) -> list[Message]:
        volts = payload.get("battery_v")
        if isinstance(volts, (int, float)) and not isinstance(volts, bool) and 0 < volts < 20:
            self._battery.append(float(volts))
            self._battery_dirty = True

        chase = self._chase
        if chase is not None and payload.get("alarm_id") == chase.alarm_id and not chase.caught:
            ts_ms = payload.get("ts_ms")
            if isinstance(ts_ms, (int, float)) and len(chase.samples) < MAX_SAMPLES:
                chase.samples.append((int(ts_ms), payload.get("lifted") is True))
            odom = payload.get("odom_m")
            if isinstance(odom, (int, float)):
                chase.last_odom_m = float(odom)
        return []

    def _caught(self, payload: dict[str, Any]) -> list[Message]:
        chase = self._chase
        if chase is None or payload.get("alarm_id") != chase.alarm_id or chase.caught:
            return []
        chase.caught = True
        chase.lift_ms = self._lift_before_caught(chase.samples)
        distance = payload.get("distance_m")
        if isinstance(distance, (int, float)):
            chase.caught_distance_m = float(distance)
        return []

    def _alarm_stopped(self, payload: dict[str, Any], now: float) -> list[Message]:
        chase = self._chase
        if chase is None or payload.get("alarm_id") != chase.alarm_id:
            return []  # an alarm this service did not see start
        self._chase = None
        reason = payload.get("reason")
        reason = reason if reason in ("caught", "user", "timeout") else "user"

        catch_valid: bool | None = None
        lift_ms: int | None = None
        if reason == "caught":
            lift_ms = chase.lift_ms if chase.lift_ms is not None else 0
            catch_valid = lift_ms >= self._setting("min_lift_s") * 1000

        self.store.add_alarm(
            AlarmRecord(
                alarm_id=chase.alarm_id,
                started=chase.started,
                stopped=now,
                reason=reason,
                distance_m=chase.caught_distance_m if chase.caught_distance_m is not None else chase.last_odom_m,
                lift_ms=lift_ms,
                catch_valid=catch_valid,
            )
        )
        return [self._results(now)]

    @staticmethod
    def _lift_before_caught(samples: list[tuple[int, bool]]) -> int:
        """How long the robot had been held when it reported caught, in ms.

        Walks back from the last reading while "lifted" stays true. The lift is
        timed from the robot's own millisecond clock, so slow delivery over
        Wi-Fi does not change it.
        """
        if not samples or not samples[-1][1]:
            return 0
        end_ms = samples[-1][0]
        start_ms = end_ms
        for ts_ms, lifted in reversed(samples):
            if not lifted:
                break
            start_ms = ts_ms
        return max(0, end_ms - start_ms)

    # ---- settings ----

    def _setting(self, key: str) -> float:
        return self.store.get_setting(key, discovery.SETTINGS[key].default)

    def _change_setting(self, key: str, payload: Any, now: float) -> list[Message]:
        setting = discovery.SETTINGS.get(key)
        if setting is None or isinstance(payload, (bool, dict, list)):
            return []
        try:
            value = float(payload)
        except (TypeError, ValueError):
            return []
        value = min(setting.maximum, max(setting.minimum, value))
        self.store.set_setting(key, value)
        return [self._results(now)]

    # ---- results ----

    def _results(self, now: float) -> Message:
        """Everything the service knows, as one retained message."""
        self._last_battery_publish = now
        self._battery_dirty = False

        last = self.store.last_alarm()
        week = self.store.week_summary(now)
        volts = statistics.median(self._battery) if self._battery else None
        warn = self._setting("battery_warn_v")

        if last is None or last.reason != "caught":
            last_catch = "not caught" if last is not None else None
        else:
            last_catch = "real" if last.catch_valid else "suspicious"

        payload: dict[str, Any] = {
            "last_alarm_id": last.alarm_id if last else None,
            "last_reason": last.reason if last else None,
            "last_wake_delay_s": _round(last.duration_s if last else None, 1),
            "last_time_to_catch_s": _round(
                last.duration_s if last and last.reason == "caught" and last.catch_valid else None, 1
            ),
            "last_distance_m": _round(last.distance_m if last else None, 2),
            "last_lift_ms": last.lift_ms if last else None,
            "last_catch": last_catch,
            "avg_wake_delay_7d_s": _round(week.avg_wake_delay_s, 1),
            "avg_time_to_catch_7d_s": _round(week.avg_time_to_catch_s, 1),
            "alarms_7d": week.alarms,
            "catches_7d": week.catches,
            "suspicious_catches_7d": week.suspicious_catches,
            "battery_v": _round(volts, 2),
            "battery_pct": _battery_percent(volts),
            "battery_low": volts is not None and volts < warn,
            "battery_critical": volts is not None and volts <= BATTERY_EMPTY_V,
            "min_lift_s": self._setting("min_lift_s"),
            "battery_warn_v": warn,
        }
        return Message(contract.TOPIC_RESULTS, payload, qos=1, retain=True)


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _battery_percent(volts: float | None) -> int | None:
    """A rough charge level: a straight line from the cut-off to full."""
    if volts is None:
        return None
    share = (volts - BATTERY_EMPTY_V) / (BATTERY_FULL_V - BATTERY_EMPTY_V)
    return round(100 * min(1.0, max(0.0, share)))
