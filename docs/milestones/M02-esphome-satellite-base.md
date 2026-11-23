# M02 — ESPHome satellite base
Status: in review   Branch: `milestone/M02-satellite-base`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/4

## Goal
The satellite runs ESPHome, talks to Home Assistant, and updates over Wi-Fi from now on.

## What was built
- `firmware/satellite/sat-hub.yaml` — new. Board (ESP32-S3 N16R8, 16MB flash, octal PSRAM), Wi-Fi with
  a recovery hotspot, encrypted Home Assistant API, OTA with a password, logging on the native USB
  port, a firmware version, and the list of packages.
- `firmware/satellite/packages/audio.yaml` — new. Two I2S buses (mic and DAC), the ICS-43434
  microphone, the PCM5102 speaker output, and the media player that enforces the speaker level cap.
- `firmware/satellite/packages/voice.yaml` — new. On-device "Hey Jarvis" wake word and the voice
  assistant, with the microphone gain as one setting.
- `firmware/satellite/packages/controls.yaml` — new. The GPIO45 mute button and the mute scripts.
- `firmware/satellite/packages/leds.yaml` — new. Solid status colours on the WS2812B strip, with a
  driver-level brightness cap for the strip's current budget.
- `firmware/satellite/secrets.example.yaml` — changed. The placeholder API key was all zeros, which
  ESPHome 2026.11 rejects; it is now an obviously fake non-zero key.
- `docs/setup/deploy.md` — changed. Tag the tested branch commit before merge, the firmware version,
  the log command, and the right USB port for flashing.
- `docs/MILESTONES.md` — M1 set to `merged`, M2 set to `in review`, and a **demo mode** idea added to
  the backlog.
- `docs/milestones/M01-home-assistant-on-proxmox.md` — status set to `merged`.
- `docs/milestones/M02-esphome-satellite-base.md` — new. This doc.

No custom C++ and no external components were needed. Everything used ships with ESPHome 2026.11.0.

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

### Pins used
| Function | Pins |
|---|---|
| Mic I2S | BCLK 42, WS 1, DIN 2 |
| DAC I2S | BCK 40, WS 38, DOUT 39 |
| Mute button | GPIO45, input, internal pull-up only, `ignore_strapping_warning: true` (not wired yet in the rebuilt hub) |
| LED ring (status colours) | GPIO41, 24 LEDs, every channel capped at 80% (worst case 1.15 A) |

## How it connects to the rest of the project
This is layer 1 of the architecture, the device.

- **Uses M1:** Home Assistant, Whisper, Piper and the `Jewel` Assist pipeline. Home Assistant connects
  to the satellite, so the firmware holds no Home Assistant address.
- **Data flow:** the wake word is detected on the device → speech is streamed to Home Assistant →
  Whisper → conversation agent → Piper → the reply plays through the capped media player.
- **Provides for M3:** the packages M3 extends. The status-light scripts (`status_light_listening`,
  `status_light_busy`, `status_light_idle`) are the points where the real LED states plug in, and the
  media player's 2% volume step is ready for the encoder.
- **Provides for M5:** alarms will ring through the same media player, so they inherit the cap.
- **Provides for every later milestone:** OTA updates and the first rollback point, `sat-hub-v1`.

## How to deploy
All commands run in the PC terminal, in the repo folder. See `docs/setup/deploy.md` for the routine.

### Before you start
1. **Back up Home Assistant:** Settings → System → Backups → create a full backup and download it.
2. **Check out this branch:**

       git fetch
       git checkout milestone/M02-satellite-base

3. **Open a new terminal** (restart PyCharm if you use its terminal), then check that both build
   folders are set. This must print `C:\ESPHome\idf` and `C:\ESPHome\data`:

       $env:ESPHOME_ESP_IDF_PREFIX; $env:ESPHOME_DATA_DIR

4. **Check the real secrets file.** `firmware/satellite/secrets.yaml` must hold your real Wi-Fi name
   and password, a fallback hotspot password, a real API encryption key and an OTA password. Keep a
   copy of the API key in your password manager; Home Assistant asks for it once.

