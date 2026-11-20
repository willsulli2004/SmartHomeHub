# Home Assistant setup

How Home Assistant is set up for the Smart Home Hub, and the steps that take it from a fresh install to
everything the satellite needs: a fixed address, backups, an MQTT broker, and a local voice pipeline.

Sections 2 to 10 are steps to do once, in order. Section 11 is the test checklist. Section 12 is for
rebuilding after a failure.

## Where things happen

| Label | Where that is |
|---|---|
| **Proxmox web UI** | The Proxmox page in a browser, signed in as `root`. The Home Assistant VM is **102 (homeassistant)** on node **pve**. |
| **HA web UI** | Home Assistant in a browser at `http://homeassistant.local:8123`, signed in as the owner. If that name does not load, use the VM's IP address instead. |
| **Router** | The admin page of whatever hands out IP addresses on the network. That is normally the router; if the Pi-hole runs DHCP, it is the Pi-hole's admin page. |
| **Phone** | The Home Assistant Companion app. |

Nothing in this guide is typed in a terminal, except the rebuild commands in section 12.

Rules that apply to every step:
- **Passwords and keys go in your password manager.** Never in this repo, a PR, a commit or a chat.
- **The VM's IP address is not written in this repo.** Code and config read it from secrets files.
- **Nothing here signs in to a cloud service.** Skip any prompt for Home Assistant Cloud (Nabu Casa).

A note on names: recent Home Assistant versions call add-ons **Apps**. Where this guide says
**Settings → Add-ons**, your version may show **Settings → Apps**. It is the same page.

## 1. What is already in place

Recorded on 2026-11-19, before the steps below:

| Item | State |
|---|---|
| Host | Mini PC running Proxmox VE 9.2, node `pve` |
| VM | 102 `homeassistant`, 4 CPU cores, 8 GiB RAM, 64 GiB boot disk |
| Install type | Home Assistant OS (supports add-ons) |
| Other guests on the host | 100 `PiHole`, 101 `tracker` |
| Automatic backups in Home Assistant | on |
| QEMU guest agent | not enabled (section 2 fixes this) |
| Fixed IP | not set (section 4) |
| Mosquitto, Whisper, Piper, Assist pipeline | not set up (sections 6 to 9) |
| Devices, integrations, cloud login | none |

## 2. Proxmox settings for the VM

**Where:** Proxmox web UI → VM 102 → **Options**.

1. **Start at boot:** double-click it and set it to **Yes**. Home Assistant then comes back by itself
   after a power cut.
2. **QEMU Guest Agent:** double-click it, tick **Use QEMU Guest Agent**, and click OK. Home Assistant OS
   already includes the agent; this only tells Proxmox to use it.
3. The agent setting only takes effect after a full power cycle, not a reboot. **Do not use Proxmox's
   Shutdown button for this one.** Once the box is ticked, Proxmox tries to shut the VM down through
   the agent, but the VM has not been restarted with the agent's connection yet, so the request fails
   after a wait with `TASK ERROR: VM quit/powerdown failed - got timeout`. Shut down from inside Home
   Assistant instead:
   1. HA web UI → **Settings → System**, click the power icon at the top right, open **Advanced
      options**, and choose **Shut down system**.
   2. Proxmox web UI: wait until VM 102's status reads *stopped* (under a minute).
   3. Click **Start**.

   From then on, Proxmox's own Shutdown button works normally.

   If Home Assistant's web page is not reachable, the fallback is to untick **Use QEMU Guest Agent**,
   click **Shutdown** (it now works the old way), tick the box again while the VM is stopped, then
   **Start**.

Check: after a minute or two, the VM's **Summary** page shows IP addresses where it used to say
"No Guest Agent configured".

Why it matters: Proxmox can then shut the VM down cleanly, make consistent backups, and show the VM's
address. The memory figure on the Summary page stays high either way; Proxmox counts memory that Home
Assistant OS is only using as disk cache, so about 85% of 8 GiB is normal.

## 3. Backups

There are three layers. Each covers a different failure.

| Layer | Where it is kept | Covers | Runs |
|---|---|---|---|
| Home Assistant automatic backup | on the VM | a bad config change or update | by itself |
| Proxmox backup of VM 102 | on the mini PC, outside the VM | a VM that will not boot | weekly, by itself |
| Downloaded copy | your PC | the mini PC's disk failing | by hand, before every deploy |

### 3.1 Home Assistant automatic backups

**Where:** HA web UI → **Settings → System → Backups**.

These are already on. Confirm three things:

1. Open the backup settings (the **Configure** or gear button) and check the schedule is daily and it
   keeps at least 3 copies.
