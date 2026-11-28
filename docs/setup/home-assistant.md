# Home Assistant setup

How Home Assistant is set up for the Smart Home Hub, and the steps that take it from a fresh install to
everything the satellite needs: a fixed address, backups, an MQTT broker, and a local voice pipeline.

Sections 2 to 10 are steps to do once, in order. Section 11 is the test checklist. Section 12 is for
rebuilding after a failure. Section 13 (added in M4) sets up device commands, timers and Claude for
general questions. Section 14
(added in M5) installs the alarm package. Section 15 (added in M6) adds the robot link.

## Where things happen

| Label | Where that is |
|---|---|
| **Proxmox web UI** | The Proxmox page in a browser, signed in as `root`. The Home Assistant VM is **102 (homeassistant)** on node **pve**. |
| **HA web UI** | Home Assistant in a browser at `http://homeassistant.local`, signed in as the owner. If that name does not load, use `http://` plus the VM's IP address instead. |
| **Router** | The admin page of whatever hands out IP addresses on the network. That is normally the router; if the Pi-hole runs DHCP, it is the Pi-hole's admin page. |
| **Phone** | The Home Assistant Companion app. |

**This install serves its web page on port 80, not Home Assistant's usual 8123.** That is why the
address above has no `:8123` on the end, and why adding it gives a page that does not load. Guides
and tools elsewhere assume 8123; wherever they ask for the Home Assistant URL, give the address
without a port. This only affects the web page and the Companion app. The satellite talks to Home
Assistant on a different port of its own and is not affected.

Nothing in this guide is typed in a terminal, except the rebuild commands in section 12.

Rules that apply to every step:
- **Passwords and keys go in your password manager.** Never in this repo, a PR, a commit or a chat.
- **The VM's IP address is not written in this repo.** Code and config read it from secrets files.
- **Nothing here signs in to a cloud service.** Skip any prompt for Home Assistant Cloud (Nabu Casa).
  The one approved exception is section 13: the text of a question goes to the Claude API.

A note on names: recent Home Assistant versions call add-ons **Apps**. Where this guide says
**Settings → Add-ons**, your version may show **Settings → Apps**. It is the same page.

## 1. What is already in place

Recorded on 2026-11-19, before the steps below:

| Item | State |
|---|---|
| Host | Mini PC running Proxmox VE 9.2, node `pve` |
| VM | 102 `homeassistant`, 4 CPU cores, 8 GiB RAM, 64 GiB boot disk |
| Install type | Home Assistant OS (supports add-ons) |
| Web page port | 80 (the default is 8123; found on 2026-11-20, origin of the setting not known) |
| Other guests on the host | 100 `PiHole`, 101 `tracker` |
| Automatic backups in Home Assistant | on |
| QEMU guest agent | not enabled (section 2 fixes this) |
| Fixed IP | not set (section 4) |
| Mosquitto, Whisper, Piper, Assist pipeline | not set up (sections 6 to 9) |
| Devices, integrations, cloud login | none |

Sections 2 to 10 were completed on 2026-11-20 and the section 11 checklist passed. The VM now has the
guest agent, a reserved address, three backup layers, Mosquitto with its three logins, Whisper, Piper,
and the `Jewel` assistant.

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
2. **Find the address the VM has now.** The reservation form asks for an IP address as well as the
   MAC; use the one the VM already has, so nothing changes or conflicts. Any of these shows it:
   - Proxmox web UI → VM 102 → **Summary → IPs** (needs the guest agent from section 2). Take the
     IPv4 address that belongs to your home network, the one that starts like your other devices'
     addresses (often `192.168.`). Ignore `127.0.0.1`, any `172.` addresses, and the long IPv6 ones.
   - HA web UI → **Settings → System → Network**, under the network adapter's IPv4 details.
   - The router's list of connected devices, on the row with the matching MAC address.
3. **Reserve it.** On the router (see the table at the top), open the DHCP settings, find the
   reservation or "static lease" list, and add an entry with that MAC address and that IP address.
   Many routers offer a "reserve" button directly on the connected-devices row, which fills in both.
4. **Make the VM pick it up.** Proxmox web UI → VM 102 → **Reboot**.
5. **Record the address** in your password manager, next to the Home Assistant login. Later milestones
   put it in gitignored secrets files.

