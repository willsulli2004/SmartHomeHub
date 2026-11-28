"""Hands what arrives from the broker to the analytics on one thread.

The MQTT library calls back on its own network thread. The history database
(SQLite) may only be used from the thread that opened it, so the callbacks must
not touch the analytics directly. Instead they drop each event into a queue and
return at once; the main thread takes events out of the queue one at a time.

This also means the analytics never runs two things at once.
"""

from __future__ import annotations

import json
import queue
import time
from collections.abc import Callable
from typing import Any

from .analytics import Analytics
from .contract import Message

Publish = Callable[[list[Message]], None]

_CONNECTED = "connected"
_MESSAGE = "message"


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


class Runner:
    def __init__(self, analytics: Analytics, publish: Publish) -> None:
        self._analytics = analytics
        self._publish = publish
        self._events: queue.Queue[tuple[str, str, bytes, float]] = queue.Queue()

    # ---- called from the MQTT library's thread: only queue, never work ----

    def connected(self) -> None:
        self._events.put((_CONNECTED, "", b"", time.time()))

    def received(self, topic: str, raw: bytes) -> None:
        # The time is taken here, when the message arrived, not when it is
        # handled, so a busy moment does not stretch the measured delays.
        self._events.put((_MESSAGE, topic, raw, time.time()))

    # ---- called from the main thread ----

    def run_once(self, wait_s: float) -> None:
        """Handle everything that has arrived, waiting up to `wait_s` for the first event."""
        try:
            event = self._events.get(timeout=wait_s) if wait_s > 0 else self._events.get_nowait()
        except queue.Empty:
            event = None
        while event is not None:
            kind, topic, raw, arrived = event
            if kind == _CONNECTED:
                self._publish(self._analytics.on_connect(arrived))
            else:
                self._publish(self._analytics.on_message(topic, decode(raw), arrived))
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                event = None
        self._publish(self._analytics.tick(time.time()))
