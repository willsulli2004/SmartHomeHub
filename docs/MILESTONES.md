# Smart Home Hub — Milestones

Status values: `planned` · `in progress` · `in review` · `merged`.
Each milestone gets a doc in `docs/milestones/` when it is done (see CLAUDE.md).

## Overview

### Phase A — CpE417 demo (due December 1st, 2026)
| # | Milestone | Target | Status |
|---|---|---|---|
| M0 | Repo and workflow | Nov 20 | merged |
| M1 | Home Assistant on Proxmox | Nov 21 | merged |
| M2 | ESPHome satellite base | Nov 23 | merged |
| M3 | Satellite controls and feedback | Nov 24 | in review |
| M4 | Core voice | Nov 25 | planned |
| M5 | Alarms | Nov 27 | planned |
| M6 | Robot link and local server | Nov 29 | planned |
| M7 | Demo hardening and report | Dec 1 | planned |

Target dates are a plan, not promises. Thanksgiving is November 26th. If Phase A slips, cut from M3's
extras and M6's analytics before cutting alarms or the robot link.

### Phase B — Jarvis platform (after December 1st)
| # | Milestone | Status |
|---|---|---|
| M8 | Jarvis Core | planned |
| M9 | Plugin SDK | planned |
| M10 | Alarms become a plugin | planned |
| M11 | Music and "guess the song" | planned |
| M12 | Sports plugin | planned |
| M13 | Proactive flows | planned |
| M14 | ChatGPT route for family | planned |

---

## Phase A

### M0 — Repo and workflow
**Goal:** a clean repo and a repeatable backup → update → test routine before any feature work.
- **Repo setup:**
  - `.gitignore` covering secrets, `.venv/`, ESPHome build output, `__pycache__/`, IDE files.
  - The repo layout from CLAUDE.md.
  - `firmware/satellite/secrets.example.yaml`.
  - Legacy Arduino tests in `tests/hardware/` (already copied in the initial commit).
- **Tooling:** ESPHome CLI installed in `.venv` (Python 3.12, version pinned in `requirements-dev.txt`);
  `gh` authenticated for PRs.
- **Deploy docs:** the backup/rollback routine written up in `docs/setup/deploy.md`, including git tags
  for firmware versions (`sat-hub-vN`).
- **Done when:** a test PR can be opened and merged, and the deploy doc is reviewed.

### M1 — Home Assistant on Proxmox
**Goal:** Home Assistant running on the mini PC with everything the satellite needs.
- **Install:** Home Assistant OS as a VM on Proxmox, with a fixed IP (DHCP reservation) and automatic
  backups.
- **Add-ons:** Mosquitto broker (with users for the hub, the robot and services), Whisper, Piper.
- **Voice:** an Assist pipeline using Whisper and Piper.
- **Docs:** setup guide `docs/setup/home-assistant.md`. Will does the install; Claude writes the guide
  and documents what was done. (Home Assistant OS was already running when M1 started, so the guide
  records the existing VM and covers the remaining setup.)
- **Done when:** HA is reachable on the network, a typed and a spoken test command work in HA's own
  Assist dialog, MQTT accepts a test publish/subscribe, and a backup exists.

### M2 — ESPHome satellite base
**Goal:** the satellite runs ESPHome, talks to HA, and updates over Wi-Fi from now on.
- **Hardware config:** board config for the N16R8 (octal PSRAM, 16MB flash), Wi-Fi, HA API with
  encryption, OTA with a password.
- **Audio:** the mic on its own I2S bus and the DAC/amp on another, at the levels proven in the Arduino
  tests. The speaker cap from hard rule 3 is enforced and verified.
- **Voice:** on-device wake word "Hey Jarvis" plus the voice assistant connected to the M1 pipeline.
- **Mute (software):** GPIO45 latching button. While muted, wake word detection stops and no audio
  leaves the device.
- **First flash** over USB; every later update goes OTA. Tag `sat-hub-v1`.
- **Done when:**
  - "Hey Jarvis, what time is it?" gets a spoken answer.
  - Mute blocks the wake word.
  - A second build goes on over OTA.
  - Rolling back to `sat-hub-v1` works.

### M3 — Satellite controls and feedback
**Goal:** the satellite feels like a finished device.
- **LED states:** idle, listening, thinking, speaking, muted, timer/alarm ringing, error. Brightness is
  capped for the strip's current budget.