2. Find the **encryption key** on the same page and save it in your password manager. Without it, a
   backup cannot be restored. This is the single most important step in this section.
3. Check the list shows at least one finished backup.

### 3.2 Weekly Proxmox backup

**Where:** Proxmox web UI.

1. Allow backups on the `local` storage: **Datacenter → Storage →** select **local → Edit**. In
   **Content**, make sure **Backup** (shown as *VZDump backup file* in some versions) is selected, then
   OK.
2. Create the job: **Datacenter → Backup → Add**, with:
   - **Node:** pve
   - **Storage:** local
   - **Schedule:** `sun 03:00`
   - **Selection mode:** Include selected VMs, and tick only **102**
   - **Mode:** Snapshot
   - **Compression:** ZSTD
3. On the job's **Retention** tab, set **Keep Last** to `3`.
4. Click OK, then select the job and click **Run now**.
5. Watch the task at the bottom of the page until it reads **TASK OK**.

Check: VM 102 → **Backup** lists a new file.

Each backup is roughly the size of the data Home Assistant actually uses, not the full 64 GiB. Glance
at **pve → local → Summary** after the first run to confirm three of them fit with room to spare.

### 3.3 Downloaded copy

**Where:** HA web UI → **Settings → System → Backups**.

1. Create a full backup now, named `M01-baseline`.
2. When it finishes, open it and choose **Download**.
3. Keep the file on your PC, outside the repo folder.

From now on this is step 1 of every deploy; see [deploy.md](deploy.md).

Follow-up, not part of this setup: if a USB drive or a NAS is added later, point the Proxmox job's
storage at it. The backups then survive the mini PC's disk, and the manual download becomes optional.

### Restoring

- **One bad change in Home Assistant:** HA web UI → **Settings → System → Backups**, pick a backup,
  **Restore**. Enter the encryption key if asked.
- **The VM will not boot:** Proxmox web UI → VM 102 → **Backup**, pick the newest file, **Restore**.
  This replaces the whole VM with its state at backup time. Then restore a newer Home Assistant backup
  on top if you have one.
- **The mini PC is lost:** follow section 12.

## 4. Fixed IP address

The satellite, the robot and the local services all need Home Assistant to stay at one address. A DHCP
reservation does that without changing anything inside Home Assistant.

1. **Find the VM's MAC address.** Proxmox web UI → VM 102 → **Hardware → Network Device**. It is the
   value that looks like `BC:24:11:xx:xx:xx`.
2. **Reserve an address.** On the router (see the table at the top), open the DHCP settings, find the
   reservation or "static lease" list, and add an entry for that MAC address. Reserving the address
   the VM already has is the simplest choice.
3. **Make the VM pick it up.** Proxmox web UI → VM 102 → **Reboot**.
4. **Record the address** in your password manager, next to the Home Assistant login. Later milestones
   put it in gitignored secrets files.

Check: after the reboot, VM 102's **Summary** page shows the reserved address, and
`http://homeassistant.local:8123` still loads.

Do not also set a static address inside Home Assistant. One source of truth, the reservation, is
easier to change later.

## 5. Privacy check

**Where:** HA web UI.

1. **Settings → System → Analytics:** turn every switch off.
2. **Settings → Home Assistant Cloud:** leave it signed out.
3. **Settings → System → Network:** leave the external URL empty. There is no remote access in this
   project.

Whisper and Piper download their models from the internet once, when first started. After that, all
speech processing runs on the mini PC and no audio leaves the network.

## 6. MQTT broker (Mosquitto)

This is the only MQTT broker in the project. The hub, the robot and the local services all connect to
it.

### 6.1 Install and add the logins

**Where:** HA web UI → **Settings → Add-ons → Add-on store**.

1. Search for **Mosquitto broker**, open it, and click **Install**.
2. Before starting it, open its **Configuration** tab. Under **Logins**, add three entries. Generate a
   different long password for each in your password manager first.

   | Username | Used by | First needed |
   |---|---|---|
   | `hub` | hub-side clients outside Home Assistant, such as Jarvis Core | Phase B |
   | `alarmbot` | the alarm robot | M6 |
   | `alarm-analytics` | the alarm analytics service | M6 |

   If the page shows a text box instead of a form, the shape is as follows. The `...` stands for the
   password you generated; do not save this file with real passwords anywhere else.

   ```yaml
   logins:
     - username: hub
       password: "..."
     - username: alarmbot
       password: "..."
     - username: alarm-analytics
       password: "..."
   ```

3. Click **Save**.
4. On the **Info** tab, turn on **Start on boot** and **Watchdog**, then click **Start**.
5. Open the **Log** tab and check there are no errors.