Check: after the reboot, VM 102's **Summary** page shows the reserved address, and
`http://homeassistant.local` still loads. Home Assistant needs two or three minutes after a reboot
before the page answers.

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
   - **Name:** `Jewel`. This is only a label in Home Assistant's menus and can be anything. It is
     not the wake word; "Hey Jarvis" is set in the satellite's firmware (M2).
   - **Language:** English
   - **Conversation agent:** Home Assistant
   - **Speech-to-text:** faster-whisper, language English
   - **Text-to-speech:** piper, language English, voice `alan` (medium)
   - **Wake word:** leave empty. The satellite detects the wake word itself (M2).
3. Click **Create**.
4. Open the new assistant's menu (the three dots) and choose **Set as preferred**. A star marks it.

The conversation agent stays as plain Home Assistant at this point. Section 13 changes it to Claude
for general questions.

## 10. Changing the voice

Trying voices is quick and does not involve the add-on page.

**To change the main voice**

1. HA web UI → **Settings → Voice assistants →** click **Jewel**.
2. In the **Text-to-speech** section, pick a different **Language** and **Voice**. Each voice comes in
   up to three quality levels: `low`, `medium`, `high`. `medium` is the usual balance; `high` sounds
   better and takes longer to start speaking.
3. Click **Update**.
4. Use **Try voice** (the play button next to the voice) or ask a question in Assist to hear it.

The first use of a new voice has a pause of several seconds while Piper downloads it. After that it is
kept on disk.

**To compare voices side by side**

1. Add a second assistant named `Voice test`, with the same settings as Jewel.
2. Change only its voice.
3. In the Assist dialog, switch between assistants with the name shown at the top.

This leaves Jewel, the preferred assistant the satellite will use, untouched until you decide.

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
2. Check the assistant shown is **Jewel**.
3. Type `what time is it` and press Enter.

Pass: it answers with the current time.

### 11.3 Spoken command
A browser will not open the microphone on a plain `http://` page, so this test uses the phone.

1. On the phone, install the **Home Assistant** Companion app, on the same Wi-Fi as the mini PC.
2. Let it find the server, or enter `http://homeassistant.local` by hand. Sign in.
3. When it asks about location and sensor sharing, decline. They are not needed.
4. Open **Assist** in the app, check the assistant is **Jewel**, tap the microphone, allow microphone
   access, and say "what time is it".

Pass: your words appear as text, and the answer is spoken in the chosen voice.

To see timings: HA web UI → **Settings → Voice assistants →** the three dots on Jewel → **Debug**.
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

5. Open `http://homeassistant.local:8123`. A brand-new install uses port 8123; the restore brings
   back this install's port 80 setting, so drop the `:8123` afterwards. On the welcome screen choose **Restore from backup**, upload
   the downloaded backup file, and enter the encryption key. A full restore brings back the add-ons,
   their settings, the MQTT logins and the Assist pipeline.

6. The new VM has a new MAC address. Redo section 4 so it gets the same reserved address as before,
   then run the test checklist in section 11.

## 13. Core voice: devices, timers and questions (M4)

After this section, one sentence to the satellite goes one of two ways:

| What you say | Who handles it | Needs the internet |
|---|---|---|
| A device command, a timer command, "what time is it" | Home Assistant, on the mini PC | no |
| Anything Home Assistant does not recognise, such as a general question | Claude, through the Anthropic integration | yes |

Speech-to-text and text-to-speech stay on the mini PC in both cases. Only the **text** of a question
is sent out, never audio.

Menu and option names below are from Home Assistant's documentation, not from sight of this install.
If a label differs slightly, pick the closest one and note it in the PR.

### 13.1 Make the devices usable by voice

**Where:** HA web UI.

1. **Settings → Voice assistants → Expose** (a tab at the top). Make sure each Nanoleaf light you
   want to control is listed and exposed to **Assist**. Remove anything you do not want voice to
   reach.
2. Click each exposed light and check its name is something you would say out loud, such as
   `Desk lights`. Add an **alias** for any other name you might use.
3. **Settings → Areas, labels & zones:** make sure the lights are in an area, such as `Bedroom`.
4. **Settings → Devices & services → ESPHome → Satellite Hub:** set the satellite's **Area** to the
   room it sits in. "Turn on the lights" with no room name then means the lights in that room.