- **Encoder:** a custom ESPHome external component (C++) for the seesaw. Rotation changes volume by 2%
  per click, and the press stops a timer/alarm or the current response. The encoder's pixel shows status.
  **Enclosure limit (found in M2):** the current enclosure gives no way to press the knob, so M3
  delivers rotation only. The press comes back when the enclosure is changed.
- **HA entities:** volume, mute state and LED brightness exposed in Home Assistant.
- **Sounds:** short feedback tones for volume changes and mute on/off.
- **Amp MUTE on GPIO4:** cleared by Will's measurement, built in M3, wired and working. It removes the
  idle hum.
- **Done when:** every state shows correctly, the knob and HA volume stay in sync, and the cap holds at
  100%.

### M4 — Core voice
**Goal:** the everyday assistant basics work.
- **Device control:** HA's built-in commands, on real devices or test helpers.
- **Timers:** set, cancel and check timers. They ring on the satellite with the LED state, and stop by
  voice or knob.
- **Questions:** answered by Claude through HA's Anthropic integration, with local handling of commands
  preferred. Responses are short and written for speech.
- **Done when:**
  - device commands, timers and a general question each work by voice
  - device commands still work with the internet unplugged
  - questions fail gracefully with the internet unplugged

### M5 — Alarms
**Goal:** the CpE417 alarm feature on the hub side.
- **Alarm data:** stored in Home Assistant (helpers), so both voice and the dashboard (M6) can set them.
- **Voice commands:** "set an alarm for 7 AM", "cancel my alarm", "when is my alarm".
- **When an alarm fires:**
  - it rings on the satellite (loud, repeating, within the cap) with the LED alarm state
  - it publishes `hub/alarm/start` with an `alarm_id`
- **Stopping:** by knob press, by voice, by `alarmbot/caught`, or by a timeout. Every stop publishes
  `hub/alarm/stop` with the reason.
- **Robot-independent:** the alarm works the same when the robot is offline.
- **Known risk:** the wake word may not hear "stop" over a loud alarm without echo cancellation, so the
  knob press is the guaranteed stop.
  **Open (found in M2):** the knob cannot be pressed in the current enclosure, so M5 needs a
  different guaranteed stop. Candidates: turning the knob, or the mute button. Decide when planning M5.
- **Done when:** an alarm set by voice fires on time, every stop path works, and the MQTT messages appear
  on the broker.

### M6 — Robot link and local server
**Note:** the alarm robot (Runaway Chase Bot) is a separate ESP32 node being built in parallel by its own
agent. Its design is discussed separately; this milestone covers only how the hub and robot connect.
- **Broker:** Mosquitto inside Home Assistant is the only broker. Nothing goes to a public cloud.
- **Robot setup guide:** `docs/robot-integration.md` brings any robot online easily:
  - broker address and credentials
  - the topic list and message formats (the MQTT contract)
  - delivery guarantees and online/offline status
  - the connection order
  - a bring-up checklist
- **Mock robot:** `tools/mock-robot/` behaves like the robot on the broker, so the hub side can be tested
  without the real robot.
- **Alarm analytics service:** `services/alarm-analytics/`, running in its own container on Proxmox. It:
  - filters IMU and distance readings to reject false catches
  - computes time-to-catch and distance traveled
  - keeps rolling 7-day averages of wake-up delay
  - flags low battery from the voltage trend
  - publishes results to HA through MQTT discovery
- **Home Assistant dashboard:** live robot status and battery, wake-up history charts, and remote alarm
  setting.
- **Done when:** a full alarm → chase → caught → stop cycle works with the mock robot, the dashboard
  updates, and the guide is ready for the robot agent.

**Draft MQTT contract** (finalized in `docs/robot-integration.md`; payloads are JSON, timestamps ISO 8601 UTC):

