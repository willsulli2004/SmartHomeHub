"""The mock robot's behaviour, with no network code.

MockRobot is told the time and what arrived, and returns the messages a real
robot would publish. __main__.py connects it to the broker; the tests drive it
directly, so no broker is needed to test it.

The numbers imitate the real robot (docs/robot-integration.md): a 2S Li-ion
pack, wheel odometry in metres, pitch and a "lifted" flag from the IMU, and the
nearest LiDAR return.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from . import contract
from .contract import Message

TELEMETRY_PERIOD_FLEEING_S = 0.2  # 5 messages a second during a chase
TELEMETRY_PERIOD_IDLE_S = 10.0  # one every 10 seconds otherwise, for the battery
MOTOR_START_SAG_V = 0.2  # the pack dips briefly when the motors start
MOTOR_START_SAG_S = 0.5


@dataclass(frozen=True)
class Scenario:
    """How one run of the mock behaves."""

    name: str
    description: str
    # Seconds into the chase when the robot reports "caught". None = never.
    catch_after_s: float | None = 15.0
    # How long the robot is held off the ground before it reports "caught". The
    # real robot waits for a sustained lift of 1 to 2 seconds; a bump is shorter.
    lift_s: float = 1.5
    battery_start_v: float = 7.9
    battery_drain_v_per_min: float = 0.02
    # Seconds into the chase when the robot drops off the network. None = never.
    offline_after_s: float | None = None
    speed_mps: float = 0.45


SCENARIOS: dict[str, Scenario] = {
    scenario.name: scenario
    for scenario in (
        Scenario("catch", "A normal chase: picked up after 15 seconds and held."),
        Scenario(
            "never",
            "Nobody catches it. The hub's alarm timeout ends the chase.",
            catch_after_s=None,
        ),
        Scenario(
            "bump",
            "A false catch: a knock makes it report 'caught' after 8 seconds with no real lift.",
            catch_after_s=8.0,
            lift_s=0.2,
        ),
        Scenario(
            "low-battery",
            "A normal chase on a nearly flat pack (starts at 6.75 V).",
            battery_start_v=6.75,
            battery_drain_v_per_min=0.3,
        ),
        Scenario(
            "offline",
            "Drops off the network 6 seconds into the chase and never reports back.",
            catch_after_s=None,
            offline_after_s=6.0,
        ),
    )
}


class MockRobot:
    """Behaves like the alarm robot on the broker."""

    def __init__(self, scenario: Scenario, boot_time: float) -> None:
        self.scenario = scenario
        self.boot_time = boot_time
        self.state = contract.STATE_IDLE
        self.alarm_id: str | None = None
        self.schedule: dict[str, Any] | None = None
        # Set when the scenario says the robot should vanish from the network.
        self.wants_disconnect = False
        self._chase_start = 0.0
        self._last_tick = boot_time
        self._last_telemetry = -math.inf
        self._odom_m = 0.0
        self._chases = 0

    # ---- events ----

    def on_connect(self, now: float) -> list[Message]:
        """Connected to the broker: announce presence and the current state."""
        return [contract.online(), self._state_message(now)]

    def on_message(self, topic: str, payload: dict[str, Any], now: float) -> list[Message]:
        if topic == contract.TOPIC_SCHEDULE:
            self.schedule = payload
            return []
        if topic == contract.TOPIC_START:
            return self._start_chase(payload, now)
        if topic == contract.TOPIC_STOP:
            return self._stop(payload, now)
        return []

    def tick(self, now: float) -> list[Message]:
        """Advance the simulation to `now`. Call it several times a second."""
        elapsed = max(0.0, now - self._last_tick)
        self._last_tick = now
        out: list[Message] = []

        if self.state == contract.STATE_FLEEING:
            chase_s = now - self._chase_start
            offline_after = self.scenario.offline_after_s
            if offline_after is not None and chase_s >= offline_after:
                self.wants_disconnect = True
                return out
            if not self._lifted(chase_s):
                self._odom_m += self.scenario.speed_mps * elapsed
            catch_after = self.scenario.catch_after_s
            if catch_after is not None and chase_s >= catch_after:
                # One last reading so the telemetry shows the lift, then "caught".
                out.append(self._telemetry(now))
                self._last_telemetry = now
                out.extend(self._report_caught(now))
                return out

        period = (
            TELEMETRY_PERIOD_FLEEING_S
            if self.state == contract.STATE_FLEEING
            else TELEMETRY_PERIOD_IDLE_S
        )
        if now - self._last_telemetry >= period:
            self._last_telemetry = now
            out.append(self._telemetry(now))
        return out

    # ---- behaviour ----

    def _start_chase(self, payload: dict[str, Any], now: float) -> list[Message]:
        alarm_id = payload.get("alarm_id")
        if not isinstance(alarm_id, str) or self.state == contract.STATE_FLEEING:
            return []  # not a valid start, or already running from this alarm
        self.alarm_id = alarm_id
        self.state = contract.STATE_FLEEING
        self._chase_start = now
        self._last_tick = now
        self._odom_m = 0.0
        self._chases += 1
        self._last_telemetry = -math.inf  # send a reading straight away
        return [self._state_message(now)]

    def _stop(self, payload: dict[str, Any], now: float) -> list[Message]:
        if payload.get("alarm_id") != self.alarm_id or self.state == contract.STATE_IDLE:
            return []  # about a different alarm, or nothing to stop
        self.state = contract.STATE_IDLE
        self._last_telemetry = -math.inf
        return [self._state_message(now)]

    def _report_caught(self, now: float) -> list[Message]:
        self.state = contract.STATE_CAUGHT
        caught = Message(
            contract.TOPIC_CAUGHT,
            {
                "alarm_id": self.alarm_id,
                "ts": contract.iso_utc(now),
                "chase_ms": round((now - self._chase_start) * 1000),
                "distance_m": round(self._odom_m, 2),
            },
            qos=1,
        )
        return [caught, self._state_message(now)]

    # ---- simulated sensors ----

    def _lifted(self, chase_s: float) -> bool:
        catch_after = self.scenario.catch_after_s
        if catch_after is None:
            return False
        return chase_s >= catch_after - self.scenario.lift_s

    def _battery_v(self, now: float) -> float:
        volts = self.scenario.battery_start_v
        if self.state == contract.STATE_FLEEING:
            chase_s = now - self._chase_start
            volts -= self.scenario.battery_drain_v_per_min * chase_s / 60.0
            if chase_s < MOTOR_START_SAG_S:
                volts -= MOTOR_START_SAG_V
        return round(volts, 2)

    def _telemetry(self, now: float) -> Message:
        fleeing = self.state == contract.STATE_FLEEING
        chase_s = now - self._chase_start if fleeing else 0.0
        lifted = fleeing and self._lifted(chase_s)
        moving = fleeing and not lifted
        payload: dict[str, Any] = {
            "alarm_id": self.alarm_id if self.state != contract.STATE_IDLE else None,
            "ts_ms": round((now - self.boot_time) * 1000),
            "state": self.state,
            "battery_v": self._battery_v(now),
            "odom_m": round(self._odom_m, 2),
            "speed_mps": self.scenario.speed_mps if moving else 0.0,
            # Level with a little wobble while driving; tipped up when held.
            "pitch_deg": 24.0 if lifted else round(2.0 * math.sin(chase_s * 3.0), 1) if moving else 0.0,
            "lifted": lifted,
            # The person chasing: closing in from behind while the robot drives.
            "nearest_cm": round(180 - 60 * math.sin(chase_s * 0.7)) if moving else None,
            "bearing_deg": 180 if moving else None,
        }
        return Message(contract.TOPIC_TELEMETRY, payload, qos=0)

    def _state_message(self, now: float) -> Message:
        payload: dict[str, Any] = {"state": self.state, "ts": contract.iso_utc(now)}
        if self.state != contract.STATE_IDLE and self.alarm_id is not None:
            payload["alarm_id"] = self.alarm_id
        return Message(contract.TOPIC_STATE, payload, qos=1, retain=True)