Check, typed in the Assist dialog with **Jewel** selected: `turn on the desk lights` (use your
light's name). The light turns on and the answer is immediate.

### 13.2 Timers

There is nothing to set up. Home Assistant handles timer sentences itself and tells the satellite
when one finishes; the satellite rings (firmware 0.5.0 and later). Timers only work when spoken to the
satellite; the Assist dialog in the browser cannot hold them.

| Say | What happens |
|---|---|
| "Set a timer for 5 minutes" | starts a timer |
| "Set a pizza timer for 10 minutes" | starts a named timer |
| "How long is left on my timer?" | speaks the time left |
| "Cancel my timer" / "Cancel the pizza timer" | cancels it |

A finished timer rings until you say "stop" or "Hey Jarvis", turn the knob, or five minutes pass.

### 13.3 Get a Claude API key

**Where:** a browser, at `console.anthropic.com`.

1. Create an account or sign in. This is separate from a Claude.ai subscription.
2. Add a small amount of credit under billing. Spoken questions are short, so a few dollars goes a
   long way. Set a low monthly spend limit while you are there.
3. Create an API key named `home-assistant`. Copy it straight into your password manager. It is shown
   only once. Never put it in this repo, a PR, a commit or a chat.

### 13.4 Add the Anthropic integration

**Where:** HA web UI → **Settings → Devices & services → Add integration**.

1. Search for **Anthropic**, select it, and paste the API key when asked.
2. Open the new **Anthropic** entry. It has a conversation agent, usually named **Claude
   conversation**. Open its settings (**Configure**, or the gear on the agent).
3. Set the options:
   - **Instructions:** replace the text with the prompt in 13.5.
   - **Control Home Assistant:** leave every box **unticked**. See "What Claude can and cannot see"
     below.
   - **Recommended model settings:** untick it, so the next options appear.
   - **Model:** the newest **Haiku** model in the list. Haiku is the small, fast tier, which suits
     short spoken answers.
   - **Maximum tokens:** `300`. This limits how long an answer can be.
   - **Web search:** leave it **off**. It can be turned on here later; see the note below.
4. Save.

**What Claude can and cannot see.** With "Control Home Assistant" unticked, Claude gets the text of
what you said, the instructions, the earlier turns of the same conversation, and whatever Home
Assistant adds to every prompt by itself (such as the current date and time). It does not get your
device list or their states, and it cannot switch anything. That matches this project's privacy rule.
The cost: if a device command is phrased so oddly that Home Assistant does not recognise it, it goes
to Claude, which answers that it cannot control devices. Say it again in a plainer form.

**Web search, for later.** The integration can let Claude search the web, which helps with news,
scores and anything recent. It is off for M4 because it adds cost and delay and passes your question
on to a search. To try it, tick **Web search** in the same settings page; untick it to go back. No
firmware change is involved either way.

### 13.5 The prompt

Paste this as the **Instructions**:

```text
You are Jarvis, the voice assistant of a smart home hub. Your reply is read aloud by a speech
synthesiser, so write for the ear.

- Answer in one short sentence, two at the very most, and under 30 words. Give the answer first
  and stop. No introductions, no background, no examples, and no closing remarks or offers of more.
- Go longer only when the user explicitly asks for more detail.
- Use plain spoken English. No lists, headings, markdown, emoji, symbols or URLs.
- Write numbers, units and abbreviations the way they are spoken.
- You cannot control devices, set timers or alarms, or see the state of the home. If asked to, say
  briefly that you could not do that and suggest saying it again more simply.
- If you do not know, or the answer depends on recent events you cannot check, say so in one sentence.
- Do not ask follow-up questions unless you cannot answer without one.
```

**Making answers shorter or longer.** Reply length is controlled in two places, both on the Claude
conversation agent's settings page (**Settings → Devices & services → Anthropic**, then the agent's
**Configure** or gear):

- **Instructions:** the first bullet of the prompt above sets the length. Change the sentence and word
  limits there. This is the main control.
- **Maximum tokens:** a hard ceiling. `300` is about 200 words. Lowering it does not make Claude
  write shorter answers; it cuts a long answer off mid-sentence, so keep it as a safety limit and
  use the instructions to set the length.