| Topic | Direction | QoS / retain | Payload |
|---|---|---|---|
| `hub/alarm/start` | hub → robot | 1 / no | `{"alarm_id", "ts"}` |
| `hub/alarm/stop` | hub → robot | 1 / no | `{"alarm_id", "reason": "caught\|user\|timeout", "ts"}` |
| `alarmbot/status` | robot → all | 1 / retained | `{"state": "online"}`; Last Will (sent automatically on disconnect): `{"state": "offline"}` |
| `alarmbot/state` | robot → all | 1 / retained | `{"state": "idle\|fleeing\|caught\|error", "ts"}` |
| `alarmbot/telemetry` | robot → all | 0 / no | `{"alarm_id", "ts_ms", "imu", "dist_cm", "odom_m", "battery_v"}` |
| `alarmbot/caught` | robot → hub | 1 / no | `{"alarm_id", "ts", "chase_ms", "distance_m"}` |

### M7 — Demo hardening and report
**Goal:** a reliable demo and the material for the report.
- **End-to-end runs:** with the real robot, plus failure cases:
  - robot offline
  - broker restart
  - Wi-Fi drop mid-alarm
  - a false "caught" from a bump
- **Demo materials:** a demo script with a fallback plan (mock robot), and final backups and tags.
- **Report material:** architecture diagram, data flow, milestone summaries, test results.
- **Done when:** three clean full demo runs in a row.

---

## Phase B

### M8 — Jarvis Core
- **Service:** a Python service in `jarvis-core/`, plus a small HA custom integration that registers it as
  the conversation agent.
- **Routing order:**
  1. active plugin session
  2. plugin trigger
  3. HA's built-in commands
  4. LLM fallback
- **Follow-ups:** supports continued conversations, so plugins can ask follow-up questions and HA's
  "start conversation" action works.
- **Text console:** test conversations by typing.

### M9 — Plugin SDK
- **Format:** a plugin is a folder with a manifest and a Python file.
- **SDK functions:** `say`, `ask`, `play_media`, HA service calls and state reads, scheduler, persistent
  state, semantic events.
- **Developer tools:** hot reload and a test harness, so plugins are easy to write in PyCharm.

### M10 — Alarms become a plugin
- Move the M5 alarm logic onto the plugin platform without changing the MQTT contract. This proves the
  SDK on a real feature.

### M11 — Music and "guess the song"
- **Music library:** set up a library source (to be decided) through Music Assistant.
- **Game plugin:**
  1. play a random clip
  2. ask for the song
  3. fuzzy-match the answer against the title and artist
  4. keep score, with multiple rounds

### M12 — Sports plugin
- **Heads-up:** announcements before your teams' games.
- **"Keep me updated":** subscribes to a game and announces score changes until it ends or you say stop.

### M13 — Proactive flows
- **Calendar + traffic:** a heads-up on when to leave, using a poll-and-compare pattern.
- **Arrival welcome:** a greeting with a follow-up question when you get home.

### M14 — ChatGPT route for family
- The "ask ___" trigger routes general questions to ChatGPT for family members.

---

## Backlog
- Demo mode: the satellite opens its own hotspot and serves a simple web page for showing off features
  from a phone, without the home network (asked for during M2; a candidate for M7 if time allows)
- Cut from M3 to protect the December 1st deadline:
  - feedback tones for volume changes and mute
  - the encoder's own status light
  - LED brightness control in Home Assistant
  - the encoder press (needs a new enclosure)
  - removing and testing the three unproven M2 measures (LED frame re-send, 500 ms ring delay,
    lowered DAC pin drive)
- Custom wake word (train a model for the hub's own name)
- Automatic deploy on merge via the mini PC over Tailscale
- Echo cancellation and ducking
- Music streaming improvements
- Enclosure with diffused LEDs
- Camera with a local vision model
- More satellites around the house

## Decisions
- **Satellite firmware:** ESPHome plus custom C++ components; the deep customization lives in
  Jarvis Core (Python).
- **Updates:** OTA, using the backup → update → test routine. Claude compiles; Will flashes.
- **Home Assistant:** HAOS as a VM on Proxmox on the mini PC.
- **Robot traffic:** the MQTT broker is local (Mosquitto in HA). The robot dashboard is a Home Assistant
  dashboard.
- **Wake word:** "Hey Jarvis" for now.
- **Camera:** out of scope; camera data never leaves the home.
- **Questions:** may go to the Claude API as text only.
- **Plugins:** written in Python.

## Open questions
- Does the CpE417 rubric accept a self-hosted broker as the "cloud" component?
- Where does the robot's code live, and how far along is the robot?
- Music library source (decide at M11).
