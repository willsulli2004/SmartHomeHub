// Wi-Fi, clock, MQTT and updates over Wi-Fi.
//
// The MQTT contract is docs/robot-integration.md. This file knows how to connect
// and how to send and receive; what the messages mean is decided in AlarmBot.ino.
#pragma once

#include <Arduino.h>

namespace net {

// One message received from the hub.
struct Incoming {
  char topic[40];
  char payload[512];
};

// Start Wi-Fi, the clock, MQTT and the update service. Returns at once; the
// connections come up in the background and are restored by themselves.
void begin();

// Call every loop. `allow_update` lets a Wi-Fi update start; pass false while
// the robot is moving.
void update(bool allow_update);

bool wifiConnected();
String address();   // the robot's IP address on the Wi-Fi, as text
bool mqttConnected();

// True once each time the broker connection is made (including reconnects), so
// the caller can announce "online" and its state again. Reading it clears it.
bool takeConnected();

// The next message from the hub, if one is waiting.
bool receive(Incoming &message);

// Queue a message for sending. Never blocks. QoS 1 messages are kept and sent
// after a reconnect; QoS 0 messages are dropped if the broker is not connected.
void publish(const char *topic, const char *payload, int qos, bool retain);

// The time as the contract writes it, "2026-11-28T15:00:00Z". Before the clock
// has been set it returns "1970-01-01T00:00:00Z".
void isoNow(char *out, size_t size);

// True while a Wi-Fi update is being received. The motors must stay off.
bool updating();

}  // namespace net
