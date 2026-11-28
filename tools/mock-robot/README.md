# Mock robot

A Python program that behaves like the alarm robot on the MQTT broker, so the hub side can be tested
without the real robot. It follows the contract in
[docs/robot-integration.md](../../docs/robot-integration.md) and doubles as a working example of it.

It connects with the robot's own login (`alarmbot`), announces itself, waits for the hub to start an
alarm, "runs away" while sending telemetry, and reports being caught.

## Set up (once)
From the repo folder, in PowerShell:

    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    Copy-Item tools\mock-robot\.env.example tools\mock-robot\.env

Open `tools\mock-robot\.env` and fill in two values: `MQTT_HOST` (the Home Assistant VM's address) and
`MQTT_PASSWORD` (the `alarmbot` password from your password manager). The file is gitignored. Never
commit it or paste its contents anywhere.

## Run

    cd tools\mock-robot
    ..\..\.venv\Scripts\python.exe -m mock_robot --scenario catch

It prints each message it receives (`<-`) and sends (`->`), except telemetry. Press Ctrl+C to stop;
it marks itself offline as it leaves.

Then start an alarm: press **Ring the alarm now (test)** on the Alarms dashboard, or let a real alarm
fire.

## Scenarios

| `--scenario` | What it does | What you should see |
|---|---|---|
| `catch` (default) | runs for 15 seconds, is "held" for the last 1.5, reports caught | the alarm stops with reason `caught`; the dashboard shows **Catch check** `real` |
| `never` | runs until told to stop | the alarm rings until you stop it or it times out |
| `bump` | reports caught after 8 seconds with almost no lift | the alarm stops, and the dashboard shows **Catch check** `suspicious` |
| `low-battery` | a normal catch on a nearly flat pack | **Battery low** turns on during the chase |
| `offline` | vanishes 6 seconds into the chase | **Hub Robot online** turns off; the alarm keeps ringing until stopped at the hub |

`--catch-after SECONDS` changes how long the chase lasts, for example `--catch-after 5` for a quick
demo.

## Tests

    .\.venv\Scripts\python.exe -m pytest tools/mock-robot

The behaviour (`mock_robot/robot.py`) has no network code, so the tests need no broker. A second set
of tests in `services/alarm-analytics/tests/test_end_to_end.py` runs the mock against the analytics
service.

## Files
| File | What |
|---|---|
| `mock_robot/contract.py` | the topics and message helpers |
| `mock_robot/robot.py` | the behaviour and the five scenarios |
| `mock_robot/__main__.py` | connects the behaviour to the broker |
| `mock_robot/envfile.py` | reads `.env` |
