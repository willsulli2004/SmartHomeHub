"""The MQTT topics the analytics service reads and writes.

docs/robot-integration.md is the reference for the hub and robot topics.
tools/mock-robot has its own copy of the robot side on purpose (the two programs
only meet at the broker); tests/test_end_to_end.py runs them against each other.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Read: the hub's alarm messages and the robot's reports.
TOPIC_START = "hub/alarm/start"
TOPIC_STOP = "hub/alarm/stop"
TOPIC_TELEMETRY = "alarmbot/telemetry"
TOPIC_CAUGHT = "alarmbot/caught"

# Written: results for Home Assistant.
TOPIC_AVAILABILITY = "hub/analytics/status"  # retained: "online" / "offline" (Last Will)
TOPIC_RESULTS = "hub/analytics/state"  # retained JSON with every result
TOPIC_SET_PREFIX = "hub/analytics/set/"  # Home Assistant writes settings here

SUBSCRIPTIONS = (TOPIC_START, TOPIC_STOP, TOPIC_TELEMETRY, TOPIC_CAUGHT, TOPIC_SET_PREFIX + "#")

# Home Assistant's MQTT discovery prefix (its default).
DISCOVERY_PREFIX = "homeassistant"


@dataclass(frozen=True)
class Message:
    """One MQTT message to publish. The payload is JSON data or plain text."""

    topic: str
    payload: dict[str, Any] | str
    qos: int = 1
    retain: bool = False

    def encode(self) -> str:
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, separators=(",", ":"))
