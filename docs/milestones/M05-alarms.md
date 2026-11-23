# M05 — Alarms
Status: in review   Branch: `milestone/M05-alarms`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/7

## Goal
The CpE417 alarm feature on the hub side: an alarm set by voice fires on time, rings on the
satellite, tells the robot over MQTT, and can be stopped several ways, each reported over MQTT. It
works the same with the robot offline.

## Where it stands
Will's results on November 23rd, 2026:
- **Section 14.4 failed** with an error about `!lambda`. The firmware's `packages/alarm.yaml` had been
  pasted into Home Assistant, because the Home Assistant package had the same file name. The two Home
  Assistant files were renamed to `hub_alarms.yaml`.
- **"Set an alarm for 3:10PM" was answered by Claude,** which said it could not set an alarm. The
  phrase file listed exact ways of writing a time and that one was not among them, so Home Assistant
  did not recognise the sentence. The phrases now hand over whatever was said as the time, and a
  script works it out.
- **Will asked to set and change alarms from the app.** The slots became a time of day instead of a
  date and time, and an Alarms dashboard was added.

None of the three fixes has been tried on the live instance yet. The firmware is unchanged at 0.6.0.

## What was built
**Home Assistant side** (new folder `homeassistant/`):
- `homeassistant/packages/hub_alarms.yaml` — new. Five alarm slots as helpers (a time of day and a
  switch each), a script that understands a spoken time, the scripts that start and
  stop an alarm, automations for every trigger and stop path, the MQTT publishing, and the handlers
  for the voice commands.
- `homeassistant/custom_sentences/en/hub_alarms.yaml` — new. The spoken phrases for setting, cancelling
  and asking about alarms.
- `homeassistant/dashboards/hub_alarms.yaml` — new. An Alarms page for the app: the five alarms, a
  stop button, and the timer and alarm settings.
- `homeassistant/tests/test_alarm_sentences.py` — new. 58 checks that phrases, written the way
  speech-to-text writes them, trigger the right command and hand over the right words as the time.
- `homeassistant/tests/test_alarm_templates.py` — new. 95 checks of the time parsing, the
  arithmetic, slot matching, the spoken wording, and that the dashboard names real entities.
- `homeassistant/README.md` — new. What each file is, where it goes, and how to run the tests.

**Satellite side:**
- `firmware/satellite/packages/alarm.yaml` — changed. Ringing now has a kind, timer or alarm. Two
  actions Home Assistant can call (`alarm_ring`, `stop_ring`), a Ringing sensor, and the settings
  that moved out of the firmware into the app.
- `firmware/satellite/includes/ring_spinner.h` — new. Draws the three circling LEDs from a colour
  picked in Home Assistant.
- `firmware/satellite/packages/leds.yaml` — changed. Separate Ringing Timer and Ringing Alarm
  effects; the alarm circles faster.
- `firmware/satellite/packages/audio.yaml` — changed. The alarm sound is built in beside the timer's.
- `firmware/satellite/packages/voice.yaml` — changed. A finished timer no longer takes over from an
  alarm that is already ringing.
- `firmware/satellite/sounds/alarm_ring.wav` — new. Three quick two-pitch beeps, 0.74 seconds.
- `firmware/satellite/sounds/make_ring.py`, `README.md` — changed. Generates and documents both
  sounds.
- `firmware/satellite/sat-hub.yaml` — changed. Version 0.6.0.

**Project:**
- `requirements-dev.txt` — changed. Adds `hassil` (approved for this milestone) and `pytest`.
- `CLAUDE.md` — changed. New convention: tunable settings live in the app. The Home Assistant test
  command and the new folders are listed.
- `docs/setup/home-assistant.md` — changed. New section 14: installing the alarm package, the
  settings, the voice commands, and watching the MQTT messages.
- `docs/MILESTONES.md` — M4 set to `merged`, M5 to `in review`; M5's text and the backlog updated.
- `docs/milestones/M04-core-voice.md` — status set to `merged`.
- `docs/milestones/M05-alarms.md` — new. This doc.

### How an alarm runs
1. **Set.** "Set an alarm for 7 AM" matches a custom sentence on the mini PC, which hands "7 AM" to
   a script. The script works out the time, stores it in the first free of five slots, and switches
   the slot on. Picking a time and switching a slot on in the app does the same thing.
2. **Wait.** A slot that is on fires the next time the clock reaches its time.
3. **Fire.** At that moment the slot switches off (alarms fire once) and `hub_alarm_start` runs. It
   creates an `alarm_id`, marks the alarm as ringing, fires the `hub_alarm_started` event, and asks
   the satellite to ring.
