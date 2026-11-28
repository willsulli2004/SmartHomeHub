#include "console.h"

#include "net.h"

Console console;

size_t Console::write(uint8_t c) {
  Serial.write(c);
  if (c == '\n') {
    if (length_ > 0) {
      line_[length_] = '\0';
      // QoS 0, not retained: a log line is not worth keeping if nobody is
      // listening, and net::publish drops it when the broker is not connected.
      net::publish("alarmbot/log", line_, 0, false);
    }
    length_ = 0;
  } else if (c != '\r' && length_ + 1 < sizeof(line_)) {
    line_[length_++] = static_cast<char>(c);
  }
  return 1;
}

size_t Console::write(const uint8_t *buffer, size_t size) {
  for (size_t i = 0; i < size; i++) write(buffer[i]);
  return size;
}
