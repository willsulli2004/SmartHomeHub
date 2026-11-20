# Deploy routine: back up, update, test, roll back

This is the routine for every milestone that changes the satellite firmware or Home Assistant. Each
milestone doc's "How to deploy" section lists its own commands and points here for the routine.

Who does what:
- **Claude** compiles the firmware and writes the exact commands. It never flashes the satellite and
  never changes the live Home Assistant instance.
- **Will** backs up, flashes, applies Home Assistant changes, tests on hardware and merges.

## Where to run things

Every step in this doc happens in one of two places. Each section says which.

| Label | Where that is |
|---|---|
| **PC terminal** | PowerShell on the Windows development PC, in the repo folder (the folder that holds `CLAUDE.md`). PyCharm's built-in Terminal tab opens there already. |
| **HA web UI** | Home Assistant in a browser, signed in as an administrator. |

Nothing is ever typed on the satellite itself, on the Proxmox host, or in a Home Assistant terminal.
The satellite only needs to be powered and on Wi-Fi (or on USB for the last-resort recovery).

Before running any PC terminal command, check you are in the repo folder. This must print `True`:

```powershell
Test-Path .\CLAUDE.md
```

If it prints `False`, move there first (adjust the path if the repo lives somewhere else):

```powershell
cd $HOME\PycharmProjects\SmartHomeHub
```

The commands call the tools inside `.venv` by their path (`.\.venv\Scripts\esphome.exe`), so the
virtual environment does not need to be activated. `git` commands work from the same terminal.

## One-time setup

**Where:** PC terminal, in the repo folder.

1. Create the virtual environment on Python 3.12 and install the pinned tools:

   ```powershell
   py -3.12 -m venv .venv
   ```
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

2. Create the real secrets file from the example and fill in every value. It is gitignored; never
   commit it or paste its contents anywhere.

   ```powershell
   Copy-Item firmware\satellite\secrets.example.yaml firmware\satellite\secrets.yaml
   ```

3. Check that git ignores it. This must print the path:

   ```powershell
   git check-ignore firmware/satellite/secrets.yaml
   ```

## 1. Back up

Do both parts before every update, even a small one.

### Home Assistant

**Where:** HA web UI.

1. In Home Assistant, open **Settings → System → Backups**.
2. Create a **full** backup (all add-ons, folders and settings). Name it after the milestone, for
   example `before-M05`.
3. Wait until it finishes, then **download a copy** to another machine. A backup that lives only on
   the Home Assistant VM does not survive losing the VM.

Two more layers run on their own and are set up in [home-assistant.md](home-assistant.md#3-backups):
Home Assistant's automatic backups (kept on the VM) and a weekly Proxmox backup of the whole VM (kept
on the mini PC). Neither replaces the downloaded copy above, because both live on the mini PC's disk.

Restoring a backup needs the **backup encryption key** from your password manager. Check that it is
there before relying on any backup.

### Satellite firmware

**Where:** PC terminal, in the repo folder.

The firmware that is running right now must be rebuildable. That means a git tag `sat-hub-vN` on the
exact commit it was built from.

1. List the existing tags and find the one for the running firmware:

   ```powershell
   git tag --list "sat-hub-v*" --sort=-v:refname
   ```

2. If the running firmware has no tag yet, tag its commit and push the tag before going further.

   The two commands below are an **example to adapt, not to run as written**. Change three things:
   - `sat-hub-v1`: the next free version number.
   - `a1b2c3d`: the hash of the commit the firmware was built from. Find it with
     `git log --oneline`.
   - the text in quotes: one line on what this firmware does.

   ```powershell
   git tag -a sat-hub-v1 a1b2c3d -m "Satellite firmware v1: ESPHome base, wake word, mute"
   ```
   ```powershell
   git push origin sat-hub-v1
   ```

**Before M2 there is nothing to tag.** No ESPHome firmware exists until M2's first flash, so skip this
whole "Satellite firmware" part until then.

Throughout this doc, `sat-hub-vN` in running text means "the tag with the right number", for example
`sat-hub-v3`. Wherever a command needs a value of yours, the step says so.

Tag rules:
- `N` counts up by one for every firmware that gets flashed and kept. The first is `sat-hub-v1` (M2).
- Tag the commit that was actually built, flashed and tested. That is normally a commit on the
  milestone branch, tagged once its checklist passes and before the PR merges. The tag keeps pointing
  at that commit after the merge, so the firmware stays rebuildable.
- The firmware reports its own version (`firmware_version` in `sat-hub.yaml`), shown in Home
  Assistant on the device page as **Firmware**. Use it to confirm which build is running.
- Tags are never moved or deleted. A bad version gets a new, higher tag once it is fixed.
- A tag pins the source and, through `requirements-dev.txt`, the ESPHome version. It does not pin
  `secrets.yaml`, which stays local.