4. **Tell the robot.** An automation that listens for `hub_alarm_started` publishes
   `hub/alarm/start`.
5. **Ring.** The satellite plays the alarm sound on repeat at the Alarm Volume and circles the Alarm
   Ring Colour.
6. **Stop.** Whatever stops it ends in `hub_alarm_stop` with a reason. That clears the ringing mark,
   fires `hub_alarm_stopped`, and tells the satellite to go quiet. An automation listening for the
   event publishes `hub/alarm/stop`.

| Stop path | How Home Assistant learns of it | Reason |
|---|---|---|
| Knob turned, "stop", or "Hey Jarvis" | the satellite's Ringing sensor turns off | `user` |
| "Stop the alarm" or "cancel my alarm" by voice | the voice command's script | `user` |
| Robot caught | `alarmbot/caught` with the matching `alarm_id` | `caught` |
| Nobody stops it | the Alarm timeout passes | `timeout` |
| Home Assistant restarts mid-alarm | a start-up check | `timeout` |

### MQTT messages
Following the draft contract in `docs/MILESTONES.md`. QoS 1, not retained, JSON, UTC timestamps.

| Topic | Payload |
|---|---|
| `hub/alarm/start` | `{"alarm_id": "alarm-1795532400", "ts": "2026-11-24T15:00:00Z"}` |
| `hub/alarm/stop` | `{"alarm_id": "alarm-1795532400", "reason": "user", "ts": "..."}` |

The `alarm_id` is `alarm-` plus the Unix time the alarm fired. Home Assistant does all publishing;
the satellite never talks to the broker.

### What a spoken time means
- **With AM or PM** ("7 AM", "7:30 p.m.", "6 in the morning"): that time, today if it is still to
  come, otherwise tomorrow.
- **Without** ("7", "7:30"): the next time the clock shows it. At 3 PM, "7" means 7 PM today; at
  9 PM it means 7 AM tomorrow.
- **24-hour** ("19:15") and **noon / midnight** are understood.
- **Any way of writing it** that speech-to-text produces: "3:10 PM", "3:10pm", "3.10 p.m.",
  "310 PM", "three ten in the afternoon".
- **Not a time** ("set an alarm for when I get home"): the hub says it did not catch the time.

### Settings in the app
| Where | Setting | Default |
|---|---|---|
| Satellite Hub device, Configuration | Timer Volume Min / Max | 25% / 50% |
| | Alarm Volume | 75% |
| | Timer Ring Timeout | 5 min |
| | Timer Ring Colour | the purple approved in M4 |
| | Alarm Ring Colour | orange-red |
| Home Assistant helpers | Alarm timeout | set to 10 min during install |
| | Alarm 1 to 5 and their times | all off |

The Alarms dashboard (section 14.11 of the setup guide) shows all of these on one page.

The colours are light entities so that Home Assistant shows a colour picker; they light nothing
themselves. The M4 values `ring_volume_min`, `ring_volume_max` and `ring_timeout` are gone from the
firmware.

Still in the firmware, at the top of `packages/alarm.yaml`: the two sound files, the silence between
repeats (`ring_gap`), and the 30-minute safety limit.

### Speaker level cap (hard rule 3)
Timer and alarm volumes are media player percentages, so `volume_max: 0.87` still applies. An Alarm
Volume of 100% is the same level as the knob at 100%: −6.4 dBFS. The default 75% is about
−17 dBFS.

### LED ring current
Three LEDs are lit at a time. Any colour at full brightness is at most 3 × 60 mA × 0.8 = 0.14 A,
inside the 1.2 A budget.

## How it connects to the rest of the project
- **Uses M1:** the Mosquitto broker through Home Assistant's own MQTT connection.
- **Uses M4:** the ring scripts, the "stop" word, the knob stop, and "prefer handling commands
  locally", which is what keeps alarm commands away from Claude.
- **Four-layer design:** helpers (the slots) → scripts (`hub_alarm_start`, `hub_alarm_stop`) →
  semantic events (`hub_alarm_started`, `hub_alarm_stopped`) → triggers (the automations). MQTT
  publishing only listens for the events.
- **For M6:** the dashboard sets alarms by writing the same slot helpers. The mock robot and the real
  one subscribe to `hub/alarm/start` and publish `alarmbot/caught`. `docs/robot-integration.md`
  finalises the contract from the table above.
- **For M10:** the alarm logic moves to a plugin behind the same events and topics.