Notes:
- Home Assistant itself does not use any of these logins. It connects with an account the add-on
  creates for it automatically.
- The usernames `homeassistant` and `addons` are reserved; do not create them.
- The add-on stores these passwords in its configuration, which is included in backups. That is one
  reason backups are encrypted.
- Leave the add-on's other options (certificates, anonymous access, custom config) at their defaults.
  Anonymous access stays off.

### 6.2 Connect Home Assistant to the broker

**Where:** HA web UI → **Settings → Devices & services**.

1. An **MQTT** card appears under **Discovered**. Click **Add** (or **Configure**) on it.
2. Confirm the prompt to use the Mosquitto add-on, and click **Submit**.

Check: **MQTT** now appears in the list of configured integrations.

## 7. Speech-to-text (Whisper)

**Where:** HA web UI → **Settings → Add-ons → Add-on store**.

1. Search for **Whisper**, open it, and click **Install**.
2. On the **Configuration** tab, set:
   - **Model:** `base-int8`
   - **Language:** `en`
   - **Beam size:** `1`
3. Click **Save**.
4. On the **Info** tab, turn on **Start on boot** and **Watchdog**, then click **Start**.
5. Watch the **Log** tab. The first start downloads the model and takes a few minutes; it is ready
   when the log says it is listening.

Then add it to Home Assistant: **Settings → Devices & services**, find the **Wyoming Protocol** card
for Whisper under **Discovered**, click **Add** and **Submit**.

Tuning, for later: if speech is often misheard, change **Model** to `small-int8` and restart the
add-on. It is more accurate and slower. Keep it only if a short command still gets its reply within
about three seconds; the pipeline debug view in section 11 shows the timing.

## 8. Text-to-speech (Piper)

**Where:** HA web UI → **Settings → Add-ons → Add-on store**.

1. Search for **Piper**, open it, and click **Install**.
2. On the **Configuration** tab, set **Voice** to `en_GB-alan-medium`. This is only the default voice;
   section 10 shows how to switch without touching the add-on.
3. Click **Save**.
4. On the **Info** tab, turn on **Start on boot** and **Watchdog**, then click **Start**.
5. Watch the **Log** tab until the voice has downloaded and it reports ready.

Then add it to Home Assistant the same way as Whisper: **Settings → Devices & services**, the
**Wyoming Protocol** card for Piper under **Discovered**, **Add**, **Submit**.

Check: **Wyoming Protocol** in the integrations list now shows two entries, Whisper and Piper.

## 9. Assist pipeline

**Where:** HA web UI → **Settings → Voice assistants**.

1. Click **Add assistant**.
2. Fill it in:
   - **Name:** `Jarvis`
   - **Language:** English
   - **Conversation agent:** Home Assistant
   - **Speech-to-text:** faster-whisper, language English
   - **Text-to-speech:** piper, language English, voice `alan` (medium)
   - **Wake word:** leave empty. The satellite detects the wake word itself (M2).
3. Click **Create**.
4. Open the new assistant's menu (the three dots) and choose **Set as preferred**. A star marks it.

The conversation agent stays as plain Home Assistant for now. M4 adds Claude for general questions.

## 10. Changing the voice

Trying voices is quick and does not involve the add-on page.

**To change the main voice**

1. HA web UI → **Settings → Voice assistants →** click **Jarvis**.
2. In the **Text-to-speech** section, pick a different **Language** and **Voice**. Each voice comes in
   up to three quality levels: `low`, `medium`, `high`. `medium` is the usual balance; `high` sounds
   better and takes longer to start speaking.
3. Click **Update**.
4. Use **Try voice** (the play button next to the voice) or ask a question in Assist to hear it.

The first use of a new voice has a pause of several seconds while Piper downloads it. After that it is
kept on disk.

**To compare voices side by side**

1. Add a second assistant named `Voice test`, with the same settings as Jarvis.
2. Change only its voice.
3. In the Assist dialog, switch between assistants with the name shown at the top.

This leaves Jarvis, the preferred assistant the satellite will use, untouched until you decide.

Samples of every voice can be heard on the Piper project's voice samples page; search for
"Piper voice samples". Voices to try for a Jarvis feel: `en_GB-alan-medium`,
`en_GB-northern_english_male-medium`, `en_US-ryan-high`.

Note for M2: the satellite speaks through whichever assistant is selected for it, so a voice change
made here carries over with no firmware change.

## 11. Test checklist

Run these in order after sections 2 to 10. Note each result in the PR.

### 11.1 Reachable at a fixed address after a reboot
1. Proxmox web UI → VM 102 → **Reboot**.
2. Wait about two minutes.

