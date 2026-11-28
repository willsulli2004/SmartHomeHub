# M06 — Robot link and local server
Status: in review   Branch: `milestone/M06-robot-link`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/9

## Goal
A full alarm → chase → caught → stop cycle works against a mock robot, the app shows the robot and its
wake-up history, and the robot's builder has a guide that is enough to bring a real robot online.

## What was built
**The contract and guide:**
- `docs/robot-integration.md` — new. The final MQTT contract, delivery guarantees, online/offline,
  connection order, the robot's states, sleeping until the next alarm, how to fill the telemetry
  from the robot's sensors, a firmware skeleton, and a 13-step bring-up checklist.

**Mock robot** (`tools/mock-robot/`, new):
- `mock_robot/contract.py` — the topics and message helpers.
- `mock_robot/robot.py` — the robot's behaviour with no network code, and five scenarios: `catch`,
  `never`, `bump`, `low-battery`, `offline`.
- `mock_robot/__main__.py` — connects the behaviour to the broker with the `alarmbot` login.
- `mock_robot/envfile.py` — reads the broker settings from a gitignored `.env`.
- `.env.example`, `README.md`, `conftest.py`, `tests/test_mock_robot.py` (17 checks).

**Alarm analytics service** (`services/alarm-analytics/`, new):
- `alarm_analytics/analytics.py` — works out wake-up delay, time to catch, distance, whether a catch
  looked real, and battery health.
- `alarm_analytics/store.py` — alarm history and settings in a SQLite file.
- `alarm_analytics/discovery.py` — announces 16 entities to Home Assistant under a "Hub Robot" device.
- `alarm_analytics/contract.py`, `envfile.py`, `__main__.py` — topics, settings, and the broker
  connection.
- `deploy/alarm-analytics.service` — the systemd unit for the container.
- `requirements.txt`, `.env.example`, `README.md`, `conftest.py`.
- `tests/test_analytics.py` (43 checks) and `tests/test_end_to_end.py` (8 checks: whole alarms with
  the mock robot through an in-memory broker).

**Home Assistant:**
- `homeassistant/packages/hub_robot.yaml` — new. **Hub Robot online** and **Hub Robot state** from the
  robot's own topics, and an automation that keeps the retained alarm schedule up to date.
- `homeassistant/dashboards/hub_alarms.yaml` — changed. A second page, Robot.
- `homeassistant/tests/test_robot_package.py` — new, 6 checks.
- `homeassistant/tests/test_alarm_templates.py` — changed. The dashboard check accepts the robot's
  entities.
- `homeassistant/README.md` — changed. Lists the new package.

**Project:**
- `docs/setup/alarm-analytics.md` — new. Creating the container on Proxmox and installing the service.
- `docs/setup/home-assistant.md` — changed. New section 15.
- `pytest.ini` — new. Plain `pytest` runs all three test folders and skips the legacy hardware scripts.
- `requirements-dev.txt` — changed. Adds `paho-mqtt` (approved for this milestone).
- `.gitignore` — changed. Ignores `*.db`, the service's history file.
- `CLAUDE.md` — changed. The all-tests command.
- `docs/MILESTONES.md` — M5 `merged`, M6 `in review`; the contract table, decisions and open
  questions updated.
- `docs/milestones/M05-alarms.md` — status set to `merged`.
- `docs/milestones/M06-robot-link.md` — new. This doc.

No satellite firmware changed. The running firmware stays 0.6.0 (`sat-hub-v6`).

### The cycle
1. Home Assistant fires an alarm and publishes `hub/alarm/start` with an `alarm_id` (M5).
2. The robot goes to `fleeing` and sends telemetry five times a second.
3. Picked up and held, it reports `lifted: true` in telemetry, then publishes `alarmbot/caught`.
4. Home Assistant accepts a `caught` for the alarm that is ringing, stops the hub, and publishes
   `hub/alarm/stop` with reason `caught` (M5).
5. The robot returns to `idle`.
6. The analytics service, which heard all of it, records the alarm and publishes the results. The
   Robot page updates.

### What the analytics service reports
| Result | How it is worked out |
|---|---|
| Wake-up delay | seconds from `start` to `stop`, whatever the reason |
| Time to catch | the same span, only for catches that looked real |
| Distance | the robot's `caught` report, or its last odometry |
| Catch check | `real` if the robot reported being held for at least 1.0 s before `caught`; otherwise `suspicious` |
| Battery | the middle value of the last 15 readings; **low** below 6.8 V, **critical** at 6.4 V |
| 7-day figures | average wake-up delay and time to catch; counts of alarms, real and suspicious catches |

