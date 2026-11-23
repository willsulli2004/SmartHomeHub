# M02 — ESPHome satellite base
Status: in review   Branch: `milestone/M02-satellite-base`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/4

## Goal
The satellite runs ESPHome, talks to Home Assistant, and updates over Wi-Fi from now on.

## Where it stands
Firmware 0.3.6 on the rebuilt hub: "Hey Jarvis" is heard from across the room, questions are answered
aloud, the LED ring shows listening and speaking, mute works, and updates go over Wi-Fi.

Will's results on November 23rd, 2026: the wake word, repeat and distance tests, the 100% volume
check, the mute button, the OTA update to 0.3.6 and the rollback to `sat-hub-v3` all passed. Test 5,
the Mic Peak reading during normal speech, was not reported as a number; the wake word working from
across the room without dropping out is the evidence that the gain is right.

## What was built
- `firmware/satellite/sat-hub.yaml` — new. Board (ESP32-S3 N16R8, 16MB flash, octal PSRAM), Wi-Fi with
  a recovery hotspot, encrypted Home Assistant API, OTA with a password, logging on the native USB
  port, a firmware version, and the list of packages.
- `firmware/satellite/packages/audio.yaml` — new. Two I2S buses, the ICS-43434 microphone, the PCM5102
  output, the media player that enforces the speaker level cap, and a script that lowers the drive
  strength of the DAC's signal pins.
- `firmware/satellite/packages/voice.yaml` — new. On-device "Hey Jarvis" wake word, the voice
  assistant, the microphone gain as one setting, and two microphone level sensors.
- `firmware/satellite/packages/controls.yaml` — new. The mute button on GPIO5 and the mute scripts.
- `firmware/satellite/packages/leds.yaml` — new. Status colours on the 24-LED ring, its brightness
  cap, and a once-a-second re-send of the current frame.
- `firmware/satellite/secrets.example.yaml` — changed. The placeholder API key was all zeros, which
  ESPHome 2026.11 rejects; it is now an obviously fake non-zero key.
- `firmware/satellite/.gitignore` — new. Written by ESPHome; repeats the repo's rules for
  `.esphome/` and `secrets.yaml`.
- `docs/setup/deploy.md` — changed. The two Windows build-folder variables, tagging the tested
  commit before merge, the log command, and the right USB port.
- `CLAUDE.md` — changed. The rebuilt hub's pin map, the LED ring, and what this milestone learned
  about mic gain, LED timings and the encoder.
- `docs/MILESTONES.md` — M1 set to `merged`, M2 set to `in review`, a demo mode idea added to the
  backlog, and notes on M3 and M5 that the encoder cannot be pressed in the current enclosure.
- `docs/milestones/M01-home-assistant-on-proxmox.md` — status set to `merged`.
- `docs/milestones/M02-esphome-satellite-base.md` — new. This doc.

No custom C++ component and no external components were needed. Everything used ships with ESPHome
2026.11.0. Three short lambdas are used where ESPHome has no action for the job.

### Hardware this firmware is for
The hub was rebuilt with a new ESP32 on November 22nd, 2026, partway through this milestone.

| Function | Pins / settings |
|---|---|
| Mic I2S | BCLK 42, WS 1, DIN 2 |
| DAC I2S | BCK 40, WS 38, DOUT 39 |
| LED ring | GPIO41, DFRobot 24-LED WS2812 ring |
| Mute button | GPIO5 to ground, input with the internal pull-up |
| Encoder | SDA 21, SCL 47; not used by this firmware (M3) |

### Speaker level cap (hard rule 3)
The rule says to verify how ESPHome's volume maps to amplitude before relying on it. From ESPHome
2026.11.0's source (`i2s_audio_speaker.cpp`, `speaker_media_player.cpp`):

- The I2S speaker applies software gain in decibels: `gain_dB = -49 × (1 − volume)`. Volume 1.0 is
  full scale; volume 0.5 is −24.5 dB, not half amplitude.
- The media player maps its 0–100% onto `volume_min`..`volume_max` before passing it to the speaker.
  Announcement volume changes go through the same mapping.

The cap of −6 dBFS is therefore a speaker volume of 0.877. `audio.yaml` sets `volume_max: 0.87`:

| Media player volume | Level | Fraction of full scale |
|---|---|---|
| 100% | −6.4 dBFS | 0.48 |
| 50% (start-up default) | −27.7 dBFS | 0.04 |

Every sound goes through the media player; nothing plays on the I2S speaker directly. This is proven
by reading the code and the config, not by measurement.

### LED ring current
The ring is the only load on its buck converter, which supplies about 1.2 A. 24 pixels at full white
would ask for about 1.44 A. `color_correct` scales every channel to 80% in the driver, so the worst
case is 1.15 A for white and 0.38 A for a single colour, whatever sets the colour.

