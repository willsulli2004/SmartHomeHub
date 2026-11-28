# CLAUDE.md — Smart Home Hub

## Project
The Smart Home Hub is the start of Will's local-first, Jarvis-style smart home on Home Assistant. Its
first device is a voice satellite (ESP32-S3) that controls the home, answers questions, sets timers and
alarms, and will later run custom plugins (games, sports updates, proactive announcements).

- **Courses:** this is Will's independent study at UNLV and part of his CpE417 final project, which is
  **due December 1st, 2026**. Until then, Phase A in `docs/MILESTONES.md` is the critical path; stay
  inside the current milestone's scope.
- **CpE417 robot:** the final project pairs the hub with an alarm robot that talks to it over MQTT.
  Since November 27th, 2026 the robot's firmware lives in this repo too (`firmware/robot/`), beside
  the hub side and the MQTT contract (`docs/robot-integration.md`). It is a separate device with its
  own pins and rules: `firmware/robot/README.md` and `AlarmBot/config.h`, not the hub's pin map below.
- **Privacy:**
  - All audio, speech processing and data stay on the home network.
  - No public cloud services, with one approved exception: the text of a question (never audio) may go
    to the Claude API for answering.
- **Camera:** out of scope for now. Do not add camera code.

## Architecture
1. **Satellite:** ESPHome firmware with Will's own C++ external components where needed (encoder, LED
   states, alarm ringing). It handles on-device wake word ("Hey Jarvis"), mic and speaker audio, LEDs,
   the volume knob and the mute button. Updates go over the air (OTA).
2. **Home Assistant (HAOS VM on Proxmox, mini PC):**
   - voice pipeline: Whisper STT and Piper TTS (Wyoming), plus a conversation agent
   - device control, timers and automations
   - Mosquitto MQTT broker
   - dashboards
3. **Local services (Python, in this repo):**
   - Phase A: `services/alarm-analytics/` processes robot telemetry and publishes results to HA over MQTT.
   - Phase B: `jarvis-core/` is Will's own conversation agent and plugin platform.

Follow Will's four-layer design: devices → HA entities → reusable scripts → semantic events → pluggable
triggers. New features fire or consume semantic events instead of wiring triggers straight to devices.

## How to work with Will

### Before every milestone
1. Read `docs/MILESTONES.md` and the docs of completed milestones in `docs/milestones/`.
2. Restate the plan:
   - the goal
   - what is in and out of scope
   - the files you expect to add or change
   - how it connects to existing parts and the greater project
   - how it will be tested
3. Ask Will about every loose end, open question or assumption.
4. **Do not write code until Will confirms the plan.**

### During a milestone
- Branch `milestone/MNN-short-name` off the latest `main`. Never commit to `main`; never force-push.
- Make small, focused commits with imperative messages.
- If something forces a change to the agreed plan, stop and ask instead of improvising.
- Ask before adding any new library, ESPHome external component, HA add-on or other dependency.

### After every milestone
1. Run the checks in Testing.
2. Write `docs/milestones/MNN-short-name.md` (template below).
3. Update the milestone's status in `docs/MILESTONES.md`. You may edit `docs/MILESTONES.md` whenever
   needed; call out significant changes in the PR.
4. Open a PR with `gh pr create`:
   - **title:** `MNN: <name>`
   - **body:** summary, link to the milestone doc, the backup + OTA + test steps, open questions
5. Stop and wait. Will backs up, flashes, tests on hardware, reviews and merges. **Never merge a PR
   yourself.** If testing finds a problem, fix it on the same branch.

### Milestone doc template
    # MNN — <name>
    Status: <planned | in progress | in review | merged>   Branch: <branch>   PR: <link>

    ## Goal
    ## What was built
    One entry per file added or changed: path — what changed and why.
    ## How it connects to the rest of the project
    Which parts it uses or provides, data flow, and where it sits in the architecture.
    ## How to deploy
    Backup steps, then the exact OTA or install commands.
    ## How to test
    Hardware checklist for Will, with expected logs or HA behavior and pass criteria.
    ## Deviations from the plan
    ## Known limitations / follow-ups

