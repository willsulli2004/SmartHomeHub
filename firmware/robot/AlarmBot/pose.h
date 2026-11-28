// Where the robot is, relative to where it was when reset() was last called.
//
// Worked out by dead reckoning: the wheel encoders say how far it moved and the
// gyro says how much it turned. Nothing outside the robot is used, so the
// estimate drifts slowly: good for the few minutes of a chase, not for hours.
//
// The frame is fixed at reset(): the robot starts at (0, 0) facing "up" the y
// axis. x is to its right as it stood then, y is ahead of it, in metres. Heading
// is in degrees, clockwise, 0 = the way it faced at the start.
#pragma once

#include <Arduino.h>

namespace pose {

void reset();    // "here, facing this way" becomes the origin
void update();   // call every loop

float x();
float y();
float headingDeg();          // -180..180, clockwise positive
float distanceFromStart();   // metres, straight line

// The direction of the starting point as seen from the robot now, as a bearing:
// 0 = straight ahead, clockwise positive, -180..180.
float bearingToStartDeg();

}  // namespace pose
