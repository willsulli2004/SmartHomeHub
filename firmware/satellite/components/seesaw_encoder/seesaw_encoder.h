#pragma once

#include "esphome/components/i2c/i2c.h"
#include "esphome/core/component.h"
#include "esphome/core/helpers.h"

#include <cstdint>
#include <utility>

namespace esphome::seesaw_encoder {

/// Adafruit I2C rotary encoder running the "seesaw" firmware (default address 0x36).
///
/// Only rotation is read. The encoder chip counts detents by itself; this component
/// asks it every update interval how far the knob has moved since the last ask, and
/// fires one callback per detent.
class SeesawEncoder : public PollingComponent, public i2c::I2CDevice {
 public:
  void setup() override;
  void update() override;
  void dump_config() override;

  void set_inverted(bool inverted) { this->inverted_ = inverted; }

  template<typename F> void add_on_clockwise_callback(F &&callback) {
    this->on_clockwise_callback_.add(std::forward<F>(callback));
  }
  template<typename F> void add_on_anticlockwise_callback(F &&callback) {
    this->on_anticlockwise_callback_.add(std::forward<F>(callback));
  }

 protected:
  /// Reads `len` bytes from a seesaw register. Returns false if the I2C exchange failed.
  bool read_register_(uint8_t module, uint8_t function, uint8_t *data, size_t len);
  /// Reads the detents turned since the previous read; the chip clears its count on read.
  bool read_delta_(int32_t *delta);

  bool inverted_{false};
  uint8_t consecutive_errors_{0};
  CallbackManager<void()> on_clockwise_callback_{};
  CallbackManager<void()> on_anticlockwise_callback_{};
};

}  // namespace esphome::seesaw_encoder
