// Battery voltage, tilt from the IMU, and the LiDAR.
#pragma once

#include <Arduino.h>

namespace battery {

void begin();
void update();   // call often; reads about 20 times a second and smooths
float volts();   // smoothed pack voltage
bool low();      // at or below the cut-off, steadily

}  // namespace battery

namespace imu {

// Start the LSM6DSOX. Returns false if it does not answer.
bool begin();
bool ok();

// Call every loop; reads at about 100 Hz.
void update();

// Remember the current direction of gravity as "level". Call while the robot is
// standing still on the floor. Returns false if the IMU is missing.
bool captureLevel();

// How far the robot has tilted from "level", in degrees, any direction.
float tiltDegrees();

}  // namespace imu

namespace lidar {

// Power the LiDAR up or down. Power-up takes about 2 seconds before scans
// arrive; update() handles the waiting without blocking.
void powerOn();
void powerOff();
void update();   // call every loop

// True while complete rotations are arriving.
bool scanning();

// Closest valid return in the last full rotation. `bearing_deg` is 0 straight
// ahead and increases clockwise. Returns false if there is no recent scan.
bool nearest(float &distance_mm, float &bearing_deg);

// Closest valid return in three arcs of the last rotation, in mm. A value of 0
// means nothing was seen in that arc. Front is 30 degrees either side of straight
// ahead; left and right are the 70 degrees beyond that on each side.
float frontMm();
float leftMm();
float rightMm();

int rotationsPerSecond();

}  // namespace lidar
