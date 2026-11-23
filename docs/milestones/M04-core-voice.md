# M04 — Core voice
Status: in review   Branch: `milestone/M04-core-voice`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/6

## Goal
The everyday assistant basics work by voice: device commands, timers and general questions. Device
commands and timers stay on the home network; only the text of a question goes to Claude.

## Where it stands
Will's results on November 23rd, 2026, on firmware 0.5.0: test 3 (a general question) first failed
with "Sorry, I couldn't understand that", typed as well as spoken. Jewel had no Claude agent to
choose, because the Anthropic integration's conversation agent was not yet set up. Once it was, Will
reported that the tests pass. Which of the two cases in section 13.4 it was, and whether the lights
answer with the internet unplugged (test 14), were not reported.

Will then asked for two changes, built as firmware 0.5.1:
- the ringing light is three purple LEDs circling the ring instead of a pulse
- the prompt asks Claude for shorter answers

Later on November 23rd: on 0.5.1 the answers were much shorter and the circling light worked, but
it looked blue. Firmware 0.5.2 adds red to all three LEDs. On 0.5.2 Will reports that all tests pass.
The one-day soak was not run as a full day. Still to do: the `sat-hub-v5` tag.

## What was built
- `firmware/satellite/packages/alarm.yaml` — new. The ringing logic: `ring_start` and `ring_stop`,
  the repeat loop, the ringing volume range, and the five-minute give-up. Timers use it now; M5 alarms
  will call the same two scripts.
- `firmware/satellite/packages/voice.yaml` — changed. A finished Home Assistant timer starts the
  ringing. A second on-device word, "stop", is added. While the hub rings, "stop" or "Hey Jarvis"
  stops the ringing and does not start a conversation.
- `firmware/satellite/packages/controls.yaml` — changed. While the hub rings, a knob turn either way
  stops the ringing and leaves the volume alone.
- `firmware/satellite/packages/leds.yaml` — changed. A ringing state, three purple LEDs circling the
  ring, which wins over every other state including mute.
- `firmware/satellite/packages/audio.yaml` — changed. The ring sound is built into the media player.
  A stale comment about the amp MUTE wire was corrected.
- `firmware/satellite/sounds/timer_ring.wav` — new. The default ring: four short beeps, 0.63 seconds.
- `firmware/satellite/sounds/make_ring.py` — new. Generates that file with standard-library Python.
- `firmware/satellite/sounds/README.md` — new. How to swap in your own ring sound.
- `firmware/satellite/sat-hub.yaml` — changed. Loads `alarm.yaml`; version 0.5.2.
- `docs/setup/home-assistant.md` — changed. New section 13: exposing devices, timer phrases, the
  Claude API key, the Anthropic integration, the prompt, and the pipeline setting.
- `docs/MILESTONES.md` — M3 set to `merged`, M4 to `in review`, web search added to the backlog.
- `docs/milestones/M03-controls-and-feedback.md` — status set to `merged`.
- `docs/milestones/M04-core-voice.md` — new. This doc.

No custom C++ and no ESPHome external component was added. There is no Python service in this
milestone.

### How a sentence is routed
| What you say | Handled by | Needs the internet |
|---|---|---|
| Device command, timer command, "what time is it" | Home Assistant on the mini PC | no |
| Anything else | Claude, through Home Assistant's Anthropic integration | yes |

Home Assistant tries its own commands first ("prefer handling commands locally"). Claude is set up
to answer questions only: it is not given the device list and cannot control anything.

### How ringing works
1. Home Assistant tells the satellite a timer has finished, and `ring_start` runs.
2. The current volume is remembered. The ring plays at that volume if it is between 25% and 50%; a
   lower volume is raised to 25% and a higher one lowered to 50%. Home Assistant's slider shows the
   ringing volume while it rings.
3. The "stop" word is switched on, three purple LEDs start circling the ring, and the sound repeats with 1.2
   seconds of silence between repeats. The silence is when the hub can hear you, because there is no
   echo cancellation.
4. `ring_stop` runs on the first of: "stop", "Hey Jarvis", a knob turn, or five minutes. It stops the
   sound, switches the "stop" word off, puts the volume back, and returns the ring to what it showed
   before.

The "stop" word is off at all other times. It is switched off at every start-up and after every
ring, so saying "stop" in normal conversation does nothing.

### Settings you can change
All at the top of `firmware/satellite/packages/alarm.yaml`:

| Setting | Default | Meaning |
|---|---|---|
| `ring_sound_file` | `sounds/timer_ring.wav` | the sound to repeat |
| `ring_gap` | `1200ms` | silence between repeats |
| `ring_timeout` | `5min` | ringing gives up after this |
| `ring_volume_min` / `ring_volume_max` | `0.25` / `0.50` | the ringing volume range |

### Speaker level cap (hard rule 3)
The ring plays through the media player as an announcement, like a spoken reply, so `volume_max:
0.87` applies. The ringing volume is at most 50% of the media player's range, which is about
−28 dBFS before the file's own level. The file peaks at 0.8 of full scale; that does not matter for
the cap, which holds for any file at any volume.

### LED ring current
The ringing effect lights three LEDs at a time: a deep purple leading LED and two lighter, fainter
ones behind it. That is about 65 mA at the 80% cap, far inside the 1.2 A budget.

## How it connects to the rest of the project
- **Uses M1:** the `Jewel` pipeline, Whisper and Piper. Only the conversation agent changes.
- **Uses M2 and M3:** the capped media player, the amp un-mute on playback, `status_light_apply`,
  and the knob's click events.
- **Four-layer design:** `ring_start` and `ring_stop` are the reusable scripts. What starts and stops
  ringing is wired in `voice.yaml` and `controls.yaml`, not inside the ring logic, so a new trigger
  is one line.
- **For M5:** alarms call `ring_start` and `ring_stop`. M5 adds its own sound, publishes
  `hub/alarm/start` and `hub/alarm/stop`, and decides whether the mute button also stops an alarm.
  The knob turn is already a guaranteed stop that does not depend on the microphone.
- **For Phase B:** Jarvis Core replaces the Anthropic integration as the conversation agent.

## How to deploy
PowerShell, in the repo folder, with the two `ESPHOME_` folder variables set (see
`docs/setup/deploy.md`).

1. **Back up Home Assistant:** Settings → System → Backups → create a full backup named
   `before-M04` and download it.
2. **The running firmware is already tagged:** `sat-hub-v4` is 0.4.1.
3. **Home Assistant:** follow section 13 of `docs/setup/home-assistant.md`. Sections 13.1 and 13.3
   to 13.6 are the steps; 13.2 is reference.
4. **Get the branch and flash over Wi-Fi:**

       git fetch
       git checkout milestone/M04-core-voice
       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

   The first build downloads the "stop" word model from
   `github.com/kahrendt/microWakeWord` (see Deviations).

Roll back, if needed:

       git checkout sat-hub-v4
       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

and in Home Assistant set Jewel's conversation agent back to **Home Assistant** (section 13.7), or
restore the `before-M04` backup.

## How to test
Claude cannot hear the speaker, see the ring or turn the knob. Pass criteria are in bold. Every
spoken line starts with "Hey Jarvis".

**1. Boot.** **Pass: Firmware reads `0.5.2 (ESPHome 2026.11.0)`, and "what time is it?" still gets a
spoken answer.**

