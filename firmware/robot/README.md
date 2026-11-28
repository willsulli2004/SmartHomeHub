# Alarm robot firmware

Firmware for the alarm robot (the Runaway Chase Bot): an ESP32-S3 that waits for the hub to start an
alarm, runs away, and reports when it has been caught. It follows the contract in
[docs/robot-integration.md](../../docs/robot-integration.md).

**This firmware has been compiled but never run on the robot.** Every behaviour below is untested
until the bring-up steps have been done. Do the first chase with the wheels off the ground.

| Folder or file | What |
|---|---|
| `AlarmBot/` | the sketch: `AlarmBot.ino` plus `config.h`, `net`, `drive`, `sensors`, `chase` |
| `robot.py` | builds and uploads, over USB or Wi-Fi |
| `.env.example` | the settings to copy into `.env` |
| `tests/` | the hardware test sketches from bring-up, kept for re-checking a part |

## Set up (once)

PowerShell, in the repo folder.

1. Copy the settings file and fill it in:

       Copy-Item firmware\robot\.env.example firmware\robot\.env

   | Setting | Value |
   |---|---|
   | `WIFI_SSID`, `WIFI_PASSWORD` | your Wi-Fi. It must be a 2.4 GHz network. |
   | `MQTT_HOST` | the Home Assistant VM's address, as in the mock robot's `.env` |
   | `MQTT_PASSWORD` | the `alarmbot` password |
   | `OTA_PASSWORD` | make up a long one and save it in your password manager |

   `.env` is gitignored. `robot.py` turns it into `AlarmBot/secrets.h` before each build; that file
   is gitignored too. Never commit either, and do not share a built firmware file: the passwords are
   inside it.

2. The tools are already on this PC: the Arduino IDE (its `arduino-cli` is what `robot.py` runs), the
   ESP32 board package 3.x, and the "Adafruit LSM6DS" library. Nothing else is needed. MQTT uses the
   client built into the ESP32 package.

## Build and upload

| Command | Does |
|---|---|
| `.\.venv\Scripts\python.exe firmware/robot/robot.py compile` | builds only, to check the code |
| `.\.venv\Scripts\python.exe firmware/robot/robot.py usb COM7` | builds and uploads over the USB cable |
| `.\.venv\Scripts\python.exe firmware/robot/robot.py ota` | builds and uploads over Wi-Fi |
| `.\.venv\Scripts\python.exe firmware/robot/robot.py monitor COM7` | shows the robot's output over the USB cable |
| `.\.venv\Scripts\python.exe firmware/robot/robot.py monitor` | shows the robot's output over Wi-Fi, and sends it what you type |

Replace `COM7` with the robot's port (Device Manager → Ports, with the cable in).

- **The first upload must be over USB.** After that the robot accepts updates over Wi-Fi.
- **Wi-Fi updates** need the robot switched on, connected, and **not in a chase**: it refuses updates
  while moving. It restarts by itself when the update finishes. If `alarmbot.local` is not found, put
  the robot's IP address in `ROBOT_ADDRESS` in `.env`.
- **Roll back** by checking out an older commit and uploading again. If a bad build stops the robot
  joining Wi-Fi, upload over USB.

The sketch also opens in the Arduino IDE (open `AlarmBot/AlarmBot.ino`), as long as `robot.py compile`
has been run once so that `secrets.h` exists. Board: **ESP32S3 Dev Module**, Flash Size 16MB, PSRAM
OPI, Partition Scheme "16M Flash (3MB APP/9.9MB FATFS)".

## Console

The robot's text output and its commands work two ways:

- **Over USB,** at 115200 baud: `robot.py monitor COM7`.
- **Over Wi-Fi,** with no cable: `robot.py monitor`. The robot copies every line it prints to the
  MQTT topic `alarmbot/log` and obeys commands sent to `alarmbot/command`; the monitor connects to
  the broker with the settings in `.env`. It also shows the alarm messages passing between the hub
  and the robot. Type a command and press Enter to send it; Ctrl+C leaves.

Over Wi-Fi you only see lines printed while the robot is connected to the broker, so the boot
messages and anything printed while Wi-Fi is down appear only over USB. **`start` typed into the
Wi-Fi monitor makes the robot drive,** the same as over USB.

A status line prints by itself every 10 seconds, and every second during a chase:

    fleeing wifi 1 mqtt 1 | batt 7.82 V | tilt  1.4 deg | odom 3.41 m 0.45 m/s | lidar 10 Hz near 1420 mm @  175 | cruise stalls 0

| Command | Does |
|---|---|
| `status` | prints that line now |
| `start` | runs a chase without the hub (alarm id `local-test`) |
| `stop` | ends the chase |
| `level` | learns "level" again; the robot must be still on the floor |
| `cal`, then `cal 1.0` | distance calibration (below) |
| `help` | lists these |

