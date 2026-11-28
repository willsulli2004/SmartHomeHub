# Refining the robot's navigation

How the alarm robot decides where to drive today, what is weak about it, and a sequence of
improvements, each small enough to build and test on its own. Written for Will and for whoever works
on `firmware/robot/AlarmBot/chase.cpp` next.

The current behaviour has been compiled but not yet run on the robot, so step 0 below comes before
any refinement.

## What it does now

All of it is in `chase.cpp`. Each loop it looks at three numbers from the last full LiDAR rotation:
the closest return **ahead** (30° either side of straight ahead), on the **left** and on the
**right** (the 70° beyond that on each side). Then:

| Step | When | What |
|---|---|---|
| Wait for LiDAR | the first 2 seconds of a chase | stand still while the LiDAR spins up |
| Cruise | nothing close ahead | drive forward; veer away from a side closer than 70 cm; slow a little if something is within 70 cm ahead |
| Turn | something within 35 cm ahead | turn on the spot towards the side with more room, until the way is clear |
| Back out, turn away | a wheel stalled | reverse half a second, turn, try again |
| Blind | no LiDAR data | slow forward runs with alternating turns; the stall check is the only sense |

It runs away from nothing in particular. It does not know where the person is.

## What is weak about it

1. **It does not flee from the person.** It only avoids things. If you stand still, it wanders off;
   if you approach from the side, it may turn towards you.
2. **Three numbers throw away most of the scan.** A chair leg and a wall look the same. Gaps it
   could drive through are not seen as gaps.
3. **It cannot see behind decisions.** Turning "towards the roomier side" uses only the 70° arcs, so
   it can turn into a dead end.
4. **It can oscillate** in a corner: turn left, see the other wall, turn right.
5. **It has no memory.** It will revisit the same dead end.
6. **Fixed speeds.** It does not slow for tight spaces or speed up in the open, and the two motors
   differ by about 2%, so "straight" drifts.
7. **Low obstacles and drops are invisible.** The LiDAR sees one horizontal slice. A cable, a rug
   edge or a stair is not in it.
8. **Tuning needs a reflash.** Speeds and distances are constants in `config.h`.

## Step 0: make the current behaviour trustworthy

Before adding anything:

1. **Set the LiDAR's direction.** `LIDAR_FRONT_OFFSET_DEG` and `LIDAR_ANGLES_CLOCKWISE` in `config.h`
   are placeholders. Until they are measured, "ahead", "left" and "right" may be wrong. The method is
   in `firmware/robot/README.md` under Tuning.
2. **Find the arcs the shell blocks.** With the robot in open space, log every return closer than
   30 cm with its bearing. Bearings that always show a return are the robot's own body; they need a
   mask, not just the 15 cm minimum.
3. **Calibrate distance** with the `cal` command.
4. **Record a baseline.** Run five chases in the same room and note, from the dashboard, time to
   catch and distance, and by eye, how often it got stuck. Every later step is judged against this.

## Step 1: straight lines and smooth speed (encoders only)

*Why first:* everything else assumes the robot goes where it is told.

- **Heading hold.** While cruising, compare the two wheels' counts and trim one side so they match.
  A simple proportional correction on the count difference is enough. The gyro's yaw rate does the
  same job and is not fooled by wheel slip; use whichever is steadier.
- **Speed control.** Replace "duty = fraction of 6 V" with a target speed in metres per second and a
  PI loop per wheel on the encoder rate. The robot then holds speed as the battery sags and on
  carpet.
- **Ramps.** The slew limit already exists (`SLEW_PER_S`). Tune it so the body does not pitch on
  start and stop, watching `tilt` on the status line.

*Test:* drive 3 metres along a tape line; it should stay within a hand's width.

## Step 2: use the whole scan (gap finding)

*Why:* this fixes weaknesses 2, 3 and 4 at once.

Instead of three arcs, divide the rotation into 36 bins of 10° and keep the closest return in each.
Then steer towards the **widest run of bins that are all farther than a clearance distance**, not
just "the roomier side". This is the idea behind the Vector Field Histogram and "follow the gap"
methods, in its simplest form:

