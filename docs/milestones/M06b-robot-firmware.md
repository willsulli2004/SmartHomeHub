# M06b — Robot firmware
Status: in review   Branch: `milestone/M06b-robot-firmware`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/10

## Goal
The real alarm robot connects to the hub's broker and runs the alarm → chase → caught → stop cycle,
with its firmware in this repo so it has the same git history and update-over-Wi-Fi routine as the
hub.

This milestone was added on November 27th, 2026. M6 planned the robot's firmware as someone else's
work; when Will had the robot ready with no networking code, he asked for it to be written here.

## What was built
**Firmware** (`firmware/robot/AlarmBot/`, new):
- `AlarmBot.ino` — the state machine (`idle`, `fleeing`, `caught`, `error`), the messages it sends,
  how it reacts to the hub's, lift detection, and a serial console.
- `config.h` — every pin and tunable number, each with a comment.
- `net.h`, `net.cpp` — Wi-Fi, the clock, MQTT with the client built into the ESP32 package, the Last
  Will, and updates over Wi-Fi.
- `drive.h`, `drive.cpp` — motors, encoders, odometry, the speed ramp and the stall check. The
  encoder decoding and motor scaling come from Will's test sketches.
- `sensors.h`, `sensors.cpp` — smoothed battery voltage, tilt from the IMU, and the LiDAR (power
  sequencing and the parser from Will's LiDAR test).
- `chase.h`, `chase.cpp` — the driving decisions: cruise, turn away from what is close, back out of a
  stall, and a slow fallback with no LiDAR.

**Build tool:**
- `firmware/robot/robot.py` — new. `compile`, `usb`, `ota` and `monitor`, using the `arduino-cli`
  that comes with the Arduino IDE. Writes `AlarmBot/secrets.h` from `.env` before each build.
- `firmware/robot/.env.example` — new. The settings, with placeholder values.
- `.gitignore` — changed. Ignores the generated `secrets.h`.

**Kept for reference:**
- `firmware/robot/tests/` — new. Will's four hardware test sketches, copied from his Arduino folder
  so they are versioned with the firmware. They are unchanged.

**Docs:**
- `firmware/robot/README.md` — new. Set-up, build and upload, the serial console, the first run in
  order, tuning, and the safety behaviour.
- `docs/robot-navigation.md` — new. How the robot drives now, what is weak about it, and six steps
  to refine it.
- `docs/robot-integration.md` — changed. Points at the firmware; the skeleton is marked as
  superseded; secrets are in `.env`, not a header in the Arduino libraries folder.
- `CLAUDE.md` — changed. The robot is part of this repo; a "Robot rules" section; the compile and
  upload commands; the secrets location.
- `docs/MILESTONES.md` — changed. An M6b row and section; the robot-code decision updated.
- `docs/milestones/M06b-robot-firmware.md` — new. This doc.

No hub firmware, Home Assistant file or Python service changed.

### How it knows it is caught
The robot cannot tell a lift from a level carry, so it looks for **tilt**:
1. When a chase starts it is standing still on the floor. It averages the accelerometer for a
   quarter of a second and remembers that direction as "down".
2. While running it tracks how "down" moves in its own axes, turning the estimate with the gyro and
   correcting slowly with the accelerometer. Using the gyro is what stops acceleration and cornering
   from looking like a tilt.
3. Tilted more than 25° for 0.2 s: the motors stop and telemetry says `lifted: true`.
4. Still tilted 1.2 s after the tilt began: it publishes `alarmbot/caught`.
5. Level again before that: the chase carries on.

This needs no knowledge of how the IMU is mounted. A perfectly level lift is not detected.

### How it drives
A simple reactive chase from three LiDAR readings (closest thing ahead, on the left, on the right).
`docs/robot-navigation.md` describes it and its limits. It avoids things; it does not yet flee from
the person.

### No new libraries
- MQTT is the ESP32 board package's own client (esp-mqtt). It publishes at QoS 1, which the common
  `PubSubClient` cannot.
- JSON is built with `snprintf` and read with two small functions; the contract's messages are flat.
- Updates over Wi-Fi use `ArduinoOTA`, also part of the board package.
- The only library outside the board package is "Adafruit LSM6DS", already installed for the tests.

## How it connects to the rest of the project
- **Uses M6:** the contract in `docs/robot-integration.md`, the `alarmbot` login, the Hub Robot
  entities and dashboard page, and the analytics service, which checks the lift the robot reports.
- **Replaces the mock** as the thing answering alarms. The mock stays for testing the hub side and as
  the demo fallback.
- **Architecture:** the robot is a second device beside the satellite. It talks only to the broker.
- **For M7:** the real-robot runs and failure cases start from a robot that passes this milestone's
  checklist.

## How to deploy
PowerShell, in the repo folder. Nothing on the hub or Home Assistant changes, so no backup is needed.

1. **Get the branch:**

       git fetch
       git checkout milestone/M06b-robot-firmware

2. **Settings:** copy `firmware\robot\.env.example` to `firmware\robot\.env` and fill it in
   (`firmware/robot/README.md`, "Set up").
3. **First upload, over USB.** Wheels off the ground. Replace `COM7` with the robot's port:

       .\.venv\Scripts\python.exe firmware/robot/robot.py usb COM7
       .\.venv\Scripts\python.exe firmware/robot/robot.py monitor COM7

4. **Later updates, over Wi-Fi,** with the robot on and idle:

       .\.venv\Scripts\python.exe firmware/robot/robot.py ota

Roll back: check out an earlier commit and upload again, or flash one of the sketches in
`firmware/robot/tests/` from the Arduino IDE.

## How to test
Claude cannot see the robot. Pass criteria are in bold. Stop the mock robot first. Keep the serial
monitor open, and the MQTT listener on `alarmbot/#` and `hub/alarm/#`.

**Part 1: on the bench (`firmware/robot/README.md`, "First run, in order")**

**1. Connects.** **Pass: battery voltage and `IMU: OK` print, then `[net] connected to the broker`;
Hub Robot online turns on and state reads `idle`.**

**2. Idle telemetry.** **Pass: a telemetry message every 10 seconds; Battery on the Robot page
matches a meter within about 0.2 V.**

**3. Tilt reading.** `status` on the floor, then held as in a chase. **Pass: under about 3° on the
floor and well over 25° when held.**

**4. Distance calibration.** `cal`, push one metre, `cal 1.0`. **Pass: it prints a counts-per-metre
figure and saves it; after a restart the boot message shows the same figure.**

**5. Wheels turn, off the ground.** `start`. **Pass: after about 2 seconds the wheels run forward
and the status line shows `lidar 10 Hz`; a hand in front makes them turn; `stop` stops them.**

**6. LiDAR direction.** One object straight ahead. **Pass: the status line reads `near ... @` close
to 0, and close to 90 with the object on the robot's right.** If not, set the two LiDAR direction
values in `config.h` and upload again.

**7. Lift, off the ground.** `start`, then tilt the robot. **Pass: wheels stop within a quarter of a
second, `LIFTED` shows, and about a second later the state prints `caught`.**

**8. Stall.** `start`, then hold one wheel still for a second (it is at half speed). **Pass: the
motors cut, then it backs out and turns.**

**9. On the floor.** `start` in a clear space. **Pass: it drives, turns away from walls without
hitting them, and stops when picked up.** Note anything it hits or any place it gets stuck.

**Part 2: with the hub (section 12 of `docs/robot-integration.md`, from step 5)**

**10. Hub starts it.** Press **Ring the alarm now (test)**. **Pass: the hub rings and the robot
runs; state reads `fleeing`.**

**11. Hub stops it.** Turn the hub's knob. **Pass: the robot stops at once and state reads `idle`.**

**12. Caught.** Ring again and pick the robot up. **Pass: the hub goes quiet by itself;
`hub/alarm/stop` shows reason `caught`; the Robot page shows Catch check `real`, a time to catch and
a distance.**

**13. Bump.** Ring again and knock the robot without lifting it. **Pass: no `caught` is sent.**

**14. Timeout.** Alarm timeout at 1 minute, ring and leave it. **Pass: the hub stops with reason
`timeout` and the robot stops.** Set the timeout back.

**15. Wi-Fi lost mid-chase.** Ring, then switch the Wi-Fi off for 20 seconds. **Pass: the robot
keeps running and still stops when lifted; it reconnects by itself.**

**16. Power pulled.** While idle, switch the robot off. **Pass: within about 25 seconds Hub Robot
online turns off.**

**17. Update over Wi-Fi.** Change nothing and run the `ota` command. **Pass: it uploads, the robot
restarts and reconnects.** Then start a chase and try again: **pass: the update is refused.**

Checks Claude ran:
- `robot.py compile --example`: builds with no errors or warnings. 1.16 MB, 37% of the 3 MB app slot.
- The Python tests are unchanged: 237 passed.
- Not run: anything on the robot. No line of this firmware has executed on hardware.

## Deviations from the plan
The plan Will confirmed on November 27th changed in two ways when he answered its questions:
- **The firmware lives in this repo,** not in the Arduino folder, with updates over Wi-Fi.
- **Settings are a `.env`,** not a header in the Arduino libraries folder. An Arduino sketch cannot
  read a `.env`, so `robot.py` converts it into a gitignored header at build time.

Other differences from what was proposed:
- **All three stages were written at once** (connect, chase, caught) instead of one at a time. The
  test list above keeps the staged order, and the motors only run in a chase.
- **The MQTT library the robot guide recommended is not used;** the board package's own client does
  the job with nothing to install.
- **A serial console and a local test chase** (`start` / `stop`) were added, so the driving and the
  lift can be tested before the hub is involved.
- **The hardware test sketches were copied into the repo.**
- **A navigation guide was written** at Will's request.

## Known limitations / follow-ups
- **Untested on hardware.** This is the largest risk. Expect fixes on this branch.
- **The LiDAR's direction is a placeholder** (offset 0, clockwise). Until test 6 is done, left and
  right may be swapped and "ahead" may be wrong. First floor runs should be in an open space.
- **The distance figure is a guess until calibrated** (test 4).
- **A level lift is not detected.** Tilt the robot when picking it up.
- **Tilt thresholds are untuned,** and a ramp or a hard bump could look like a lift.
- **It does not flee from the person,** only from what is near.
- **No deep sleep.** The robot stays awake, so battery life overnight is not addressed.
- **Tunable values are in `config.h`, not the app,** which is against the project's own rule. The
  navigation guide's step 6 is the plan for moving them.
- **Updates over Wi-Fi are untested,** including how `arduino-cli` passes the password.
- **The clock needs internet time servers.** Without them timestamps read 1970; nothing depends on
  them.
- **The firmware file contains the Wi-Fi and MQTT passwords.** It is built outside the repo and never
  committed, but do not share it.
- **No automated tests for the firmware.** The decision logic is tied to the hardware calls; the
  navigation guide suggests separating it so it can be tested on the PC.