## First run, in order

Each step relies on the ones before. Stop the mock robot first; only one robot may answer alarms.
Keep the MQTT listener open on `alarmbot/#` (Home Assistant → Settings → Devices & services → MQTT →
Configure).

1. **Upload over USB and open the monitor.** Pass: it prints the battery voltage, `IMU: OK`, then
   `[net] connected to the broker`. In the app, **Hub Robot online** turns on and the state reads
   `idle`. If it never connects, check `.env`; the status line shows `wifi 0` or `mqtt 0`.
2. **Leave it for a minute.** Pass: a telemetry message every 10 seconds, and **Battery** on the
   dashboard's Robot page matches a meter.
3. **Tilt check, motors never on.** Type `status` with the robot on the floor: tilt should read
   under about 3°. Pick it up the way you would in a chase and type `status` again: it should read
   well over 25°. If it does not, change `LIFT_TILT_DEG` in `config.h`.
4. **Calibrate distance.** Type `cal`, push the robot exactly one metre along the floor with the
   wheels rolling, then type `cal 1.0`. It saves the result; it survives restarts and updates.
5. **Wheels off the ground,** type `start`. Pass: after about 2 seconds for the LiDAR, the wheels
   turn forward, and the status line shows `lidar 10 Hz`. Hold a hand in front: the wheels change to
   a turn. Type `stop`.
   - If the wheels turn the wrong way for an obstacle on one side, the LiDAR's direction settings
     are wrong: see "LiDAR direction" below.
6. **Still off the ground,** `start` again and tilt the robot. Pass: the wheels stop within a
   quarter of a second, the status line shows `LIFTED`, and about a second later it prints the state
   `caught`. With no hub alarm running, it returns to idle after 30 seconds.
7. **On the floor, in a clear space,** `start`. Be ready to pick it up. Pass: it drives, avoids
   walls, and stops when lifted.
8. **With the hub:** follow the bring-up checklist in section 12 of the robot guide from step 5.

## Tuning

Everything tunable is in `AlarmBot/config.h`, with a comment on each value.

- **Speed.** `MAX_SPEED` is a hard cap at half speed for first runs. `CRUISE_SPEED` and `TURN_SPEED`
  must stay at or under it.
- **Lift detection.** `LIFT_TILT_DEG` (25°), `LIFT_BEGIN_MS` (200 ms before the motors stop) and
  `LIFT_CAUGHT_MS` (1.2 s held = caught). If bumps or ramps trigger it, raise the angle. If pick-ups
  are missed, lower it. The robot only sees tilt, so a perfectly level lift is not detected.
- **LiDAR direction.** `LIDAR_FRONT_OFFSET_DEG` is the LiDAR angle that points straight ahead, and
  `LIDAR_ANGLES_CLOCKWISE` says which way its angles run. To measure: put one object straight ahead
  of the robot with nothing else near, run `start` with the wheels off the ground, and read
  `near ... @ N` on the status line. It should say about 0. If it says 90, set the offset to 90. Then
  move the object to the robot's right: it should read about 90, and if it reads about 270 (or −90),
  flip `LIDAR_ANGLES_CLOCKWISE`.
- **Obstacle distances.** `OBSTACLE_STOP_MM` (turn away) and `OBSTACLE_SLOW_MM` (start steering).
- **Shell.** `LIDAR_MIN_VALID_MM` ignores returns closer than 15 cm, which are the robot's own body.

These are in the firmware, not in the app, for now. Moving the ones worth tuning live (speed, lift
angle) into Home Assistant is a follow-up; see [docs/robot-navigation.md](../../docs/robot-navigation.md).

## Safety built in

- The motor driver is in standby at boot and whenever the robot is not in a chase.
- Speed is capped by `MAX_SPEED`, and duty is scaled so the motors never see more than 6 V.
- A wheel that has power but does not turn for 0.3 s cuts the motors; the robot then backs out. Six
  stalls in one chase end it with the state `error`.
- No chase starts, and a running one ends, at or below 6.4 V.
- A lift stops the motors after 0.2 s, before the catch is confirmed.
- A chase ends by itself after 15 minutes with no `stop`.
- Wi-Fi updates are refused during a chase, and the motors are held off while one is received.
- Losing Wi-Fi or the broker does not stop a chase or the lift detection; the catch is sent when the
  connection returns.

## Not built yet

- **Tuning from the app.** The numbers are in `config.h`.
- **Deep sleep** and waking before the alarm (section 8 of the robot guide). The robot stays awake.
- **Following or fleeing from a person** specifically. It avoids whatever is near.
- **Touch pads** on GPIO2.