Times are taken on the service's own clock as messages arrive, so they do not depend on the robot's
clock. The lift is timed from the robot's millisecond counter, so slow Wi-Fi does not change it.

### Settings in the app
| Setting | Default | Where |
|---|---|---|
| Shortest real lift | 1.0 s | Hub Robot device, and the Robot page |
| Battery warning level | 6.8 V | Hub Robot device, and the Robot page |

Both are remembered by the service across restarts.

### What the robot's hardware notes changed
Will's handoff of November 27th, 2026 shaped the contract:
- **Telemetry fields** match the real sensors: battery voltage, wheel odometry and speed, pitch and
  a lifted flag from the LSM6DSOX, and the nearest LiDAR return. The draft's `imu` and `dist_cm` are
  gone.
- **Battery levels** are for a 2S Li-ion pack: 8.4 V full, warn at 6.8 V, stop at 6.4 V, with
  smoothing for the 0.2 V dip on motor start.
- **A schedule topic was added.** The robot is meant to deep-sleep and wake shortly before the alarm,
  so it has to know when the next alarm is. Home Assistant now keeps a retained
  `hub/alarm/schedule`.
- **The guide starts from nothing,** because the robot has no Wi-Fi, MQTT, state machine or sleep
  code yet.

## How it connects to the rest of the project
- **Uses M1:** the Mosquitto broker and the `alarmbot` and `alarm-analytics` logins, proven here for
  the first time.
- **Uses M5:** `hub/alarm/start`, `hub/alarm/stop`, the `alarmbot/caught` handling, the alarm slots
  (for the schedule), and the Alarms dashboard.
- **Architecture:** the analytics service is layer 3, a local Python service. It talks to Home
  Assistant only through the broker, with entities created by MQTT discovery.
- **Independence:** the alarm does not depend on the robot or on the service. Robot status is defined
  in Home Assistant, not in the service, so the app shows the robot's presence with the service down.
- **For M7:** the mock's scenarios are the fallback demo and the rehearsal for the failure cases
  (robot offline, a false catch from a bump). The real-robot runs happen there.
- **For the robot's builder:** `docs/robot-integration.md` and the mock are the two things to read.

## How to deploy
Nothing is flashed. PowerShell commands run in the repo folder.

1. **Back up Home Assistant:** Settings → System → Backups → full backup named `before-M06`,
   downloaded.
2. **Get the branch and the new library:**

       git fetch
       git checkout milestone/M06-robot-link
       .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

3. **Home Assistant:** section 15.1 of `docs/setup/home-assistant.md` (copy `hub_robot.yaml`, check,
   restart).
4. **Analytics service on the PC:** "Run it on the PC" in `services/alarm-analytics/README.md`.
5. **Dashboard:** section 15.3 (re-paste `hub_alarms.yaml`).
6. **Mock robot:** `tools/mock-robot/README.md`.
7. **Container, once the above works:** `docs/setup/alarm-analytics.md`. Stop the PC copy first.

Roll back: section 15.5, or restore `before-M06`.

## How to test
Claude has no access to the broker, Home Assistant or Proxmox, so everything below is first run by
Will. Pass criteria are in bold. Keep the MQTT listener open on `hub/alarm/#` and, in a second tab,
`alarmbot/#`.

**1. All tests.** `.\.venv\Scripts\python.exe -m pytest`. **Pass: 227 passed.**

**2. Package loads.** Section 15.1. **Pass: the configuration check is valid, the two `hub_robot`
entities exist, and switching an alarm on or off publishes a new `hub/alarm/schedule`.**

**3. Service connects.** Start the analytics service on the PC. **Pass: it prints `Connected to the
broker.` and a Hub Robot device with 16 entities appears under MQTT.** This also proves the
`alarm-analytics` login from M1.

**4. Dashboard.** Section 15.3. **Pass: the Robot page shows every row with no "Entity not
available".** Most values read *unknown* until the first alarm.

**5. Mock connects.** Run the mock with `--scenario catch`. **Pass: Hub Robot online turns on, state
reads `idle`, and within about 10 seconds Battery reads 7.9 V.** This proves the `alarmbot` login.

**6. The full cycle.** Press **Ring the alarm now (test)**. **Pass: the hub rings; state reads
`fleeing`; after 15 seconds the hub goes quiet by itself; `hub/alarm/stop` shows reason `caught`; the
Robot page shows Stopped by `caught`, a wake-up delay and time to catch near 15 s, a distance near
6 m, and Catch check `real`.**

**7. Stopped at the hub.** Ring again and turn the knob after a few seconds. **Pass: the mock prints
the `stop` and goes idle; the Robot page shows Stopped by `user` and Catch check `not caught`.**