## Deploy flow: backup, update, test
Will's routine for every milestone that changes the satellite or Home Assistant:
1. **Back up:**
   - Take a full Home Assistant backup.
   - Make sure the currently running firmware is tagged in git (`sat-hub-vN`) so it can be rebuilt.
2. **Update:** OTA-flash the satellite and/or apply the HA changes.
3. **Test:** run the milestone's checklist.
4. **Roll back if needed:** check out the previous tag and OTA it, or restore the HA backup. USB flashing
   is the last-resort recovery.

**Claude never flashes the satellite or the robot, and never changes the live Home Assistant instance.** It compiles, then
gives Will the exact commands to run. Will may change this rule later.

## Testing
Claude cannot hear the speaker or see the LEDs. Hardware verification is Will's job, and every PR needs
an explicit test checklist.

- **ESPHome compile check:** `esphome compile firmware/satellite/sat-hub.yaml`. For CI-style checks without
  real secrets, use `firmware/satellite/secrets.example.yaml` copied to a temp location; never create or
  edit the real `secrets.yaml`.
- **OTA command for Will:** `esphome run firmware/satellite/sat-hub.yaml --device sat-hub.local`.
  Use the satellite's IP address if mDNS fails.
- **Robot firmware compile check:** `.\.venv\Scripts\python.exe firmware/robot/robot.py compile --example`
  builds with the placeholder settings in `firmware/robot/.env.example`. Claude cannot see the robot
  move; every robot change needs a test list for Will, and the first run of any change to the
  driving logic is with the wheels off the ground.
- **Robot upload commands for Will:** `... robot.py usb COMx` over the cable, `... robot.py ota` over
  Wi-Fi (the robot must be idle).
