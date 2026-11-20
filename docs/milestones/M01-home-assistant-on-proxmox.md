# M01 — Home Assistant on Proxmox
Status: in review   Branch: `milestone/M01-home-assistant`   PR: https://github.com/willsulli2004/SmartHomeHub/pull/2

## Goal
Home Assistant running on the mini PC with everything the satellite needs: a fixed address, backups,
an MQTT broker, and a local voice pipeline.

## What was built
This milestone has no code. Home Assistant OS was already running as VM 102 on Proxmox when it
started, so the work is a guide that records the install and walks through the remaining setup, which
Will carries out.

- `docs/setup/home-assistant.md` — new. The as-found state of the install, then steps for the Proxmox
  VM settings, three backup layers, the fixed IP, a privacy check, Mosquitto with three logins,
  Whisper, Piper, the Assist pipeline, changing the voice, the test checklist, and a rebuild path.
- `docs/setup/deploy.md` — changed.
  - The Home Assistant backup section now names the two automatic layers and the encryption key, and
    the rollback section points at the VM restore.
  - The tagging commands are a worked example with a list of what to change, instead of
    angle-bracket placeholders that PowerShell rejects.
  - A note says there is nothing to tag before M2.
- `docs/milestones/M00-repo-and-workflow.md` — status set to `merged`.
- `docs/MILESTONES.md` — M0 set to `merged`, M1 set to `in review`, and M1's install line reworded to
  match what happened.
- `docs/milestones/M01-home-assistant-on-proxmox.md` — new. This doc.

## How it connects to the rest of the project
This is layer 2 of the architecture, the Home Assistant side that everything else talks to.

- **M2** points the satellite at this Home Assistant and its `Jewel` Assist pipeline. The satellite's
  secrets file gets the fixed address reserved here.
- **M4** changes the pipeline's conversation agent to add Claude for general questions.
- **M5 and M6** publish and subscribe on the Mosquitto broker. The robot uses the `alarmbot` login and
  the analytics service uses `alarm-analytics`. Phase B's Jarvis Core uses `hub`.
- **Every later deploy** starts with the backup routine made real here.

Data flow once M2 exists: satellite audio → Home Assistant → Whisper (text) → conversation agent →
Piper (audio) → satellite. All of it stays on the home network.

## How to deploy
Nothing is flashed. All changes are made by Will in the Proxmox and Home Assistant web pages.

1. **Back up first.** In Home Assistant, **Settings → System → Backups**, create a full backup and
   download it. This is before any add-on is installed, so it is the clean rollback point.
2. Follow `docs/setup/home-assistant.md` sections 2 to 10 in order.

Roll back: restore that backup, or uninstall the three add-ons and delete the `Jewel` assistant.

## How to test
The checklist is section 11 of `docs/setup/home-assistant.md`. Pass criteria, from the milestone's
done-when list:

1. **Reachable:** after a VM reboot, Home Assistant loads at its reserved address and all three
   add-ons start by themselves.
2. **Typed command:** "what time is it" in Assist returns the time.
3. **Spoken command:** the same question spoken in the Companion app is transcribed and answered
   aloud.
4. **MQTT:** a message published to `test/m1` appears in the listener.
5. **Backups:** an automatic backup and `M01-baseline` exist, `M01-baseline` is on the PC, the Proxmox
   job has produced a file, and the encryption key is saved.

Checks Claude ran on this branch:
- Every relative link and section anchor in the changed docs resolves.
- No IP address, password or key appears in any changed file.
- Not run: any step of the guide. Claude has no access to Proxmox or Home Assistant, so the guide is
  untested until Will follows it.

## Deviations from the plan
- **The install already existed.** The milestone plan had Will installing Home Assistant OS from the
  guide. Instead the guide documents the existing VM and covers only the remaining setup; the install
  steps became a short, untested rebuild section.
- **Added: QEMU guest agent and start-at-boot.** The Proxmox screenshot showed the agent was not
  configured.
- **Added: a weekly Proxmox backup job** as a second backup layer, agreed with Will because there is
  no NAS decision yet.
- **Carried over from M0:** the M0 status update and the `deploy.md` placeholder fix.

## Known limitations / follow-ups
- **The guide is written without sight of the live system.** Menu names follow current Home Assistant
  and Proxmox 9; small differences are likely. Will's notes from the run get folded back in on this
  branch before merge.
- **The three MQTT logins are not proven until M6.** The M1 test only exercises Home Assistant's own
  connection.
- **Both automatic backup layers live on the mini PC's disk.** Only the manual download survives that
  disk failing. A USB drive or NAS as Proxmox backup storage would fix this.
- **Whisper model choice is a starting point.** `base-int8` may need to move to `small-int8` once real
  far-field audio arrives from the satellite in M2.
- **The rebuild commands in section 12 have not been run on this host.**
- The mini PC's CPU model was not recorded, so no speed estimate is given for Whisper.
