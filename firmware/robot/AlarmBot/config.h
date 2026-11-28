// Pins and tunable numbers for the alarm robot, in one place.
//
// Pins are from Will's hardware notes (November 27th, 2026) and match the test
// sketches in firmware/robot/tests/. Do not use GPIO 9, 10, 13, 14 (dead solder
// stubs), 0/3/45/46 (strapping), 19/20 (USB), 43/44 (USB-UART), 35-37 (PSRAM)
// or 48 (RGB LED).
#pragma once

#include <Arduino.h>

// ---- motor driver (TB6612FNG) ----
constexpr int PIN_PWMA = 6;   // left motor speed
constexpr int PIN_AIN2 = 7;
constexpr int PIN_AIN1 = 15;
constexpr int PIN_STBY = 16;  // HIGH enables the driver; 10k pulldown keeps it off at boot
constexpr int PIN_BIN1 = 17;
constexpr int PIN_BIN2 = 18;
constexpr int PIN_PWMB = 8;   // right motor speed

// ---- wheel encoders ----
constexpr int PIN_ENC_L_A = 41;
constexpr int PIN_ENC_L_B = 42;
constexpr int PIN_ENC_R_A = 4;
constexpr int PIN_ENC_R_B = 5;

// ---- IMU (LSM6DSOX on I2C, address 0x6A) ----
constexpr int PIN_IMU_SDA = 40;
constexpr int PIN_IMU_SCL = 39;

// ---- LiDAR (RPLIDAR C1 on Serial1) ----
constexpr int PIN_LIDAR_RX = 21;  // LiDAR TX -> ESP RX
constexpr int PIN_LIDAR_TX = 47;  // ESP TX -> LiDAR RX
constexpr int PIN_LIDAR_EN = 38;  // HIGH powers the LiDAR's 5 V buck

// ---- battery ----
constexpr int PIN_BATTERY_ADC = 1;

// Directions found in the motor test: forward gives positive counts on both wheels.
constexpr bool INVERT_MOTOR_L = false;
constexpr bool INVERT_MOTOR_R = true;
constexpr bool INVERT_ENC_L = true;
constexpr bool INVERT_ENC_R = true;

// ---- motors ----
constexpr float MOTOR_VOLTS = 6.0f;      // the motors' rating; duty is scaled so 1.0 = 6 V average
constexpr int PWM_HZ = 20000;
constexpr int PWM_BITS = 10;
// SAFETY: the fastest the chase logic may ask for, as a fraction of 6 V. Kept at
// half speed for first runs. Raise it only after the chase has been watched.
constexpr float MAX_SPEED = 0.5f;
constexpr float CRUISE_SPEED = 0.45f;    // driving straight
constexpr float TURN_SPEED = 0.40f;      // turning on the spot
constexpr float SLEW_PER_S = 2.5f;       // how fast a command may change, so the body stays level

// Stall: power is on but a wheel is not turning. The motors can draw more than the
// driver's 1.2 A continuous rating when stalled, so cut power quickly.
constexpr float STALL_MIN_COMMAND = 0.25f;
constexpr int STALL_MIN_COUNTS = 5;      // fewer counts than this in the window = not turning
constexpr uint32_t STALL_WINDOW_MS = 300;
constexpr int STALL_LIMIT = 6;           // this many stalls in one chase ends it with an error

// Encoder counts per metre driven. 44 counts per motor turn x gear ratio / wheel
// circumference. The gear ratio is not confirmed, so this is a guess (1:34 gearbox,
// 65 mm wheel). The "cal" serial command measures the real value and saves it.
constexpr float DEFAULT_COUNTS_PER_METER = 7330.0f;

// ---- battery (2S Li-ion: 8.4 V full) ----
constexpr float BATTERY_DIVIDER = 132.0f / 32.0f;  // 100k over 32k
constexpr float BATTERY_CUTOFF_V = 6.4f;           // do not run the motors at or below this

// ---- lift detection (how the robot knows it has been caught) ----
// The robot learns which way is down while standing still, then watches how far
// it has tilted from that. Tuned on the real robot with the "status" command.
constexpr float LIFT_TILT_DEG = 25.0f;      // tilted this far = off the ground
constexpr float LIFT_RELEASE_DEG = 15.0f;   // back under this = on the ground again
constexpr uint32_t LIFT_BEGIN_MS = 200;     // tilted this long before the motors stop
constexpr uint32_t LIFT_CAUGHT_MS = 1200;   // held this long = caught

// ---- LiDAR ----
// Which LiDAR angle points straight ahead on the robot, and which way its angles
// run. Both are "TBD after mounting" in the hardware notes; measure and set them.
constexpr float LIDAR_FRONT_OFFSET_DEG = 90.0f;
constexpr bool LIDAR_ANGLES_CLOCKWISE = true;
constexpr float LIDAR_MIN_VALID_MM = 150.0f;   // closer returns are the robot's own shell
constexpr float OBSTACLE_STOP_MM = 350.0f;     // something this close ahead: turn away
constexpr float OBSTACLE_SLOW_MM = 700.0f;     // start steering away from this distance
constexpr uint32_t LIDAR_WARMUP_MS = 2000;     // wait after power-on before sending commands
constexpr uint32_t LIDAR_STALE_MS = 600;       // no full rotation for this long = no LiDAR data

// ---- chase ----
constexpr uint32_t CHASE_MAX_MS = 15UL * 60UL * 1000UL;   // give up after 15 minutes with no stop
constexpr uint32_t CAUGHT_RESEND_MS = 5000;               // send "caught" again if no stop arrives
constexpr int CAUGHT_SENDS = 3;
constexpr uint32_t CAUGHT_GIVE_UP_MS = 30000;             // back to idle if the hub never answers

// ---- telemetry ----
constexpr uint32_t TELEMETRY_FLEEING_MS = 200;    // 5 a second during a chase
constexpr uint32_t TELEMETRY_IDLE_MS = 10000;     // one every 10 seconds otherwise

// ---- network ----
constexpr char ROBOT_HOSTNAME[] = "alarmbot";     // mDNS name (alarmbot.local) and MQTT client id
constexpr int MQTT_KEEPALIVE_S = 15;
