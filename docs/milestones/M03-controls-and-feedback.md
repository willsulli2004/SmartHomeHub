# M03 — Satellite controls and feedback
Status: in review   Branch: `milestone/M03-controls-feedback`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/5

## Goal
The satellite feels like a finished device: the knob changes the volume, the ring shows what the hub
is doing, and the amp is silent when nothing is playing.

## What was built
- `firmware/satellite/components/seesaw_encoder/__init__.py` — new. The configuration side of the
  project's first own ESPHome component: options, defaults, and the `on_clockwise` and
  `on_anticlockwise` automations.
- `firmware/satellite/components/seesaw_encoder/seesaw_encoder.h` and `.cpp` — new. The C++ side. It
  asks the encoder chip over I2C every 20 ms how many clicks the knob has turned and fires one
  callback per click. Rotation only.
- `firmware/satellite/packages/controls.yaml` — changed. The I2C bus (SDA 21, SCL 47), the encoder at
  address 0x36, and volume up and down on each click.
- `firmware/satellite/packages/leds.yaml` — changed. A `ring_state` value and one script,
  `status_light_apply`, that turns it into a colour; new thinking, speaking and error states; a
  volume display effect.
- `firmware/satellite/packages/voice.yaml` — changed. Thinking starts when speech-to-text ends,
  speaking when the reply is ready, and errors show the error flash.
- `firmware/satellite/packages/audio.yaml` — changed. The amp MUTE switch on GPIO4 and the scripts
  that release it for a sound and mute it again a second after.
- `firmware/satellite/sat-hub.yaml` — changed. Loads components from `components/`; version 0.4.0.
- `CLAUDE.md` — changed. The amp MUTE firmware is described, and GPIO4 is marked as driven.
- `docs/MILESTONES.md` — M2 set to `merged`, M3 to `in review`, and the items cut from M3 moved to
  the backlog.
- `docs/milestones/M02-esphome-satellite-base.md` — status set to `merged`.
- `docs/milestones/M03-controls-and-feedback.md` — new. This doc.

### How the encoder component works
The Adafruit encoder board has its own small chip running "seesaw" firmware. It counts the knob's
clicks by itself, so the ESP32 never has to watch the knob's pins. The component:

1. At start-up, reads the chip's hardware id to confirm it is there. If there is no answer it logs
   an error naming the wires to check and switches itself off; the rest of the hub carries on.
2. Throws away any turns made before start-up.
3. Every 20 ms, asks for the "delta": the clicks turned since the last ask. The chip clears its count
   each time it answers.
4. Fires `on_clockwise` or `on_anticlockwise` once per click, up to 12 per poll. Anything larger is a
   corrupt read and is clamped.
5. If the chip stops answering for about a second, logs one warning, and one message when it returns.

A seesaw register is read in two steps: send two address bytes, wait 300 µs, then read the answer.

### LED states
| State | Colour | When |
|---|---|---|
| Idle | off | waiting for the wake word |
| Listening | blue | wake word heard |
| Thinking | amber | speech understood, waiting for the answer |
| Speaking | green | the reply is ready and being spoken |
| Muted | red | mute button latched; overrides everything else |
| Error | red for 1 second | the voice assistant reported a problem |
| Volume | white arc | for 1.5 seconds after a knob click |

The volume arc lights LEDs in proportion to the volume: half the ring at 50%. With Home Assistant's
built-in commands the answer comes back in milliseconds, so amber is too brief to see. It becomes
visible in M4, when questions go to Claude.

### Amp mute
GPIO4 is an open-drain output: the ESP32 pulls it to ground to mute the amp, or lets go. It never
drives it high. The amp is muted at start-up, released when the media player starts a sound (about
100 ms before audio comes out, by the M2 logs), and muted again one second after playback goes idle.
Until Will fits the wire, the pin switches with nothing attached.

## How it connects to the rest of the project
- **Speaker cap (hard rule 3):** the knob calls the media player's volume up and down. It never
  touches the speaker, so `volume_max: 0.87` applies to it as it does to Home Assistant's slider. The
  two stay in step because they are the same setting. 2% is the media player's `volume_increment`.
- **Four-layer design:** the encoder is a device that raises events (`on_clockwise`,
  `on_anticlockwise`); what a click does is decided in `controls.yaml`, not in the component. The LED
  scripts are the reusable layer: anything can call `status_light_listening` and the rest.
- **For M4 and M5:** timers and alarms add a `ring_state` value and a colour in `status_light_apply`.
  Their sounds play through the media player, so the amp un-mutes for them with no extra work.
