#include "sensors.h"

#include <Adafruit_LSM6DSOX.h>
#include <Wire.h>

#include "config.h"

// ============================================================ battery ====

namespace battery {

namespace {
float smoothed = 0;
uint32_t last_ms = 0;
uint32_t low_since_ms = 0;

float readOnce() {
  long mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(PIN_BATTERY_ADC);
  return (mv / 8.0f) * BATTERY_DIVIDER / 1000.0f;
}
}  // namespace

void begin() {
  smoothed = readOnce();
  last_ms = millis();
}

void update() {
  const uint32_t now = millis();
  if (now - last_ms < 50) return;
  last_ms = now;
  // Slow average: the pack dips about 0.2 V for a moment when the motors start,
  // and one dip must not look like a flat battery.
  smoothed += 0.05f * (readOnce() - smoothed);
  if (smoothed > BATTERY_CUTOFF_V) low_since_ms = now;
}

float volts() { return smoothed; }

bool low() { return millis() - low_since_ms > 2000; }

}  // namespace battery

// ================================================================ imu ====

namespace imu {

namespace {
Adafruit_LSM6DSOX sensor;
bool present = false;
uint32_t last_us = 0;

// Direction of gravity in the robot's own axes, as a unit vector. "now" follows
// the robot as it tilts; "level" is what it was when standing on the floor.
float now_x = 0, now_y = 0, now_z = 1;
float level_x = 0, level_y = 0, level_z = 1;

void normalise(float &x, float &y, float &z) {
  const float length = sqrtf(x * x + y * y + z * z);
  if (length < 1e-6f) return;
  x /= length;
  y /= length;
  z /= length;
}
}  // namespace

bool begin() {
  Wire.begin(PIN_IMU_SDA, PIN_IMU_SCL);
  present = sensor.begin_I2C(0x6A, &Wire);
  if (!present) return false;
  sensor.setAccelRange(LSM6DS_ACCEL_RANGE_4_G);
  sensor.setGyroRange(LSM6DS_GYRO_RANGE_500_DPS);
  sensor.setAccelDataRate(LSM6DS_RATE_104_HZ);
  sensor.setGyroDataRate(LSM6DS_RATE_104_HZ);
  delay(50);
  captureLevel();
  last_us = micros();
  return true;
}

bool ok() { return present; }

void update() {
  if (!present) return;
  const uint32_t now_us = micros();
  if (now_us - last_us < 10000) return;  // about 100 Hz
  const float dt = (now_us - last_us) / 1e6f;
  last_us = now_us;

  sensors_event_t accel, gyro, temp;
  sensor.getEvent(&accel, &gyro, &temp);

  // 1. Turn the remembered gravity direction by how much the gyro says the robot
  //    rotated. This follows fast tilts and ignores sideways pushes, which is why
  //    accelerating or cornering does not look like a tilt.
  const float wx = gyro.gyro.x, wy = gyro.gyro.y, wz = gyro.gyro.z;  // rad/s
  const float dx = (now_y * wz - now_z * wy) * dt;
  const float dy = (now_z * wx - now_x * wz) * dt;
  const float dz = (now_x * wy - now_y * wx) * dt;
  now_x += dx;
  now_y += dy;
  now_z += dz;

  // 2. Nudge it towards what the accelerometer reads, to cancel the gyro's slow
  //    drift, but only when the reading is close to 1 g (the robot is not being
  //    shoved around).
  float ax = accel.acceleration.x, ay = accel.acceleration.y, az = accel.acceleration.z;
  const float magnitude = sqrtf(ax * ax + ay * ay + az * az);
  if (magnitude > 7.8f && magnitude < 11.8f) {
    normalise(ax, ay, az);
    const float blend = 0.02f;
    now_x += blend * (ax - now_x);
    now_y += blend * (ay - now_y);
    now_z += blend * (az - now_z);
  }
  normalise(now_x, now_y, now_z);
}

bool captureLevel() {
  if (!present) return false;
  // Average the accelerometer for about a quarter of a second.
  float sx = 0, sy = 0, sz = 0;
  for (int i = 0; i < 25; i++) {
    sensors_event_t accel, gyro, temp;
    sensor.getEvent(&accel, &gyro, &temp);
    sx += accel.acceleration.x;
    sy += accel.acceleration.y;
    sz += accel.acceleration.z;
    delay(10);
  }
  normalise(sx, sy, sz);
  level_x = now_x = sx;
  level_y = now_y = sy;
  level_z = now_z = sz;
  last_us = micros();
  return true;
}

float tiltDegrees() {
  if (!present) return 0;
  const float dot = constrain(now_x * level_x + now_y * level_y + now_z * level_z, -1.0f, 1.0f);
  return acosf(dot) * 180.0f / PI;
}

}  // namespace imu

// ============================================================== lidar ====

