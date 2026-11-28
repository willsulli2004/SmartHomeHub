// Alarm robot (Runaway Chase Bot) firmware.
//
// The robot waits for the Smart Home Hub to start an alarm, runs away, and
// reports when it has been caught. The messages it exchanges with the hub are
// defined in docs/robot-integration.md; this file is the robot's side of that
// contract and its state machine:
//
//     idle --start--> fleeing --lifted and held--> caught --stop--> idle
//                        |                                            ^
//                        +----------------stop------------------------+
//
// Files:
//   config.h    pins and every tunable number
//   net.*       Wi-Fi, clock, MQTT, updates over Wi-Fi
//   drive.*     motors, encoders, odometry, stall check
//   sensors.*   battery, tilt from the IMU, LiDAR
//   chase.*     the driving decisions while running away
//   secrets.h   generated from firmware/robot/.env by robot.py; never committed
//
// Build and upload with firmware/robot/robot.py (see firmware/robot/README.md).
//
// Serial console at 115200 baud: type "help".

#include <esp_system.h>

#include "chase.h"
#include "config.h"
#include "console.h"
#include "drive.h"
#include "net.h"
#include "sensors.h"

enum class State { Idle, Fleeing, Caught, Error };

State state = State::Idle;
char alarm_id[40] = "";            // the alarm being run from; empty when idle
const char *error_reason = "";
uint32_t chase_start_ms = 0;

// Lift detection.
bool lifted = false;               // off the ground right now (sent in telemetry)
uint32_t tilt_since_ms = 0;        // when the tilt first went over the limit; 0 = not tilted

// "caught" re-sends.
uint32_t caught_at_ms = 0;
uint32_t caught_last_send_ms = 0;
int caught_sends = 0;
uint32_t caught_chase_ms = 0;
float caught_distance_m = 0;

uint32_t last_telemetry_ms = 0;
uint32_t last_status_ms = 0;
double next_alarm_epoch = 0;       // from hub/alarm/schedule; 0 = no alarm set

// Calibration ("cal" command): counts when it started, or -1 when not running.
long cal_start_l = -1, cal_start_r = -1;

// ------------------------------------------------------------ helpers ----

const char *stateName() {
  switch (state) {
    case State::Fleeing: return "fleeing";
    case State::Caught:  return "caught";
    case State::Error:   return "error";
    default:             return "idle";
  }
}

// Find "key" in a JSON object and copy its text value. Enough for the flat
// messages in the contract; it does not handle escapes or nesting.
bool jsonText(const char *json, const char *key, char *out, size_t size) {
  char pattern[48];
  snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char *at = strstr(json, pattern);
  if (!at) return false;
  at += strlen(pattern);
  while (*at == ' ' || *at == ':') at++;
  if (*at != '"') return false;
  at++;
  size_t n = 0;
  while (*at && *at != '"' && n + 1 < size) out[n++] = *at++;
  out[n] = '\0';
  return *at == '"';
}

// Find "key" and read its number. Returns false for null or anything else.
bool jsonNumber(const char *json, const char *key, double &out) {
  char pattern[48];
  snprintf(pattern, sizeof(pattern), "\"%s\"", key);
  const char *at = strstr(json, pattern);
  if (!at) return false;
  at += strlen(pattern);
  while (*at == ' ' || *at == ':') at++;
  char *end = nullptr;
  const double value = strtod(at, &end);
  if (end == at) return false;
  out = value;
  return true;
}

// ---------------------------------------------------------- publishing ----

void publishState() {
  char ts[24], payload[160];
  net::isoNow(ts, sizeof(ts));
  if (state == State::Idle || alarm_id[0] == '\0') {
    snprintf(payload, sizeof(payload), "{\"state\":\"%s\",\"ts\":\"%s\"}", stateName(), ts);
  } else {
    snprintf(payload, sizeof(payload), "{\"state\":\"%s\",\"ts\":\"%s\",\"alarm_id\":\"%s\"}",
             stateName(), ts, alarm_id);
  }
  net::publish("alarmbot/state", payload, 1, true);
}

