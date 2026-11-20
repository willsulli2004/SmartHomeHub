# M00 — Repo and workflow
Status: in review   Branch: `milestone/M00-repo-workflow`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/1

## Goal
A clean repo and a repeatable backup → update → test routine before any feature work.

## What was built
- `requirements-dev.txt` — new. Pins `esphome==2026.11.0` so a tagged firmware can be rebuilt with the
  compiler it was first built with.
- `firmware/satellite/secrets.example.yaml` — new. Placeholder values for `wifi_ssid`, `wifi_password`,
  `fallback_ap_password`, `api_encryption_key` and `ota_password`. The API key placeholder is 32 zero
  bytes in base64, so compile-only checks accept it.
- `docs/setup/deploy.md` — new. The backup, update, test and rollback routine, the `sat-hub-vN` tag
  rules, and USB recovery.
- `docs/milestones/M00-repo-and-workflow.md` — new. This doc.
- `docs/MILESTONES.md` — M0 status set to `in review`; the tooling line now names Python 3.12 and the
  pin file.
- `.gitignore` — reviewed, not changed. It already covers secrets, `.venv/`, ESPHome build output,
  `__pycache__/` and IDE files.

Not in git: `.venv` was recreated on Python 3.12 (it was an empty Python 3.14 environment) and ESPHome
2026.11.0 was installed into it.

## How it connects to the rest of the project
M0 adds no runtime parts. It provides what every later milestone relies on:
- M2 copies `secrets.example.yaml` to the real `secrets.yaml`, builds `sat-hub.yaml` with the pinned
  ESPHome, and creates the first tag, `sat-hub-v1`.
- Every milestone doc's "How to deploy" section lists its own commands and points at
  `docs/setup/deploy.md` for the routine.
- M1 extends the Home Assistant backup section with the specifics of the real install.
- Later milestones add their own keys to `secrets.example.yaml` (for example the MQTT broker address),
  which keeps hard rules 4 and 5 enforceable from the start.

## How to deploy
Nothing is flashed and Home Assistant is not touched, so no backup is needed for this milestone.

On any machine that will build firmware, set up the tools once:

    py -3.12 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

To open PRs from this machine, install and sign in to the GitHub CLI:

    winget install --id GitHub.cli
    gh auth login

## How to test
No hardware is involved. Checklist for Will:

1. `.\.venv\Scripts\esphome.exe version` prints `Version: 2026.11.0`.
2. `git check-ignore firmware/satellite/secrets.yaml` prints the path (the real secrets file is ignored).
3. `git check-ignore firmware/satellite/secrets.example.yaml` prints nothing (the example is tracked).
4. `gh auth status` reports a signed-in account.
5. Read `docs/setup/deploy.md` end to end. Pass if every step is one you could follow at M2 without
   asking; note anything unclear or wrong in the PR.
6. The PR for this branch opens and merges. It is the "test PR" from the done criteria.

Checks Claude ran on this branch:
- Items 1 to 3 above: pass.
- `.env`, `HubSecrets.h`, `.venv/`, `.esphome/` and `.idea/` paths are all ignored.
- `secrets.example.yaml` parses as YAML with the five expected keys, and the API key decodes to 32 bytes.
- `pip check` reports no broken requirements.
- Not run: `esphome compile`. There is no `sat-hub.yaml` until M2.
- Item 4: pass, after Will installed `gh` and signed in. The PR was opened with `gh pr create`.

## Deviations from the plan
- The ESPHome version came out as 2026.11.0; the plan did not name a version.
- `gh` was not installed when the branch was finished, so the PR was opened a little later, once Will
  had installed it and signed in.

## Known limitations / follow-ups
- The deploy routine is untested against real hardware until M2 (first flash, first OTA, first rollback).
  Expect corrections to `deploy.md` then.
- The Home Assistant backup steps are generic until M1.
- Only the folders this milestone needs were created (`firmware/satellite/`, `docs/setup/`,
  `docs/milestones/`). The rest of the layout arrives with the milestones that use it.
- `secrets.example.yaml` has no MQTT or Home Assistant address keys yet; M2 and M5/M6 add them.
- There is no CI. The compile check is run by hand.
