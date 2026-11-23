# Home Assistant configuration

The parts of Home Assistant's configuration that this project owns, kept here so they are versioned.
Nothing in this folder reaches the live instance by itself: Will copies the files across. The steps
are in section 14 of [docs/setup/home-assistant.md](../docs/setup/home-assistant.md).

| File here | Goes on Home Assistant at | What it is |
|---|---|---|
| `packages/hub_alarms.yaml` | `/config/packages/hub_alarms.yaml` | Alarm helpers, scripts, automations and voice intents (M5) |
| `custom_sentences/en/hub_alarms.yaml` | `/config/custom_sentences/en/hub_alarms.yaml` | The spoken alarm phrases (M5) |
| `tests/` | not copied | `pytest` checks for the two files above |

A file changed here must be copied again, and Home Assistant restarted, before the change is live.

## Tests
From the repo folder:

    .\.venv\Scripts\python.exe -m pytest homeassistant

- `tests/test_alarm_sentences.py` matches phrases with `hassil`, the matcher inside Home Assistant.
- `tests/test_alarm_templates.py` runs the time and wording logic with stand-ins for Home Assistant's
  template functions.

The tests cannot check that Home Assistant loads the package. After copying, use **Developer tools →
YAML → Check configuration** before restarting.

## Rules
- No IP addresses, passwords or keys in these files. MQTT topics are fine; credentials are not.
- New features fire or listen for the semantic events (`hub_alarm_started`, `hub_alarm_stopped`)
  instead of wiring triggers straight to devices.
- Values someone might want to tune are helpers, so they can be changed from the app.