void publishTelemetry() {
  char id[48] = "null";
  if (state != State::Idle && alarm_id[0] != '\0') snprintf(id, sizeof(id), "\"%s\"", alarm_id);

  char nearest[16] = "null", bearing[16] = "null";
  float distance_mm, bearing_deg;
  if (lidar::nearest(distance_mm, bearing_deg)) {
    if (bearing_deg < 0) bearing_deg += 360.0f;  // the contract counts 0 to 359, clockwise
    snprintf(nearest, sizeof(nearest), "%d", (int)(distance_mm / 10.0f));
    snprintf(bearing, sizeof(bearing), "%d", (int)bearing_deg);
  }

  char payload[320];
  snprintf(payload, sizeof(payload),
           "{\"alarm_id\":%s,\"ts_ms\":%lu,\"state\":\"%s\",\"battery_v\":%.2f,\"odom_m\":%.2f,"
           "\"speed_mps\":%.2f,\"pitch_deg\":%.1f,\"lifted\":%s,\"nearest_cm\":%s,\"bearing_deg\":%s}",
           id, (unsigned long)millis(), stateName(), battery::volts(), drive::odometryMetres(),
           drive::speedMetresPerSecond(), imu::tiltDegrees(), lifted ? "true" : "false", nearest, bearing);
  net::publish("alarmbot/telemetry", payload, 0, false);
}

void publishCaught() {
  char ts[24], payload[200];
  net::isoNow(ts, sizeof(ts));
  snprintf(payload, sizeof(payload),
           "{\"alarm_id\":\"%s\",\"ts\":\"%s\",\"chase_ms\":%lu,\"distance_m\":%.2f}",
           alarm_id, ts, (unsigned long)caught_chase_ms, caught_distance_m);
  net::publish("alarmbot/caught", payload, 1, false);  // QoS 1: this is what ends the alarm
  caught_last_send_ms = millis();
  caught_sends++;
}

// -------------------------------------------------------- state changes ----

void setState(State next) {
  state = next;
  console.printf("[state] %s%s%s\n", stateName(), next == State::Error ? ": " : "",
                next == State::Error ? error_reason : "");
  publishState();
  last_telemetry_ms = 0;  // send a reading straight away in the new state
}

void stopEverything() {
  drive::sleep();
  lidar::powerOff();
  lifted = false;
  tilt_since_ms = 0;
}

void goIdle() {
  stopEverything();
  drive::resetOdometry();  // the contract reports 0 metres when idle
  setState(State::Idle);
  alarm_id[0] = '\0';
}

void fail(const char *reason) {
  stopEverything();
  error_reason = reason;
  setState(State::Error);
}

void startChase(const char *id) {
  if (state == State::Fleeing) return;  // already running from an alarm
  strlcpy(alarm_id, id, sizeof(alarm_id));
  if (battery::low()) {
    fail("battery too low to run");
    return;
  }
  console.printf("[chase] start, alarm_id %s\n", alarm_id);
  drive::resetOdometry();
  // The robot is standing still on the floor at this moment: learn "level" now.
  if (!imu::captureLevel()) console.println("[chase] WARNING: no IMU, so a lift cannot be detected");
  lidar::powerOn();
  chase::begin();
  lifted = false;
  tilt_since_ms = 0;
  chase_start_ms = millis();
  setState(State::Fleeing);
}

void reportCaught() {
  drive::sleep();
  lidar::powerOff();
  caught_chase_ms = millis() - chase_start_ms;
  caught_distance_m = drive::odometryMetres();
  caught_at_ms = millis();
  caught_sends = 0;
  // One more reading first, so the hub sees the lift right up to the catch.
  publishTelemetry();
  publishCaught();
  setState(State::Caught);
}

// ------------------------------------------------------ incoming messages ----