A change takes effect on the next question. Nothing is flashed.

### 13.6 Point the assistant at Claude

**Where:** HA web UI → **Settings → Voice assistants →** click **Jewel**.

1. **Conversation agent:** choose **Claude conversation**.
2. Turn **on** the switch **Prefer handling commands locally**. This is what keeps device and timer
   commands on the mini PC and working with no internet. It appears under the conversation agent once
   an agent other than Home Assistant is chosen.
3. Click **Update**.

Check, typed in the Assist dialog with **Jewel** selected:
- `turn on the desk lights` still answers at once (handled locally).
- `why is the sky blue` gets a one or two sentence answer after a second or two (handled by Claude).

To see which side handled a sentence: **Settings → Voice assistants →** the three dots on Jewel →
**Debug**. The last run shows the conversation step and whether it was processed locally.

### 13.7 Going back

To undo this section: open **Jewel**, set **Conversation agent** back to **Home Assistant**, and click
**Update**. To remove Claude completely, delete the **Anthropic** integration and revoke the key at
`console.anthropic.com`.

## 14. Alarms (M5)

Alarms live in Home Assistant: five alarm slots, the logic for firing and stopping them, the MQTT
messages for the robot, and the voice commands. All of it is in two files in this repo's
`homeassistant/` folder, which this section copies onto the live instance.

Do this **after** flashing firmware 0.6.0 or later, because the files refer to things that firmware
adds to the satellite.

As in section 13, menu names are from Home Assistant's documentation, not from sight of this install.

### 14.1 Install the File editor

**Where:** HA web UI → **Settings → Add-ons → Add-on store**.

1. Search for **File editor**, open it, and click **Install**.
2. On the **Info** tab, turn on **Show in sidebar**, then click **Start**.
3. Click **File editor** in the sidebar. The folder icon at the top left opens the file browser,
   which starts in Home Assistant's configuration folder (`/config`, shown as `homeassistant/`).

### 14.2 Turn on packages

**Where:** File editor → folder icon → `configuration.yaml`.

Look for a line that reads exactly `homeassistant:` at the start of a line.

- **If there is none,** add these two lines at the end of the file:

  ```yaml
  homeassistant:
    packages: !include_dir_named packages
  ```

- **If there is one,** add only the second line beneath it, indented by two spaces like its
  neighbours.

Save with the disk icon. Do not restart yet.

### 14.3 Copy the two files

For each file, open it on the PC (in PyCharm, or on GitHub with the **Raw** button), select
everything, and copy it.

| Copy from the repo | Create on Home Assistant |
|---|---|
| `homeassistant/packages/hub_alarms.yaml` | `packages/hub_alarms.yaml` |
| `homeassistant/custom_sentences/en/hub_alarms.yaml` | `custom_sentences/en/hub_alarms.yaml` |

In the File editor's file browser:

1. Use the **new folder** icon to create `packages`. Click into it, use the **new file** icon to
   create `hub_alarms.yaml`, paste, and save.
2. Go back to the top folder. Create the folder `custom_sentences`, then `en` inside it, then the file
   `hub_alarms.yaml` inside that. Paste and save.

Both files are named `hub_alarms.yaml`; the folder is what tells them apart. Take care to copy from
the repo's `homeassistant/` folder. The firmware has its own `firmware/satellite/packages/alarm.yaml`,
which is a different kind of file: pasting that one makes the configuration check fail with an error
about `!lambda`.

### 14.4 Check and restart

1. **Developer tools → YAML → Check configuration.** It must report that the configuration is valid.
   If it reports an error, copy the message into the PR and do not restart.
2. **Settings → System →** the power icon at the top right **→ Restart Home Assistant.** A full
   restart is needed the first time; "quick reload" does not pick up new voice phrases.

### 14.5 Check the names match

The package refers to three things on the satellite by name. Check each exists:

| Where to look | What should be there |
|---|---|
| **Developer tools → Actions**, type `sat_hub` | `esphome.sat_hub_alarm_ring` and `esphome.sat_hub_stop_ring` |
| **Developer tools → States**, type `ringing` | `binary_sensor.satellite_hub_ringing` |

