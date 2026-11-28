#include "chase.h"

#include "config.h"
#include "drive.h"
#include "sensors.h"

namespace chase {

namespace {

enum class Step {
  WaitForLidar,  // LiDAR is still spinning up: stay put
  Cruise,        // drive forward, steering away from the nearer side
  Turn,          // something close ahead: turn on the spot
  BackOut,       // a wheel stalled: reverse
  TurnAway,      // after backing out: turn before trying again
  Blind,         // no LiDAR data: short forward runs and turns, slowly
};

Step step = Step::WaitForLidar;
uint32_t step_start_ms = 0;
uint32_t chase_start_ms = 0;
float turn_direction = 1;   // +1 = clockwise (right), -1 = anticlockwise
int stall_count = 0;
int blind_leg = 0;

void go(Step next) {
  step = next;
  step_start_ms = millis();
}

// Turn towards whichever side has more room. With nothing seen on a side (0),
// that side counts as wide open.
float roomierSide() {
  const float left = lidar::leftMm() == 0 ? 99999.0f : lidar::leftMm();
  const float right = lidar::rightMm() == 0 ? 99999.0f : lidar::rightMm();
  return right >= left ? 1.0f : -1.0f;
}

}  // namespace

void begin() {
  stall_count = 0;
  blind_leg = 0;
  chase_start_ms = millis();
  go(Step::WaitForLidar);
}

int stalls() { return stall_count; }

const char *activity() {
  switch (step) {
    case Step::WaitForLidar: return "waiting for lidar";
    case Step::Cruise:       return "cruise";
    case Step::Turn:         return "turn";
    case Step::BackOut:      return "back out";
    case Step::TurnAway:     return "turn away";
    case Step::Blind:        return "blind";
  }
  return "?";
}

void update() {
  const uint32_t now = millis();
  const uint32_t in_step_ms = now - step_start_ms;

  // A stall interrupts whatever was happening.
  if (drive::takeStall()) {
    stall_count++;
    turn_direction = roomierSide();
    go(Step::BackOut);
    return;
  }

  switch (step) {
    case Step::WaitForLidar:
      drive::command(0, 0);
      if (lidar::scanning()) go(Step::Cruise);
      // No scans well after the warm-up: carry on without the LiDAR.
      else if (now - chase_start_ms > LIDAR_WARMUP_MS + 2000) go(Step::Blind);
      break;

    case Step::Cruise: {
      if (!lidar::scanning()) {
        go(Step::Blind);
        break;
      }
      const float front = lidar::frontMm();
      if (front != 0 && front < OBSTACLE_STOP_MM) {
        turn_direction = roomierSide();
        go(Step::Turn);
        break;
      }
      // Steer gently away from whichever side is closer than OBSTACLE_SLOW_MM.
      float steer = 0;
      const float left = lidar::leftMm(), right = lidar::rightMm();
      if (left != 0 && left < OBSTACLE_SLOW_MM) steer += 0.15f;   // veer right
      if (right != 0 && right < OBSTACLE_SLOW_MM) steer -= 0.15f; // veer left
      // Ease off when something is coming up ahead.
      const float speed = (front != 0 && front < OBSTACLE_SLOW_MM) ? CRUISE_SPEED * 0.7f : CRUISE_SPEED;
      drive::command(speed + steer, speed - steer);
      break;
    }

    case Step::Turn:
      drive::command(TURN_SPEED * turn_direction, -TURN_SPEED * turn_direction);
      // Keep turning for at least 300 ms, then until the way ahead is clear, and
      // never for more than 3 seconds.
      if (in_step_ms > 300) {
        const float front = lidar::frontMm();
        const bool clear = front == 0 || front > OBSTACLE_STOP_MM * 1.5f;
        if (clear || in_step_ms > 3000) go(lidar::scanning() ? Step::Cruise : Step::Blind);
      }
      break;

    case Step::BackOut:
      drive::command(-TURN_SPEED, -TURN_SPEED);
      if (in_step_ms > 500) go(Step::TurnAway);
      break;

    case Step::TurnAway:
      drive::command(TURN_SPEED * turn_direction, -TURN_SPEED * turn_direction);
      if (in_step_ms > 600) go(lidar::scanning() ? Step::Cruise : Step::Blind);
      break;

    case Step::Blind:
      // Without the LiDAR the stall check is the only obstacle sense, so go
      // slowly: 1.5 s forward, 0.6 s turn, alternating the turn direction.
      if (lidar::scanning()) {
        go(Step::Cruise);
        break;
      }
      if (in_step_ms < 1500) {
        drive::command(CRUISE_SPEED * 0.7f, CRUISE_SPEED * 0.7f);
      } else if (in_step_ms < 2100) {
        const float direction = (blind_leg % 2 == 0) ? 1.0f : -1.0f;
        drive::command(TURN_SPEED * direction, -TURN_SPEED * direction);
      } else {
        blind_leg++;
        go(Step::Blind);
      }
      break;
  }
}

}  // namespace chase
