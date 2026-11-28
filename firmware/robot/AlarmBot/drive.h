// Motors, wheel encoders, odometry and the stall check.
#pragma once

#include <Arduino.h>

namespace drive {

// Set up the driver pins, PWM and encoder interrupts. The driver stays in standby.
void begin();

// Ask for wheel speeds, each from -1.0 (full reverse) to 1.0 (full forward).
// The request is clamped to MAX_SPEED and reached gradually (see update()).
void command(float left, float right);

// Stop now: short-brake both motors and drop any pending command.
void brake();

// Brake and put the driver in standby. Use when the robot will not move for a while.
void sleep();

// Call often (every loop). Moves the motor outputs towards the command, updates
// the odometry, and runs the stall check. `battery_volts` scales the duty so the
// motors never see more than their 6 V rating.
void update(float battery_volts);

// True once after a stall was detected and the motors were cut. Reading it clears it.
bool takeStall();

// Distance driven since resetOdometry(), in metres (both directions add up).
float odometryMetres();
float speedMetresPerSecond();
void resetOdometry();

// Raw counts since boot, forward positive, for calibration.
long rawCountLeft();
long rawCountRight();

// Counts per metre: loaded from flash at begin(), changed by the "cal" command.
float countsPerMetre();
void setCountsPerMetre(float value);

}  // namespace drive