void handleMessage(const net::Incoming &message) {
  char id[40];
  if (strcmp(message.topic, "alarmbot/command") == 0) {
    // A console command typed into `robot.py monitor`, the same as one typed
    // over USB. The payload is the command text, for example "status".
    console.printf("> %s\n", message.payload);
    handleCommand(String(message.payload));
    return;
  }
  if (strcmp(message.topic, "hub/alarm/schedule") == 0) {
    double epoch = 0;
    next_alarm_epoch = jsonNumber(message.payload, "next_epoch", epoch) ? epoch : 0;
    console.printf("[hub] schedule: next alarm epoch %.0f\n", next_alarm_epoch);
  } else if (strcmp(message.topic, "hub/alarm/start") == 0) {
    if (jsonText(message.payload, "alarm_id", id, sizeof(id))) startChase(id);
  } else if (strcmp(message.topic, "hub/alarm/stop") == 0) {
    if (!jsonText(message.payload, "alarm_id", id, sizeof(id))) return;
    if (state == State::Idle || strcmp(id, alarm_id) != 0) return;  // not about our alarm
    char reason[16] = "?";
    jsonText(message.payload, "reason", reason, sizeof(reason));
    console.printf("[hub] stop, reason %s\n", reason);
    goIdle();
  }
}

// ----------------------------------------------------------- the chase ----

void runFleeing() {
  const uint32_t now = millis();

  if (battery::low()) {
    fail("battery reached the cut-off");
    return;
  }
  if (now - chase_start_ms > CHASE_MAX_MS) {
    console.println("[chase] no stop after 15 minutes: giving up");
    goIdle();
    return;
  }

  // Lift detection. A tilt past the limit that lasts LIFT_BEGIN_MS stops the
  // motors and counts as "lifted"; held for LIFT_CAUGHT_MS in total it is a catch.
  // Coming back level before then cancels it and the chase carries on.
  const float tilt = imu::tiltDegrees();
  if (!lifted) {
    if (tilt > LIFT_TILT_DEG) {
      if (tilt_since_ms == 0) tilt_since_ms = now;
      else if (now - tilt_since_ms >= LIFT_BEGIN_MS) {
        lifted = true;
        drive::brake();
        console.printf("[chase] lifted (tilt %.0f deg)\n", tilt);
      }
    } else {
      tilt_since_ms = 0;
    }
  } else if (tilt < LIFT_RELEASE_DEG) {
    lifted = false;
    tilt_since_ms = 0;
    console.println("[chase] put down again: carrying on");
  } else if (now - tilt_since_ms >= LIFT_CAUGHT_MS) {
    reportCaught();
    return;
  }

  if (lifted) {
    drive::brake();  // wheels stay stopped while held
  } else {
    chase::update();
    if (chase::stalls() >= STALL_LIMIT) {
      fail("wheels stalled too many times");
      return;
    }
  }
  drive::update(battery::volts());
}

void runCaught() {
  const uint32_t now = millis();
  if (now - caught_at_ms > CAUGHT_GIVE_UP_MS) {
    console.println("[chase] the hub never answered the catch: back to idle");
    goIdle();
  } else if (caught_sends < CAUGHT_SENDS && now - caught_last_send_ms > CAUGHT_RESEND_MS) {
    publishCaught();  // the hub ignores repeats
  }
}

// ------------------------------------------------------ serial console ----

void printStatus() {
  float distance_mm = 0, bearing_deg = 0;
  const bool seen = lidar::nearest(distance_mm, bearing_deg);
  console.printf(
      "%-7s wifi %d mqtt %d | batt %.2f V | tilt %4.1f deg%s | odom %.2f m %.2f m/s | lidar %2d Hz near %4.0f mm @ %4.0f | %s stalls %d\n",
      stateName(), net::wifiConnected(), net::mqttConnected(), battery::volts(), imu::tiltDegrees(),
      lifted ? " LIFTED" : "", drive::odometryMetres(), drive::speedMetresPerSecond(),
      lidar::rotationsPerSecond(), seen ? distance_mm : 0.0f, seen ? bearing_deg : 0.0f,
      state == State::Fleeing ? chase::activity() : "-", chase::stalls());
}

void printHelp() {
  console.println("Commands:");
  console.println("  status       one line of readings (also printed by itself)");
  console.println("  start        run a chase without the hub (alarm id local-test)");
  console.println("  stop         end the chase");
  console.println("  level        learn 'level' again; robot must be still on the floor");
  console.println("  cal          begin distance calibration, then push the robot a measured distance");
  console.println("  cal 1.0      finish it: the number is the distance pushed, in metres");
  console.println("  help         this list");
}