### Microphone gain
`mic_gain_factor` is 4 (+12 dB). The Arduino tests' value of 32 (+30 dB) clipped in the assembled hub
and made the wake word unreliable; see "What this milestone learned".

## How it connects to the rest of the project
This is layer 1 of the architecture, the device.

- **Uses M1:** Home Assistant, Whisper, Piper and the `Jewel` Assist pipeline. Home Assistant connects
  to the satellite, so the firmware holds no Home Assistant address.
- **Data flow:** the wake word is detected on the device → speech is streamed to Home Assistant →
  Whisper → conversation agent → Piper → the reply plays through the capped media player.
- **Provides for M3:** the packages M3 extends. The status scripts (`status_light_listening`,
  `status_light_busy`, `status_light_idle`) are where the real LED states plug in, and the media
  player's 2% volume step is ready for the encoder.
- **Provides for M5:** alarms will ring through the same media player, so they inherit the cap.
- **Provides for every later milestone:** OTA updates and a tagged firmware to roll back to.

Entities in Home Assistant: Media Player, Mute, Status Ring, and under Diagnostic, Mic Level and
Mic Peak.

## How to deploy
All commands run in a PowerShell terminal, in the repo folder. `docs/setup/deploy.md` has the routine
and the one-time setup, including the two `ESPHOME_` folder variables this PC needs.

1. **Back up Home Assistant:** Settings → System → Backups → create a full backup and download it.
2. **Check the build folders are set.** This must print `C:\ESPHome\idf` and `C:\ESPHome\data`:

       $env:ESPHOME_ESP_IDF_PREFIX; $env:ESPHOME_DATA_DIR

3. **Get the branch:**

       git checkout milestone/M02-satellite-base
       git pull

4. **Flash over Wi-Fi:**

       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

A blank ESP32 needs its first flash over USB instead: connect the port labelled USB, find the COM port
in Device Manager, and use `--device COMx`. Then, in Home Assistant under Settings → Devices &
services → ESPHome, delete any old Satellite Hub entry, add the discovered device with the API
encryption key, and choose the Jewel assistant.

## How to test
Claude cannot hear the speaker or see the ring. Pass criteria are in bold.

**1. Boot and connection.** **Pass: the device page shows the satellite online, Firmware reads
`0.3.5 (ESPHome 2026.11.0)`, and the ring is off.**

**2. Wake word and answer.** Say "Hey Jarvis", then "what time is it?". **Pass: the ring turns blue,
then green while the answer is spoken, then off.** Done.

**3. Repeat and distance.** **Pass: six questions in a row all work, and it works from across the
room.** Done, with gain 4.

**4. Speaker cap.** Set the Media Player volume to 100% in Home Assistant and ask a question.
**Pass: the reply is loud and clean, with no harsh distortion.** Set it back to 50% afterwards. If it
distorts, stop and report it. Done: clean at 100%.

**5. Mic headroom.** While speaking normally from where you would stand, watch Mic Peak.
**Pass: it peaks between about −20 and −6 dB and never reads 0.**

**6. Tag.** With the tests above passing on the firmware that is running:

    git tag -a sat-hub-v3 3847a0b -m "Satellite firmware v3: rebuilt hub, wake word, LED ring, mute on GPIO5"
    git push origin sat-hub-v3

`3847a0b` is the commit holding firmware 0.3.5. Naming the commit means the tag lands on the right
firmware even if newer commits have been pulled since.

Two older tags exist and are not rollback targets for the finished hub:
- `sat-hub-v1` is firmware 0.2.0 for the first build's wiring. Do not flash it on the rebuilt hub: its
  audio pins are wrong for this hardware.
- `sat-hub-v2` is firmware 0.3.4. It was tagged just before the mute button moved, so it still expects
  the button on GPIO45. Everything else in it works on the rebuilt hub, but mute does not.

**7. OTA of a newer build.** Tell Claude the tag is pushed. Claude pushes firmware 0.3.6, a version
bump only. Then:

    git pull
    .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

**Pass: Firmware reads `0.3.6` and test 2 still works.** Done.

**8. Rollback.**

    git checkout sat-hub-v3
    .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

**Pass: Firmware reads `0.3.5` again and test 2 works.** Done. Then return to the newer build:

    git checkout milestone/M02-satellite-base
    .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

**9. Mute.** The button is on GPIO5, wired to ground only. Done. **Pass:
latched turns the ring red, turns the Mute entity on, and "Hey Jarvis" gets no reaction; unlatched
restores it; latching in the middle of a question stops the conversation.** This passed on the first
build with the button on GPIO45.

Checks Claude ran, using a temporary copy with the example secrets (the real `secrets.yaml` was never
opened):
- `esphome config` and `esphome compile`: pass for 0.3.5.

## What this milestone learned
These cost many test builds. They are recorded so they are not repeated.