## How to deploy
PowerShell, in the repo folder, with the two `ESPHOME_` folder variables set (see
`docs/setup/deploy.md`).

1. **Back up Home Assistant:** Settings → System → Backups → full backup named `before-M05`,
   downloaded.
2. **The running firmware is already tagged:** `sat-hub-v5` is 0.5.2.
3. **Get the branch and flash over Wi-Fi:**

       git fetch
       git checkout milestone/M05-alarms
       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

4. **Home Assistant:** follow section 14 of `docs/setup/home-assistant.md`, 14.1 to 14.6, then 14.11
   for the dashboard.
5. **On a new machine only,** to run the tests: `.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.

Roll back, if needed:

       git checkout sat-hub-v5
       .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local

and remove the two files from Home Assistant (section 14.10), or restore `before-M05`.

## How to test
Claude cannot hear the speaker, see the ring, or reach Home Assistant. Pass criteria are in bold.
Every spoken line starts with "Hey Jarvis". Keep the MQTT listener from section 14.9 open on
`hub/alarm/#` throughout.

**1. Boot.** **Pass: Firmware reads `0.6.0 (ESPHome 2026.11.0)`, a question still gets an answer,
and a ten-second timer still rings purple and stops with the knob.**

**2. Install checks.** Section 14.4 and 14.5. **Pass: the configuration check is valid, and the two
actions and the Ringing sensor exist under the expected names.**

**3. Settings appear.** Open the Satellite Hub device page. **Pass: Configuration lists Timer Volume
Min, Timer Volume Max, Alarm Volume, Timer Ring Timeout, Timer Ring Colour and Alarm Ring Colour,
with the defaults in the table above.**

**4. Set and ask.** "Set an alarm for" a time two minutes from now, with AM or PM. Then "when is my
alarm?" **Pass: it confirms the time, repeats it when asked, and Alarm 1 is on with that time in
Home Assistant.**

**5. Fire.** Wait. **Pass: at the set minute the hub plays the alarm sound on repeat, louder than a
timer, with an orange-red light circling faster than the timer's. A message appears on
`hub/alarm/start` with an `alarm_id`. Alarm 1 is off again.**

**6. Stop by knob.** Turn the knob one click. **Pass: silence at once, the ring goes off, the volume
is what it was before, and `hub/alarm/stop` shows the same `alarm_id` with reason `user`.**

**7. Stop by "stop".** Fire another alarm and say "stop" in a pause. **Pass: it stops, reason
`user`.** At 75% this may be harder to hear than with a timer; note how reliable it is.

**8. Stop by voice command.** Fire another, say "Hey Jarvis" (the ringing stops, reason `user`).
Fire one more and stop it from the Assist dialog by typing `stop the alarm`. **Pass: it stops, it
answers "Alarm stopped", reason `user`.**

**9. Robot caught.** Fire another. Copy the `alarm_id` from the start message and publish it to
`alarmbot/caught` as in section 14.9. **Pass: the alarm stops, reason `caught`.** Before that,
publish once with a wrong id: **pass: nothing happens.**

**10. Timeout.** Set Alarm timeout to 1, fire an alarm and leave it. **Pass: it stops after one
minute, reason `timeout`.** Set Alarm timeout back to 10.

**11. Several alarms.** Set alarms for 7 AM, 8:30 AM and 7 PM. "What alarms are set?" **Pass: it
lists all three, soonest first.** "Cancel my alarm": **pass: it says there are three and asks
which.** "Cancel my 8:30 AM alarm": **pass: only that one goes.** "Cancel all alarms": **pass: none
are left.**

**11a. Set from the app.** On the Alarms dashboard, set Alarm 2's time to two minutes from now and
switch it on. **Pass: it rings on the hub at that minute and Alarm 2 switches itself off.** Then set
one by voice and check it appears on the dashboard, change its time there, and ask "when is my
alarm?": **pass: the hub says the new time.**

**11b. Odd ways of saying a time.** "Set an alarm for three ten PM", then one for "7:30", then
"set an alarm for when I get home". **Pass: the first two are set correctly; the third answers that
it did not catch the time, and none of them is answered by Claude.** Cancel them.

**12. Without AM or PM.** "Set an alarm for" an hour that is next due in the other half of the day
than you might assume. **Pass: it announces the next occurrence, with "tomorrow" when it falls
tomorrow.** Cancel it.

