#include "seesaw_encoder.h"

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

namespace esphome::seesaw_encoder {

static const char *const TAG = "seesaw_encoder";

// Seesaw register map. A register is addressed by a module byte and a function byte.
static constexpr uint8_t MODULE_STATUS = 0x00;
static constexpr uint8_t STATUS_HW_ID = 0x01;
static constexpr uint8_t MODULE_ENCODER = 0x11;
static constexpr uint8_t ENCODER_DELTA = 0x40;

// The seesaw chip needs a short pause between receiving a register address and
// being ready to send the answer. Adafruit's library waits 250 us.
static constexpr uint32_t READ_DELAY_US = 300;

// Detents handled per update. A fast spin between two 20 ms polls is a handful of
// detents; anything far larger is a corrupt read and is clamped.
static constexpr int32_t MAX_STEPS_PER_UPDATE = 12;

// Failed reads in a row before a warning is logged (about one second at 20 ms).
static constexpr uint8_t ERROR_LOG_THRESHOLD = 50;

void SeesawEncoder::setup() {
  uint8_t hardware_id = 0;
  if (!this->read_register_(MODULE_STATUS, STATUS_HW_ID, &hardware_id, 1)) {
    ESP_LOGE(TAG, "No answer from the encoder; check SDA, SCL, 3V and GND");
    this->mark_failed();
    return;
  }
  ESP_LOGD(TAG, "Found seesaw chip, hardware id 0x%02X", hardware_id);

  // Throw away any turns made before start-up so they do not move the volume.
  int32_t discarded = 0;
  this->read_delta_(&discarded);
}

void SeesawEncoder::update() {
  int32_t delta = 0;
  if (!this->read_delta_(&delta)) {
    if (this->consecutive_errors_ < UINT8_MAX)
      this->consecutive_errors_++;
    if (this->consecutive_errors_ == ERROR_LOG_THRESHOLD) {
      ESP_LOGW(TAG, "Encoder has stopped answering");
      this->status_set_warning();
    }
    return;
  }
  if (this->consecutive_errors_ >= ERROR_LOG_THRESHOLD) {
    ESP_LOGI(TAG, "Encoder is answering again");
    this->status_clear_warning();
  }
  this->consecutive_errors_ = 0;

  if (delta == 0)
    return;
  if (this->inverted_)
    delta = -delta;
  if (delta > MAX_STEPS_PER_UPDATE)
    delta = MAX_STEPS_PER_UPDATE;
  if (delta < -MAX_STEPS_PER_UPDATE)
    delta = -MAX_STEPS_PER_UPDATE;

  ESP_LOGD(TAG, "Turned %+d", static_cast<int>(delta));
  for (; delta > 0; delta--)
    this->on_clockwise_callback_.call();
  for (; delta < 0; delta++)
    this->on_anticlockwise_callback_.call();
}

void SeesawEncoder::dump_config() {
  ESP_LOGCONFIG(TAG, "Seesaw rotary encoder:");
  LOG_I2C_DEVICE(this);
  LOG_UPDATE_INTERVAL(this);
  ESP_LOGCONFIG(TAG, "  Inverted: %s", YESNO(this->inverted_));
  if (this->is_failed()) {
    ESP_LOGE(TAG, "  Encoder was not found at start-up");
  }
}

bool SeesawEncoder::read_register_(uint8_t module, uint8_t function, uint8_t *data, size_t len) {
  const uint8_t address[2] = {module, function};
  if (this->write(address, sizeof(address)) != i2c::ERROR_OK)
    return false;
  delayMicroseconds(READ_DELAY_US);
  return this->read(data, len) == i2c::ERROR_OK;
}

bool SeesawEncoder::read_delta_(int32_t *delta) {
  uint8_t raw[4];
  if (!this->read_register_(MODULE_ENCODER, ENCODER_DELTA, raw, sizeof(raw)))
    return false;
  // The chip sends a signed 32-bit count, most significant byte first.
  *delta = static_cast<int32_t>(encode_uint32(raw[0], raw[1], raw[2], raw[3]));
  return true;
}

}  // namespace esphome::seesaw_encoder
