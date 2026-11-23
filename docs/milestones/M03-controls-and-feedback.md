# M03 — Satellite controls and feedback
Status: in review   Branch: `milestone/M03-controls-feedback`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/5

## Goal
The satellite feels like a finished device: the knob changes the volume, the ring shows what the hub
is doing, and the amp is silent when nothing is playing.

## Where it stands
Will's results on November 23rd, 2026, on firmware 0.4.0: the knob works, and the amp mute works with
the MUTE wire fitted to GPIO4: no hum when idle, and no reply has its first word cut off. The knob
counted backwards, so firmware 0.4.1 sets `inverted: true`. Still to do: confirm the direction on
0.4.1, the remaining checklist items, the one-day soak, and the `sat-hub-v4` tag.

Later on November 23rd, on firmware 0.4.1: the knob direction is correct and Will reports that every
checklist item passes. After he assembled the enclosure the ring began sticking again. He swapped the
two 5V buck converters, so the one that fed the ESP32 now feeds the ring, and the ring has since
worked through several spoken answers without sticking. The one-day soak was not run as a full day.
Still to do: the `sat-hub-v4` tag.

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
Will fitted the wire during M3 testing and confirmed it works.

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

**1. Boot.** **Pass: Firmware reads `0.4.1 (ESPHome 2026.11.0)`, and the wake word still gets a
spoken answer.** If the knob does nothing in test 2, read the log
(`esphome logs ... --device sat-hub.local`): `No answer from the encoder` means a wiring or power
problem on the encoder board.

**2. Knob.** Turn the knob one click clockwise, then several. **Pass: the Media Player volume in Home
Assistant rises 2% per click, and falls 2% per click the other way.** On 0.4.0 the knob worked but
ran backwards; 0.4.1 inverts it. Confirm clockwise is louder on 0.4.1.

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

**11. Amp mute** (MUTE on the amp to GPIO4). **Pass: no hum when idle, the hum returns only while
it speaks, and the first word of a reply is not cut off.** Done: Will reports no hum and nothing
cut off.

Checks Claude ran, using a temporary copy with the example secrets (the real `secrets.yaml` was never
opened):
- `esphome config`: valid.
- `esphome compile`: passes, including the new C++ component.

## Deviations from the plan
- **The amp MUTE wire was fitted during M3 testing,** not left until the enclosure was finished as
  first planned, so the mute could be tested straight away.
- **The knob needed `inverted: true`.**

The plan Will confirmed on November 23rd cut these from the original M3 list:
- Feedback sounds for volume and mute: backlog.
- Encoder press: waits for a new enclosure.
- The encoder's own status light: backlog.
- LED brightness control in Home Assistant: backlog.
- Timer and alarm LED states: M4 and M5, with the features.
- Removing the three unproven M2 measures: after the demo.

## Known limitations / follow-ups
- **The idle hum from M2 is solved by the amp mute.** It is still there underneath while the hub
  speaks, and for a few seconds at power-up.
- **The volume arc is white on up to 24 LEDs.** At the 80% cap that is 1.15 A at full volume, inside
  the 1.2 A budget.
- **The three unproven M2 measures are still in:** the ring's frame re-sent once a second, the 500 ms
  wait before the ring turns off, and lowered drive strength on the DAC pins. Given the buck finding,
  they were probably never the fix.
- **The LED freeze was traced to the ring's power supply, not the firmware.** It came back when the
  enclosure was assembled and stopped when Will swapped the two buck converters. The converters'
  voltages were not measured, so the exact cause is inferred: most likely the ring's supply sat high
  enough that the ESP32's 3.3V data signal was only just readable. The margin is still thin. A diode
  in the ring's power lead or a level shifter on the data wire would make it dependable.
- **The ESP32 now runs from the converter that upset the ring.** It regulates its own 3.3V, so this
  should be fine, but unexplained restarts or Wi-Fi drops would point there first.
- **No unit tests for the component.** Its logic is small and tied to the I2C bus; it is verified on
  the hardware.
