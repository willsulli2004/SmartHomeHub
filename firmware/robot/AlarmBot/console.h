// The robot's text output, sent to two places at once: the USB serial port and,
// when the broker is connected, the MQTT topic alarmbot/log, one message per
// line. That is what lets `robot.py monitor` show the robot's output over Wi-Fi
// while it drives around with no cable.
//
// Use `console.printf(...)` and `console.println(...)` instead of `Serial`.
// Reading typed commands from the USB port still uses `Serial` directly;
// commands sent over Wi-Fi arrive on alarmbot/command (see AlarmBot.ino).
#pragma once

#include <Arduino.h>

class Console : public Print {
 public:
  size_t write(uint8_t c) override;
  size_t write(const uint8_t *buffer, size_t size) override;

 private:
  char line_[256];
  size_t length_ = 0;
};

extern Console console;