**8. False catch.** Restart the mock with `--scenario bump` and ring. **Pass: the alarm stops after
about 8 seconds, and Catch check reads `suspicious`; Suspicious catches goes up by one and Real
catches does not.**

**9. Never caught.** Set Alarm timeout to 1, restart the mock with `--scenario never`, and ring.
**Pass: after a minute the hub stops with reason `timeout` and the mock goes idle.** Set the timeout
back to 10.

**10. Low battery.** `--scenario low-battery`, ring. **Pass: Battery low turns on during the chase.**

**11. Robot offline.** `--scenario offline`, ring. **Pass: six seconds in, Hub Robot online turns
off; the hub keeps ringing; the knob stops it with reason `user`.**

**12. Robot not running at all.** Stop the mock and ring. **Pass: the alarm rings and stops by knob
exactly as in M5, and the service still records a wake-up delay.**

**13. Service not running.** Stop the analytics service, start the mock, and ring. **Pass: the full
cycle of test 6 still completes; the Hub Robot entities read unavailable, while Hub Robot online and
state still work.** Start the service again.

**14. Settings.** On the Robot page set "Shortest lift that counts as a catch" to 0.2 and repeat test
8. **Pass: the bump now reads `real`.** Set it back to 1.0.

**15. A real alarm.** With the mock running (`catch`), set an alarm by voice for two minutes ahead.
**Pass: `hub/alarm/schedule` shows it, the mock prints the schedule, and the cycle of test 6 runs
when it fires.**

**16. History.** After a few runs: **pass: the two charts on the Robot page show points, and the
7-day averages match the runs you did.**

**17. Container.** `docs/setup/alarm-analytics.md`, with the PC copy stopped. **Pass: the service is
active after a container reboot, and the 7-day figures count up from zero there** (the PC's history
file is not moved).

Checks Claude ran:
- `pytest`: 227 passed (159 Home Assistant, 17 mock robot, 51 analytics).
- Both programs start far enough to print their help text and to report missing settings by name.
- Not run: anything against a real broker, Home Assistant, Proxmox, or the robot. The firmware
  skeleton in the guide has not been compiled.

## Deviations from the plan
- **`hub/alarm/schedule` was added.** It was not in the plan Will confirmed. The robot's hardware
  notes, which arrived with the confirmation, describe a robot that sleeps until shortly before the
  alarm, and that cannot work without it. It is one automation and changes nothing else.
- **Two analytics settings are adjustable from the app** (shortest real lift, battery warning level),
  following the project rule that tunable values live in the app.
- **Entity ids for the service's entities come from their names,** not from a fixed id field, because
  the field for fixing them differs between Home Assistant versions.
- **`pytest.ini` was added** so one command runs every test.

## Known limitations / follow-ups
- **Nothing here has touched the real broker.** The two M1 logins, MQTT discovery and the Last Will
  are all first exercised by Will's tests 3 to 5.
- **MQTT discovery details are from documentation.** If the Hub Robot entities do not appear, or
  appear with different ids, the service log and the discovery payloads are where to look.
- **A catch is trusted first and checked afterwards** (Will's decision). A bump still stops the
  alarm; the dashboard says so. M7 decides whether that is acceptable for the demo.
- **The lift check needs telemetry.** A `caught` with no `lifted: true` readings before it, for
  example because Wi-Fi dropped them, is marked suspicious.
- **Wake-up delay includes alarms nobody chased.** A timeout counts as a 10-minute delay in the
  7-day average.
- **Battery "trend" is smoothing, not prediction.** It reports low once the smoothed voltage is under
  the warning level; it does not estimate time remaining.
- **Battery level in percent is a straight line** from 6.4 V to 8.4 V, which is rough for Li-ion.
- **History on the PC and in the container are separate files.**
- **The mock's `offline` scenario sends the offline message itself** instead of waiting for the
  broker to notice, to keep the test short. Stopping the mock with Ctrl+C sends it too. The broker's
  own Last Will is only exercised by cutting the network or power under a running mock or robot
  (step 2 of the guide's bring-up checklist).
- **A sleeping robot can miss an alarm set less than 15 minutes ahead** (the guide's wake interval).
  The hub rings regardless.
- **The robot's gear ratio, IMU axis mapping and LiDAR front offset are unmeasured,** so its
  odometry, pitch and bearing cannot be final yet.
- **The firmware skeleton is untested,** and its MQTT library needs Will's approval on the robot
  side.
- **Telemetry is not stored.** Only one row per alarm is kept.
