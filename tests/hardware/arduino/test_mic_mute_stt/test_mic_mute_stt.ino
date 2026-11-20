// test_mic_mute_stt.ino — mic + mute button + PC transcription test (Smart Home Hub)
// Board: ESP32S3 Dev Module, OPI PSRAM, Arduino core 3.x. Serial 115200.
// Needs HubSecrets.h: HUB_WIFI_SSID, HUB_WIFI_PASS, HUB_PC_HOST, HUB_PC_PORT

#include <Arduino.h>
#include <WiFi.h>
#include <ESP_I2S.h>
#include <esp_system.h>
#include <HubSecrets.h>

// ============================ MIC MODULE ============================
namespace Mic {
  constexpr int PIN_BCLK = 42;
  constexpr int PIN_WS   = 1;    // LRCL
  constexpr int PIN_DIN  = 2;    // mic DOUT -> ESP data in
  constexpr uint32_t SAMPLE_RATE = 16000;
  constexpr int GAIN_SHIFT = 11; // 16 = unity, 11 = +30 dB (far-field)

  I2SClass i2s;

  bool begin() {
    i2s.setPins(PIN_BCLK, PIN_WS, -1, PIN_DIN);
    return i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                     I2S_SLOT_MODE_MONO, I2S_STD_SLOT_LEFT);
  }

  size_t readRaw(int32_t* buf, size_t n) {
    return i2s.readBytes((char*)buf, n * sizeof(int32_t)) / sizeof(int32_t);
  }

  inline int16_t toPcm16(int32_t raw) {
    int32_t s = raw >> GAIN_SHIFT;
    if (s > 32767) s = 32767;
    else if (s < -32768) s = -32768;
    return (int16_t)s;
  }
}

// ========================= MUTE BUTTON MODULE =========================
namespace MuteButton {
  constexpr int  PIN = 45;              // switch to GND. NO external pull-up: strapping pin
  constexpr bool MUTED_WHEN_LOW = true; // latched in = closed = LOW = muted. Flip if backwards
  constexpr uint32_t DEBOUNCE_MS = 30;

  bool stable = false, lastRaw = false, changedFlag = false;
  uint32_t lastEdge = 0;

  bool readRaw() {
    bool low = (digitalRead(PIN) == LOW);
    return MUTED_WHEN_LOW ? low : !low;
  }

  void begin() {
    pinMode(PIN, INPUT_PULLUP);
    delay(5);
    stable = lastRaw = readRaw();
  }

  void update() {
    bool r = readRaw();
    if (r != lastRaw) {
      lastRaw = r;
      lastEdge = millis();
    } else if (r != stable && millis() - lastEdge >= DEBOUNCE_MS) {
      stable = r;
      changedFlag = true;
    }
  }

  bool muted()   { return stable; }
  bool changed() { bool c = changedFlag; changedFlag = false; return c; }
}

// ===================== PC LINK MODULE (test-only protocol) =====================
// ESP -> PC: raw PCM16 LE mono 16 kHz.  PC -> ESP: transcript lines ending in '\n'.
namespace Link {
  WiFiClient client;
  uint32_t lastAttempt = 0;
  bool wifiWasUp = false;
  String line;

  void begin() {
    WiFi.mode(WIFI_STA);
    WiFi.setHostname("sat-hub");
    WiFi.setSleep(false);               // no modem sleep while streaming
    WiFi.begin(HUB_WIFI_SSID, HUB_WIFI_PASS);
    Serial.println("[wifi] connecting...");
  }

  void update() {
    bool up = (WiFi.status() == WL_CONNECTED);
    if (up != wifiWasUp) {
      wifiWasUp = up;
      if (up) Serial.printf("[wifi] connected, IP %s, RSSI %d dBm\n",
                            WiFi.localIP().toString().c_str(), WiFi.RSSI());
      else    Serial.println("[wifi] disconnected");
    }
    if (!up) return;

    if (!client.connected()) {
      if (millis() - lastAttempt < 3000) return;
      lastAttempt = millis();
      Serial.printf("[link] connecting to %s:%d ...\n", HUB_PC_HOST, HUB_PC_PORT);
      if (client.connect(HUB_PC_HOST, HUB_PC_PORT, 1000)) {
        client.setNoDelay(true);
        Serial.println("[link] connected");
      } else {
        Serial.println("[link] failed (PC script running? firewall? right IP?)");
      }
      return;
    }

    while (client.available()) {
      char c = client.read();
      if (c == '\n') {
        Serial.printf("[heard] %s\n", line.c_str());
        line = "";
      } else if (c != '\r' && line.length() < 512) {
        line += c;
      }
    }
  }

  bool ready() { return client.connected(); }

  bool sendAll(const uint8_t* p, size_t len) {   // keep int16 alignment intact
    while (len) {
      size_t n = client.write(p, len);
      if (n == 0) {
        client.stop();
        Serial.println("[link] write failed, reconnecting");
        return false;
      }
      p += n;
      len -= n;
    }
    return true;
  }
}

// ============================ TEST HARNESS ============================
constexpr size_t BLOCK = 256;          // 16 ms
int32_t  rawBuf[BLOCK];
int16_t  pcm[BLOCK];
uint32_t sentBytes = 0, lastStat = 0;
int      ledState = -1;

const char* resetReasonStr() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "power-on";
    case ESP_RST_SW:       return "software";
    case ESP_RST_PANIC:    return "PANIC";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT:
    case ESP_RST_WDT:      return "WATCHDOG";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_EXT:      return "external pin";
    default:               return "other";
  }
}

// Onboard RGB on GPIO48 as status: red = muted, green = streaming, blue = waiting for link.
// (Temporary: GPIO48 is the planned amp MUTE pin later.)
void updateLed() {
  int s = MuteButton::muted() ? 0 : (Link::ready() ? 1 : 2);
  if (s == ledState) return;
  ledState = s;
  if (s == 0)      rgbLedWrite(48, 20, 0, 0);
  else if (s == 1) rgbLedWrite(48, 0, 20, 0);
  else             rgbLedWrite(48, 0, 0, 20);
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\n=== Smart Home Hub: mic + mute + STT test ===");
  Serial.printf("[boot] reset reason: %s\n", resetReasonStr());

  MuteButton::begin();
  Serial.printf("[mute] %s at boot\n", MuteButton::muted() ? "MUTED" : "live");

  if (!Mic::begin()) {
    Serial.println("[mic] I2S begin FAILED");
    while (true) delay(1000);
  }
  uint32_t t0 = millis();
  while (millis() - t0 < 300) Mic::readRaw(rawBuf, BLOCK);   // settle
  Serial.println("[mic] ok");

  Link::begin();
}

void loop() {
  MuteButton::update();
  if (MuteButton::changed()) {
    Serial.printf("[mute] %s\n", MuteButton::muted()
                  ? "MUTED - audio is discarded on the device" : "live");
  }

  Link::update();

  // Always read so the I2S DMA never overflows; only forward when live + connected.
  size_t n = Mic::readRaw(rawBuf, BLOCK);
  if (n && !MuteButton::muted() && Link::ready()) {
    for (size_t i = 0; i < n; i++) pcm[i] = Mic::toPcm16(rawBuf[i]);
    if (Link::sendAll((uint8_t*)pcm, n * sizeof(int16_t))) sentBytes += n * sizeof(int16_t);
  }

  updateLed();

  if (millis() - lastStat >= 5000) {
    if (sentBytes) Serial.printf("[link] streaming %.1f kB/s\n", sentBytes / 5000.0);
    sentBytes = 0;
    lastStat = millis();
  }
}