If the two actions are missing, reload the ESPHome integration (**Settings → Devices & services →
ESPHome →** three dots on Satellite Hub **→ Reload**) and look again. If a name is different on your
install, change it in `packages/hub_alarms.yaml` on Home Assistant (each appears once or twice, and the
top of the file lists them), restart, and tell Claude so the repo copy can be corrected.

### 14.6 Set the alarm timeout

**Where:** **Developer tools → States**, type `alarm timeout`, click the entity.

Set **Alarm timeout** to `10`. A new install starts at 1 minute. This is how long an alarm rings
before it gives up; change it here whenever you like.

### 14.7 What you can change from the app

Nothing below needs a flash or a file edit.

**On the satellite** (**Settings → Devices & services → ESPHome → Satellite Hub**, under
**Configuration**):

| Setting | Default | Meaning |
|---|---|---|
| Timer Volume Min / Max | 25% / 50% | a timer rings at the current volume, kept inside this range |
| Alarm Volume | 75% | an alarm always rings at this volume |
| Timer Ring Timeout | 5 min | a timer stops ringing by itself after this |
| Timer Ring Colour | purple | colour and brightness of the circling light for timers |
| Alarm Ring Colour | orange-red | the same, for alarms |

The two colours appear as lights so that Home Assistant shows a colour picker. They are not real
lights: pick a colour and brightness, and the ring uses it the next time it rings. Switching one off
does nothing. Volumes are percentages of the hub's safe range, so 100% is still under the speaker
level cap.

**In Home Assistant** (**Developer tools → States**, or add them to a dashboard):

| Setting | Meaning |
|---|---|
| Alarm timeout | minutes an alarm rings before it gives up |
| Alarm 1 to 5, and Alarm 1 to 5 time | the alarm slots: a switch and a time of day each |

Setting an alarm from the app: pick a slot's time, then turn its switch on. It rings on the hub the
next time the clock reaches that time, then switches itself off. Section 14.11 adds a dashboard page
that puts the alarms and all the settings above in one place.

### 14.8 Voice commands

| Say | What happens |
|---|---|
| "Set an alarm for 7 AM" / "for 7:30 PM" / "for 19:15" | sets an alarm in the first free slot |
| "Set an alarm for" something that is not a time | the hub says it did not catch the time |
| "Set an alarm for 7" | sets it for the next 7 o'clock to come, morning or evening |
| "Wake me up at 6:45" | the same as "set an alarm" |
| "When is my alarm?" / "What alarms are set?" | lists the alarms, soonest first |
| "Cancel my alarm" | cancels the alarm if there is only one; otherwise asks which |
| "Cancel my 7 AM alarm" | cancels that one |
| "Cancel all alarms" | cancels every alarm |
| "Stop the alarm" | stops an alarm that is going off |

An alarm fires once and its slot switches off. While it rings, turning the knob, "stop" or "Hey
Jarvis" also stops it.

### 14.9 Watching the MQTT messages

**Where:** **Settings → Devices & services → MQTT → Configure**.

Under **Listen to a topic**, enter `hub/alarm/#` and start listening. When an alarm goes off a
message appears on `hub/alarm/start`, and when it stops, one on `hub/alarm/stop` with the reason
(`user`, `caught` or `timeout`).

To pretend to be the robot: while an alarm rings, copy the `alarm_id` from the start message and
publish to `alarmbot/caught` with this payload, putting the id in place of `ID`:

```json
{"alarm_id": "ID"}
```

The alarm stops with reason `caught`. A wrong id is ignored.

### 14.10 Going back

Delete `packages/hub_alarms.yaml` and `custom_sentences/en/hub_alarms.yaml` in the File editor and restart Home
Assistant. The alarm helpers, scripts and voice commands disappear. The `packages:` line in
`configuration.yaml` can stay; an empty `packages` folder is harmless.

### 14.11 The Alarms dashboard

A page in the app for setting and changing alarms and for tuning how timers and alarms ring. Alarms
set here ring on the hub exactly like alarms set by voice; both use the same five slots.

**Where:** HA web UI → **Settings → Dashboards**.

1. Click **Add dashboard** and choose **New dashboard from scratch**.
2. Title `Alarms`, icon `mdi:alarm`, leave **Show in sidebar** on, and click **Create**.
3. Open **Alarms** from the sidebar. Click the pencil at the top right to edit. If it asks whether to
   take control of the dashboard, confirm.