## 2. Update

### Satellite (OTA)

**Where:** PC terminal, in the repo folder. The PC and the satellite must be on the same network.

1. Check out the branch or commit to deploy and make sure the tools match it:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

2. Compile first, so a build error never reaches the device:

   ```powershell
   .\.venv\Scripts\esphome.exe compile firmware/satellite/sat-hub.yaml
   ```

3. Flash over Wi-Fi:

   ```powershell
   .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local
   ```

   If `sat-hub.local` does not resolve, replace it with the satellite's IP address from the router or
   from Home Assistant's device page.

4. Watch the log, which `esphome run` prints in the same terminal, until the satellite reconnects to
   Wi-Fi and to Home Assistant. Press Ctrl+C to stop watching; that does not affect the satellite.

The very first flash (M2) goes over USB, because OTA needs ESPHome already on the device. It uses the
same command as "Last resort: USB" below.

To read the satellite's log later without flashing anything:

```powershell
.\.venv\Scripts\esphome.exe logs firmware/satellite/sat-hub.yaml --device sat-hub.local
```

### Home Assistant

**Where:** HA web UI, unless the milestone doc says otherwise for a specific step.

Apply the changes listed in the milestone doc (packages from `homeassistant/`, add-on settings,
helpers). The milestone doc says how each file gets from the repo onto Home Assistant. Then:

1. Run **Developer tools → YAML → Check configuration** and fix anything it reports.
2. Reload the affected parts, or restart Home Assistant if the milestone doc says so.

## 3. Test

**Where:** at the satellite and in the HA web UI, as each checklist item says.

Run the checklist in the milestone doc's "How to test" section, top to bottom. Note every result in
the PR, including failures and anything that looked odd.

- All pass: if the satellite changed, tag the commit you flashed as the next `sat-hub-vN`, then
  review and merge the PR.
- Anything fails: report it in the PR. If the device is still usable, leave it; fixes go on the same
  branch. If it is not usable, roll back.

## 4. Roll back

### Satellite

**Where:** PC terminal, in the repo folder.

1. Check out the last good tag. Replace `sat-hub-v1` with that tag's real name:

   ```powershell
   git checkout sat-hub-v1
   ```

2. Install the tool versions that tag was built with:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

3. Flash it over Wi-Fi:

   ```powershell
   .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local
   ```

4. Return to the branch you were working on. Replace `main` with its name if it was a milestone
   branch:

   ```powershell
   git checkout main
   ```

### Home Assistant

**Where:** HA web UI.

1. Open **Settings → System → Backups** and pick the backup taken in step 1. If it is no longer listed,
   upload the copy you downloaded.
2. Restore it. Choose a full restore unless the milestone doc names the specific parts to restore.
   Enter the backup encryption key if asked.
3. Wait for Home Assistant to restart, then confirm the satellite reconnects.

If Home Assistant will not start at all, restore the whole VM from the weekly Proxmox backup instead.
See [home-assistant.md](home-assistant.md#restoring).

### Last resort: USB

**Where:** PC terminal, in the repo folder, with the satellite plugged into the PC by USB.

Use this only when the satellite does not come back on Wi-Fi, so OTA is impossible.

1. Check out the last good tag (as above).
2. Connect the devkit's USB port labelled **USB** (the native one, not the one labelled UART) to the
   PC. The 12V supply may stay connected, as it was for the Arduino tests.
3. Find the COM port: open Device Manager, expand **Ports (COM & LPT)**, and note the entry that
   appears when the cable is plugged in, for example `COM5`. Put that in place of `COMx` below and
   flash over USB:

   ```powershell
   .\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device COMx
   ```

4. If the upload cannot connect, hold **BOOT**, tap **RESET**, release **BOOT**, and run it again.

Hard rules still apply during recovery: nothing may pull GPIO45 high, and USB-C PD stays at 12V.

## Quick reference

| Step | Where | Command or place |
|---|---|---|
| HA backup | HA web UI | Settings → System → Backups → full backup, then download |
| List firmware tags | PC terminal | `git tag --list "sat-hub-v*" --sort=-v:refname` |
| Tag firmware | PC terminal | see the worked example under "Satellite firmware"; fill in the version, commit and message |
| Compile | PC terminal | `.\.venv\Scripts\esphome.exe compile firmware/satellite/sat-hub.yaml` |
| OTA flash | PC terminal | `.\.venv\Scripts\esphome.exe run firmware/satellite/sat-hub.yaml --device sat-hub.local` |
| Roll back firmware | PC terminal | `git checkout sat-hub-vN`, reinstall requirements, OTA flash |
| Roll back HA | HA web UI | Settings → System → Backups → restore |
