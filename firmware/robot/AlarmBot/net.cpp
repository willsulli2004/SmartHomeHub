#include "net.h"

#include <ArduinoOTA.h>
#include <WiFi.h>
#include <mqtt_client.h>   // the MQTT client built into the ESP32 core (esp-mqtt)
#include <time.h>

#include "config.h"
#include "secrets.h"       // generated from firmware/robot/.env by robot.py; never committed

namespace net {

namespace {

esp_mqtt_client_handle_t client = nullptr;
QueueHandle_t inbox = nullptr;          // messages waiting for the main loop
volatile bool connected = false;
volatile bool just_connected = false;
bool ota_started = false;
bool ota_running = false;
bool mqtt_started = false;

// Runs on the MQTT client's own task, not the main loop. It only records what
// happened and hands messages over through the queue.
void onMqttEvent(void *, esp_event_base_t, int32_t event_id, void *event_data) {
  auto *event = static_cast<esp_mqtt_event_handle_t>(event_data);
  switch (static_cast<esp_mqtt_event_id_t>(event_id)) {
    case MQTT_EVENT_CONNECTED:
      // One subscription covers hub/alarm/schedule, /start and /stop.
      esp_mqtt_client_subscribe(client, "hub/alarm/#", 1);
      // Console commands sent over Wi-Fi by `robot.py monitor`.
      esp_mqtt_client_subscribe(client, "alarmbot/command", 1);
      connected = true;
      just_connected = true;
      break;
    case MQTT_EVENT_DISCONNECTED:
      connected = false;
      break;
    case MQTT_EVENT_DATA: {
      // A message too big for one event arrives in pieces; none of ours is.
      if (event->current_data_offset != 0 || event->data_len != event->total_data_len) break;
      Incoming message = {};
      const int topic_len = min<int>(event->topic_len, sizeof(message.topic) - 1);
      const int data_len = min<int>(event->data_len, sizeof(message.payload) - 1);
      memcpy(message.topic, event->topic, topic_len);
      memcpy(message.payload, event->data, data_len);
      xQueueSend(inbox, &message, 0);  // if the queue is full the message is dropped
      break;
    }
    default:
      break;
  }
}

void startMqtt() {
  esp_mqtt_client_config_t config = {};
  config.broker.address.hostname = SECRET_MQTT_HOST;
  config.broker.address.port = SECRET_MQTT_PORT;
  config.broker.address.transport = MQTT_TRANSPORT_OVER_TCP;
  config.credentials.client_id = ROBOT_HOSTNAME;
  config.credentials.username = SECRET_MQTT_USERNAME;
  config.credentials.authentication.password = SECRET_MQTT_PASSWORD;
  config.session.keepalive = MQTT_KEEPALIVE_S;
  // The Last Will: the broker publishes this for the robot if it vanishes.
  config.session.last_will.topic = "alarmbot/status";
  config.session.last_will.msg = "{\"state\":\"offline\"}";
  config.session.last_will.qos = 1;
  config.session.last_will.retain = 1;
  config.network.reconnect_timeout_ms = 3000;
  config.buffer.size = 1024;

  client = esp_mqtt_client_init(&config);
  esp_mqtt_client_register_event(client, MQTT_EVENT_ANY, onMqttEvent, nullptr);
  esp_mqtt_client_start(client);   // connects, and reconnects by itself from now on
  mqtt_started = true;
}

void startOta() {
  ArduinoOTA.setHostname(ROBOT_HOSTNAME);
  ArduinoOTA.setPassword(SECRET_OTA_PASSWORD);
  ArduinoOTA.onStart([]() { ota_running = true; });
  ArduinoOTA.onEnd([]() { ota_running = false; });
  ArduinoOTA.onError([](ota_error_t) { ota_running = false; });
  ArduinoOTA.begin();
  ota_started = true;
}

}  // namespace

void begin() {
  inbox = xQueueCreate(6, sizeof(Incoming));
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(ROBOT_HOSTNAME);
  WiFi.setAutoReconnect(true);
  // Keep the radio awake. Power saving delays incoming messages by up to a few
  // hundred milliseconds, and "start" and "stop" should be acted on at once.
  WiFi.setSleep(false);
  WiFi.begin(SECRET_WIFI_SSID, SECRET_WIFI_PASSWORD);
  // UTC from the internet's time servers; the robot has no clock of its own.
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

void update(bool allow_update) {
  if (WiFi.status() != WL_CONNECTED) return;
  // Both need Wi-Fi to be up, so they start the first time it is.
  if (!mqtt_started) startMqtt();
  if (!ota_started) startOta();
  if (allow_update || ota_running) ArduinoOTA.handle();
}

bool wifiConnected() { return WiFi.status() == WL_CONNECTED; }
bool mqttConnected() { return connected; }

bool takeConnected() {
  const bool was = just_connected;
  just_connected = false;
  return was;
}

bool receive(Incoming &message) {
  return inbox != nullptr && xQueueReceive(inbox, &message, 0) == pdTRUE;
}

void publish(const char *topic, const char *payload, int qos, bool retain) {
  if (client == nullptr) return;
  if (qos == 0 && !connected) return;  // telemetry is not worth keeping for later
  // "enqueue" hands the message to the client's task and returns immediately.
  esp_mqtt_client_enqueue(client, topic, payload, 0, qos, retain ? 1 : 0, true);
}

void isoNow(char *out, size_t size) {
  time_t now = time(nullptr);
  if (now < 1700000000) now = 0;  // the clock has not been set yet
  struct tm utc;
  gmtime_r(&now, &utc);
  strftime(out, size, "%Y-%m-%dT%H:%M:%SZ", &utc);
}

bool updating() { return ota_running; }

}  // namespace net