void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;
  if (line == "help") {
    printHelp();
  } else if (line == "status") {
    printStatus();
  } else if (line == "start") {
    startChase("local-test");
  } else if (line == "stop") {
    if (state != State::Idle) goIdle();
  } else if (line == "level") {
    console.println(imu::captureLevel() ? "Level learned." : "No IMU.");
  } else if (line == "cal") {
    if (state != State::Idle) {
      console.println("Calibrate while idle.");
      return;
    }
    cal_start_l = drive::rawCountLeft();
    cal_start_r = drive::rawCountRight();
    console.println("Calibration started. Push the robot straight along a measured distance, wheels");
    console.println("rolling without slipping, then type: cal <metres>   for example: cal 1.0");
  } else if (line.startsWith("cal ")) {
    const float metres = line.substring(4).toFloat();
    if (cal_start_l < 0 || metres <= 0.05f) {
      console.println("Type 'cal' first, push the robot, then 'cal <metres>'.");
      return;
    }
    const float counts = (labs(drive::rawCountLeft() - cal_start_l) + labs(drive::rawCountRight() - cal_start_r)) / 2.0f;
    cal_start_l = cal_start_r = -1;
    if (counts < 200) {
      console.printf("Only %.0f counts: the wheels did not turn enough. Nothing saved.\n", counts);
      return;
    }
    drive::setCountsPerMetre(counts / metres);
    console.printf("%.0f counts over %.2f m = %.0f counts per metre. Saved.\n", counts, metres,
                  drive::countsPerMetre());
  } else {
    console.println("Unknown command. Type 'help'.");
  }
}

void readSerial() {
  static String line;
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\n' || c == '\r') {
      handleCommand(line);
      line = "";
    } else if (line.length() < 40) {
      line += c;
    }
  }
}

const char *resetName(esp_reset_reason_t reason) {
  switch (reason) {
    case ESP_RST_POWERON:  return "power on";
    case ESP_RST_SW:       return "software (includes a Wi-Fi update)";
    case ESP_RST_PANIC:    return "CRASH";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT: return "WATCHDOG";
    default:               return "other";
  }
}

// ---------------------------------------------------------------- main ----

void setup() {
  // Outputs to a safe state before anything else: motors off, LiDAR off.
  drive::begin();
  pinMode(PIN_LIDAR_EN, OUTPUT);
  digitalWrite(PIN_LIDAR_EN, LOW);

  Serial.begin(115200);
  delay(500);
  console.printf("\nAlarmBot. Reset reason: %s\n", resetName(esp_reset_reason()));

  battery::begin();
  console.printf("Battery: %.2f V\n", battery::volts());
  console.printf("IMU: %s\n", imu::begin() ? "OK" : "NOT FOUND");
  console.printf("Counts per metre: %.0f\n", drive::countsPerMetre());

  net::begin();
  console.println("Type 'help' for commands.\n");
}

void loop() {
  const bool resting = state == State::Idle || state == State::Error;
  net::update(resting);  // a Wi-Fi update may only start while the robot is not moving
  if (net::updating()) {
    drive::sleep();
    return;
  }

  battery::update();
  imu::update();
  lidar::update();
  readSerial();

  if (net::takeConnected()) {
    // The address is what ROBOT_ADDRESS in .env needs if alarmbot.local is not found.
    console.printf("[net] connected to the broker; this robot's address is %s\n", net::address().c_str());
    net::publish("alarmbot/status", "{\"state\":\"online\"}", 1, true);
    publishState();
  }

  net::Incoming message;
  while (net::receive(message)) handleMessage(message);

  switch (state) {
    case State::Fleeing: runFleeing(); break;
    case State::Caught:  runCaught();  break;
    default: break;
  }

  const uint32_t now = millis();
  const uint32_t telemetry_period = state == State::Fleeing ? TELEMETRY_FLEEING_MS : TELEMETRY_IDLE_MS;
  if (last_telemetry_ms == 0 || now - last_telemetry_ms >= telemetry_period) {
    last_telemetry_ms = now == 0 ? 1 : now;
    publishTelemetry();
  }

  const uint32_t status_period = state == State::Fleeing ? 1000 : 10000;
  if (now - last_status_ms >= status_period) {
    last_status_ms = now;
    printStatus();
  }
}