**2. Device command.** "Turn on the desk lights" (use your light's name), then "turn them off".
**Pass: the light follows both, and each reply comes at once.**

**3. General question.** "Why is the sky blue?" **Pass: blue, then amber for a second or two, then
green while a one or two sentence answer is spoken.** This is the first time amber should be visible.

**4. Set and check a timer.** "Set a timer for two minutes", then "how long is left on my timer?"
**Pass: it confirms the timer, then speaks the time left.**

**5. Cancel a timer.** "Cancel my timer." **Pass: it confirms, and nothing rings at the two-minute
mark.**

**6. Ring.** "Set a timer for ten seconds." **Pass: when it ends, the hub beeps four times, pauses,
and repeats, and three purple LEDs circle the ring: a deep purple one in front with two lighter ones
trailing.** Note which way it turns; the direction is one small change in `leds.yaml`.

**7. Stop by knob.** While it rings, turn the knob one click either way. **Pass: the ringing stops
at once, the ring goes off, and the Media Player volume in Home Assistant is what it was before the
timer.**

**8. Stop by "stop".** Start another ten-second timer. While it rings, say "stop" in a pause between
beeps, with no "Hey Jarvis". **Pass: the ringing stops.** Without echo cancellation this may take a
second try; note how reliable it is.

**9. Stop by wake word.** Same again, and say "Hey Jarvis". **Pass: the ringing stops and the ring
does not turn blue (no conversation starts).**

**10. "Stop" is off when not ringing.** With nothing ringing, say "stop" a few times, on its own and
in a sentence. **Pass: nothing happens; the ring stays off.**

**11. Ringing volume.** Run a ten-second timer three times, stopping each with the knob:
- volume at 10% first: **pass: it rings clearly (25%), and the volume reads 10% again afterwards**
- volume at 40%: **pass: it rings at that level, and reads 40% afterwards**
- volume at 90%: **pass: it rings more quietly than a reply would be (50%), and reads 90% afterwards**

**12. Ring while muted.** Latch mute, then finish a timer set beforehand. **Pass: it still rings and
shows purple, the knob stops it, and the ring returns to red.** "Stop" and "Hey Jarvis" do not work
while muted, because the microphone is off.

**13. Timeout.** Start a ten-second timer and leave it. **Pass: it stops by itself after five
minutes.** To shorten the wait, this test can be skipped and noted as not run.

**14. Offline: device command.** Unplug the router's internet (WAN) cable so Wi-Fi stays up. Wait a
minute, then "turn on the desk lights" and "set a timer for ten seconds". **Pass: both work as
before, and the timer rings.** If the Nanoleaf lights do not respond, check in Home Assistant whether
they show as unavailable: that would be the lights needing the internet, not the hub.

**15. Offline: question.** Still unplugged, "why is the sky blue?" **Pass: within about ten seconds
it either speaks a short error or flashes red, and then answers the next device command normally.**
Note which it did. Plug the cable back in and check a question works again.

**16. Soak.** Use the hub normally for a day. **Pass: no stuck ringing, no "stop" false triggers,
the ring never freezes and the wake word never goes deaf.**

**17. Tag.** When the tests above pass (`fa0bea3` is the commit holding firmware 0.5.2):

    git tag -a sat-hub-v5 fa0bea3 -m "Satellite firmware v5: timers ring, stop word, core voice"
    git push origin sat-hub-v5

Checks Claude ran, using a temporary copy with the example secrets (the real `secrets.yaml` was never
opened):
- `esphome config`: valid.
- `esphome compile`: passes for 0.5.0, 0.5.1 and 0.5.2. Flash use is 18.6% (1.51 MB of the 8.1 MB app space), RAM
  39.4%.
- `make_ring.py` runs and writes a 0.63-second, 60 kB WAV.
- Not run: anything on the hardware or in Home Assistant. Ringing, the "stop" word, the volume range
  and the Anthropic setup are untested until Will runs the checklist.

## Deviations from the plan
- **The "stop" word model comes from a different place than first stated.** The plan called it
  ESPHome's built-in model. It is not in ESPHome's model list; the build downloads it from
  `github.com/kahrendt/microWakeWord/releases/download/stop/stop.json`, the file the official Home
  Assistant Voice PE firmware uses, published by the wake word engine's author. Will approved this
  source on November 23rd, 2026.
- **Ringing volume is a 25% to 50% range,** not the current volume as first proposed (Will's
  decision).
- **No test helpers:** Will has Nanoleaf lights, so device control is tested on real devices and no
  `homeassistant/` package was needed.
- **Web search is off,** with the switch documented in section 13.4 so it can be tried later (Will's
  decision).

- **The ringing light circles instead of pulsing,** and its purple is deeper (Will's request after
  testing 0.5.0).
- **The prompt was tightened** to one short sentence, two at most, under 30 words (Will's request).

## Known limitations / follow-ups
- **"Stop" and "Hey Jarvis" may not be heard over the beeps.** There is no echo cancellation. The
  1.2-second pauses are the listening window; the knob is the stop that always works.
- **Voice stop does not work while muted.** The microphone is off; use the knob.
- **A timer that ends while the hub is speaking cuts the reply off** with the ring.
- **The Home Assistant volume slider moves during ringing** and is put back afterwards. A volume
  change made in Home Assistant while it rings is overwritten when the ringing stops.
- **A power cut during ringing** leaves the volume at the ringing level, which is always 25% to 50%.
- **Several timers ending together ring as one;** one stop silences it.
- **The mute button does not stop ringing** (Will's decision). M5 decides this again for alarms.
- **A running timer shows nothing on the ring.** A countdown display is not built.
- **An oddly phrased device command goes to Claude,** which says it cannot control devices.
- **The Home Assistant steps were written without sight of the live system.** Menu names may differ
  slightly.
- **Offline behaviour for questions is not known until test 15.** If it hangs instead of failing
  cleanly, that is a fix for this branch.
- **Replies longer than 30 seconds** would turn the ring off before the speech ends (the M2 wait
  limit). The prompt keeps answers short.
- **The circling light has not been seen by Claude.** Its colours, speed and direction are a first
  guess from Will's description.
- **The ring sound has not been heard by Claude.** Its pitch and rhythm are a first guess; see
  `sounds/README.md` to change it.
