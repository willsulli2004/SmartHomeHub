# M06c — Robot navigation
Status: in progress   Branch: `milestone/M06c-robot-navigation`   PR: (added when the PR is opened)

## Goal
The robot runs away with purpose instead of wandering: it gets away from where it started (beside the
bed), does not circle back over where it has been, and moves away from the person chasing it.

Asked for by Will on November 28th, 2026 after the first floor runs. The M6b firmware avoided walls
and objects but drifted in slow circles, because it only steered away from whichever side was
nearer.

It is built in three stages, each one upload over Wi-Fi and tested before the next:

| Stage | What | State |
|---|---|---|
| A | See what the robot sees: scan streaming, a browser viewer, position tracking, a LiDAR test | built, not yet run on the robot |
| B | Steer for the best gap, away from the start and from where it has been; faster | not started |
| C | Find and avoid the person | not started; needs recordings from stage A |

This doc covers stage A. It will grow with B and C.

## What was built (stage A)
**Firmware** (`firmware/robot/AlarmBot/`):
- `sensors.h`, `sensors.cpp` — changed. The LiDAR keeps each rotation as 72 slices of 5°, the closest
  thing in each. The IMU reports how fast the robot is turning on the floor, and measures the gyro's
  resting offset whenever it learns "level".
- `pose.h`, `pose.cpp` — new. Where the robot is and which way it faces, relative to where the chase
  (or LiDAR test) started: distance from the encoders, turning from the gyro.
- `drive.h`, `drive.cpp` — changed. Reports forward movement since last asked, for the position
  tracking. It reads the encoders directly, so it also works when the robot is pushed by hand.
- `AlarmBot.ino` — changed. Publishes each scan with the robot's position on `alarmbot/scan`, about
  three times a second while the LiDAR runs. New commands `scan on` and `scan off`: a LiDAR test with
  the motors off, which ends by itself after 10 minutes.
- `net.cpp` — changed. Room for the larger scan message.
- `config.h` — changed by Will: `INVERT_MOTOR_R = true` and `LIDAR_FRONT_OFFSET_DEG = 90`, his bench
  values, committed on their own.

**PC tools** (`firmware/robot/`):
- `viewer.py` — new. Listens to the robot on the broker and serves one page, on this PC only, that
  draws the scans live. `--record FILE` saves every message; `--demo` shows a made-up robot with no
  robot or broker.
- `viewer.html` — new. The page: Robot view and Room view, range buttons, the nearest thing, the
  robot's position and log, and buttons for LiDAR on/off, stop and start. No libraries, nothing loaded
  from the internet.
- `robot.py` — changed. The `view` command.
- `tests_pc/test_robot_tools.py` — new. 17 checks of the settings handling and the viewer.

**Docs:**
- `firmware/robot/README.md` — changed. "Seeing what the robot sees" and an eight-step LiDAR test.
- `docs/robot-integration.md` — changed. The `alarmbot/scan` development topic.
- `docs/MILESTONES.md` — changed. An M6c row and section.
- `pytest.ini` — changed. Runs the new tests.

## How it connects to the rest of the project
- **Uses M6b:** the firmware, the Wi-Fi console and the update-over-Wi-Fi routine.
- **The hub is not involved.** `alarmbot/scan` is a development topic; Home Assistant and the
  analytics service ignore it.
- **For stages B and C:** the slices are what the steering will read, the position is what "away
  from the start" is measured against, and the recordings are what the person detection is tuned on.

## How to deploy
PowerShell, in the repo folder. Nothing on the hub or Home Assistant changes.

    git fetch
    git checkout milestone/M06c-robot-navigation
    .\.venv\Scripts\python.exe firmware/robot/robot.py ota
    .\.venv\Scripts\python.exe firmware/robot/robot.py view

Roll back: `git checkout milestone/M06b-robot-firmware` and run the `ota` command again.

## How to test (stage A)
Claude cannot see the robot. Pass criteria are in bold.

**1. The page, with no robot.** `robot.py view --demo`. **Pass: a page opens showing a rectangular
room with a box in it and a green triangle driving a slow circle; Robot and Room views both work.**

**2. Scans arrive.** `robot.py view`, press **LiDAR on**. **Pass: the LiDAR spins up, dots appear
within about 3 seconds and refresh about three times a second; the motors stay off.**

**3 to 8. The LiDAR test** in `firmware/robot/README.md`: front, right, left and back, distance, own
body, turning, and moving. **Pass: each step as written there.** Steps 7 and 8 also prove the
position tracking that stage B depends on.

**9. A chase still works.** Start one from the hub and pick the robot up. **Pass: it behaves as in
M6b, the alarm stops about a second after the lift, and the page shows the scans during the chase.**

**10. A recording for stage C.** `robot.py view --record walk.jsonl`, **LiDAR on**, robot still on
the floor. Walk a slow lap around it at 1 to 2 metres, walk towards it and away twice, then stand
still for 10 seconds. **Pass: `walk.jsonl` exists in the repo folder and has grown.** Tell Claude;
the file stays on this PC.

Checks Claude ran:
- `robot.py compile --example`: no errors or warnings, 37% of the app slot.
- `pytest`: 254 passed (17 new).
- The page was opened in a browser in `--demo` mode: Robot view and Room view both draw the made-up
  room correctly as the made-up robot moves and turns, which checks the page's geometry.
- Not run: anything on the robot. The firmware's turn direction and position tracking are unproven
  until steps 7 and 8.

## Deviations from the plan
- **Position tracking was built in stage A** instead of B, because the viewer's Room view and the
  LiDAR test need it. It only measures; it does not change how the robot drives.
- **A demo mode was added** so the page can be checked without the robot.

## Known limitations / follow-ups
- **The turn direction is a sign in the firmware that has not been checked on the robot.** If Room
  view turns the wrong way in step 7, it is a one-character fix.
- **Position drifts.** It is dead reckoning: wheel slip and gyro drift add up. It is meant for the
  minutes of a chase.
- **Distance needs the `cal` step** before step 8 means anything.
- **The scan is coarse on purpose:** 72 slices from about 400 points a rotation, to keep the Wi-Fi
  message small. Thin things between slices can be missed in the picture; the robot's own obstacle
  checks still use every point.
- **The viewer shows about 3 scans a second** of the LiDAR's 10.
- **The driving has not changed yet.** The robot still circles until stage B.
- **`alarmbot/scan` adds about 1.2 kB a second** of Wi-Fi traffic while the LiDAR runs.