namespace lidar {

namespace {
enum class Power { Off, Warming, Scanning };
Power power = Power::Off;
uint32_t power_on_ms = 0;

HardwareSerial &port = Serial1;

// The rotation being received, and the last complete one.
struct Scan {
  float nearest_mm = 0, nearest_deg = 0;
  float front_mm = 0, left_mm = 0, right_mm = 0;
  int points = 0;
};
Scan building, complete;
uint32_t complete_ms = 0;
int rotations_this_second = 0, rotations_per_second = 0;
uint32_t rate_window_ms = 0;

void keepSmallest(float &slot, float value) {
  if (slot == 0 || value < slot) slot = value;
}

// A raw LiDAR angle as a bearing on the robot: 0 ahead, clockwise, -180..180.
float toBearing(float lidar_deg) {
  float bearing = lidar_deg - LIDAR_FRONT_OFFSET_DEG;
  if (!LIDAR_ANGLES_CLOCKWISE) bearing = -bearing;
  while (bearing > 180.0f) bearing -= 360.0f;
  while (bearing < -180.0f) bearing += 360.0f;
  return bearing;
}

void handleNode(const uint8_t *node) {
  const float angle = ((node[1] >> 1) | (node[2] << 7)) / 64.0f;
  const float distance = (node[3] | (node[4] << 8)) / 4.0f;

  if (node[0] & 1) {  // start of a new rotation
    complete = building;
    complete_ms = millis();
    building = Scan();
    rotations_this_second++;
  }
  if (distance < LIDAR_MIN_VALID_MM) return;  // 0 = no return; very close = our own shell

  const float bearing = toBearing(angle);
  building.points++;
  if (building.nearest_mm == 0 || distance < building.nearest_mm) {
    building.nearest_mm = distance;
    building.nearest_deg = bearing;
  }
  if (fabsf(bearing) <= 30.0f) keepSmallest(building.front_mm, distance);
  else if (bearing > 30.0f && bearing <= 100.0f) keepSmallest(building.right_mm, distance);
  else if (bearing < -30.0f && bearing >= -100.0f) keepSmallest(building.left_mm, distance);
}

void sendCommand(uint8_t command) {
  const uint8_t packet[2] = {0xA5, command};
  port.write(packet, 2);
}

void readNodes() {
  // Same framing check as the LiDAR test: the first byte's two low bits must
  // differ, and the second byte's low bit must be 1.
  static uint8_t node[5];
  static int index = 0;
  while (port.available()) {
    node[index++] = port.read();
    if (index == 1 && ((node[0] & 1) == ((node[0] >> 1) & 1))) index = 0;
    else if (index == 2 && !(node[1] & 1)) index = 0;
    else if (index == 5) {
      handleNode(node);
      index = 0;
    }
  }
}
}  // namespace

void powerOn() {
  if (power != Power::Off) return;
  pinMode(PIN_LIDAR_EN, OUTPUT);
  digitalWrite(PIN_LIDAR_EN, HIGH);
  power = Power::Warming;
  power_on_ms = millis();
  building = Scan();
  complete = Scan();
  complete_ms = 0;
}

void powerOff() {
  pinMode(PIN_LIDAR_EN, OUTPUT);
  if (power == Power::Scanning) {
    sendCommand(0x25);  // stop
    port.flush();
    port.end();
  }
  // Let go of the TX line first: left idle-high it would back-power the LiDAR
  // through its RX pin after the supply is cut.
  pinMode(PIN_LIDAR_TX, INPUT);
  digitalWrite(PIN_LIDAR_EN, LOW);
  power = Power::Off;
  complete = Scan();
  complete_ms = 0;
  rotations_per_second = 0;
}

void update() {
  const uint32_t now = millis();
  if (power == Power::Warming && now - power_on_ms >= LIDAR_WARMUP_MS) {
    port.setRxBufferSize(8192);
    port.begin(460800, SERIAL_8N1, PIN_LIDAR_RX, PIN_LIDAR_TX);
    sendCommand(0x25);  // stop anything left running
    delay(50);
    while (port.available()) port.read();
    sendCommand(0x20);  // start scanning; the reply header fails the framing check and is skipped
    power = Power::Scanning;
    rate_window_ms = now;
    rotations_this_second = 0;
  }
  if (power == Power::Scanning) {
    readNodes();
    if (now - rate_window_ms >= 1000) {
      rotations_per_second = rotations_this_second;
      rotations_this_second = 0;
      rate_window_ms = now;
    }
  }
}

bool scanning() {
  return power == Power::Scanning && complete_ms != 0 && millis() - complete_ms < LIDAR_STALE_MS;
}

bool nearest(float &distance_mm, float &bearing_deg) {
  if (!scanning() || complete.nearest_mm == 0) return false;
  distance_mm = complete.nearest_mm;
  bearing_deg = complete.nearest_deg;
  return true;
}

float frontMm() { return scanning() ? complete.front_mm : 0; }
float leftMm() { return scanning() ? complete.left_mm : 0; }
float rightMm() { return scanning() ? complete.right_mm : 0; }
int rotationsPerSecond() { return rotations_per_second; }

}  // namespace lidar
