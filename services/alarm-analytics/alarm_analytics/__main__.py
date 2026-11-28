"""Run the alarm analytics service.

    cd services/alarm-analytics
    ..\\..\\.venv\\Scripts\\python.exe -m alarm_analytics

On the Proxmox container it is started by systemd (deploy/alarm-analytics.service);
see docs/setup/alarm-analytics.md. Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from . import contract
from .analytics import Analytics
from .envfile import BrokerSettings, load_env_file
from .store import Store

TICK_S = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alarm analytics service for the Smart Home Hub.")
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".env",
        help="Settings file (default: services/alarm-analytics/.env).",
    )
    return parser.parse_args()


def decode(raw: bytes) -> Any:
    """A message's payload as data: JSON if it is JSON, otherwise the text."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def main() -> None:
    args = parse_args()
    load_env_file(args.env)
    settings = BrokerSettings.from_env()
    database = os.environ.get("ANALYTICS_DB", "alarm-analytics.db")

    store = Store(database)
    analytics = Analytics(store)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="alarm-analytics")
    client.username_pw_set(settings.username, settings.password)
    # The Last Will: Home Assistant shows the results as unavailable if the service dies.
    client.will_set(contract.TOPIC_AVAILABILITY, "offline", qos=1, retain=True)

    def publish(messages: list[contract.Message]) -> None:
        for message in messages:
            client.publish(message.topic, message.encode(), qos=message.qos, retain=message.retain)

    def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code.is_failure:
            print(f"Broker refused the connection: {reason_code}", flush=True)
            return
        print("Connected to the broker.", flush=True)
        for topic in contract.SUBSCRIPTIONS:
            client.subscribe(topic, qos=1)
        publish(analytics.on_connect(time.time()))

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        out = analytics.on_message(message.topic, decode(message.payload), time.time())
        if message.topic in (contract.TOPIC_START, contract.TOPIC_STOP, contract.TOPIC_CAUGHT):
            print(f"{message.topic} {message.payload.decode('utf-8', 'replace')}", flush=True)
        publish(out)

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"History file: {database}", flush=True)
    # paho reconnects by itself if the broker restarts; on_connect runs again each time.
    client.connect(settings.host, settings.port, keepalive=30)
    client.loop_start()
    try:
        while True:
            publish(analytics.tick(time.time()))
            time.sleep(TICK_S)
    except KeyboardInterrupt:
        print("Stopping.", flush=True)
        client.publish(contract.TOPIC_AVAILABILITY, "offline", qos=1, retain=True)
        time.sleep(0.5)
    finally:
        client.loop_stop()
        client.disconnect()
        store.close()


if __name__ == "__main__":
    main()
