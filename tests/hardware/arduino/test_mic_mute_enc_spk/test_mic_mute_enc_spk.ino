// test_mic_mute_enc_spk.ino — mic + mute + encoder + speaker + PC transcription test (Smart Home Hub)
// Board: ESP32S3 Dev Module, OPI PSRAM, Arduino core 3.x. Serial 115200.
// Libraries: Adafruit seesaw (+ Adafruit BusIO). Needs HubSecrets.h.
// Serial commands: 'c' chime, 's' sweep 100 Hz-8 kHz, 't' toggle 440 Hz calibration tone, 'x' stop

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <ESP_I2S.h>
#include <esp_system.h>
#include <math.h>
#include <Adafruit_seesaw.h>
#include <seesaw_neopixel.h>
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

// ========================== ENCODER MODULE ==========================
// Adafruit I2C Stemma QT rotary encoder (seesaw) at 0x36 on Wire (I2C port 0).
namespace Encoder {
  constexpr int     PIN_SDA   = 21;
  constexpr int     PIN_SCL   = 47;
  constexpr uint8_t ADDR      = 0x36;
  constexpr uint8_t SS_SWITCH = 24;
  constexpr uint8_t SS_PIXEL  = 6;
  constexpr int     DIR       = 1;     // flip to -1 if clockwise turns the value down
  constexpr uint32_t POLL_MS  = 20;

  Adafruit_seesaw ss(&Wire);
  seesaw_NeoPixel pixel(1, SS_PIXEL, NEO_GRB + NEO_KHZ800, &Wire);

  bool ok = false, btnDown = false, pressEvt = false, releaseEvt = false;
  int32_t  pendingDelta = 0;
  uint32_t lastPoll = 0, pressStart = 0, lastHeldMs = 0, lastColor = 0xFFFFFFFF;

  void scanBus() {
    Serial.print("[enc] I2C scan:");
    int found = 0;
    for (uint8_t a = 1; a < 127; a++) {
      Wire.beginTransmission(a);
      if (Wire.endTransmission() == 0) { Serial.printf(" 0x%02X", a); found++; }
    }
    Serial.println(found ? "" : " nothing found");
  }

  bool begin() {
    Wire.begin(PIN_SDA, PIN_SCL);       // must come before ss.begin() so our pins stick
    if (!ss.begin(ADDR)) {
      Serial.println("[enc] seesaw NOT found at 0x36 (check SDA 21, SCL 47, 3V, GND)");
      scanBus();
      return false;
    }
    uint32_t product = (ss.getVersion() >> 16) & 0xFFFF;
    Serial.printf("[enc] seesaw ok, product %lu%s\n",
                  (unsigned long)product, product == 4991 ? "" : " (expected 4991)");
    ss.pinMode(SS_SWITCH, INPUT_PULLUP);
    ss.getEncoderDelta();               // discard clicks from before boot
    pixel.begin(ADDR);
    pixel.show();
    ok = true;
    return true;
  }

  void update() {
    if (!ok || millis() - lastPoll < POLL_MS) return;
    lastPoll = millis();

    pendingDelta += DIR * ss.getEncoderDelta();

    bool down = !ss.digitalRead(SS_SWITCH);   // 20 ms polling doubles as debounce
    if (down != btnDown) {
      btnDown = down;
      if (down) {
        pressEvt = true;
        pressStart = millis();
      } else {
        releaseEvt = true;
        lastHeldMs = millis() - pressStart;
      }
    }
  }

  int32_t takeDelta() { int32_t d = pendingDelta; pendingDelta = 0; return d; }
  bool    pressed()   { bool e = pressEvt; pressEvt = false; return e; }
  bool    isDown()    { return btnDown; }

  bool released(uint32_t* heldMs) {
    if (!releaseEvt) return false;
    releaseEvt = false;
    if (heldMs) *heldMs = lastHeldMs;
    return true;
  }

  void setPixel(uint8_t r, uint8_t g, uint8_t b) {
    if (!ok) return;
    uint32_t c = pixel.Color(r, g, b);
    if (c == lastColor) return;         // only touch I2C when the color changes
    lastColor = c;
    pixel.setPixelColor(0, c);
    pixel.show();
  }

  bool present() { return ok; }
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
    WiFi.setSleep(false);
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

