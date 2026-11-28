#include <Wire.h>
#include <Adafruit_LSM6DSOX.h>
#include <esp_system.h>

#define PWMA 6
#define AIN2 7
#define AIN1 15
#define STBY 16
#define BIN1 17
#define BIN2 18
#define PWMB 8
#define ENC_L_A 41
#define ENC_L_B 42
#define ENC_R_A 4
#define ENC_R_B 5
#define BATT_ADC 1
#define IMU_SCL 39
#define IMU_SDA 40
#define LIDAR_RX 21
#define LIDAR_TX 47
#define LIDAR_EN 38

// copy the flags that worked in the motor test
const bool INVERT_MOTOR_L = false;
const bool INVERT_MOTOR_R = false;
const bool INVERT_ENC_L = true;
const bool INVERT_ENC_R = true;

const float MOTOR_V = 6.0;
float vbat = 8.4;

Adafruit_LSM6DSOX imu;
bool imuOK = false;
HardwareSerial &lidar = Serial1;

// ---------- encoders ----------
volatile long countL = 0, countR = 0;
volatile uint8_t stateL = 0, stateR = 0;
const int8_t QDEC[16] = {0,-1,1,0, 1,0,0,-1, -1,0,0,1, 0,1,-1,0};

void IRAM_ATTR isrL() {
  stateL = ((stateL << 2) | (digitalRead(ENC_L_A) << 1) | digitalRead(ENC_L_B)) & 0x0F;
  countL += QDEC[stateL];
}
void IRAM_ATTR isrR() {
  stateR = ((stateR << 2) | (digitalRead(ENC_R_A) << 1) | digitalRead(ENC_R_B)) & 0x0F;
  countR += QDEC[stateR];
}

// ---------- battery / motors ----------
void readBattery() {
  long mv = 0;
  for (int i = 0; i < 8; i++) mv += analogReadMilliVolts(BATT_ADC);
  vbat = (mv / 8.0) * (132.0 / 32.0) / 1000.0;
}

void drive(int in1, int in2, int pwmPin, float speed, bool invert) {
  if (invert) speed = -speed;
  float maxDuty = constrain(MOTOR_V / vbat, 0.0, 1.0);
  digitalWrite(in1, speed > 0);
  digitalWrite(in2, speed < 0);
  ledcWrite(pwmPin, fabs(speed) * maxDuty * 1023);
}
void setLeft(float s)  { drive(AIN1, AIN2, PWMA, s, INVERT_MOTOR_L); }
void setRight(float s) { drive(BIN1, BIN2, PWMB, s, INVERT_MOTOR_R); }

// ---------- lidar ----------
int pts = 0, lastPts = 0, scans = 0, badBytes = 0;
float curNear = 0, lastNear = 0;
int curNearDeg = -1, lastNearDeg = -1;

void sendCmd(uint8_t cmd) { uint8_t p[2] = {0xA5, cmd}; lidar.write(p, 2); }

bool readBytes(uint8_t *buf, size_t n, uint32_t timeout) {
  uint32_t start = millis(); size_t i = 0;
  while (i < n && millis() - start < timeout)
    if (lidar.available()) buf[i++] = lidar.read();
  return i == n;
}

bool readDescriptor() {
  uint8_t d[6];
  uint32_t start = millis();
  while (millis() - start < 1000)
    if (lidar.available() && lidar.read() == 0xA5)
      if (readBytes(d, 6, 200) && d[0] == 0x5A) return true;
  return false;
}

void processNode(uint8_t *n) {
  float angle = ((n[1] >> 1) | (n[2] << 7)) / 64.0;
  float dist = (n[3] | (n[4] << 8)) / 4.0;
  if (n[0] & 1) {
    lastPts = pts; pts = 0; scans++;
    lastNear = curNear; lastNearDeg = curNearDeg;
    curNear = 0; curNearDeg = -1;
  }
  if (dist > 0) {
    pts++;
    if (curNear == 0 || dist < curNear) { curNear = dist; curNearDeg = (int)angle; }
  }
}

void pollLidar() {
  static uint8_t node[5];
  static int idx = 0;
  while (lidar.available()) {
    node[idx++] = lidar.read();
    if (idx == 1 && ((node[0] & 1) == ((node[0] >> 1) & 1))) { idx = 0; badBytes++; }
    else if (idx == 2 && !(node[1] & 1)) { idx = 0; badBytes++; }
    else if (idx == 5) { processNode(node); idx = 0; }
  }
}

// ---------- test phases ----------
struct Phase { const char *name; float l; float r; int ms; };
Phase phases[] = {
  {"idle",    0,    0,   3000},
  {"fwd 40",  0.4,  0.4, 3000},
  {"fwd 80",  0.8,  0.8, 3000},
  {"spin",    0.5, -0.5, 3000},
  {"rev 40", -0.4, -0.4, 3000},
  {"stop",    0,    0,   3000},
};
const int NPHASES = sizeof(phases) / sizeof(phases[0]);