- **Home Assistant config:** `.\.venv\Scripts\python.exe -m pytest homeassistant` checks the custom
  sentences (with `hassil`, Home Assistant's own matcher) and the template logic. It cannot check that
  the live instance loads a package; Will runs "Check configuration" after copying.
- **All Python tests at once:** `.\.venv\Scripts\python.exe -m pytest` from the repo folder runs the
  Home Assistant, mock robot and analytics tests (`pytest.ini` lists them).
- **Python:** `pytest` for every service and plugin. Logic must be testable without hardware: mock MQTT,
  fake HA responses, the mock robot. Jarvis Core gets a text console (Phase B) so conversations can be
  tested by typing.
- **Legacy Arduino component tests** live in `tests/hardware/arduino/` and are kept as reference for
  re-checking hardware. Compile them with `arduino-cli` if needed:

      arduino-cli compile --fqbn "esp32:esp32:esp32s3:PSRAM=opi,FlashSize=16M,PartitionScheme=app3M_fat9M_16MB" <sketch>

## Hard rules: never break these
1. **GPIO45 is a strapping pin.** It must be low at boot, otherwise the chip selects 1.8V flash.
   - Never pull it high, never add an external pull-up, never drive it as an output.
   - Nothing is connected to it in the rebuilt hub (the mute button moved to GPIO5). Keep it that way
     unless Will decides otherwise.
2. **USB-C PD (HUSB238) stays at 12V.** Never 15V or 20V. The MAX9744's maximum is 14V.
3. **Speaker level is capped at 0.5 of digital full scale (−6 dBFS).** The DAC's 2.1 Vrms full scale
   overdrives the amp.
   - Every volume path must stay at or under the cap: voice, knob, HA, media, alarms.
   - Verify how ESPHome's volume maps to amplitude before relying on it.
4. **Secrets live only in gitignored files.**
   - ESPHome: `firmware/satellite/secrets.yaml`.
   - Python services: `.env` files.
   - Robot firmware: `firmware/robot/.env`, and the header `robot.py` generates from it
     (`firmware/robot/AlarmBot/secrets.h`).
   - Legacy Arduino tests: `HubSecrets.h` in the Arduino libraries folder.
   - Never put Wi-Fi or MQTT credentials, API keys, OTA passwords or encryption keys in code, docs,
     commits, PR text or logs. Never open or print the real secrets files.
5. **Network addresses come from secrets or config, never hard-coded.** That covers Home Assistant, the
   MQTT broker and any other host.

## Hardware constraints
- **MAX9744 I2C:** its I2C lines are cut and it runs in analog volume mode (a pot sets the max level).
  Never write I2C code for the amp.
- **MAX9744 MUTE:** on GPIO4, open-drain only: the firmware pulls it to ground to mute, or lets go. Never
  drive it high. Will measured it on November 22nd, 2026: the pin floats between about 0 and 3V (under
  the 3.6V limit), and connecting it to ground mutes the amp, including the idle hum. The firmware has
  driven GPIO4 since M3 (muted when idle, released for each sound). Will fitted the wire and tested it
  on November 23rd, 2026: no hum when idle, and no reply has its first word cut off.
- **LED ring current:** the 24-LED WS2812 ring is on its own buck with a ~1.2A budget. 24 LEDs at full
  white would draw ~1.44A, so cap brightness in software. The firmware caps every channel at 80%
  (worst case 1.15A).
- **GPIO48:** the devkit's onboard RGB LED.
- **Pins never to use:**
  - GPIO33–37: used by the OPI PSRAM.
  - GPIO0, 3, 46: strapping pins.
  - GPIO19/20: native USB.
  - GPIO43/44: UART0.
- **Camera pins (GPIO4–18):** free, but ask before assigning them. GPIO4 is reserved for the amp MUTE and
  GPIO5 is the mute button.

## Hardware and pin map
| Component | Interface | Pins / settings |
|---|---|---|
| ICS-43434 mic | I2S RX, 16 kHz, 24-bit data in a 32-bit slot, left channel (SEL→GND) | BCLK 42, WS 1, DIN 2 |
| PCM5102 DAC → MAX9744 (left in; 4Ω 20W speaker on left out) | I2S TX, 16-bit stereo | BCK 40, WS 38, DOUT 39 |
| Seesaw rotary encoder (0x36) | I2C bus 0, read by `components/seesaw_encoder/`, `inverted: true` | SDA 21, SCL 47; seesaw switch pin 24, seesaw pixel pin 6 (switch and pixel unused) |
| MAX9744 MUTE | open-drain output, low = muted | GPIO4 |
| DFRobot WS2812 RGB LED ring, 24 LEDs | addressable LED | DATA 41 |
| Mute button (latching) | GPIO to GND, internal pull-up, debounced; latched = muted | GPIO5 |

The pin map above is the rebuilt hub (new ESP32, November 22nd, 2026). The first build used DAC BCK 39,
WS 40, DOUT 38, a 71-LED WS2812B strip, and the mute button on GPIO45.

Proven in the Arduino tests:
- **Mic:** +30 dB digital gain (shift 11 from the 32-bit slot) gave good far-field pickup in open air.
- **Encoder:** 2% volume per click.

Learned in M2 on the assembled hub (details in `docs/milestones/M02-esphome-satellite-base.md`):
- **Mic gain:** the Arduino value clips in the assembled hub and makes the wake word unreliable. ESPHome
  uses `mic_gain_factor: 4` (+12 dB). Tune it with the Mic Peak sensor: speech should peak between about
  −20 and −6 dB and never reach 0.
- **LED ring:** it needs the Adafruit NeoPixel bit timings (400/850/800/450 ns, 300 µs reset), not
  ESPHome's built-in WS2812 timings, and the firmware must always drive the data line.
- **Encoder press:** the current enclosure gives no way to press the knob. Only rotation is usable until
  the enclosure is changed, so nothing may depend on the press.

Board: ESP32-S3-DevKitC-1 N16R8 clone, 16MB flash, 8MB octal PSRAM. Hostname `sat-hub`.

Power: HUSB238 at 12V feeds the MAX9744 VDD and two MPM3610 5V bucks.
- Buck A: LED ring.
- Buck B: devkit 5V (logic).
- Star grounding.

Will swapped the two bucks on November 23rd, 2026 (Buck A used to feed the devkit and Buck B the LEDs).
With Buck B on the LEDs, they froze on their last colour after spoken replies, on both hub builds;
after the swap the freeze stopped. The bucks' output voltages were not measured. The likely cause is the
LED supply voltage: WS2812 LEDs need the data signal to reach about 70% of their supply, and the
ESP32's 3.3V signal is borderline at 5V. Do not swap the bucks back. If the freeze returns, measure the
LED supply first; a diode in the LED power lead or a level shifter on the data wire gives real margin.

## Code conventions
- **ESPHome:**
  - Keep `sat-hub.yaml` readable and split into packages under `firmware/satellite/packages/` by
    function: audio, voice, leds, controls, alarm.
  - Custom C++ goes in `firmware/satellite/components/<name>/` as ESPHome external components. No large
    inline lambdas.
- **Python:** 3.11+, type hints, small modules, `pytest` tests next to the code. Configuration comes from
  `.env` or config files.
- **Home Assistant config:** kept in `homeassistant/` as packages (helpers, scripts, automations, custom
  sentences, dashboards) so it's versioned. Each milestone doc says how to apply it to the live instance.
- **Tunable settings live in the app:** anything Will might want to tune (LED colours, timer and alarm
  volumes, timeouts and the like) is a Home Assistant entity with a sensible default, not a value
  hard-coded in firmware: a `number` or colour-picker `light` on the satellite, or a helper in
  `homeassistant/`. Safety limits stay hard-coded: the speaker cap, the LED current cap and the GPIO
  rules.
- **Complete files only:** never leave "paste X here" placeholders.

## Repo layout
    CLAUDE.md
    docs/MILESTONES.md            milestone list and status
    docs/milestones/              one doc per completed milestone
    docs/setup/                   setup guides (Home Assistant, Proxmox, ...)
    docs/robot-integration.md     robot setup guide + MQTT contract (M6)
    docs/robot-navigation.md      how the robot drives today and how to refine it
    firmware/robot/               alarm robot firmware (Arduino sketch in AlarmBot/), robot.py to build
                                  and upload, hardware test sketches in tests/
    firmware/satellite/           ESPHome config, packages/, components/, includes/ (small C++
                                  helpers), sounds/, secrets.example.yaml
    hardware/enclosure/           STEP files for the 3D printed enclosure
    homeassistant/                HA packages, custom sentences, dashboards, tests/
    services/alarm-analytics/     robot telemetry processing (M6); runs in its own Proxmox container
    jarvis-core/                  conversation agent + plugin platform (Phase B)
    tools/mock-robot/             mock robot for testing the hub side (M6)
    tests/hardware/arduino/       legacy Arduino component tests
    tests/hardware/pc/            PC side of the legacy tests

Folders are created by the milestone that first needs them.

## Robot rules
These apply to `firmware/robot/` only. The details are in `firmware/robot/AlarmBot/config.h`.
- **Motor voltage:** the motors are rated 6 V on a pack that reaches 8.4 V. Duty is always scaled by
  6 V over the battery voltage. Never write a raw duty.
- **Speed cap:** `MAX_SPEED` is a hard limit. Do not raise it without Will saying so.
- **Stall check stays on:** a stalled motor can draw more than the TB6612's 1.2 A continuous rating.
- **Battery cut-off:** no driving at or below 6.4 V.
- **LiDAR power sequence:** wait 2 s after EN goes high; before cutting power, end Serial1 and set
  GPIO47 to input so the TX line does not back-power it.
- **Pins never to use on the robot:** GPIO 9, 10, 13, 14 (dead solder stubs), 0/3/45/46 (strapping),
  19/20 (USB), 43/44 (USB-UART), 35–37 (PSRAM), 48 (RGB LED).
- **No motion during a Wi-Fi update,** and no update during a chase.

## Out of scope unless a milestone says otherwise
Camera, music streaming beyond what a milestone defines, echo cancellation, enclosure work, automatic
deploys, multiple satellites.
