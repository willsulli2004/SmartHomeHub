"""Keeps the alarm history and the settings in a small SQLite file.

SQLite is part of Python, so nothing is installed. The file lives wherever
ANALYTICS_DB points; pass ":memory:" in tests.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

SEVEN_DAYS_S = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class AlarmRecord:
    """One finished alarm."""

    alarm_id: str
    started: float  # seconds since 1970, when hub/alarm/start arrived
    stopped: float
    reason: str  # caught, user or timeout
    distance_m: float | None
    lift_ms: int | None  # how long the robot was held before it reported caught
    catch_valid: bool | None  # None when the alarm was not stopped by a catch

    @property
    def duration_s(self) -> float:
        return self.stopped - self.started


@dataclass(frozen=True)
class WeekSummary:
    """Figures over the last seven days."""

    alarms: int
    catches: int
    suspicious_catches: int
    avg_wake_delay_s: float | None
    avg_time_to_catch_s: float | None


class Store:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS alarms (
                alarm_id    TEXT PRIMARY KEY,
                started     REAL NOT NULL,
                stopped     REAL NOT NULL,
                reason      TEXT NOT NULL,
                distance_m  REAL,
                lift_ms     INTEGER,
                catch_valid INTEGER
            );
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value REAL NOT NULL
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    # ---- alarm history ----

    def add_alarm(self, record: AlarmRecord) -> None:
        """Save a finished alarm. A repeated alarm_id replaces the earlier row."""
        self._db.execute(
            "INSERT OR REPLACE INTO alarms VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                record.alarm_id,
                record.started,
                record.stopped,
                record.reason,
                record.distance_m,
                record.lift_ms,
                None if record.catch_valid is None else int(record.catch_valid),
            ),
        )
        self._db.commit()

    def last_alarm(self) -> AlarmRecord | None:
        row = self._db.execute(
            "SELECT alarm_id, started, stopped, reason, distance_m, lift_ms, catch_valid "
            "FROM alarms ORDER BY stopped DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return AlarmRecord(
            alarm_id=row[0],
            started=row[1],
            stopped=row[2],
            reason=row[3],
            distance_m=row[4],
            lift_ms=row[5],
            catch_valid=None if row[6] is None else bool(row[6]),
        )

    def week_summary(self, now: float) -> WeekSummary:
        """Counts and averages for alarms that stopped in the seven days before `now`."""
        since = now - SEVEN_DAYS_S
        alarms, avg_delay = self._db.execute(
            "SELECT COUNT(*), AVG(stopped - started) FROM alarms WHERE stopped >= ?", (since,)
        ).fetchone()
        # Time-to-catch only counts catches that looked real.
        catches, avg_catch = self._db.execute(
            "SELECT COUNT(*), AVG(stopped - started) FROM alarms "
            "WHERE stopped >= ? AND reason = 'caught' AND catch_valid = 1",
            (since,),
        ).fetchone()
        (suspicious,) = self._db.execute(
            "SELECT COUNT(*) FROM alarms WHERE stopped >= ? AND reason = 'caught' AND catch_valid = 0",
            (since,),
        ).fetchone()
        return WeekSummary(
            alarms=alarms,
            catches=catches,
            suspicious_catches=suspicious,
            avg_wake_delay_s=avg_delay,
            avg_time_to_catch_s=avg_catch,
        )

    # ---- settings ----

    def get_setting(self, key: str, default: float) -> float:
        row = self._db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return default if row is None else float(row[0])

    def set_setting(self, key: str, value: float) -> None:
        self._db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
        self._db.commit()
