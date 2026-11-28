# Home Assistant configuration

The parts of Home Assistant's configuration that this project owns, kept here so they are versioned.
Nothing in this folder reaches the live instance by itself: Will copies the files across. The steps
are in sections 14 and 15 of [docs/setup/home-assistant.md](../docs/setup/home-assistant.md).

| File here | Goes on Home Assistant at | What it is |
|---|---|---|
| `packages/hub_alarms.yaml` | `/config/packages/hub_alarms.yaml` | Alarm helpers, scripts, automations and voice intents (M5) |
| `packages/hub_robot.yaml` | `/config/packages/hub_robot.yaml` | Robot online and state entities, and the retained alarm schedule the robot reads (M6) |
| `custom_sentences/en/hub_alarms.yaml` | `/config/custom_sentences/en/hub_alarms.yaml` | The spoken alarm phrases (M5) |
| `dashboards/hub_alarms.yaml` | pasted into a dashboard's raw configuration editor | The Alarms dashboard for the app: set alarms and tune how timers and alarms ring (M5), plus a Robot page (M6) |
| `tests/` | not copied | `pytest` checks for the two files above |

A file changed here must be copied again, and Home Assistant restarted, before the change is live.

## Tests
From the repo folder:

    .\.venv\Scripts\python.exe -m pytest homeassistant

- `tests/test_robot_package.py` checks the robot entities and the schedule message.
- `tests/test_alarm_sentences.py` matches phrases with `hassil`, the matcher inside Home Assistant.
- `tests/test_alarm_templates.py` runs the time parsing, arithmetic and wording with stand-ins for
  Home Assistant's template functions, and checks the dashboard only names entities that exist.

The tests cannot check that Home Assistant loads the package. After copying, use **Developer tools →
YAML → Check configuration** before restarting.

## Rules
- No IP addresses, passwords or keys in these files. MQTT topics are fine; credentials are not.
- New features fire or listen for the semantic events (`hub_alarm_started`, `hub_alarm_stopped`)
  instead of wiring triggers straight to devices.
- Values someone might want to tune are helpers, so they can be changed from the app.