const char *resetName(esp_reset_reason_t r) {
  switch (r) {
    case ESP_RST_POWERON:  return "power on";
    case ESP_RST_SW:       return "software";
    case ESP_RST_PANIC:    return "CRASH";
    case ESP_RST_BROWNOUT: return "BROWNOUT";
    case ESP_RST_INT_WDT:
    case ESP_RST_TASK_WDT: return "WATCHDOG";
    default:               return "other";
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.printf("\nReset reason: %s\n", resetName(esp_reset_reason()));

  pinMode(AIN1, OUTPUT); pinMode(AIN2, OUTPUT);
  pinMode(BIN1, OUTPUT); pinMode(BIN2, OUTPUT);
  pinMode(STBY, OUTPUT);
  ledcAttach(PWMA, 20000, 10);
  ledcAttach(PWMB, 20000, 10);

  pinMode(ENC_L_A, INPUT_PULLUP); pinMode(ENC_L_B, INPUT_PULLUP);
  pinMode(ENC_R_A, INPUT_PULLUP); pinMode(ENC_R_B, INPUT_PULLUP);
  attachInterrupt(ENC_L_A, isrL, CHANGE); attachInterrupt(ENC_L_B, isrL, CHANGE);
  attachInterrupt(ENC_R_A, isrR, CHANGE); attachInterrupt(ENC_R_B, isrR, CHANGE);

  readBattery();
  Serial.printf("Battery: %.2f V\n", vbat);
  if (vbat < 6.4) {
    Serial.println("Battery too low. Stopping.");
    while (true) delay(1000);
  }

  Wire.begin(IMU_SDA, IMU_SCL);
  imuOK = imu.begin_I2C(0x6A, &Wire);
  if (imuOK) {
    imu.setAccelRange(LSM6DS_ACCEL_RANGE_4_G);
    imu.setGyroRange(LSM6DS_GYRO_RANGE_500_DPS);
    imu.setAccelDataRate(LSM6DS_RATE_104_HZ);
    imu.setGyroDataRate(LSM6DS_RATE_104_HZ);
  }
  Serial.printf("IMU: %s\n", imuOK ? "OK" : "NOT FOUND");

  pinMode(LIDAR_EN, OUTPUT);
  digitalWrite(LIDAR_EN, HIGH);
  delay(2000);
  lidar.setRxBufferSize(8192);
  lidar.begin(460800, SERIAL_8N1, LIDAR_RX, LIDAR_TX);
  sendCmd(0x25);
  delay(50);
  while (lidar.available()) lidar.read();
  sendCmd(0x20);
  Serial.printf("LiDAR: %s\n\n", readDescriptor() ? "scanning" : "NO RESPONSE");

  digitalWrite(STBY, HIGH);
}

void loop() {
  pollLidar();

  static int phase = -1;
  static unsigned long phaseStart = 0;
  if (phase < 0 || millis() - phaseStart >= phases[phase].ms) {
    phase = (phase + 1) % NPHASES;
    phaseStart = millis();
    setLeft(phases[phase].l);
    setRight(phases[phase].r);
  }

  static float aMin = 99, aMax = 0, gMax = 0;
  static unsigned long lastImu = 0;
  if (imuOK && millis() - lastImu >= 10) {
    lastImu = millis();
    sensors_event_t a, g, t;
    imu.getEvent(&a, &g, &t);
    float mag = sqrt(sq(a.acceleration.x) + sq(a.acceleration.y) + sq(a.acceleration.z));
    aMin = min(aMin, mag);
    aMax = max(aMax, mag);
    float gm = max(fabs(g.gyro.x), max(fabs(g.gyro.y), fabs(g.gyro.z))) * 57.3;
    gMax = max(gMax, gm);
  }

  static float vMin = 99;
  static unsigned long lastBatt = 0;
  if (millis() - lastBatt >= 50) {
    lastBatt = millis();
    readBattery();
    vMin = min(vMin, vbat);
  }

  static unsigned long lastPrint = 0;
  static long prevL = 0, prevR = 0;
  if (millis() - lastPrint >= 500) {
    lastPrint = millis();
    noInterrupts();
    long l = countL, r = countR;
    interrupts();
    long rateL = (l - prevL) * 2, rateR = (r - prevR) * 2;
    prevL = l; prevR = r;
    if (INVERT_ENC_L) rateL = -rateL;
    if (INVERT_ENC_R) rateR = -rateR;

    Serial.printf("%-7s vbat %.2f min %.2f | enc L %5ld R %5ld /s | |a| %5.2f vib %4.2f gyro %4.0f | lidar %2d Hz %3d pts bad %3d near %4.0f@%3d\n",
                  phases[phase].name, vbat, vMin, rateL, rateR,
                  (aMin + aMax) / 2, aMax - aMin, gMax,
                  scans * 2, lastPts, badBytes, lastNear, lastNearDeg);

    aMin = 99; aMax = 0; gMax = 0; vMin = 99;
    scans = 0; badBytes = 0;
  }
}