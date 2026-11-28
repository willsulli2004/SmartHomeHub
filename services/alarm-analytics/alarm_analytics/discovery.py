"""Tells Home Assistant which entities the service provides (MQTT discovery).

Each entity is announced with one retained message. Home Assistant then creates
it under a "Hub Robot" device and fills it from the results message, so nothing
about these entities is typed into Home Assistant by hand.

Every entity reads one field of the JSON on hub/analytics/state. The two
settings are numbers Will can change from the app; Home Assistant sends the new
value to hub/analytics/set/<key>.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from . import contract
from .contract import Message

DEVICE = {
    "identifiers": ["hub_robot_analytics"],
    "name": "Hub Robot",
    "manufacturer": "Smart Home Hub",
    "model": "Alarm analytics service",
}


@dataclass(frozen=True)
class Setting:
    """A value that can be changed from Home Assistant."""

    key: str
    name: str
    default: float
    minimum: float
    maximum: float
    step: float
    unit: str
    icon: str


SETTINGS: dict[str, Setting] = {
    s.key: s
    for s in (
        Setting(
            "min_lift_s",
            "Shortest real lift",
            # The real robot reports `lifted` from 0.2 s into a lift and says
            # "caught" at 1.2 s, so a real catch shows about 0.8 to 1.0 s of
            # lift in the telemetry. A knock shows 0.2 s or less. 0.5 sits
            # between the two. (It was 1.0 until the first runs with the real
            # robot, which would have marked every real catch suspicious.)
            default=0.5,
            minimum=0.2,
            maximum=3.0,
            step=0.1,
            unit="s",
            icon="mdi:hand-back-left",
        ),
        Setting(
            "battery_warn_v",
            "Battery warning level",
            default=6.8,
            minimum=6.5,
            maximum=7.4,
            step=0.05,
            unit="V",
            icon="mdi:battery-alert",
        ),
    )
}

# key in the results JSON, name, unit, device class, state class, icon
_SENSORS: tuple[tuple[str, str, str | None, str | None, str | None, str], ...] = (
    ("last_wake_delay_s", "Last wake-up delay", "s", "duration", "measurement", "mdi:alarm-snooze"),
    ("last_time_to_catch_s", "Last time to catch", "s", "duration", "measurement", "mdi:run-fast"),
    ("last_distance_m", "Last distance", "m", "distance", "measurement", "mdi:map-marker-distance"),
    ("last_catch", "Last catch", None, None, None, "mdi:hand-back-left"),
    ("last_reason", "Last stop reason", None, None, None, "mdi:alarm-off"),
    ("avg_wake_delay_7d_s", "Wake-up delay 7 day average", "s", "duration", "measurement", "mdi:chart-line"),
    ("avg_time_to_catch_7d_s", "Time to catch 7 day average", "s", "duration", "measurement", "mdi:chart-line"),
    ("alarms_7d", "Alarms in 7 days", None, None, "measurement", "mdi:alarm-multiple"),
    ("catches_7d", "Catches in 7 days", None, None, "measurement", "mdi:hand-back-left"),
    ("suspicious_catches_7d", "Suspicious catches in 7 days", None, None, "measurement", "mdi:alert"),
    ("battery_v", "Battery", "V", "voltage", "measurement", "mdi:battery"),
    ("battery_pct", "Battery level", "%", "battery", "measurement", "mdi:battery"),
)

# key, name, device class
_BINARY_SENSORS: tuple[tuple[str, str, str], ...] = (
    ("battery_low", "Battery low", "battery"),
    ("battery_critical", "Battery critical", "problem"),
)


def entity_id(domain: str, name: str) -> str:
    """The entity id Home Assistant gives an entity: the device name plus its name.

    "Hub Robot" + "Last wake-up delay" becomes sensor.hub_robot_last_wake_up_delay.
    The dashboard in homeassistant/dashboards names entities this way, and a test
    checks the two stay in step.
    """
    words = re.sub(r"[^a-z0-9]+", "_", f"{DEVICE['name']} {name}".lower()).strip("_")
    return f"{domain}.{words}"


def entity_ids() -> set[str]:
    """Every entity id the service creates in Home Assistant."""
    ids = {entity_id("sensor", name) for _, name, *_ in _SENSORS}
    ids |= {entity_id("binary_sensor", name) for _, name, _ in _BINARY_SENSORS}
    ids |= {entity_id("number", setting.name) for setting in SETTINGS.values()}
    return ids


def _base(domain: str, key: str, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "unique_id": f"hub_robot_{key}",
        "state_topic": contract.TOPIC_RESULTS,
        "availability_topic": contract.TOPIC_AVAILABILITY,
        "device": DEVICE,
    }


def _config_topic(domain: str, key: str) -> str:
    return f"{contract.DISCOVERY_PREFIX}/{domain}/hub_robot/{key}/config"


def messages() -> list[Message]:
    """The retained discovery messages for every entity."""
    out: list[Message] = []
    for key, name, unit, device_class, state_class, icon in _SENSORS:
        config = _base("sensor", key, name)
        config["value_template"] = "{{ value_json." + key + " }}"
        config["icon"] = icon
        if unit:
            config["unit_of_measurement"] = unit
        if device_class:
            config["device_class"] = device_class
        if state_class:
            config["state_class"] = state_class
        out.append(Message(_config_topic("sensor", key), config, qos=1, retain=True))

    for key, name, device_class in _BINARY_SENSORS:
        config = _base("binary_sensor", key, name)
        config["value_template"] = "{{ 'ON' if value_json." + key + " else 'OFF' }}"
        config["device_class"] = device_class
        out.append(Message(_config_topic("binary_sensor", key), config, qos=1, retain=True))

    for setting in SETTINGS.values():
        config = _base("number", setting.key, setting.name)
        config["value_template"] = "{{ value_json." + setting.key + " }}"
        config["command_topic"] = contract.TOPIC_SET_PREFIX + setting.key
        config["min"] = setting.minimum
        config["max"] = setting.maximum
        config["step"] = setting.step
        config["unit_of_measurement"] = setting.unit
        config["icon"] = setting.icon
        config["mode"] = "box"
        config["entity_category"] = "config"
        out.append(Message(_config_topic("number", setting.key), config, qos=1, retain=True))
    return out