4. Click the three dots at the top right and choose **Raw configuration editor**.
5. Delete everything in the editor. On the PC, open `homeassistant/dashboards/hub_alarms.yaml` from
   the repo, copy all of it, and paste it in.
6. Click **Save**, then close the editor and click **Done**.

The page has five cards:

| Card | What it is for |
|---|---|
| Stop the alarm | a button that only appears while an alarm is going off |
| Alarms | the five alarms: a time and an on/off switch each |
| How alarms ring | volume, light colour, how long before giving up, and a button to ring the alarm now as a test |
| How timers ring | quietest and loudest volume, light colour, how long before giving up |
| Status | whether the hub is ringing, and the last alarm id |

**To set an alarm:** tap an alarm's time and pick it, then switch that alarm on. **To change it:**
pick a new time. **To cancel it:** switch it off. An alarm switches itself off after it has rung.

If a row shows "Entity not available", the satellite's entity has a different id on your install.
Edit the card, pick the right entity for that row, and tell Claude so the repo copy can be corrected.

The same dashboard works in the phone app.

## 15. Robot link (M6)

Adds the alarm robot to Home Assistant: whether it is online, what it is doing, the alarm schedule it
reads, and a Robot page on the Alarms dashboard. No firmware is flashed.

There are three parts, and each works without the others:

| Part | Where it runs | What it gives |
|---|---|---|
| `packages/hub_robot.yaml` | Home Assistant | **Hub Robot online**, **Hub Robot state**, and the retained alarm schedule |
| The alarm analytics service | the PC for a first try, then its own Proxmox container | the **Hub Robot** device: battery, wake-up history, catch check, 7-day figures |
| The mock robot | the PC | a stand-in for the robot, for testing |

### 15.1 Copy the package

In the File editor, create `packages/hub_robot.yaml` and paste in all of
`homeassistant/packages/hub_robot.yaml` from the repo. Then **Developer tools → YAML → Check
configuration**, and if it is valid, **Restart Home Assistant**.

Check: **Developer tools → States**, type `hub_robot`. `binary_sensor.hub_robot_online` and
`sensor.hub_robot_state` exist. Both read *unknown* until a robot, real or mock, has connected.

Check the schedule: on the MQTT page (**Settings → Devices & services → MQTT → Configure**), listen to
`hub/alarm/schedule`, then switch any alarm on or off on the Alarms dashboard. A message appears
listing the alarms that are set and `next_epoch`, the moment the next one fires.

### 15.2 Start the analytics service

Follow "Run it on the PC" in `services/alarm-analytics/README.md`. When it prints `Connected to the
broker.`, a **Hub Robot** device appears under **Settings → Devices & services → MQTT** with its
entities. Nothing is typed into Home Assistant for this; the service announces them.

Once it works on the PC, stop it there and move it to its container with
[alarm-analytics.md](alarm-analytics.md).

### 15.3 Update the dashboard

Open the **Alarms** dashboard → pencil → three dots → **Raw configuration editor**. Replace
everything with the new `homeassistant/dashboards/hub_alarms.yaml` from the repo and save. A second
page, **Robot**, appears beside Alarms.

| Card on the Robot page | Shows |
|---|---|
| Robot | online, what it is doing, battery voltage and level, low and critical warnings |
| Last alarm | what stopped it, wake-up delay, time to catch, distance, catch check |
| Last 7 days | average wake-up delay and time to catch, and counts |
| Wake-up history | a 7-day chart of wake-up delay and time to catch |
| Battery | a 24-hour chart |
| Robot settings | the shortest lift that counts as a catch, and the battery warning level |

If a row shows "Entity not available" while the service is running, the entity has a different id on
your install; pick the right one on that row and tell Claude.

### 15.4 Run the mock robot

Follow `tools/mock-robot/README.md`. With the mock running, **Hub Robot online** turns on. Press
**Ring the alarm now (test)** on the Alarms page: the hub rings, the mock "runs" for 15 seconds and
reports caught, the hub goes quiet, and the Robot page fills in.

### 15.5 Going back

Delete `packages/hub_robot.yaml` in the File editor and restart Home Assistant. Stop the analytics
service (and delete the **Hub Robot** device under MQTT if you want its entities gone). Alarms are
unaffected: they never depended on any of this.