1. Mark each bin free if its closest return is beyond, say, 60 cm.
2. Find the widest run of free bins.
3. Steer towards the middle of that run. Turn rate is proportional to its bearing.
4. Speed is proportional to the clearance straight ahead, between a crawl and the cruise speed.

Add **hysteresis**: once a gap is chosen, keep it unless another is clearly better, which stops the
corner oscillation.

*Cost:* one array of 36 numbers and a loop over it per rotation. The ESP32 has room to spare.

*Test:* a corridor of boxes with one opening; it should find the opening without touching.

## Step 3: flee from the person

*Why:* this is the point of the robot.

The person is the thing that **moves**. Walls do not.

1. **Find what moved.** Keep the previous rotation's 36 bins. A bin whose distance changed by more
   than about 15 cm between rotations, after allowing for the robot's own motion, holds something
   moving. Allowing for the robot's motion is the hard part: start by only looking while the robot
   is turning slowly or stopped, or subtract the motion predicted from the encoders.
2. **Legs are narrow.** A person at 1 to 3 metres shows as one or two clusters 5 to 20 cm wide. A
   wall is a long run. Filter clusters by width.
3. **Track it.** Keep the bearing and distance of the best candidate and smooth it; a person does
   not jump across the room between rotations.
4. **Flee.** Combine with step 2: among the free gaps, prefer the one whose bearing is farthest from
   the person. When the person is close, raise the speed; when they are far, slow down or stop and
   wait, which also saves the battery.

The telemetry already has `nearest_cm` and `bearing_deg`. Once the person is tracked, send **their**
distance and bearing there instead of the nearest object, and the dashboard shows the chase.

*Test:* stand still, then walk towards it from different sides; it should always leave in a
direction away from you.

## Step 4: do not get cornered

- **Escape memory.** Remember the bearing of the last gap that led to a dead end (a stall or a turn
  of more than 150°) and avoid it for a few seconds.
- **Room to run.** Prefer gaps that are deep as well as wide: weight each gap by the distance of its
  farthest bin.
- **A way out before going in.** Do not enter a gap narrower than the robot plus a margin, even if
  it is the widest.

## Step 5: things the LiDAR cannot see

- **Bumps and tangles** already show as stalls. Count where they happen relative to the last turn to
  avoid repeating them.
- **Being pushed or dragged** shows as the encoders and the gyro disagreeing. The same comparison
  detects wheel slip on a rug.
- **Drops** (stairs) need a downward sensor. Without one, keep the robot in a room with no stairs,
  and say so in the demo notes.

## Step 6: tune from the app instead of reflashing

The project rule is that tunable values live in Home Assistant. For the robot that means a retained
settings message, the same pattern as `hub/alarm/schedule`:

- Home Assistant publishes `hub/robot/settings` (retained) with, for example,
  `{"max_speed": 0.5, "lift_tilt_deg": 25, "clearance_cm": 60}`, from `input_number` helpers.
- The robot reads it on connect and whenever it changes, clamps each value to a safe range held in
  the firmware, and uses it.
- The hard limits stay in `config.h`: the 6 V motor cap, the battery cut-off, the stall check.

This needs a contract change in `docs/robot-integration.md`, a small package in `homeassistant/`,
and a parser in the firmware. It makes every step above much faster to tune.

## How to work on it

- **One step per branch,** tested against the step 0 baseline before the next.
- **Log before deciding.** Add what the new logic sees (bins, chosen gap, person bearing) to the
  status line first, watch it with the wheels off the ground, and only then let it drive.
- **Keep the behaviour separate from the hardware.** `chase.cpp` reads `lidar::` and `drive::` and
  nothing else. Kept that way, the decision logic can be moved into plain C++ functions and tested
  on the PC with recorded scans, the same way the hub's logic is tested without a broker.
- **Record scans.** A build flag that prints each rotation's 36 bins over serial gives data to
  replay. Tuning on recordings is quicker and safer than tuning on a moving robot.
- **Wheels off the ground first,** every time the driving logic changes.

## A realistic order for the time available

With the demo on December 1st: step 0 is required. Step 1's heading hold and step 2's gap finding
are each about an evening and make the chase look deliberate. Step 3 is the impressive one and the
riskiest; attempt it only once steps 0 to 2 are solid, and keep the previous build ready to flash
back.
