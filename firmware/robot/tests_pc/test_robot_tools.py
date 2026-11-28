"""Checks the PC-side robot tools: robot.py's settings handling and the viewer.

    .\\.venv\\Scripts\\python.exe -m pytest firmware/robot

These do not touch a robot, a broker or the Arduino tools.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROBOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROBOT_DIR))

import viewer  # noqa: E402 - needs the path set above

_spec = importlib.util.spec_from_file_location("robot_tool", ROBOT_DIR / "robot.py")
robot_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(robot_tool)


# ---- robot.py: .env -> secrets.h ----

GOOD = {
    "WIFI_SSID": "home",
    "WIFI_PASSWORD": 'p"a\\ss',
    "MQTT_HOST": "192.0.2.10",
    "MQTT_PORT": "1883",
    "MQTT_USERNAME": "alarmbot",
    "MQTT_PASSWORD": "not-a-real-password",
    "OTA_PASSWORD": "not-a-real-password-either",
}


def test_env_file_is_parsed(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\n\nWIFI_SSID=home\nMQTT_PORT = 1883 \nOTA_PASSWORD='quoted value'\nno equals sign\n", "utf-8")
    assert robot_tool.read_env(env) == {"WIFI_SSID": "home", "MQTT_PORT": "1883", "OTA_PASSWORD": "quoted value"}


def test_missing_env_file_says_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        robot_tool.read_env(tmp_path / ".env")
    assert ".env.example" in str(error.value)


def test_secrets_header_has_every_setting_and_escapes_text(tmp_path: Path) -> None:
    header = tmp_path / "secrets.h"
    robot_tool.write_secrets(GOOD, header)
    text = header.read_text("utf-8")
    assert '#define SECRET_WIFI_SSID "home"' in text
    assert '#define SECRET_WIFI_PASSWORD "p\\"a\\\\ss"' in text  # quotes and backslashes escaped for C
    assert "#define SECRET_MQTT_PORT 1883" in text
    assert "#pragma once" in text
    for key in robot_tool.TEXT_KEYS:
        assert f"#define SECRET_{key} " in text


@pytest.mark.parametrize("missing", ["WIFI_SSID", "MQTT_PASSWORD", "OTA_PASSWORD", "MQTT_PORT"])
def test_a_missing_setting_is_named(tmp_path: Path, missing: str) -> None:
    values = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(SystemExit) as error:
        robot_tool.write_secrets(values, tmp_path / "secrets.h")
    assert missing in str(error.value)


def test_port_must_be_a_number(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        robot_tool.write_secrets({**GOOD, "MQTT_PORT": "mqtt"}, tmp_path / "secrets.h")


def test_example_settings_are_complete_and_are_placeholders() -> None:
    values = robot_tool.read_env(ROBOT_DIR / ".env.example")
    assert all(values.get(key) for key in robot_tool.REQUIRED)
    assert values["MQTT_HOST"].startswith("192.0.2.")  # an address reserved for documentation
    assert "example" in values["WIFI_PASSWORD"]


def test_the_generated_header_and_env_are_gitignored() -> None:
    ignore = (ROBOT_DIR.parent.parent / ".gitignore").read_text("utf-8")
    assert "firmware/robot/AlarmBot/secrets.h" in ignore
    assert ".env" in ignore.split()


# ---- viewer ----


def test_json_messages_are_parsed_and_log_lines_stay_text() -> None:
    assert viewer.to_event("alarmbot/state", b'{"state":"idle"}') == {"topic": "alarmbot/state", "data": {"state": "idle"}}
    assert viewer.to_event("alarmbot/log", b"idle wifi 1 mqtt 1")["data"] == "idle wifi 1 mqtt 1"
    assert viewer.to_event("alarmbot/log", b"\xff")["data"] == "�"  # bad bytes do not crash it


def test_events_are_written_the_way_browsers_expect() -> None:
    wire = viewer.sse({"topic": "t", "data": {"a": 1}})
    assert wire.startswith(b"data: ") and wire.endswith(b"\n\n")
    assert json.loads(wire[6:]) == {"topic": "t", "data": {"a": 1}}


def test_feed_reaches_every_listener_and_the_recording(tmp_path: Path) -> None:
    record = tmp_path / "session.jsonl"
    feed = viewer.Feed(record)
    first, second = feed.subscribe(), feed.subscribe()
    feed.publish({"topic": "alarmbot/log", "data": "hello"})
    assert first.get_nowait()["data"] == "hello"
    assert second.get_nowait()["data"] == "hello"
    feed.unsubscribe(second)
    feed.publish({"topic": "alarmbot/log", "data": "again"})
    assert second.empty()
    feed.close()
    lines = [json.loads(line) for line in record.read_text("utf-8").splitlines()]
    assert [line["data"] for line in lines] == ["hello", "again"]
    assert all("time" in line for line in lines)


def test_a_slow_page_does_not_block_the_feed() -> None:
    feed = viewer.Feed()
    listener = feed.subscribe()
    for i in range(500):  # more than the listener's queue holds
        feed.publish({"topic": "alarmbot/log", "data": i})
    assert listener.qsize() == 200


def test_only_known_commands_can_be_sent_from_the_page() -> None:
    assert "scan on" in viewer.ALLOWED_COMMANDS and "stop" in viewer.ALLOWED_COMMANDS
    assert all(command == command.strip().lower() for command in viewer.ALLOWED_COMMANDS)


def test_demo_scan_matches_its_room() -> None:
    # At the start the made-up robot is at (0, 0) facing up the room: the walls are
    # 2 m ahead, 2.5 m to the right, 1 m behind and 1.5 m to the left.
    scan = viewer.demo_scan(0.0)
    assert len(scan["d"]) == 72
    assert (scan["d"][0], scan["d"][18], scan["d"][36], scan["d"][54]) == (200, 250, 100, 150)
    assert (scan["x"], scan["y"], scan["h"]) == (0.0, 0.0, 0)


def test_the_page_matches_the_scan_format() -> None:
    page = (ROBOT_DIR / "viewer.html").read_text("utf-8")
    assert "const SLICES = 72" in page
    assert "http://" not in page.replace("http://127.0.0.1", "") and "https://" not in page  # nothing loaded from the internet
    assert "/events" in page and "/command" in page
