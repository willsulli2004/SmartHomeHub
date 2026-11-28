# Alarm analytics service on Proxmox

How to run `services/alarm-analytics/` in its own small container on the mini PC, so it is always on.
Do this after the service has been tried on the PC (its README), because problems are easier to see
there.

The container is a Debian LXC container: lighter than a VM and enough for one Python program. The
service runs under systemd, which starts it at boot and restarts it if it stops.

These steps were written without sight of this Proxmox host. Menu names are from Proxmox's
documentation; note anything that differs in the PR.

Rules, as everywhere in this project:
- The broker address and password go only in the container's `/etc/alarm-analytics.env`. Never in
  this repo, a PR, a commit or a chat.
- Stop the copy running on the PC before starting this one. Two copies with the same login knock
  each other off the broker.

## 1. Get a container template

**Where:** Proxmox web UI → **pve → local → CT Templates → Templates**.

Pick the newest **debian-12-standard** (or debian-13 if listed) and click **Download**.

## 2. Create the container

**Where:** Proxmox web UI → **Create CT** (top right).

| Tab | Setting |
|---|---|
| General | CT ID: the next free number (for example 103). Hostname: `alarm-analytics`. Set a root password and save it in your password manager. Leave **Unprivileged container** ticked. |
| Template | the Debian template from step 1 |
| Disks | 4 GiB |
| CPU | 1 core |
| Memory | 256 MiB, swap 256 MiB |
| Network | bridge `vmbr0`, IPv4 **DHCP** |
| DNS | leave as is |

Click **Finish**. Then select the new container → **Options → Start at boot → Yes**, and click
**Start**.

The service only makes outgoing connections to the broker, so the container needs no fixed address.

## 3. Install the service

**Where:** Proxmox web UI → the container → **Console**. Log in as `root`.

1. Install Python's venv support and git:

   ```bash
   apt update && apt install -y python3-venv git
   ```

2. Get the code. The repo is public, so no login is needed:

   ```bash
   git clone https://github.com/willsulli2004/SmartHomeHub.git /opt/SmartHomeHub
   ```

3. Put the service where the systemd unit expects it, with its own Python environment:

   ```bash
   mkdir -p /opt/alarm-analytics && cp -r /opt/SmartHomeHub/services/alarm-analytics/alarm_analytics /opt/alarm-analytics/
   ```
   ```bash
   python3 -m venv /opt/alarm-analytics/venv && /opt/alarm-analytics/venv/bin/pip install -r /opt/SmartHomeHub/services/alarm-analytics/requirements.txt
   ```

4. Create the user the service runs as. It has no password and cannot log in:

   ```bash
   useradd --system --no-create-home --shell /usr/sbin/nologin alarm-analytics
   ```

## 4. Give it the broker settings

Still in the container's console:

1. Create the settings file so that only root can read it:

   ```bash
   install -m 600 /dev/null /etc/alarm-analytics.env && nano /etc/alarm-analytics.env
   ```

2. Type these four lines, with the Home Assistant VM's address and the `alarm-analytics` password
   from your password manager in place of the two blanks. Do not add an `ANALYTICS_DB` line; the
   systemd unit sets where the history is kept.

   ```
   MQTT_HOST=
   MQTT_PORT=1883
   MQTT_USERNAME=alarm-analytics
   MQTT_PASSWORD=
   ```

3. Save with Ctrl+O, Enter, and leave with Ctrl+X.

## 5. Start it

```bash
cp /opt/SmartHomeHub/services/alarm-analytics/deploy/alarm-analytics.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now alarm-analytics
```

Check it:

```bash
systemctl status alarm-analytics --no-pager
```

Pass: it shows **active (running)**, and the log lines include `Connected to the broker.` In Home
Assistant, the **Hub Robot** device's entities are available (not greyed out).

If it shows `Broker refused the connection`, the username or password in the settings file is wrong.
If it cannot reach the broker at all, the address is wrong.

To follow the log live (Ctrl+C to leave):

```bash
journalctl -u alarm-analytics -f
```

## 6. Check it survives a restart

Proxmox web UI → the container → **Reboot**. After a minute, the Hub Robot entities in Home Assistant
are available again without anyone logging in, and the 7-day figures are unchanged.

## Updating to a newer version

In the container's console:

```bash
cd /opt/SmartHomeHub && git pull && rm -rf /opt/alarm-analytics/alarm_analytics && cp -r services/alarm-analytics/alarm_analytics /opt/alarm-analytics/ && systemctl restart alarm-analytics
```

The history file is kept; it lives in `/var/lib/alarm-analytics/`, outside the code.

## Where things are

| What | Where |
|---|---|
| The code | `/opt/alarm-analytics/alarm_analytics/` |
| Its Python environment | `/opt/alarm-analytics/venv/` |
| Broker settings (root only) | `/etc/alarm-analytics.env` |
| Alarm history | `/var/lib/alarm-analytics/history.db` |
| The systemd unit | `/etc/systemd/system/alarm-analytics.service` |
| The log | `journalctl -u alarm-analytics` |

## Backups

The container is not in the weekly Proxmox backup job unless you add it: **Datacenter → Backup →**
edit the job and tick the new container. Without a backup, losing the container loses the wake-up
history, and nothing else; rebuilding it is this page again.

## Removing it

Proxmox web UI → the container → **Stop**, then **More → Destroy**. The Hub Robot entities in Home
Assistant go unavailable. To remove them too, delete the **Hub Robot** device under **Settings →
Devices & services → MQTT**.