  bool sendAll(const uint8_t* p, size_t len) {
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

// ========================== SPEAKER MODULE ==========================
// ESP --I2S--> PCM5102 DAC --analog LOUT--> MAX9744 (analog volume mode) --> speaker.
// Runs in its own task so playback never blocks the mic loop. The latest play() request wins.
namespace Speaker {
  constexpr int PIN_BCK  = 39;
  constexpr int PIN_WS   = 40;          // WSEL / LRCK (not LOUT)
  constexpr int PIN_DOUT = 38;          // ESP data out -> DAC DIN
  constexpr uint32_t RATE = 22050;      // matches Piper's usual output rate
  constexpr float MAX_LEVEL = 0.5f;     // DAC full scale (2.1 Vrms) overdrives the amp
  constexpr size_t FRAMES = 256;        // ~11.6 ms per block
  constexpr uint32_t RAMP = RATE / 200; // 5 ms fades, no clicks

  enum class Sound : uint8_t { Stop, Tick, Chime, MuteOn, MuteOff, Sweep, CalTone };

  // f0 = 0: silence.  ms = 0: until stopped.  f1 != f0: logarithmic glide.
  struct Seg { float f0, f1; uint32_t ms; };
  const Seg TICK[]     = {{1500, 1500, 25}};
  const Seg CHIME[]    = {{659, 659, 120}, {0, 0, 30}, {880, 880, 220}};
  const Seg MUTE_ON[]  = {{880, 880, 90},  {0, 0, 20}, {587, 587, 150}};
  const Seg MUTE_OFF[] = {{587, 587, 90},  {0, 0, 20}, {880, 880, 150}};
  const Seg SWEEP[]    = {{100, 8000, 5000}};
  const Seg CAL[]      = {{440, 440, 0}};

  I2SClass i2s;
  QueueHandle_t queue = nullptr;
  volatile float gain = 0.0f;
  volatile bool  active = false;

  // ---- player state (only touched inside the speaker task) ----
  const Seg* segs = nullptr;
  uint8_t  segCount = 0, segIdx = 0;
  uint32_t pos = 0, len = 0, fadeLeft = 0;
  bool     stopping = false;
  float    phase = 0, freq = 0, glide = 1;

  void startSeg() {
    const Seg& g = segs[segIdx];
    pos = 0;
    len = (uint32_t)((uint64_t)g.ms * RATE / 1000);
    freq = g.f0;
    glide = (len && g.f0 > 0 && g.f1 != g.f0) ? powf(g.f1 / g.f0, 1.0f / len) : 1.0f;
  }

  void load(Sound s) {
    stopping = false;
    switch (s) {
      case Sound::Tick:    segs = TICK;     segCount = 1; break;
      case Sound::Chime:   segs = CHIME;    segCount = 3; break;
      case Sound::MuteOn:  segs = MUTE_ON;  segCount = 3; break;
      case Sound::MuteOff: segs = MUTE_OFF; segCount = 3; break;
      case Sound::Sweep:   segs = SWEEP;    segCount = 1; break;
      case Sound::CalTone: segs = CAL;      segCount = 1; break;
      case Sound::Stop:
        if (segs) { stopping = true; fadeLeft = RAMP; }
        return;
    }
    segIdx = 0;
    startSeg();
  }

  float nextSample() {
    if (!segs) return 0.0f;
    if (len && pos >= len) {
      if (++segIdx >= segCount) { segs = nullptr; return 0.0f; }
      startSeg();
    }
    const Seg& g = segs[segIdx];

    float env = 1.0f;
    if (pos < RAMP) env = (float)pos / RAMP;
    if (len && len - pos < RAMP) env = fminf(env, (float)(len - pos) / RAMP);
    if (stopping) {
      if (fadeLeft == 0) { segs = nullptr; return 0.0f; }
      env = fminf(env, (float)fadeLeft-- / RAMP);
    }

    float s = 0.0f;
    if (g.f0 > 0) {
      s = sinf(phase) * env;
      phase += TWO_PI * freq / RATE;
      if (phase >= TWO_PI) phase -= TWO_PI;
      freq *= glide;
    }
    pos++;
    return s;
  }

  void task(void*) {
    static int16_t buf[FRAMES * 2];
    for (;;) {
      Sound cmd;
      if (xQueueReceive(queue, &cmd, 0) == pdTRUE) load(cmd);
      float g = gain;
      for (size_t i = 0; i < FRAMES; i++) {
        int16_t v = (int16_t)(nextSample() * g * 32767.0f);
        buf[2 * i]     = v;   // left -> MAX9744 left input -> speaker
        buf[2 * i + 1] = v;   // right, mirrored (unused)
      }
      active = (segs != nullptr);
      i2s.write((uint8_t*)buf, sizeof(buf));   // blocks until DMA has room: paces the task
    }
  }

  bool begin() {
    i2s.setPins(PIN_BCK, PIN_WS, PIN_DOUT);
    if (!i2s.begin(I2S_MODE_STD, RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) return false;
    queue = xQueueCreate(1, sizeof(Sound));
    xTaskCreatePinnedToCore(task, "speaker", 4096, nullptr, 2, nullptr, 1);
    return true;
  }

  void play(Sound s)      { if (queue) xQueueOverwrite(queue, &s); }
  void setVolume(int pct) { float v = constrain(pct, 0, 100) / 100.0f; gain = MAX_LEVEL * v * v; }
  bool playing()          { return active; }
}

// ============================ TEST HARNESS ============================
constexpr size_t BLOCK = 256;          // 16 ms of mic audio
constexpr int    VOL_STEP = 2;         // % per click

int32_t  rawBuf[BLOCK];
int16_t  pcm[BLOCK];
uint32_t sentBytes = 0, lastStat = 0;
int      ledState = -1;
int      volumePct = 30;
bool     calTone = false;

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

// Onboard RGB (GPIO48): red = muted, green = streaming, blue = waiting for link. Temporary.
void updateBoardLed() {
  int s = MuteButton::muted() ? 0 : (Link::ready() ? 1 : 2);
  if (s == ledState) return;
  ledState = s;
  if (s == 0)      rgbLedWrite(48, 20, 0, 0);
  else if (s == 1) rgbLedWrite(48, 0, 20, 0);
  else             rgbLedWrite(48, 0, 0, 20);
}

// Encoder pixel: white = pressed, red = muted, amber = calibration tone, green = volume.
void updateEncoderPixel() {
  if (Encoder::isDown())          Encoder::setPixel(40, 40, 40);
  else if (MuteButton::muted())   Encoder::setPixel(40, 0, 0);
  else if (calTone)               Encoder::setPixel(40, 20, 0);
  else                            Encoder::setPixel(0, (uint8_t)(2 + volumePct * 0.6), 0);
}

void setCalTone(bool on) {
  calTone = on;
  Speaker::play(on ? Speaker::Sound::CalTone : Speaker::Sound::Stop);
  Serial.printf("[spk] calibration tone %s\n", on ? "ON (440 Hz, continuous)" : "off");
}

void handleSerial() {
  while (Serial.available()) {
    switch (Serial.read()) {
      case 'c': calTone = false; Speaker::play(Speaker::Sound::Chime); break;
      case 's': calTone = false; Speaker::play(Speaker::Sound::Sweep);
                Serial.println("[spk] sweep 100 Hz -> 8 kHz (5 s)"); break;
      case 't': setCalTone(!calTone); break;
      case 'x': calTone = false; Speaker::play(Speaker::Sound::Stop); break;
    }
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("\n=== Smart Home Hub: mic + mute + encoder + speaker + STT test ===");
  Serial.printf("[boot] reset reason: %s\n", resetReasonStr());

  MuteButton::begin();
  Serial.printf("[mute] %s at boot\n", MuteButton::muted() ? "MUTED" : "live");

  Encoder::begin();
  Serial.printf("[vol] %d%%\n", volumePct);

  if (!Mic::begin()) {
    Serial.println("[mic] I2S begin FAILED");
    while (true) delay(1000);
  }
  uint32_t t0 = millis();
  while (millis() - t0 < 300) Mic::readRaw(rawBuf, BLOCK);   // settle
  Serial.println("[mic] ok");

  if (Speaker::begin()) {
    Speaker::setVolume(volumePct);
    Speaker::play(Speaker::Sound::Chime);                   // boot chime
    Serial.println("[spk] I2S ok (22050 Hz, 16-bit stereo)");
  } else {
    Serial.println("[spk] I2S begin FAILED");
  }

  Link::begin();
  Serial.println("Serial: c = chime, s = sweep, t = calibration tone, x = stop");
}

void loop() {
  handleSerial();

  MuteButton::update();
  if (MuteButton::changed()) {
    bool m = MuteButton::muted();
    Serial.printf("[mute] %s\n", m ? "MUTED - audio is discarded on the device" : "live");
    if (!calTone) Speaker::play(m ? Speaker::Sound::MuteOn : Speaker::Sound::MuteOff);
  }

  Encoder::update();
  int32_t d = Encoder::takeDelta();
  if (d) {
    int v = constrain(volumePct + (int)d * VOL_STEP, 0, 100);
    if (v != volumePct) {
      volumePct = v;
      Speaker::setVolume(volumePct);
      Serial.printf("[vol] %d%%\n", volumePct);
      if (!calTone) Speaker::play(Speaker::Sound::Tick);
    }
  }
  if (Encoder::pressed()) Serial.println("[enc] pressed");
  uint32_t held;
  if (Encoder::released(&held)) {
    if (held >= 1000)  setCalTone(!calTone);                // long press: calibration tone
    else if (calTone)  setCalTone(false);                   // short press stops it
    else               Speaker::play(Speaker::Sound::Chime);
  }

  Link::update();

  size_t n = Mic::readRaw(rawBuf, BLOCK);
  if (n && !MuteButton::muted() && Link::ready()) {
    for (size_t i = 0; i < n; i++) pcm[i] = Mic::toPcm16(rawBuf[i]);
    if (Link::sendAll((uint8_t*)pcm, n * sizeof(int16_t))) sentBytes += n * sizeof(int16_t);
  }

  updateBoardLed();
  updateEncoderPixel();

  if (millis() - lastStat >= 5000) {
    if (sentBytes) Serial.printf("[link] streaming %.1f kB/s\n", sentBytes / 5000.0);
    sentBytes = 0;
    lastStat = millis();
  }
}