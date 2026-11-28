# Alarm robot integration guide

How the alarm robot (the Runaway Chase Bot) connects to the Smart Home Hub. It is written for whoever
writes the robot's firmware, person or agent, and assumes the robot's hardware bring-up is done: the
motors, encoders, IMU and LiDAR each work in their own test sketch, and there is no Wi-Fi, MQTT, state
machine or sleep code yet.

**The firmware now exists:** `firmware/robot/` in this repo, written against this document on
November 27th, 2026. `firmware/robot/README.md` covers building, uploading and the first run. This
guide remains the reference for what the robot must do on the broker.

This document is the contract. The hub side already follows it and is tested against a mock robot
that follows it too. If the robot needs something the contract does not give, change this document
first and tell Will, so the hub side changes with it.

Contents:
1. [The short version](#1-the-short-version)
2. [The broker and the robot's login](#2-the-broker-and-the-robots-login)
3. [Topics and messages](#3-topics-and-messages)
4. [Delivery guarantees](#4-delivery-guarantees)
5. [Online and offline](#5-online-and-offline)
6. [Connection order](#6-connection-order)
7. [The robot's states](#7-the-robots-states)
8. [Sleeping through the night](#8-sleeping-through-the-night)
9. [Filling in the telemetry](#9-filling-in-the-telemetry)
10. [Firmware skeleton](#10-firmware-skeleton)
11. [The mock robot: a working reference](#11-the-mock-robot-a-working-reference)
12. [Bring-up checklist](#12-bring-up-checklist)
13. [What changed from the robot's draft](#13-what-changed-from-the-robots-draft)

## 1. The short version

- The hub's Home Assistant decides when an alarm goes off. It publishes `hub/alarm/start` with an
  `alarm_id`.
- The robot runs away and publishes telemetry while it does.
- When the robot is picked up and held, it publishes `alarmbot/caught` with the same `alarm_id`. The
  hub stops the alarm and publishes `hub/alarm/stop` with reason `caught`.
- The alarm can also be stopped at the hub (reason `user`) or time out (reason `timeout`). The robot
  gets the same `hub/alarm/stop` and must stop running.
- The hub never waits for the robot. An alarm rings and stops the same way with the robot switched
  off.

```
Home Assistant                      broker                         robot
     |  hub/alarm/schedule (retained)  |                             |
     |-------------------------------->|---------------------------->|  on connect
     |  hub/alarm/start {alarm_id}     |                             |
     |-------------------------------->|---------------------------->|  state: fleeing
     |                                 |  alarmbot/telemetry (5/s)   |
     |                                 |<----------------------------|
     |                                 |  alarmbot/caught {alarm_id} |
     |<--------------------------------|<----------------------------|  held for 1 to 2 s
     |  hub/alarm/stop {reason:caught} |                             |
     |-------------------------------->|---------------------------->|  state: idle
```

## 2. The broker and the robot's login

- **Broker:** Mosquitto, running as an add-on inside Home Assistant on the home network. It is the
  only broker in the project. Nothing goes to a public cloud. Will confirmed on November 27th, 2026
  that the CpE417 rubric accepts this self-hosted broker as the project's "cloud" part.
- **Address and port:** the Home Assistant VM's fixed address, port 1883, plain MQTT 3.1.1. The
  address is **not written in any repo**. Will supplies it.
- **Login:** username `alarmbot`. Its password was created in M1 and is in Will's password manager.
- **Client id:** `alarmbot`. The mock robot uses `alarmbot-mock`, so the two can run side by side
  during bring-up, but only one of them should answer alarms at a time.

**Where the robot keeps these:** in `firmware/robot/.env`, which is gitignored. `robot.py` turns it
into a header (`AlarmBot/secrets.h`, also gitignored) before each build. Never put the values in a
sketch, a commit, a log line or a chat.

## 3. Topics and messages

Every payload is JSON in UTF-8. Timestamps named `ts` are ISO 8601 in UTC with a `Z`, for example
`2026-11-28T15:00:00Z`. Unknown fields must be ignored by both sides, so fields can be added later.

| Topic | From → to | QoS | Retained | When |
|---|---|---|---|---|
| `hub/alarm/schedule` | hub → robot | 1 | yes | whenever the set alarms change |
| `hub/alarm/start` | hub → robot | 1 | no | an alarm goes off |
| `hub/alarm/stop` | hub → robot | 1 | no | the alarm stops, for any reason |
| `alarmbot/status` | robot → all | 1 | yes | on connect; `offline` by Last Will |
| `alarmbot/state` | robot → all | 1 | yes | every time the robot's state changes |
| `alarmbot/telemetry` | robot → all | 0 | no | 5 a second while fleeing, one every 10 s otherwise |
| `alarmbot/caught` | robot → hub | 1 | no | the robot has been caught |

Two more topics exist for development only. The hub ignores both.

| Topic | From → to | QoS | Retained | What |
|---|---|---|---|---|
| `alarmbot/log` | robot → anyone listening | 0 | no | each line of the robot's text output, as plain text |
| `alarmbot/command` | developer → robot | 1 | no | a console command as plain text, for example `status` |

`firmware/robot/robot.py monitor` uses them to show the robot's output and send commands over
Wi-Fi. A command can start the motors (`start`), so anything with a login to the broker can make
the robot drive, which is equally true of `hub/alarm/start`.

### `hub/alarm/schedule`
The alarms that are set. Retained, so the robot receives it the moment it subscribes.

```json
{"alarms": ["07:00", "19:30"], "next_epoch": 1795618800, "next": "2026-11-28T15:00:00Z", "ts": "2026-11-27T23:00:42Z"}
```

| Field | Meaning |
|---|---|
| `alarms` | clock times in the home's time zone, soonest first. For people reading the message. |
| `next_epoch` | when the next alarm fires, in seconds since 1970 UTC. `null` if no alarm is set. **Use this one.** |
| `next` | the same moment as text. `null` if no alarm is set. |
| `ts` | when the message was published |

### `hub/alarm/start`
```json
{"alarm_id": "alarm-1795618800", "ts": "2026-11-28T15:00:00Z"}
```
`alarm_id` identifies this one alarm. Keep it; every later message about this alarm carries it.

### `hub/alarm/stop`
```json
{"alarm_id": "alarm-1795618800", "reason": "caught", "ts": "2026-11-28T15:00:21Z"}
```
`reason` is `caught` (the hub accepted the robot's report), `user` (stopped at the hub by knob, voice
or the app) or `timeout` (nobody stopped it; 10 minutes by default). Whatever the reason, the robot
stops.

### `alarmbot/status`
```json
{"state": "online"}
```
Published retained by the robot when it connects. The broker publishes `{"state": "offline"}` for the
robot when the connection is lost (section 5).

### `alarmbot/state`
```json
{"state": "fleeing", "ts": "2026-11-28T15:00:00Z", "alarm_id": "alarm-1795618800"}
```
`state` is `idle`, `fleeing`, `caught` or `error`. Include `alarm_id` in every state except `idle`.
Publish it retained on connect and on every change.

### `alarmbot/telemetry`
```json
{"alarm_id": "alarm-1795618800", "ts_ms": 734210, "state": "fleeing", "battery_v": 7.82,
 "odom_m": 3.41, "speed_mps": 0.45, "pitch_deg": 1.4, "lifted": false, "nearest_cm": 142, "bearing_deg": 175}
```

| Field | Type | Meaning |
|---|---|---|
| `alarm_id` | text or `null` | the alarm being run from; `null` when idle |
| `ts_ms` | whole number | milliseconds since the robot booted (`millis()`). The hub times the lift from this, so it must come from the robot's clock, not from when the message was sent. |
| `state` | text | the same value as `alarmbot/state` |
| `battery_v` | number | pack voltage in volts. **Required in every message.** |
| `odom_m` | number | distance driven in this chase, in metres; 0 when idle |
| `speed_mps` | number | current speed in metres per second |
| `pitch_deg` | number | body pitch in degrees |
| `lifted` | true/false | whether the robot believes it is off the ground **right now**. **Required while fleeing.** |
| `nearest_cm` | whole number or `null` | distance to the nearest LiDAR return; `null` if the LiDAR is off |
| `bearing_deg` | whole number or `null` | direction of that return, 0 = straight ahead, clockwise |

`battery_v`, `ts_ms`, `alarm_id` and `lifted` are the fields the hub side computes with. The others are
shown and recorded, and may be `null` until the robot can fill them.

### `alarmbot/caught`
```json
{"alarm_id": "alarm-1795618800", "ts": "2026-11-28T15:00:20Z", "chase_ms": 20140, "distance_m": 6.07}
```
`alarm_id` is required and must match the alarm that is ringing, or the hub ignores the message.
`chase_ms` is the time from receiving `start` to deciding it was caught; `distance_m` is the odometry
at that moment.

## 4. Delivery guarantees

- **QoS 1 topics** (everything except telemetry) are delivered at least once. A message can arrive
  twice. Both sides must cope: a second `start` for the alarm already being run from, or a second
  `stop`, changes nothing.
- **Telemetry is QoS 0.** A lost reading is simply gone. Never put something that must arrive in
  telemetry.
- **The robot must be able to publish at QoS 1.** `alarmbot/caught` is the one message that ends the
  alarm. The common `PubSubClient` library can only publish at QoS 0, so do not use it; section 10
  names a library that can.
- **`caught` and the hub's answer.** After publishing `caught`, wait for `hub/alarm/stop`. If none
  arrives in 5 seconds, publish `caught` again, up to three times. The hub ignores repeats.
- **Stale starts.** If the robot reconnects with a stored session, the broker may hand it a `start`
  from minutes ago. Ignore a `start` whose `ts` is more than 60 seconds old. Connecting with a clean
  session (the default in most libraries) avoids this entirely and is recommended.
- **Retained messages** (`schedule`, `status`, `state`) are the last value, delivered on subscribe.
  They say what is true now, not that something just happened.
- **The hub does not need the robot.** If the robot hears nothing, the alarm still stops at the hub
  or times out.

## 5. Online and offline

The robot's presence is one retained topic, `alarmbot/status`.

- **On connect,** the robot publishes `{"state": "online"}`, retained, QoS 1.
- **Before connecting,** the robot registers a Last Will: topic `alarmbot/status`, payload
  `{"state": "offline"}`, retained, QoS 1. If the robot loses power or Wi-Fi, the broker publishes it.
- **Keepalive:** 15 seconds. The broker declares the robot gone after about one and a half times the
  keepalive with no traffic, so `offline` appears within roughly 25 seconds of a failure.
- **Going to sleep on purpose:** publish `{"state": "offline"}` yourself (retained), then disconnect
  cleanly. A clean disconnect does not trigger the Last Will, so without this the app would show the
  robot online all night.

Home Assistant shows this as **Hub Robot online**. A robot that is asleep shows as offline; that is
expected.

## 6. Connection order

Do these in order, every time the robot connects, including after waking from sleep.

1. Join Wi-Fi. Give up after 20 seconds and go to step 9.
2. Get the time by NTP (`configTime(0, 0, "pool.ntp.org")` and wait until `time(nullptr)` is past
   2024). The robot needs real time for `ts` and to work out how long to sleep. Give up after 10
   seconds; without the time, do not sleep on `next_epoch` (section 8).
3. Set the Last Will (section 5) and the keepalive.
4. Connect to the broker with the client id and login from section 2.
5. Subscribe to `hub/alarm/schedule`, `hub/alarm/start` and `hub/alarm/stop` at QoS 1. Subscribing to
   `hub/alarm/#` covers all three.
6. Publish `alarmbot/status` `{"state": "online"}`, retained.
7. Publish `alarmbot/state`, retained, with the current state.
8. Start the telemetry timer.
9. If any step failed: wait, then start again from step 1. Use a growing delay (2, 4, 8, up to 60
   seconds). **Never block the control loop on a reconnect.** A chase in progress must keep running
   and keep watching for a lift while the network is down.

## 7. The robot's states

```
            start (new alarm_id, fresh ts)
   idle ----------------------------------> fleeing
     ^                                         |
     |  stop (matching alarm_id)               |  held off the ground for 1 to 2 s
     |<----------------------------------------|
     |                                         v
     |  stop (matching alarm_id),            caught
     |  or 30 s with no stop                   |
     +<----------------------------------------+

   any state --(battery at or below 6.4 V, stall, sensor fault)--> error
```

| State | The robot is | Leaves when |
|---|---|---|
| `idle` | connected, motors off, LiDAR off | a `start` arrives → `fleeing` |
| `fleeing` | running from the alarm, LiDAR on | it is lifted and held → `caught`; a matching `stop` arrives → `idle` |
| `caught` | stopped, has published `caught` | a matching `stop` arrives, or 30 seconds pass → `idle` |
| `error` | stopped, cannot run | the fault clears, or a restart |

Rules:
- **On `start`:** store the `alarm_id`, power the LiDAR, publish `state` `fleeing`, start driving.
  Ignore a `start` while already fleeing.
- **On `stop`:** if its `alarm_id` matches, brake, power the LiDAR down, publish `state` `idle`. A
  `stop` for another alarm is ignored.
- **Caught is decided on the robot.** The IMU must show a sustained lift, held for 1 to 2 seconds,
  before the robot publishes `caught`. Stop the motors as soon as the lift begins, not when it is
  confirmed, so the wheels are not spinning in someone's hands.
- **The hub double-checks the lift.** It reads `lifted` in the telemetry before `caught`. If the
  robot reported `lifted: true` for less than about 1 second, the catch is recorded as *suspicious*
  on the dashboard (a knock, not a pick-up). The alarm still stops. So send `lifted: true` in
  telemetry from the moment the lift begins, and keep sending telemetry while being held.
- **A chase ends by itself.** If no `stop` arrives, stop after 15 minutes regardless. The hub's own
  timeout is 10 minutes by default.
- **Network lost mid-chase:** keep fleeing and keep the lift detection running. When lifted, stop the
  motors anyway and publish `caught` once reconnected, if the alarm is still within its 15 minutes.
- **Battery at or below 6.4 V:** do not start a chase. Publish `state` `error` and keep sending
  telemetry so the app shows why.

## 8. Sleeping through the night

The robot's design is to deep-sleep with the LiDAR off and wake shortly before the alarm. The retained
`hub/alarm/schedule` message makes that possible without the hub knowing whether the robot is awake.

1. After connecting, the robot receives `hub/alarm/schedule` at once (it is retained).
2. If `next_epoch` is set and more than 5 minutes away: publish `offline`, disconnect, and deep-sleep
   until **3 minutes before** `next_epoch`. Cap any single sleep at 15 minutes (see below).
3. If `next_epoch` is within 5 minutes: stay awake and connected, and wait for `start`.
4. If `next_epoch` is `null`: no alarm is set. Sleep for 15 minutes, then wake and check again.

**Why the 15-minute cap.** An alarm can be set or changed while the robot is asleep, by voice or from
the app. The robot only learns of it the next time it wakes. Waking every 15 minutes means an alarm
set at least 15 minutes ahead is never missed. An alarm set for sooner than that may ring with the
robot still asleep; the hub rings regardless. Shorten the cap if that matters for the demo.

**For the demo,** a build with no sleep is the simplest reliable setup. That is what the firmware in
`firmware/robot/` does today: sleep is not built yet, and the robot stays awake and connected.

Before sleeping: brake and set the driver's STBY low, power the LiDAR down as the hardware notes
describe, and publish `offline` (section 5).

## 9. Filling in the telemetry

From the robot's hardware notes (Will's handoff of November 27th, 2026).

| Field | Source | Notes |
|---|---|---|
| `battery_v` | divider on GPIO1: `analogReadMilliVolts(1) × 132 / 32 / 1000` | Average several readings. The pack dips about 0.2 V for a moment when the motors start; the hub also smooths it, but do not send a single raw sample. |
| `odom_m` | wheel encoders | 44 counts per motor turn × the gear ratio = counts per wheel turn. Metres = counts ÷ counts per wheel turn × wheel circumference. Average the two wheels. The gear ratio is still to be confirmed. |
| `speed_mps` | change in `odom_m` over the last 200 ms | |
| `pitch_deg` | LSM6DSOX, accelerometer and gyro fused | Use fusion, not the accelerometer alone: turns add sideways acceleration. The axis mapping is set once the IMU is mounted. |
| `lifted` | LSM6DSOX | A lift shows as the body tilting well away from level and staying there, or the vertical acceleration departing from 9.8 m/s² and the wheels running free. Start with pitch or roll beyond about 20° for more than 200 ms and tune on the real robot. |
| `nearest_cm`, `bearing_deg` | RPLIDAR C1 | The closest valid return in the last rotation (distance not 0). Apply the front-angle offset once it is measured, and skip arcs blocked by the shell. |

Battery levels for a 2S Li-ion pack: full 8.4 V, warn at 6.8 V, stop at 6.4 V. The hub's dashboard
shows **Battery low** below 6.8 V (adjustable in the app) and **Battery critical** at 6.4 V.

Rates: 5 messages a second while `fleeing`, one every 10 seconds otherwise. At 5 a second each JSON
message is about 200 bytes, around 1 kB a second.

## 10. Firmware skeleton

**The real firmware is in `firmware/robot/AlarmBot/` and supersedes this skeleton.** It uses the MQTT
client built into the ESP32 board package (esp-mqtt), which publishes at QoS 1 and needs no extra
library, and it builds its JSON by hand, so neither library named below is used. The skeleton is
kept because it shows the contract's calls in the fewest lines. It has not been compiled or run.

**Library:** "MQTT" by Joël Gähwiler (`256dpi/arduino-mqtt` in the Arduino Library Manager). It can
publish at QoS 1, set a retained Last Will, and has a small API. Asking Will before adding it is the
rule in this project. Add "ArduinoJson" for building and reading payloads.

```cpp
#include <WiFi.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <RobotSecrets.h>   // ROBOT_WIFI_SSID, ROBOT_WIFI_PASSWORD, ROBOT_MQTT_HOST,
                            // ROBOT_MQTT_USER, ROBOT_MQTT_PASSWORD. Never committed.

enum class State { Idle, Fleeing, Caught, Error };

WiFiClient net;
MQTTClient mqtt(1024);            // room for the schedule message
State state = State::Idle;
String alarmId;                   // empty when idle
uint32_t chaseStartMs = 0;
uint32_t lastTelemetryMs = 0;
uint32_t nextReconnectMs = 0;
uint32_t reconnectDelayMs = 2000;
long nextAlarmEpoch = 0;          // 0 = no alarm set

const char *stateName() {
  switch (state) {
    case State::Fleeing: return "fleeing";
    case State::Caught:  return "caught";
    case State::Error:   return "error";
    default:             return "idle";
  }
}

String isoNow() {                 // "2026-11-28T15:00:00Z"
  time_t now = time(nullptr);
  struct tm utc;
  gmtime_r(&now, &utc);
  char text[21];
  strftime(text, sizeof(text), "%Y-%m-%dT%H:%M:%SZ", &utc);
  return String(text);
}

void publishState() {
  JsonDocument doc;
  doc["state"] = stateName();
  doc["ts"] = isoNow();
  if (state != State::Idle) doc["alarm_id"] = alarmId;
  String out;
  serializeJson(doc, out);
  mqtt.publish("alarmbot/state", out, true, 1);       // retained, QoS 1
}

void setState(State next) {
  if (next == state) return;
  state = next;
  publishState();
}

void onMessage(String &topic, String &payload) {
  JsonDocument doc;
  if (deserializeJson(doc, payload)) return;          // not JSON: ignore

  if (topic == "hub/alarm/schedule") {
    nextAlarmEpoch = doc["next_epoch"] | 0L;          // null becomes 0
  } else if (topic == "hub/alarm/start") {
    const char *id = doc["alarm_id"];
    if (!id || state == State::Fleeing) return;       // bad, or already running
    alarmId = id;
    chaseStartMs = millis();
    // Power the LiDAR here (EN high, wait 2 s), reset the odometry, then:
    setState(State::Fleeing);
  } else if (topic == "hub/alarm/stop") {
    const char *id = doc["alarm_id"];
    if (!id || alarmId != id || state == State::Idle) return;
    // Brake and power the LiDAR down here, then:
    setState(State::Idle);
    alarmId = "";
  }
}

bool connectBroker() {
  mqtt.begin(ROBOT_MQTT_HOST, 1883, net);
  mqtt.setKeepAlive(15);
  mqtt.setWill("alarmbot/status", "{\"state\":\"offline\"}", true, 1);
  mqtt.onMessage(onMessage);
  if (!mqtt.connect("alarmbot", ROBOT_MQTT_USER, ROBOT_MQTT_PASSWORD)) return false;
  mqtt.subscribe("hub/alarm/#", 1);
  mqtt.publish("alarmbot/status", "{\"state\":\"online\"}", true, 1);
  publishState();
  return true;
}

void keepConnected() {            // call every loop; never blocks for long
  if (mqtt.connected()) { mqtt.loop(); return; }
  if (millis() < nextReconnectMs) return;
  if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
  if (WiFi.status() == WL_CONNECTED && connectBroker()) {
    reconnectDelayMs = 2000;
  } else {
    nextReconnectMs = millis() + reconnectDelayMs;
    reconnectDelayMs = min<uint32_t>(reconnectDelayMs * 2, 60000);
  }
}

void publishTelemetry() {
  JsonDocument doc;
  if (state == State::Idle) doc["alarm_id"] = nullptr; else doc["alarm_id"] = alarmId;
  doc["ts_ms"] = millis();
  doc["state"] = stateName();
  doc["battery_v"] = readBatteryVolts();              // averaged; see section 9
  doc["odom_m"] = odometryMetres();
  doc["speed_mps"] = speedMetresPerSecond();
  doc["pitch_deg"] = pitchDegrees();
  doc["lifted"] = isLifted();
  // nearest_cm and bearing_deg: set them, or leave them out, when the LiDAR is off
  String out;
  serializeJson(doc, out);
  mqtt.publish("alarmbot/telemetry", out, false, 0);  // not retained, QoS 0
}

void publishCaught() {
  JsonDocument doc;
  doc["alarm_id"] = alarmId;
  doc["ts"] = isoNow();
  doc["chase_ms"] = millis() - chaseStartMs;
  doc["distance_m"] = odometryMetres();
  String out;
  serializeJson(doc, out);
  mqtt.publish("alarmbot/caught", out, false, 1);     // QoS 1: this ends the alarm
}

void setup() {
  WiFi.begin(ROBOT_WIFI_SSID, ROBOT_WIFI_PASSWORD);
  configTime(0, 0, "pool.ntp.org");                   // UTC
  // Motors, encoders, IMU and battery ADC set-up goes here.
}

void loop() {
  keepConnected();
  // 1. Read the sensors and run the drive control every loop, connected or not.
  // 2. If fleeing and the lift has been held long enough: stop the motors,
  //    publishCaught(), setState(State::Caught), and remember when, so it can be
  //    sent again after 5 s if no stop has arrived (section 4).
  // 3. Telemetry on its timer:
  uint32_t period = (state == State::Fleeing) ? 200 : 10000;
  if (mqtt.connected() && millis() - lastTelemetryMs >= period) {
    lastTelemetryMs = millis();
    publishTelemetry();
  }
}
```

`readBatteryVolts()`, `odometryMetres()`, `speedMetresPerSecond()`, `pitchDegrees()` and `isLifted()`
are the robot's own functions, built from its test sketches. The sleep logic of section 8 and the
re-send of `caught` are described above and left out of the skeleton to keep it readable.

## 11. The mock robot: a working reference

`tools/mock-robot/` in the hub repo is a Python program that follows this contract and passes the
hub's tests. When a detail here is unclear, the mock's behaviour is the answer:

- `tools/mock-robot/mock_robot/contract.py`: the topics.
- `tools/mock-robot/mock_robot/robot.py`: what is published and when, including the lift before a
  catch.
- `tools/mock-robot/README.md`: how to run it and its five scenarios.

Running the mock while listening on the broker shows exactly what the hub expects to see. Compare the
real robot's messages with it, field by field.

## 12. Bring-up checklist

Work down the list; each step relies on the ones before it. "Listen" means Home Assistant's **Settings
→ Devices & services → MQTT → Configure → Listen to a topic**, with the topic `alarmbot/#` (and
`hub/alarm/#` in a second browser tab). Stop the mock robot before testing the real one.

| # | Do | Pass when |
|---|---|---|
| 1 | Flash a build that only joins Wi-Fi and connects to the broker | `alarmbot/status` shows `{"state":"online"}`; **Hub Robot online** turns on in the app |
| 2 | Pull the robot's power | within about 25 seconds `alarmbot/status` shows `offline` and the app follows |
| 3 | Power it again | `online` again, and `alarmbot/state` shows `idle` with a sensible `ts` (NTP works) |
| 4 | Leave it idle for a minute | a telemetry message every 10 seconds with a believable `battery_v`; **Battery** appears on the Robot page of the dashboard |
| 5 | Wheels off the ground. Press **Ring the alarm now (test)** on the Alarms dashboard | the robot logs the `start`, `alarmbot/state` shows `fleeing` with the `alarm_id`, telemetry speeds up to about 5 a second, `odom_m` climbs |
| 6 | Turn the hub's knob | `hub/alarm/stop` with reason `user`; the robot brakes and `alarmbot/state` shows `idle` |
| 7 | Start again, on the floor. Pick the robot up and hold it | motors stop at once; telemetry shows `lifted: true`; after 1 to 2 seconds `alarmbot/caught` appears; the hub goes quiet and publishes `stop` with reason `caught`; the robot returns to `idle` |
| 8 | Check the dashboard's Robot page | **Stopped by** `caught`, a time to catch, a distance, and **Catch check** `real` |
| 9 | Start again and knock the robot without lifting it | no `caught` is published. If one is, the lift detection is too sensitive; the dashboard would show **Catch check** `suspicious` |
| 10 | Start again and leave it | the hub times out (set **Alarm timeout** to 1 minute for this); the robot gets `stop` with reason `timeout` and stops |
| 11 | Set an alarm in the app | `hub/alarm/schedule` updates; the robot logs the new `next_epoch` |
| 12 | Switch the Wi-Fi off mid-chase, then on | the robot keeps running and still stops when lifted; it reconnects by itself and its state is right afterwards |
| 13 | With sleep enabled, set an alarm 20 minutes ahead | the robot publishes `offline` and sleeps, wakes about 3 minutes before, shows `online`, and runs when the alarm fires |

## 13. What changed from the robot's draft

The robot's hardware notes listed draft topics. The hub side was already built and tested when they
arrived, so the hub's names are final:

| Robot's draft | Final |
|---|---|
| `alarm/schedule` | `hub/alarm/schedule` |
| `alarm/start` | `hub/alarm/start` |
| (none) | `hub/alarm/stop` |
| `alarm/caught` | `alarmbot/caught` |
| `robot/telemetry` | `alarmbot/telemetry` |
| `robot/status` | `alarmbot/status` (online/offline) and `alarmbot/state` (what it is doing) |

Other differences from the draft:
- **The broker is local,** not a cloud service.
- **"Time-to-catch" is worked out on the hub side,** from when `start` and `stop` pass the broker.
  The robot still sends its own `chase_ms` in `caught`.
- **The dashboard is Home Assistant's,** fed by the hub's alarm analytics service, not by the robot
  directly.
