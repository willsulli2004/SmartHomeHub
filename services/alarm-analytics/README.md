# Alarm analytics service

A small Python service that listens to the hub's alarm messages and the robot's reports on the MQTT
broker, works out how each wake-up went, and reports the results to Home Assistant.

It only listens and reports. Home Assistant runs the alarm and never waits for this service, so an
alarm works the same with the service stopped.

## What it works out
| Result | How |
|---|---|
| Wake-up delay | seconds from `hub/alarm/start` to `hub/alarm/stop`, whatever the reason |
| Time to catch | the same span, for alarms stopped by a catch that looked real |
| Distance | from the robot's `caught` report, or its last odometry reading |
| Catch check | `real` if the robot reported being held for at least the "Shortest real lift" (1.0 s by default) before saying caught; otherwise `suspicious`, which is what a knock looks like |
| Battery | the middle value of the last 15 readings, so the dip when the motors start raises no false warning; **low** below 6.8 V, **critical** at 6.4 V |
| 7-day figures | average wake-up delay and time to catch, and counts of alarms, real catches and suspicious catches |

The history is kept in a SQLite file, so the averages survive a restart.

## How Home Assistant gets the results
Through MQTT discovery: when the service connects it announces its entities, and Home Assistant
creates them under a device named **Hub Robot** with no typing. Entity ids come from the names, for
example `sensor.hub_robot_last_wake_up_delay`. The Robot page of the Alarms dashboard shows them.

Two settings can be changed from the app (on the Hub Robot device, or the dashboard's Robot settings
card), and are remembered:

| Setting | Default | Meaning |
|---|---|---|
| Shortest real lift | 1.0 s | how long the robot must have been held for a catch to count as real |
| Battery warning level | 6.8 V | Battery low turns on below this |

## Run it on the PC
From the repo folder, in PowerShell:

    Copy-Item services\alarm-analytics\.env.example services\alarm-analytics\.env

Fill in `MQTT_HOST` and `MQTT_PASSWORD` (the `alarm-analytics` login from M1) in the new `.env`. Then:

    cd services\alarm-analytics
    ..\..\.venv\Scripts\python.exe -m alarm_analytics

It prints a line when it connects and one for each alarm start, catch and stop. Press Ctrl+C to stop.
Run only one copy at a time: a second copy with the same login knocks the first off the broker.

## Run it on Proxmox
[docs/setup/alarm-analytics.md](../../docs/setup/alarm-analytics.md) creates a small container and
installs the service under systemd, using `deploy/alarm-analytics.service`.

## Tests

    .\.venv\Scripts\python.exe -m pytest services/alarm-analytics

- `tests/test_analytics.py`: the logic, with no broker.
- `tests/test_end_to_end.py`: whole alarms with the mock robot, through an in-memory broker.
- `tests/test_runner.py`: events arriving on the MQTT library's thread.

## Files
| File | What |
|---|---|
| `alarm_analytics/contract.py` | the topics it reads and writes |
| `alarm_analytics/analytics.py` | what it works out |
| `alarm_analytics/store.py` | the SQLite history and settings |
| `alarm_analytics/discovery.py` | the entities announced to Home Assistant |
| `alarm_analytics/runner.py` | hands broker events to the logic on one thread |
| `alarm_analytics/__main__.py` | connects the logic to the broker |
| `deploy/alarm-analytics.service` | the systemd unit for the container |
| `requirements.txt` | the one library it needs, `paho-mqtt` |