- **Mic gain was the cause of the wake word going deaf.** At 32 times, the signal sat at the clipping
  limit (Mic Peak 0.0 dB) whenever the room was noisy or the hub had just spoken, and the wake word
  failed until it quietened. It looked like the microphone or the firmware stalling. The Mic Level and
  Mic Peak sensors made it visible.
- **This kind of LED needs custom bit timings.** The first build's strip ignored ESPHome's built-in
  WS2812 timings and responded only to the Adafruit NeoPixel library's (400/850/800/450 ns, 300 µs
  reset).
- **An undriven LED data line lights the LEDs at random.** It floats and picks up the audio signals
  beside it. The firmware must always drive it.
- **"Voice assistant end" fires before the reply is spoken.** Turning the ring off on that event made
  green invisible. The firmware waits until the voice assistant is idle.
- **Never set `timeout: never` on a speaker the media player uses directly.** The speaker never
  reports that it stopped, and the voice assistant then ignores the wake word.
- **ESP-IDF will not build on this PC from the default folders.** Microsoft Store Python and the repo
  path both exceed Windows' 260-character limit; `deploy.md` has the two variables that fix it. Run
  ESPHome from PowerShell, not Git Bash.
- **A frozen LED strip survives a software restart.** Several builds were judged while the first
  build's strip was already frozen from an earlier one, which gave false results. Power-cycle before
  judging an LED change.

## Deviations from the plan
- **The hub was rebuilt with a new ESP32** and some pins moved: the DAC from BCK 39 / WS 40 / DOUT 38
  to BCK 40 / WS 38 / DOUT 39. The 71-LED strip was replaced by a 24-LED ring on the same pin.
- **Status colours on the LEDs were added,** pulling a small part of M3 forward, because an undriven
  strip misbehaved and M2 had no other feedback. M3 still owns the full set of states and animations.
- **The speaker cap is `volume_max: 0.87`, not 0.5.** ESPHome's volume scale is in decibels.
- **Mic gain is 4 times, not the 32 proven in the Arduino tests.**
- **A firmware version, two mic level sensors and a Status Ring light were added** to make testing
  and tuning possible from Home Assistant.
- **`sat-hub-v1` was tagged on the first build at 0.2.0**, before these problems were found, and
  `sat-hub-v2` landed on 0.3.4, one commit before the mute button moved to GPIO5. Tags are never moved,
  so the rebuilt hub's rollback point is `sat-hub-v3` (0.3.5).
- **Two Windows environment variables were added** for the build.
- **The example API key changed**, because ESPHome rejects an all-zero key.
- **The speaker runs mono on the left channel at 48 kHz.** The amp only has its left input connected.
- **The mute button moved from GPIO45 to GPIO5** in the rebuilt hub. GPIO45 is a strapping pin, and
  using an ordinary pin removes the risk of a wiring mistake stopping the ESP32 from booting.

## Known limitations / follow-ups
- **The speaker hums when idle.** Tests with a diagnostic build on the first hub showed the hum in
  every state of the DAC's signal pins, quietest with the I2S output stopped, which is the current
  behaviour. Firmware cannot remove it. Parked by Will. The planned fix is the amp's MUTE pin on GPIO4
  (open-drain). Will measured it on the rebuilt hub: the pin floats between about 0 and 3V, and
  connecting it to ground silences the amp and the hum. He will wire it last, when the enclosure is
  finished; the firmware side is planned for M3.
- **Three firmware measures are unproven.** They were added while chasing the LED freeze and the
  deaf wake word, before mic gain turned out to be the cause of the second. They are harmless and the
  hub works with them, so they stay until M3 reworks the LEDs, when each can be removed and tested:
  - the ring's frame re-sent once a second (`leds.yaml`)
  - the 500 ms wait before the ring turns off after a reply (`voice.yaml`)
  - the lowered drive strength on the DAC pins (`audio.yaml`)
- **The LED freeze was never fully explained.** On both hubs the LEDs sometimes froze on their last
  colour after a spoken reply. It has not been seen since firmware 0.3.2, but that is a short record.
  The LED data pin (41) still sits beside the DAC's bit clock (40). If it returns, move the data wire
  to a pin away from 38–42 and add a level shifter or a diode in the LEDs' supply.
- **The encoder does nothing yet,** and in the current enclosure it cannot be pressed. M3 adds
  rotation only; the press waits for a new enclosure.
- **The cap is verified by reading code, not by measuring the output.**
- **No echo cancellation.** The wake word may not be heard while the satellite is speaking.
- **ESPHome warns that an OTA password is the older method** and suggests OTA encryption.
- **The Mute entity is read-only.** It shows the physical button; Home Assistant cannot mute the hub.
- **Demo mode** (hotspot plus a simple web page) is in the backlog, not in this milestone.