**13. Change settings from the app.** Set Alarm Volume to 40% and Alarm Ring Colour to green, then
fire an alarm. **Pass: it is quieter and green, with no flash needed.** Set Timer Ring Colour to
another colour and run a ten-second timer: **pass: the timer uses it.** Restart the satellite from
its device page and check the settings kept their values. Put back what you like.

**14. Timer then alarm.** Start a ten-second timer so it is ringing when an alarm fires. **Pass: the
ringing switches to the alarm sound and colour, and one knob turn stops everything with reason
`user`.**

**15. Robot offline.** Nothing extra to do: every test above ran with no robot. **Pass: tests 5 to
10 behaved normally.**

**16. Internet unplugged.** With only the internet (WAN) cable out, set an alarm and let it fire.
**Pass: setting, ringing and the MQTT messages all work.**

**17. Tag.** When the tests above pass:

    git tag -a sat-hub-v6 -m "Satellite firmware v6: alarms, ring settings in the app"
    git push origin sat-hub-v6

Checks Claude ran:
- `pytest homeassistant`: 153 passed (58 phrase checks, 95 logic checks).
- `esphome config`: valid, using a temporary copy with the example secrets (the real `secrets.yaml`
  was never opened).
- `esphome compile`: passes for 0.6.0. Flash use is 19.6% (1.59 MB of the 8.1 MB app space), RAM 39.7%.
- Not run: loading the package in a real Home Assistant, anything over MQTT, anything on the
  hardware.

## Deviations from the plan
- **Several alarms instead of one** (Will's decision when confirming the plan). Built as five slots,
  because Home Assistant helpers have no growing list. Five is Claude's choice.
- **An Alarms dashboard was added** (Will's request during testing). The milestone list had remote
  alarm setting in M6; the alarm part is now here, and M6 keeps the robot status and history.
- **Slots hold a time of day, not a date and time** as first built, so the app only needs a time
  and a switch.
- **The spoken time is parsed by a script, not by the phrase file** as first built, after a real
  phrase was missed.
- **The Home Assistant files are named `hub_alarms.yaml`,** not `alarm.yaml`, after the mix-up with
  the firmware file.
- **Settings moved into the app** (Will's request when confirming the plan, to cover M4 as well).
  Ringing volumes, colours and the timer's timeout are entities on the satellite; the alarm timeout
  is a Home Assistant helper. Sound files and the silence between repeats stay in the firmware.
- **Alarm Volume default is 75%** rather than the 80% first proposed (Will's decision).
- **`pytest` was added to `requirements-dev.txt`** along with the approved `hassil`. CLAUDE.md names
  `pytest` as the test tool but it had not been installed.
- **A small C++ header was added** in `firmware/satellite/includes/` for the circling light, instead
  of a longer inline lambda repeated in two effects.
- **A start-up check was added** that ends an alarm left "ringing" by a Home Assistant restart.

## Known limitations / follow-ups
- **The Home Assistant package has never been loaded.** Its logic is tested with stand-ins, but
  syntax Home Assistant itself rejects would only show at "Check configuration". The way the voice
  handlers pass a script's reply back as speech (`action_response`) is the part most likely to need
  a fix.
- **The entity and action names are assumed** from the device name (section 14.5 checks them).
- **An alarm missed while Home Assistant is off does not fire late.** Its slot stays on and it
  rings the next day at that time, unless it is cancelled.
- **A second alarm that fires while one is ringing is dropped.** Its slot still switches off.
- **If the satellite is offline when an alarm fires,** the MQTT messages still go out and the robot
  runs, but nothing rings and only the robot or the timeout can stop it.
- **If Home Assistant disappears mid-alarm,** the satellite keeps ringing until the knob is turned
  or its 30-minute safety limit.
- **Five alarms at most, each firing once.** No snooze and no repeat.
- **Minutes said as words are limited** to o'clock, oh five, fifteen, twenty, thirty, forty, forty
  five and fifty. Digits always work. "Half past" and "quarter to" are not understood.
- **Any sentence shaped like "set an alarm for ..." is now handled locally,** even when the rest is
  not a time. The hub then says it did not catch the time instead of passing it to Claude.
- **The dashboard's entity ids for the satellite are assumed,** like the names in section 14.5.
- **"Stop" and "Hey Jarvis" over a 75% alarm** may be hard for the hub to hear; the knob always
  works.
- **Changing a colour or volume while the hub is ringing** takes effect for the colour at once and
  for the volume at the next ring.
- **A timer that finishes during an alarm is not rung separately.**
- **Other status colours** (listening, thinking, speaking) are still firmware values; in the backlog.
- **Neither sound has been heard, nor the orange-red seen, by Claude.**
