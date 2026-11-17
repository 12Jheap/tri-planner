# Running tri-planner on a spare Windows laptop

One old laptop (a Surface is fine) left plugged in, screen off, serving the site to your
phone. It's for you only: there are no accounts or passwords, so it must never be opened
to the whole internet.

## 1. Install (once)

You need [Python 3.12+](https://www.python.org/downloads/) (tick "Add to PATH") and
[Git for Windows](https://git-scm.com/download/win). Git for Windows signs you in to
GitHub through your browser the first time, which is how a private repo gets cloned.

```bat
cd %USERPROFILE%
git clone https://github.com/12jheap/tri-planner.git
cd tri-planner
py -m venv .venv
.venv\Scripts\pip install -e ".[fit,web,garmin]"
```

Copy your settings file in as `athlete.yaml` (or set it up in the site the first time).
Garmin key: Profile → Garmin Connect, or save it as
`%USERPROFILE%\.config\garmin\connect-personal-api-key`. Never put it in the project folder.

Check it runs: double-click `scripts\start-server.bat` (the window stays blank; output goes
to `out\server.log`), then open http://localhost:8000 on the laptop. Close the window to
stop it.

## 2. Keep it awake

- Settings → System → Power: when plugged in, turn the **screen off** after a few minutes
  and set **sleep to Never**.
- Control Panel → Power Options → "Choose what closing the lid does": **Do nothing** when
  plugged in. Now the lid can stay shut.
- Battery: a battery kept at 100% for months swells. If your Surface has it, turn on
  **Battery Limit** (Surface UEFI: hold Volume Up while powering on → Boot configuration →
  Advanced options) or **Smart Charging** in the Surface app. Both hold it around 50–80%.
  If yours has neither, unplug it now and then.

## 3. Start it automatically

Task Scheduler → Create Task (not "Basic Task"):

- **General:** name it `tri-planner`; choose "Run whether user is logged on or not".
- **Triggers:** New → "At startup", delay 1 minute.
- **Actions:** New → Start a program → browse to `scripts\start-server.bat` in your
  tri-planner folder.
- **Settings:** untick "Stop the task if it runs longer than 3 days"; tick "If the task
  fails, restart every 1 minute".

Restart the laptop and check http://localhost:8000. If it's not up, read `out\server.log`.

## 4. Reach it from your phone (same wifi)

- The first time it runs, Windows asks about the firewall: allow it on **Private**
  networks. Your home wifi must be set to Private (Settings → Network → your wifi →
  Network profile type). If you missed the prompt, run this in an admin Command Prompt:
  `netsh advfirewall firewall add rule name="tri-planner" dir=in action=allow protocol=TCP localport=8000 profile=private`
- Find the laptop's address: `ipconfig` → IPv4 Address (e.g. 192.168.1.23). On the phone
  open `http://192.168.1.23:8000`. Give the laptop a fixed address in your router's
  settings ("DHCP reservation") so the link doesn't change. On many home networks
  `http://<laptop name>:8000` works too.
- Add it to your home screen (iPhone: Share → Add to Home Screen; Android: menu → Add to
  Home screen). It opens full-screen with its own icon.

## 5. Reach it from anywhere

Use [Tailscale](https://tailscale.com) (free for personal use): install it on the laptop
and on your phone and sign in to the same account on both. Your phone can then open
`http://<laptop name>:8000` from school, 4G or a hotel, and nobody else can.

Don't forward a port on your router instead: anyone who found the address would have
your plan, your log and your Garmin sync button.

## 6. Calendar

The Week page shows a calendar link (`http://<address>:8000/calendar.ics`). Add it as a
**subscribed calendar on the phone itself** (iPhone: Settings → Calendar → Accounts →
Add Account → Other → Add Subscribed Calendar). The phone re-reads it, so re-plans and moved
sessions appear on their own. Google Calendar's "From URL" won't work: Google fetches it from
its own servers, which can't see your laptop.

## 7. Updating

Double-click `scripts\update-server.bat` (it pulls the latest code and installs anything
new). Then restart the server: Task Scheduler → tri-planner → End, then Run. The version
at the bottom of Profile tells you which code is running.

## 8. Backups

- Every day the site writes a backup to `out\backups\` (the newest 14 are kept).
- A backup on the laptop dies with the laptop. Now and then press **Profile → Download
  backup** on your phone or main computer and keep the zip somewhere else (cloud drive).
- Or from a terminal: `tri-plan backup --to D:\somewhere`.
- To restore: unzip it into the tri-planner folder (it holds `athlete.yaml` and `out\`).
  Backups never contain your Garmin key.
