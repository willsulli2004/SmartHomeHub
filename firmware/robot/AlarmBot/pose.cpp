#include "pose.h"

#include "drive.h"
#include "sensors.h"

namespace pose {

namespace {
float pos_x = 0, pos_y = 0;
float heading_deg = 0;
uint32_t last_us = 0;

float wrap(float degrees) {
  while (degrees > 180.0f) degrees -= 360.0f;
  while (degrees < -180.0f) degrees += 360.0f;
  return degrees;
}
}  // namespace

void reset() {
  pos_x = pos_y = 0;
  heading_deg = 0;
  drive::takeForwardMetres();  // discard movement from before the reset
  last_us = micros();
}

void update() {
  const uint32_t now_us = micros();
  const float dt = (now_us - last_us) / 1e6f;
  if (dt < 0.005f) return;  // 200 times a second is plenty
  last_us = now_us;

  // Turning: from the gyro. Readings under half a degree a second are treated
  // as standing still, so its leftover offset does not slowly spin the estimate.
  const float rate = imu::yawRateDegPerSec();
  if (fabsf(rate) > 0.5f) heading_deg = wrap(heading_deg + rate * dt);

  // Moving: from the encoders, along the direction the robot is facing.
  const float moved = drive::takeForwardMetres();
  const float heading_rad = heading_deg * PI / 180.0f;
  pos_x += moved * sinf(heading_rad);
  pos_y += moved * cosf(heading_rad);
}

float x() { return pos_x; }
float y() { return pos_y; }
float headingDeg() { return heading_deg; }
float distanceFromStart() { return sqrtf(pos_x * pos_x + pos_y * pos_y); }

float bearingToStartDeg() {
  // The start is at (0, 0). Its direction in the room frame, then relative to
  // the way the robot faces.
  const float room_deg = atan2f(-pos_x, -pos_y) * 180.0f / PI;
  return wrap(room_deg - heading_deg);
}

}  // namespace pose
