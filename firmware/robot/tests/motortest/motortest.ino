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

const bool INVERT_MOTOR_L = false;
const bool INVERT_MOTOR_R = false;
const bool INVERT_ENC_L = false;
const bool INVERT_ENC_R = false;

const float MOTOR_V = 6.0;
float vbat = 8.4;

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

void readBattery() {
  long mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(BATT_ADC);
  vbat = (mv / 16.0) * (132.0 / 32.0) / 1000.0;
}

// speed: -1.0 to 1.0, where 1.0 = 6 V average at the motor
void drive(int in1, int in2, int pwmPin, float speed, bool invert) {
  if (invert) speed = -speed;
  float maxDuty = constrain(MOTOR_V / vbat, 0.0, 1.0);
  digitalWrite(in1, speed > 0);
  digitalWrite(in2, speed < 0);
  ledcWrite(pwmPin, fabs(speed) * maxDuty * 1023);
}

void setLeft(float s)  { drive(AIN1, AIN2, PWMA, s, INVERT_MOTOR_L); }
void setRight(float s) { drive(BIN1, BIN2, PWMB, s, INVERT_MOTOR_R); }

struct Step { const char* name; float l; float r; int ms; };
Step steps[] = {
  {"LEFT forward",   0.4, 0,   2000}, {"stop", 0, 0, 1000},
  {"LEFT reverse",  -0.4, 0,   2000}, {"stop", 0, 0, 1000},
  {"RIGHT forward",  0,   0.4, 2000}, {"stop", 0, 0, 1000},
  {"RIGHT reverse",  0,  -0.4, 2000}, {"stop", 0, 0, 1000},
  {"BOTH forward",   0.4, 0.4, 2000}, {"stop", 0, 0, 3000},
};
const int NSTEPS = sizeof(steps) / sizeof(steps[0]);

void setup() {
  Serial.begin(115200);
  delay(1000);

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
    Serial.println("Battery too low (or divider not reading). Stopping.");
    while (true) delay(1000);
  }
  digitalWrite(STBY, HIGH);
}

void loop() {
  static int step = 0;
  static unsigned long stepStart = 0, lastPrint = 0;
  static bool started = false;

  if (!started || millis() - stepStart >= steps[step].ms) {
    if (started) step = (step + 1) % NSTEPS;
    started = true;
    stepStart = millis();
    noInterrupts(); countL = 0; countR = 0; interrupts();
    setLeft(steps[step].l);
    setRight(steps[step].r);
    Serial.printf("\n--- %s ---\n", steps[step].name);
  }

  if (millis() - lastPrint >= 250) {
    lastPrint = millis();
    readBattery();
    noInterrupts(); long l = countL, r = countR; interrupts();
    if (INVERT_ENC_L) l = -l;
    if (INVERT_ENC_R) r = -r;
    Serial.printf("vbat %.2f V   L %7ld   R %7ld\n", vbat, l, r);
  }
}