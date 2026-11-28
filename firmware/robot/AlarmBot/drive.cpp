#include "drive.h"

#include <Preferences.h>

#include "config.h"

namespace drive {

namespace {

// ---- encoders: same decoding as the motor test (interrupt on every edge) ----
volatile long count_l = 0;
volatile long count_r = 0;
volatile uint8_t state_l = 0;
volatile uint8_t state_r = 0;
const int8_t QUADRATURE[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};

void IRAM_ATTR isrLeft() {
  state_l = ((state_l << 2) | (digitalRead(PIN_ENC_L_A) << 1) | digitalRead(PIN_ENC_L_B)) & 0x0F;
  count_l += QUADRATURE[state_l];
}

void IRAM_ATTR isrRight() {
  state_r = ((state_r << 2) | (digitalRead(PIN_ENC_R_A) << 1) | digitalRead(PIN_ENC_R_B)) & 0x0F;
  count_r += QUADRATURE[state_r];
}

void readCounts(long &left, long &right) {
  noInterrupts();
  left = count_l;
  right = count_r;
  interrupts();
  if (INVERT_ENC_L) left = -left;
  if (INVERT_ENC_R) right = -right;
}

// ---- state ----
float target_l = 0, target_r = 0;    // what was asked for
float output_l = 0, output_r = 0;    // what the motors are getting now
uint32_t last_update_ms = 0;

float counts_per_metre = DEFAULT_COUNTS_PER_METER;
long odo_last_l = 0, odo_last_r = 0;
float odo_metres = 0;
float speed_mps = 0;
uint32_t speed_last_ms = 0;
float speed_last_metres = 0;

long stall_last_l = 0, stall_last_r = 0;
uint32_t stall_window_start_ms = 0;
bool stall_flag = false;
bool pushed_l = true, pushed_r = true;  // powered for the whole stall window so far

void writeMotor(int in1, int in2, int pwm_pin, float speed, bool invert, float battery_volts) {
  if (invert) speed = -speed;
  // Scale so 1.0 means 6 V average at the motor, whatever the pack voltage.
  const float max_duty = constrain(MOTOR_VOLTS / max(battery_volts, 1.0f), 0.0f, 1.0f);
  digitalWrite(in1, speed > 0);
  digitalWrite(in2, speed < 0);
  ledcWrite(pwm_pin, (uint32_t)(fabsf(speed) * max_duty * ((1 << PWM_BITS) - 1)));
}

void shortBrake() {
  // IN1 = IN2 = HIGH is the TB6612's short brake.
  digitalWrite(PIN_AIN1, HIGH);
  digitalWrite(PIN_AIN2, HIGH);
  digitalWrite(PIN_BIN1, HIGH);
  digitalWrite(PIN_BIN2, HIGH);
  ledcWrite(PIN_PWMA, 0);
  ledcWrite(PIN_PWMB, 0);
}

float approach(float current, float target, float max_step) {
  if (target > current + max_step) return current + max_step;
  if (target < current - max_step) return current - max_step;
  return target;
}

}  // namespace

void begin() {
  pinMode(PIN_STBY, OUTPUT);
  digitalWrite(PIN_STBY, LOW);
  pinMode(PIN_AIN1, OUTPUT);
  pinMode(PIN_AIN2, OUTPUT);
  pinMode(PIN_BIN1, OUTPUT);
  pinMode(PIN_BIN2, OUTPUT);
  ledcAttach(PIN_PWMA, PWM_HZ, PWM_BITS);
  ledcAttach(PIN_PWMB, PWM_HZ, PWM_BITS);
  shortBrake();

  pinMode(PIN_ENC_L_A, INPUT_PULLUP);
  pinMode(PIN_ENC_L_B, INPUT_PULLUP);
  pinMode(PIN_ENC_R_A, INPUT_PULLUP);
  pinMode(PIN_ENC_R_B, INPUT_PULLUP);
  attachInterrupt(PIN_ENC_L_A, isrLeft, CHANGE);
  attachInterrupt(PIN_ENC_L_B, isrLeft, CHANGE);
  attachInterrupt(PIN_ENC_R_A, isrRight, CHANGE);
  attachInterrupt(PIN_ENC_R_B, isrRight, CHANGE);

  Preferences prefs;
  if (prefs.begin("alarmbot", true)) {
    counts_per_metre = prefs.getFloat("cpm", DEFAULT_COUNTS_PER_METER);
    prefs.end();
  }
  if (!(counts_per_metre > 100.0f)) counts_per_metre = DEFAULT_COUNTS_PER_METER;

  last_update_ms = millis();
  stall_window_start_ms = last_update_ms;
  speed_last_ms = last_update_ms;
  readCounts(odo_last_l, odo_last_r);
  stall_last_l = odo_last_l;
  stall_last_r = odo_last_r;
}

void command(float left, float right) {
  target_l = constrain(left, -MAX_SPEED, MAX_SPEED);
  target_r = constrain(right, -MAX_SPEED, MAX_SPEED);
  digitalWrite(PIN_STBY, HIGH);
}

void brake() {
  target_l = target_r = 0;
  output_l = output_r = 0;
  speed_mps = 0;
  shortBrake();
}

void sleep() {
  brake();
  digitalWrite(PIN_STBY, LOW);
}

void update(float battery_volts) {
  const uint32_t now = millis();
  const float dt = (now - last_update_ms) / 1000.0f;
  last_update_ms = now;

  long left, right;
  readCounts(left, right);

  // Odometry: the average of the two wheels, counting distance in either direction.
  const float moved = (fabsf((float)(left - odo_last_l)) + fabsf((float)(right - odo_last_r))) / 2.0f;
  odo_last_l = left;
  odo_last_r = right;
  odo_metres += moved / counts_per_metre;
  if (now - speed_last_ms >= 200) {
    speed_mps = (odo_metres - speed_last_metres) / ((now - speed_last_ms) / 1000.0f);
    speed_last_metres = odo_metres;
    speed_last_ms = now;
  }

  // Move the outputs towards the command a little at a time.
  const float step = SLEW_PER_S * dt;
  output_l = approach(output_l, target_l, step);
  output_r = approach(output_r, target_r, step);

  if (output_l == 0 && output_r == 0 && target_l == 0 && target_r == 0) {
    shortBrake();
  } else {
    writeMotor(PIN_AIN1, PIN_AIN2, PIN_PWMA, output_l, INVERT_MOTOR_L, battery_volts);
    writeMotor(PIN_BIN1, PIN_BIN2, PIN_PWMB, output_r, INVERT_MOTOR_R, battery_volts);
  }

  // Stall check: a wheel had real power for the whole window and barely turned.
  // "The whole window" matters: a wheel that only just started has not had time
  // to move, and must not count as stuck.
  pushed_l &= fabsf(output_l) >= STALL_MIN_COMMAND;
  pushed_r &= fabsf(output_r) >= STALL_MIN_COMMAND;
  if (now - stall_window_start_ms >= STALL_WINDOW_MS) {
    const bool stuck_l = pushed_l && labs(left - stall_last_l) < STALL_MIN_COUNTS;
    const bool stuck_r = pushed_r && labs(right - stall_last_r) < STALL_MIN_COUNTS;
    if (stuck_l || stuck_r) {
      brake();
      stall_flag = true;
    }
    stall_last_l = left;
    stall_last_r = right;
    stall_window_start_ms = now;
    pushed_l = pushed_r = true;
  }
}

bool takeStall() {
  const bool was = stall_flag;
  stall_flag = false;
  return was;
}

float odometryMetres() { return odo_metres; }
float speedMetresPerSecond() { return speed_mps; }

void resetOdometry() {
  odo_metres = 0;
  speed_last_metres = 0;
  speed_mps = 0;
}

float takeForwardMetres() {
  static long last_l = 0, last_r = 0;
  static bool first = true;
  long left, right;
  readCounts(left, right);
  if (first) {
    last_l = left;
    last_r = right;
    first = false;
  }
  const float counts = ((left - last_l) + (right - last_r)) / 2.0f;
  last_l = left;
  last_r = right;
  return counts / counts_per_metre;
}

long rawCountLeft() {
  long l, r;
  readCounts(l, r);
  return l;
}

long rawCountRight() {
  long l, r;
  readCounts(l, r);
  return r;
}

float countsPerMetre() { return counts_per_metre; }

void setCountsPerMetre(float value) {
  if (!(value > 100.0f)) return;
  counts_per_metre = value;
  Preferences prefs;
  if (prefs.begin("alarmbot", false)) {
    prefs.putFloat("cpm", value);
    prefs.end();
  }
}

}  // namespace drive
