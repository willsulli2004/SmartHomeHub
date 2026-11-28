// How the robot runs away: the driving decisions during a chase.
//
// This is deliberately simple: drive forward, steer away from what is near, turn
// on the spot when something is close ahead, and back out when a wheel stalls.
// docs/robot-navigation.md explains it and how to make it smarter.
#pragma once

#include <Arduino.h>

namespace chase {

// Start a chase: clears the stall count and the manoeuvre in progress.
void begin();

// Decide the wheel speeds for this moment and send them to the drive. Call
// every loop while fleeing and not lifted.
void update();

// How many times the wheels have stalled in this chase.
int stalls();

// What the chase logic is doing, for the serial status line.
const char *activity();

}  // namespace chase
