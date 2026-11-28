"""Run the mock robot against the real broker.

    cd tools/mock-robot
    ..\\..\\.venv\\Scripts\\python.exe -m mock_robot --scenario catch

It connects with the robot's login, announces itself, and waits for the hub to
start an alarm. Press Ctrl+C to stop; the broker then marks the robot offline.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import threading
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from . import contract
from .envfile import BrokerSettings, load_env_file
from .robot import SCENARIOS, MockRobot

TICK_S = 0.05


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mock alarm robot for testing the hub side.")
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="catch",
        help="; ".join(f"{name}: {s.description}" for name, s in sorted(SCENARIOS.items())),
    )
    parser.add_argument(
        "--catch-after",
        type=float,
        metavar="SECONDS",
        help="Override how long the chase lasts before the robot reports 'caught'.",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".env",
        help="Settings file (default: tools/mock-robot/.env).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(args.env)
    settings = BrokerSettings.from_env()

    scenario = SCENARIOS[args.scenario]
    if args.catch_after is not None:
        scenario = dataclasses.replace(scenario, catch_after_s=args.catch_after)
    robot = MockRobot(scenario, boot_time=time.time())
    # The MQTT library calls back on its own thread while the loop below ticks the
    # robot on this one. The lock makes sure only one of them touches the robot at
    # a time.
    lock = threading.Lock()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="alarmbot-mock")
    client.username_pw_set(settings.username, settings.password)
    # The Last Will: the broker publishes this for us if the connection dies.
    will = contract.offline()
    client.will_set(will.topic, will.encode(), qos=will.qos, retain=will.retain)

    def publish(messages: list[contract.Message]) -> None:
        for message in messages:
            client.publish(message.topic, message.encode(), qos=message.qos, retain=message.retain)
            if message.topic != contract.TOPIC_TELEMETRY:
                print(f"-> {message.topic} {message.encode()}")

    def on_connect(client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any) -> None:
        if reason_code.is_failure:
            print(f"Broker refused the connection: {reason_code}")
            return
        print("Connected. Waiting for the hub to start an alarm.")
        for topic in contract.SUBSCRIPTIONS:
            client.subscribe(topic, qos=1)
        with lock:
            publish(robot.on_connect(time.time()))

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            print(f"<- {message.topic} (not JSON, ignored)")
            return
        print(f"<- {message.topic} {json.dumps(payload)}")
        if isinstance(payload, dict):
            with lock:
                publish(robot.on_message(message.topic, payload, time.time()))

    client.on_connect = on_connect
    client.on_message = on_message

    print(f"Scenario: {scenario.name}. {scenario.description}")
    client.connect(settings.host, settings.port, keepalive=30)
    client.loop_start()
    try:
        while not robot.wants_disconnect:
            with lock:
                publish(robot.tick(time.time()))
            time.sleep(TICK_S)
        # A real robot that loses power says nothing; the broker notices after
        # the keepalive runs out and sends the Last Will. To keep the test
        # short, the mock sends the same message itself and leaves.
        print("Scenario: dropping off the network now.")
        publish([contract.offline()])
        time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping.")
        publish([contract.offline()])
        time.sleep(0.5)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