### Stage 1: first flash over USB (firmware 0.2.0)
1. Connect the devkit's port labelled **USB** to the PC. The 12V supply may stay connected.
2. Find the COM port in Device Manager under **Ports (COM & LPT)**, for example `COM5`.
3. Flash, replacing `COM5` with yours. The first build takes 10 to 20 minutes:

       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device COM5

   If the upload cannot connect, hold **BOOT**, tap **RESET**, release **BOOT**, and run it again.
   After a flash started that way, tap **RESET** once to start the firmware.
4. The log should show the Wi-Fi connecting. Press Ctrl+C to stop watching.
5. **Add it to Home Assistant:** Settings → Devices & services. A discovered **Satellite Hub** device
   appears. Click **Add**, paste the API encryption key, and finish the voice assistant set-up
   wizard, choosing the **Jewel** assistant. If the wizard does not appear, open the device page and
   pick Jewel under **Assistant**.
6. Run tests 1 to 5 below.
7. If they pass, tag this firmware and push the tag:

       git tag -a sat-hub-v1 -m "Satellite firmware v1: ESPHome base, wake word, mute"
       git push origin sat-hub-v1

8. Tell Claude. Claude then pushes the second build (firmware 0.2.1) to this branch.

### Stage 2: second build over OTA (firmware 0.2.1)
1. Get the new commit:

       git pull

2. Flash over Wi-Fi. No USB cable is needed:

       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

   If `sat-hub.local` does not resolve, use the satellite's IP address from its Home Assistant device
   page.
3. Run tests 6 and 7 below.

## How to test
Claude cannot hear the speaker or see the LED. Pass criteria are in bold.

**1. Boot and connection.** After the flash, the device page in Home Assistant shows the satellite as
online. **Pass: Firmware reads the version just flashed, for example `0.2.2 (ESPHome 2026.11.0)`, the
entities Media Player and Mute exist, the strip is off, and there is no hum from the speaker when
idle, including before the first question.**

**2. Wake word and answer.** From about one metre, say "Hey Jarvis", wait for the strip to turn blue, then ask
"what time is it?". **Pass: the strip turns blue on the wake word, green while it works, the time is
spoken through the speaker, and the strip goes off.** Expected log lines include
`Detected 'Hey Jarvis'` and voice assistant state changes ending in idle.

**3. Far-field pickup.** Repeat test 2 from across the room at a normal speaking volume. **Pass: it
works at least 4 times out of 5.** If it misses, or if close speech is misheard, note which; the fix
is `mic_gain_factor` in `packages/voice.yaml`.

**4. Mute.** Latch the mute button. **Pass: the strip shows dim red, the Mute entity in Home Assistant
turns on, and "Hey Jarvis" gets no reaction at all.** Unlatch it. **Pass: the strip goes off, Mute
turns off, and test 2 works again.** Also latch it in the middle of a question: **the conversation
stops.**

**5. Speaker cap.** In Home Assistant, set the Media Player volume to 100% and ask for the time.
**Pass: the reply is loud and clean, with no harsh distortion or clipping, and no louder than the
Arduino test at 100%.** Set it back to 50% afterwards. If it distorts, stop and report it; do not
keep testing at 100%.

**6. OTA.** After stage 2, **pass: the upload completes over Wi-Fi, the device reconnects by itself,
and Firmware reads `0.2.1 (ESPHome 2026.11.0)`.** Repeat test 2 to confirm it still works.

**7. Rollback.** Return to the tagged firmware and flash it over Wi-Fi:

    git checkout sat-hub-v1
    .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

**Pass: Firmware reads `0.2.0` again and test 2 works.** Then return to the branch and put the newer
build back:

    git checkout milestone/M02-satellite-base
    .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

Checks Claude ran on this branch, using a temporary copy with the example secrets (the real
`secrets.yaml` was never opened):
- `esphome config`: valid.
- `esphome compile`: passes. The firmware is 1.37 MB, 17% of the 7.9 MB app partition, and uses 39% of
  RAM. Both the USB (`firmware.factory.bin`) and OTA (`firmware.ota.bin`) images were produced.
- The compile only passes with the two environment variables from `docs/setup/deploy.md`
  (one-time setup, step 2). Both are saved for Will's Windows account.