Pass: the HA web UI loads again, the Summary page shows the reserved address, and the Mosquitto,
Whisper and Piper add-ons are all running (**Settings → Add-ons**) without being started by hand.

### 11.2 Typed command
1. HA web UI → click the **Assist** icon at the top right of the dashboard.
2. Check the assistant shown is **Jarvis**.
3. Type `what time is it` and press Enter.

Pass: it answers with the current time.

### 11.3 Spoken command
A browser will not open the microphone on a plain `http://` page, so this test uses the phone.

1. On the phone, install the **Home Assistant** Companion app, on the same Wi-Fi as the mini PC.
2. Let it find the server, or enter `http://homeassistant.local:8123` by hand. Sign in.
3. When it asks about location and sensor sharing, decline. They are not needed.
4. Open **Assist** in the app, check the assistant is **Jarvis**, tap the microphone, allow microphone
   access, and say "what time is it".

Pass: your words appear as text, and the answer is spoken in the chosen voice.

To see timings: HA web UI → **Settings → Voice assistants →** the three dots on Jarvis → **Debug**.
The last run shows how long speech-to-text and text-to-speech each took.

The app connects straight to Home Assistant on the local network. Its push notifications would travel
through Apple or Google; this project does not use them.

### 11.4 MQTT publish and subscribe
**Where:** HA web UI → **Settings → Devices & services → MQTT → Configure** (the gear).

1. Under **Listen to a topic**, enter `test/m1` and click **Start listening**.
2. Under **Publish a packet**, enter topic `test/m1` and payload `hello`, then click **Publish**.

Pass: the message `hello` on `test/m1` appears in the listening box.

This proves the broker and Home Assistant's own connection. The three logins from section 6 are
proven in M6, when the mock robot connects with them.

### 11.5 Backups exist
Pass, all four:
- **Settings → System → Backups** lists an automatic backup and `M01-baseline`.
- `M01-baseline` is saved on your PC.
- Proxmox web UI → VM 102 → **Backup** lists a file from the weekly job's first run.
- The backup encryption key is in your password manager.

## 12. Rebuilding from scratch

Use this only if the mini PC or its disk is replaced. If the VM still exists, restore instead
(section 3).

**Fastest path, with a Proxmox backup file available:** copy the file into the new host's backup
storage, then Proxmox web UI → **pve → local → Backups →** select it → **Restore**.

**Otherwise, create a new VM and restore a Home Assistant backup into it.** These commands run in the
Proxmox **Shell** (Proxmox web UI → **pve → Shell**). They describe one standard way to create the VM;
the original VM 102 may have been created differently, and this path has not been run on this host.

1. Download and unpack the Home Assistant OS image for KVM. Look up the newest version number on the
   Home Assistant OS releases page (github.com/home-assistant/operating-system/releases) and put it in
   the first command in place of `16.3`, which is only an example:

   ```bash
   VER=16.3
   ```
   ```bash
   cd /tmp && wget "https://github.com/home-assistant/operating-system/releases/download/${VER}/haos_ova-${VER}.qcow2.xz" -O haos.qcow2.xz && unxz haos.qcow2.xz
   ```

2. Create the VM with the same shape as the original. Home Assistant OS needs UEFI with Secure Boot
   off, which is what `pre-enrolled-keys=0` does:

   ```bash
   qm create 102 --name homeassistant --memory 8192 --cores 4 --cpu host --machine q35 --bios ovmf --efidisk0 local-lvm:0,efitype=4m,pre-enrolled-keys=0 --scsihw virtio-scsi-pci --net0 virtio,bridge=vmbr0 --agent 1 --onboot 1
   ```

3. Import the image as the VM's disk, attach it, make it the boot disk, and grow it to 64 GiB:

   ```bash
   qm importdisk 102 /tmp/haos.qcow2 local-lvm
   ```
   ```bash
   qm set 102 --scsi0 local-lvm:vm-102-disk-1 --boot order=scsi0
   ```
   ```bash
   qm resize 102 scsi0 64G
   ```

   If the second command reports that the disk does not exist, check the disk's real name under
   VM 102 → **Hardware** (it appears as *Unused Disk*) and use that name.

4. Start the VM:

   ```bash
   qm start 102
   ```

5. Open `http://homeassistant.local:8123`. On the welcome screen choose **Restore from backup**, upload
   the downloaded backup file, and enter the encryption key. A full restore brings back the add-ons,
   their settings, the MQTT logins and the Assist pipeline.

6. The new VM has a new MAC address. Redo section 4 so it gets the same reserved address as before,
   then run the test checklist in section 11.