- **For M5:** the knob's events can also serve as an alarm stop, since the knob cannot be pressed.

## How to deploy
PowerShell, in the repo folder, with the two `ESPHOME_` folder variables set (see
`docs/setup/deploy.md`).

1. **Back up Home Assistant:** Settings → System → Backups → create a full backup and download it.
2. **The running firmware is already tagged:** `sat-hub-v3` is 0.3.5, and 0.3.6 differs only in its
   version number.
3. **Get the branch and flash over Wi-Fi:**

       git fetch
       git checkout milestone/M03-controls-feedback
       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

Roll back, if needed:

       git checkout sat-hub-v3
       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

## How to test
Claude cannot hear the speaker, see the ring or turn the knob. Pass criteria are in bold.

**1. Boot.** **Pass: Firmware reads `0.4.0 (ESPHome 2026.11.0)`, and the wake word still gets a
spoken answer.** If the knob does nothing in test 2, read the log
(`esphome logs ... --device sat-hub.local`): `No answer from the encoder` means a wiring or power
problem on the encoder board.

**2. Knob.** Turn the knob one click clockwise, then several. **Pass: the Media Player volume in Home
Assistant rises 2% per click, and falls 2% per click the other way.** If it runs backwards, tell
Claude; it is one setting.

**3. Volume display.** **Pass: while turning, the ring shows a white arc that grows and shrinks with
the volume, and about 1.5 seconds after the last click it returns to off.**

**4. Knob and Home Assistant together.** Move the Media Player slider in Home Assistant to 30%, then
turn the knob one click up. **Pass: it reads 32%.**

**5. Limits.** Turn down past zero and up past the top. **Pass: it stops at 0% and 100%, and a reply
at 100% is loud and clean.** Set it back to about 50%.

**6. LED states.** Ask a question. **Pass: blue while listening, green while it speaks, off after.**
Amber may be too brief to see. Latch mute: **red.** Unlatch: **off.**

**7. Knob during other states.** Latch mute and turn the knob. **Pass: the white arc shows, then the
ring returns to red.**

**8. Error state.** Say "Hey Jarvis" and then stay silent until it gives up. **Pass: a red flash,
then off.** If nothing flashes, note what the ring did; some timeouts may not count as errors.

**9. Soak.** Use the hub normally for a day. **Pass: the ring never freezes and the wake word never
goes deaf.**

**10. Tag.** When the tests above pass:

    git tag -a sat-hub-v4 -m "Satellite firmware v4: volume knob, LED states, amp mute"
    git push origin sat-hub-v4

**11. Amp mute, after the wire is fitted** (MUTE on the amp to GPIO4, ideally through a 1 kΩ
resistor). Do this before the enclosure's last panel goes on. **Pass: no hum when idle, the hum
returns only while it speaks, and the first word of a reply is not cut off.** If the first word is
clipped, tell Claude; the release timing can be moved earlier.

Checks Claude ran, using a temporary copy with the example secrets (the real `secrets.yaml` was never
opened):
- `esphome config`: valid.
- `esphome compile`: passes, including the new C++ component.

## Deviations from the plan
None from the plan Will confirmed on November 23rd. That plan cut these from the original M3 list:
- Feedback sounds for volume and mute: backlog.
- Encoder press: waits for a new enclosure.
- The encoder's own status light: backlog.
- LED brightness control in Home Assistant: backlog.
- Timer and alarm LED states: M4 and M5, with the features.
- Removing the three unproven M2 measures: after the demo.

## Known limitations / follow-ups
- **Nothing here has run on the hardware.** The encoder protocol is written from the seesaw register
  map and Will's working Arduino code, but this C++ has never talked to the real chip.
- **The amp mute is untested until the wire is fitted,** and it is the last thing done before the
  enclosure closes.
- **The hub hums for a few seconds at power-up,** before the firmware pulls MUTE low, and while it
  speaks.
- **The volume arc is white on up to 24 LEDs.** At the 80% cap that is 1.15 A at full volume, inside
  the 1.2 A budget.
- **The three unproven M2 measures are still in:** the ring's frame re-sent once a second, the 500 ms
  wait before the ring turns off, and lowered drive strength on the DAC pins.
- **The LED data pin (41) still sits beside the DAC's bit clock (40).** If the ring freezes during the
  soak test, move that wire before closing the enclosure.
- **No unit tests for the component.** Its logic is small and tied to the I2C bus; it is verified on
  the hardware.
