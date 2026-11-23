#pragma once

// Draws the "ringing" pattern on the LED ring: three LEDs in a row, used by the
// Ringing Timer and Ringing Alarm effects in packages/leds.yaml.
//
//   head   the chosen colour at the chosen brightness
//   middle 75% as bright and a little lighter (20% of the way towards white)
//   tail   40% as bright and lighter still (30% of the way towards white)
//
// The colour comes from a light entity that exists only as a colour picker in
// Home Assistant ("Timer Ring Colour", "Alarm Ring Colour"), so it can be
// changed from the app. Only its colour and brightness are used; switching that
// entity off does not switch the ringing light off.
//
// LED current: three LEDs are lit, so even white at full brightness is about
// 3 x 60 mA x 0.8 (the cap in leds.yaml) = 0.14 A, far inside the 1.2 A budget.

#include <algorithm>
#include <cstdint>

#include "esphome/components/light/addressable_light.h"
#include "esphome/components/light/light_state.h"
#include "esphome/core/color.h"

namespace ring_spinner {

// One LED's colour: the head colour dimmed to `level` and moved `lighten` of the
// way towards white at that level.
inline esphome::Color shade(float red, float green, float blue, float level, float lighten) {
  const float top = std::max({red, green, blue}) * level;
  const auto channel = [&](float value) -> uint8_t {
    const float dimmed = value * level;
    const float out = dimmed + (top - dimmed) * lighten;
    return static_cast<uint8_t>(std::min(255.0f, std::max(0.0f, out * 255.0f)));
  };
  return esphome::Color(channel(red), channel(green), channel(blue));
}

// Draws one frame with the head at `position` and returns the next position.
// Call it once per effect update. To reverse the direction, swap the + and - on
// the three lines marked "direction".
inline int draw(esphome::light::AddressableLight &ring, int position, esphome::light::LightState *colour_picker) {
  const int count = ring.size();
  if (count <= 0)
    return 0;
  position %= count;

  const auto &picked = colour_picker->remote_values;
  const float brightness = picked.get_brightness();
  const float red = picked.get_red() * brightness;
  const float green = picked.get_green() * brightness;
  const float blue = picked.get_blue() * brightness;

  ring.all() = esphome::Color::BLACK;
  ring[position] = shade(red, green, blue, 1.0f, 0.0f);
  ring[(position - 1 + count) % count] = shade(red, green, blue, 0.75f, 0.2f);  // direction
  ring[(position - 2 + count) % count] = shade(red, green, blue, 0.4f, 0.3f);   // direction
  return (position + 1) % count;                                                // direction
}

}  // namespace ring_spinner
