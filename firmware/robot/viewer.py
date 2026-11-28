"""A live view of what the robot's LiDAR sees, in a web browser.

Started by `robot.py view`. It listens to the robot on the MQTT broker and
serves one page on this PC only (127.0.0.1) that draws each scan as it arrives.

    robot (LiDAR) --alarmbot/scan--> broker --> this program --> browser page

Nothing here needs installing beyond paho-mqtt, which the project already uses.
The page gets its data as "server-sent events": the browser opens /events and
this program writes one line of JSON per message for as long as the page is open.

With --record FILE every message from the robot is also appended to FILE, one
JSON object per line, so a session can be studied or replayed later.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PAGE = Path(__file__).resolve().parent / "viewer.html"

# What the page may ask the robot to do. Anything else is refused, so the page
# cannot be used to send arbitrary text to the robot.
ALLOWED_COMMANDS = ("scan on", "scan off", "stop", "start", "status", "level")

TOPICS = ("alarmbot/scan", "alarmbot/state", "alarmbot/status", "alarmbot/telemetry",
          "alarmbot/log", "alarmbot/caught", "hub/alarm/#")


def to_event(topic: str, payload: bytes) -> dict[str, Any]:
    """One message from the broker as the object sent to the page.

    JSON payloads are parsed; anything else (log lines are plain text) is passed
    on as a string.
    """
    text = payload.decode("utf-8", "replace")
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        data = text
    return {"topic": topic, "data": data}


def sse(event: dict[str, Any]) -> bytes:
    """An event in the wire format browsers expect: 'data: <json>' and a blank line."""
    return b"data: " + json.dumps(event, separators=(",", ":")).encode("utf-8") + b"\n\n"


class Feed:
    """Passes every event to every open page, and to the recording if there is one."""

    def __init__(self, record: Path | None = None) -> None:
        self._listeners: list[queue.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._record = record.open("a", encoding="utf-8") if record else None

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        listener: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        with self._lock:
            self._listeners.append(listener)
        return listener

    def unsubscribe(self, listener: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            if self._record:
                self._record.write(json.dumps({"time": round(time.time(), 3), **event}) + "\n")
                self._record.flush()
            for listener in self._listeners:
                try:
                    listener.put_nowait(event)
                except queue.Full:
                    pass  # a page that has fallen behind misses this one

    def close(self) -> None:
        with self._lock:
            if self._record:
                self._record.close()
                self._record = None


def make_handler(feed: Feed, send_command):  # noqa: ANN001, ANN201 - small local factory
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:  # keep the terminal quiet
            pass

        def do_GET(self) -> None:  # noqa: N802 - name set by http.server
            if self.path in ("/", "/index.html"):
                body = PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                listener = feed.subscribe()
                try:
                    while True:
                        try:
                            self.wfile.write(sse(listener.get(timeout=10)))
                        except queue.Empty:
                            self.wfile.write(b": still here\n\n")  # keeps the connection open
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionError, OSError):
                    pass  # the page was closed
                finally:
                    feed.unsubscribe(listener)
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/command":
                self.send_error(404)
                return
            length = min(int(self.headers.get("Content-Length", "0") or 0), 100)
            command = self.rfile.read(length).decode("utf-8", "replace").strip()
            if command not in ALLOWED_COMMANDS:
                self.send_error(400, "Unknown command")
                return
            send_command(command)
            self.send_response(204)
            self.end_headers()

    return Handler


def run(values: dict[str, str], port: int = 8765, record: Path | None = None, open_browser: bool = True) -> None:
    """Connect to the broker, serve the page, and keep going until Ctrl+C."""
    import paho.mqtt.client as mqtt

    feed = Feed(record)

    # A client id of its own, so it never knocks the robot or the monitor off the broker.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"alarmbot-viewer-{port}")
    client.username_pw_set(values["MQTT_USERNAME"], values["MQTT_PASSWORD"])

    def on_connect(client, userdata, flags, reason_code, properties) -> None:  # noqa: ANN001
        if reason_code.is_failure:
            print(f"Broker refused the connection: {reason_code}", flush=True)
            return
        print("Connected to the broker.", flush=True)
        for topic in TOPICS:
            client.subscribe(topic, qos=0)

    def on_message(client, userdata, message) -> None:  # noqa: ANN001
        feed.publish(to_event(message.topic, message.payload))

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(values["MQTT_HOST"], int(values["MQTT_PORT"]), keepalive=30)
    client.loop_start()

    def send_command(command: str) -> None:
        client.publish("alarmbot/command", command, qos=1, retain=False)

    # 127.0.0.1: the page is reachable from this PC only, not from the network.
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(feed, send_command))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"Viewer running at {url}  (Ctrl+C to stop)", flush=True)
    if record:
        print(f"Recording to {record}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        client.loop_stop()
        client.disconnect()
        feed.close()


# ------------------------------------------------------------------ demo ----


def demo_scan(elapsed_s: float) -> dict[str, Any]:
    """A made-up scan: a robot driving a slow circle in a 4 m by 3 m room.

    Used by `robot.py view --demo` to try the page with no robot, and by the
    tests. The room's walls are at x = -1.5 and 2.5, y = -1 and 2 (metres), with
    the start at (0, 0), and there is a box near (1.6, 1.2).
    """
    import math

    angle = elapsed_s * 0.25                      # radians around the circle
    x, y = 0.6 * math.sin(angle), 0.6 - 0.6 * math.cos(angle)
    heading = math.degrees(angle) % 360           # facing along the circle, clockwise
    if heading > 180:
        heading -= 360
    walls = (-1.5, 2.5, -1.0, 2.0)
    box = (1.4, 1.8, 1.0, 1.4)
    distances = []
    for i in range(72):
        ray = math.radians(heading + i * 5)
        dx, dy = math.sin(ray), math.cos(ray)
        best = 12.0
        for x0, x1, y0, y1 in (walls, box):
            for edge, along, lo, hi in ((x0, True, y0, y1), (x1, True, y0, y1), (y0, False, x0, x1), (y1, False, x0, x1)):
                step = (edge - x) / dx if along and dx else (edge - y) / dy if not along and dy else None
                if step is None or step <= 0.05:
                    continue
                hit = (y + step * dy) if along else (x + step * dx)
                if lo - 1e-9 <= hit <= hi + 1e-9:
                    best = min(best, step)
        distances.append(0 if best >= 12.0 else round(best * 100))
    return {"t": round(elapsed_s * 1000), "s": "idle", "x": round(x, 2), "y": round(y, 2),
            "h": round(heading), "d": distances}


def run_demo(port: int = 8765, open_browser: bool = True) -> None:
    """Serve the page with made-up scans. No robot and no broker are involved."""
    feed = Feed()

    def produce() -> None:
        started = time.time()
        feed.publish({"topic": "alarmbot/status", "data": {"state": "online"}})
        while True:
            elapsed = time.time() - started
            feed.publish({"topic": "alarmbot/scan", "data": demo_scan(elapsed)})
            if int(elapsed * 3) % 30 == 0:
                feed.publish({"topic": "alarmbot/status", "data": {"state": "online"}})
                feed.publish({"topic": "alarmbot/telemetry", "data": {"battery_v": 7.9, "pitch_deg": 0.8, "lifted": False}})
            time.sleep(1 / 3)

    threading.Thread(target=produce, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(feed, lambda command: print(f"(demo) {command}")))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"Demo viewer running at {url} with a made-up robot. Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
