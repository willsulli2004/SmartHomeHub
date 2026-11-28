"""The MQTT contract between the hub and the alarm robot, as the robot sees it.

docs/robot-integration.md is the reference; this file is the same contract in
code. services/alarm-analytics has its own copy on purpose: the two programs are
deployed separately and only meet at the broker. A test in the analytics service
runs both against each other, so a mismatch fails there.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# hub -> robot
TOPIC_SCHEDULE = "hub/alarm/schedule"  # retained: the alarms that are set
TOPIC_START = "hub/alarm/start"
TOPIC_STOP = "hub/alarm/stop"
SUBSCRIPTIONS = (TOPIC_SCHEDULE, TOPIC_START, TOPIC_STOP)

# robot -> everyone
TOPIC_STATUS = "alarmbot/status"  # retained; "offline" is sent by the broker (Last Will)
TOPIC_STATE = "alarmbot/state"  # retained
TOPIC_TELEMETRY = "alarmbot/telemetry"
TOPIC_CAUGHT = "alarmbot/caught"

STATE_IDLE = "idle"
STATE_FLEEING = "fleeing"
STATE_CAUGHT = "caught"
STATE_ERROR = "error"


@dataclass(frozen=True)
class Message:
    """One MQTT message to publish."""

    topic: str
    payload: dict[str, Any]
    qos: int = 1
    retain: bool = False

    def encode(self) -> str:
        return json.dumps(self.payload, separators=(",", ":"))


def iso_utc(epoch_s: float) -> str:
    """A timestamp the way the contract writes them: ISO 8601, UTC, whole seconds."""
    return datetime.fromtimestamp(epoch_s, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def online() -> Message:
    return Message(TOPIC_STATUS, {"state": "online"}, qos=1, retain=True)


def offline() -> Message:
    """What the broker sends for the robot when its connection is lost."""
    return Message(TOPIC_STATUS, {"state": "offline"}, qos=1, retain=True)
