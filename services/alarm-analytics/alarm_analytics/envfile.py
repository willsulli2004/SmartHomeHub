"""Reads settings from a .env file and the environment.

A .env file holds KEY=VALUE lines. Values already set in the environment win,
so a container or service manager can override the file. The file is
gitignored; .env.example shows the keys. Nothing here prints a value.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_env_file(path: Path) -> None:
    """Copy KEY=VALUE lines from `path` into the environment, if the file exists."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


@dataclass(frozen=True)
class BrokerSettings:
    host: str
    port: int
    username: str
    password: str

    @classmethod
    def from_env(cls) -> "BrokerSettings":
        """Read the broker settings. Raises SystemExit naming any that are missing."""
        missing = [key for key in ("MQTT_HOST", "MQTT_USERNAME", "MQTT_PASSWORD") if not os.environ.get(key)]
        if missing:
            raise SystemExit(
                "Missing settings: " + ", ".join(missing) + ". Copy .env.example to .env and fill it in."
            )
        return cls(
            host=os.environ["MQTT_HOST"],
            port=int(os.environ.get("MQTT_PORT", "1883")),
            username=os.environ["MQTT_USERNAME"],
            password=os.environ["MQTT_PASSWORD"],
        )
