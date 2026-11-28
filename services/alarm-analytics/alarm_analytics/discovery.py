"""Tells Home Assistant which entities the service provides (MQTT discovery).

Each entity is announced with one retained message. Home Assistant then creates
it under a "Hub Robot" device and fills it from the results message, so nothing
about these entities is typed into Home Assistant by hand.

Every entity reads one field of the JSON on hub/analytics/state. The two
settings are numbers Will can change from the app; Home Assistant sends the new
value to hub/analytics/set/<key>.
"""

from __future__ import annotations

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
            default=1.0,
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


def _base(domain: str, key: str, name: str) -> dict[str, Any]:
    return {
        "name": name,
        "unique_id": f"hub_robot_{key}",
        # Fixes the entity id, so the dashboard in homeassistant/dashboards can name it.
        "default_entity_id": f"{domain}.hub_robot_{key}",
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