## Deviations from the plan
- **The hub was rebuilt with a new ESP32 on November 22nd**, partway through this milestone. The DAC
  pins moved from BCK 39 / WS 40 / DOUT 38 to BCK 40 / WS 38 / DOUT 39, and the 71-LED strip was
  replaced by a DFRobot 24-LED WS2812 ring on the same pin. Firmware 0.3.1 is the first build for the
  new hardware (0.3.0 had the mic clock on the wrong pin, from a typo). The mute button is not wired
  yet, so the firmware reads it as "not muted".
- **The speaker cap is `volume_max: 0.87`, not 0.5.** ESPHome's volume scale is in decibels, so 0.87 is
  what gives −6.4 dBFS. See "Speaker level cap" above.
- **Status colours on the LED strip were added**, pulling a small part of M3 forward. The first build
  used the devkit's onboard LED, but the strip is what Will watches, and leaving the strip undriven
  let its data line float: it lit white from audio-output noise. The firmware now always drives the
  strip and caps every channel at 25% (worst case 0.9 A for 60 LEDs against the 1.2 A budget). M3 still owns the
  full set of states, animations and the encoder pixel.
- **The I2S output is on ESPHome's defaults** (it stops 500 ms after each sound). Three attempts to cure
  the idle hum by keeping the output alive (`timeout: never`, `keep_alive: true`, a mixer with a
  never-stopping output) were tried on the hardware and removed: they made the hum louder, and the
  first also made the voice assistant ignore the wake word.
- **A firmware version was added**, so the OTA and rollback tests can show which build is running.
- **`sat-hub-v1` is tagged on the branch before merge**, not after, because the rollback test needs it.
- **The example API key changed**, because ESPHome rejects an all-zero key.
- **Two Windows environment variables were added**, `ESPHOME_ESP_IDF_PREFIX` and `ESPHOME_DATA_DIR`,
  both pointing under `C:\ESPHome`, agreed with Will. Without them the build fails on Windows'
  260-character path limit. As a result, build output no longer lives in the repo folder.
- **The speaker runs mono on the left channel at 48 kHz**, not 16-bit stereo as in the pin table. The
  amp only has its left input connected, and Home Assistant converts replies to this format.

## Known limitations / follow-ups
- **The speaker hums when idle.** Will's tests with a diagnostic build showed the hum is there in every
  state of the DAC's signal pins, quietest with the I2S output stopped (the current behaviour) and
  louder while it runs. Firmware cannot remove it. Will has chosen to park it until after the demo
  video. The planned fix is the amp's MUTE pin on GPIO4 (open-drain, only after Will measures that MUTE
  idles at 3.6V or less), which needs the assembled hub reopened; wiring and grounding are the other
  suspects.
- **The LED strip needs custom bit timings.** It ignored ESPHome's built-in WS2812 timings through
  firmware 0.2.5 and responded as soon as 0.2.6 copied the Adafruit NeoPixel library's timings.
- **The strip's current limit depends on the firmware showing one colour at a time.** Channels are
  capped at 70%, which keeps a single colour on all 71 LEDs at about 1.0 A against the buck's 1.2 A.
  White or mixed colours at that level would overload it, so the strip is not adjustable from Home
  Assistant. Will chose this over a 25% cap that was safe for any colour but too dim. M3 should add a
  limiter that checks each frame before adding mixed colours or animations.
- **DMA for the LED driver is not used.** With it enabled (0.2.6) the strip stopped updating for good
  after the first voice reply. The cause was not investigated.
- **Nothing here has run on the hardware yet.** Mic levels, wake word reliability and speaker loudness
  are all unproven until Will's tests.
- **The +30 dB mic gain is a starting point.** It was proven for speech-to-text in the Arduino tests,
  not for this wake word engine. Expect to tune `mic_gain_factor`.
- **The cap is verified by reading code, not by measuring the output.** A scope or meter on the DAC
  output at 100% would confirm it.
- **No echo cancellation.** The wake word may not be heard while the satellite is speaking.
- **ESPHome warns that an OTA password is the older method** and suggests OTA encryption instead. The
  password was the agreed plan; switching is a possible follow-up.
- **The Mute entity is read-only.** It shows the physical button; Home Assistant cannot mute the
  device.
- **Logs on the native USB port** assume that is the port Will flashes through. If the UART port is
  used instead, change `hardware_uart` in `sat-hub.yaml` to `UART0`.
- **Demo mode** (hotspot plus a simple web page for showing the device off) was requested during
  planning and is in the backlog, not in this milestone.
