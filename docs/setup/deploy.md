# Deploy routine: back up, update, test, roll back

This is the routine for every milestone that changes the satellite firmware or Home Assistant. Each
milestone doc's "How to deploy" section lists its own commands and points here for the routine.

Who does what:
- **Claude** compiles the firmware and writes the exact commands. It never flashes the satellite and
  never changes the live Home Assistant instance.
- **Will** backs up, flashes, applies Home Assistant changes, tests on hardware and merges.

All commands run from the repo root in PowerShell, with the project's virtual environment active:

```powershell
.\.venv\Scripts\Activate.ps1
```

## One-time setup

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

1. In Home Assistant, open **Settings → System → Backups**.
2. Create a **full** backup (all add-ons, folders and settings). Name it after the milestone, for
   example `before-M05`.
3. Wait until it finishes, then **download a copy** to another machine. A backup that lives only on
   the Home Assistant VM does not survive losing the VM.

M1 adds the specifics for this install (automatic backups, where copies are kept, the Proxmox VM
snapshot as a second safety net) in `docs/setup/home-assistant.md`.

### Satellite firmware

The firmware that is running right now must be rebuildable. That means a git tag `sat-hub-vN` on the
exact commit it was built from.

1. List the existing tags and find the one for the running firmware:

   ```powershell
   git tag --list "sat-hub-v*" --sort=-v:refname
   ```

2. If the running firmware has no tag yet, tag its commit and push the tag before going further:

   ```powershell
   git tag -a sat-hub-vN <commit> -m "Satellite firmware vN: <what it does>"
   ```
   ```powershell
   git push origin sat-hub-vN
   ```

Tag rules:
- `N` counts up by one for every firmware that gets flashed and kept. The first is `sat-hub-v1` (M2).
- Tag the commit that was actually built and flashed. After a milestone PR merges, that is the merge
  result on `main`; if `main` differs from what is on the device, re-flash from `main` and tag that.
- Tags are never moved or deleted. A bad version gets a new, higher tag once it is fixed.
- A tag pins the source and, through `requirements-dev.txt`, the ESPHome version. It does not pin
  `secrets.yaml`, which stays local.

## 2. Update

### Satellite (OTA)

1. Check out the branch or commit to deploy and make sure the tools match it:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

2. Compile first, so a build error never reaches the device:

   ```powershell
   esphome compile firmware/satellite/sat-hub.yaml
   ```

3. Flash over Wi-Fi:

   ```powershell
   esphome run firmware/satellite/sat-hub.yaml --device sat-hub.local
   ```

   If `sat-hub.local` does not resolve, replace it with the satellite's IP address from the router or
   from Home Assistant's device page.

4. Watch the log until the satellite reconnects to Wi-Fi and to Home Assistant.

The very first flash (M2) goes over USB, because OTA needs ESPHome already on the device.

### Home Assistant

Apply the changes listed in the milestone doc (packages from `homeassistant/`, add-on settings,
helpers). Then:

1. Run **Developer tools → YAML → Check configuration** and fix anything it reports.
2. Reload the affected parts, or restart Home Assistant if the milestone doc says so.

## 3. Test

Run the checklist in the milestone doc's "How to test" section, top to bottom. Note every result in
the PR, including failures and anything that looked odd.

- All pass: review and merge the PR, then tag the new firmware as `sat-hub-vN+1` if the satellite
  changed.
- Anything fails: report it in the PR. If the device is still usable, leave it; fixes go on the same
  branch. If it is not usable, roll back.

## 4. Roll back

### Satellite

1. Check out the last good tag:

   ```powershell
   git checkout sat-hub-vN
   ```

2. Install the tool versions that tag was built with:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

3. Flash it over Wi-Fi:

   ```powershell
   esphome run firmware/satellite/sat-hub.yaml --device sat-hub.local
   ```

4. Return to the working branch:

   ```powershell
   git checkout <branch>
   ```

### Home Assistant

1. Open **Settings → System → Backups** and pick the backup taken in step 1.
2. Restore it. Choose a full restore unless the milestone doc names the specific parts to restore.
3. Wait for Home Assistant to restart, then confirm the satellite reconnects.

### Last resort: USB

Use this only when the satellite does not come back on Wi-Fi, so OTA is impossible.

1. Check out the last good tag (as above).
2. Connect the devkit's **UART** USB port to the PC.
3. Find the COM port in Device Manager, then flash over USB:

   ```powershell
   esphome run firmware/satellite/sat-hub.yaml --device COMx
   ```

4. If the upload cannot connect, hold **BOOT**, tap **RESET**, release **BOOT**, and run it again.

Hard rules still apply during recovery: nothing may pull GPIO45 high, and USB-C PD stays at 12V.

## Quick reference

| Step | Command or place |
|---|---|
| HA backup | Settings → System → Backups → full backup, then download |
| List firmware tags | `git tag --list "sat-hub-v*" --sort=-v:refname` |
| Tag firmware | `git tag -a sat-hub-vN <commit> -m "..."` then `git push origin sat-hub-vN` |
| Compile | `esphome compile firmware/satellite/sat-hub.yaml` |
| OTA flash | `esphome run firmware/satellite/sat-hub.yaml --device sat-hub.local` |
| Roll back firmware | `git checkout sat-hub-vN`, reinstall requirements, OTA flash |
| Roll back HA | Settings → System → Backups → restore |
