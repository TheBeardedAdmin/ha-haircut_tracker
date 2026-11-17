# Haircut Tracker Home Assistant Integration

<img src="logo.jpg" align="right" width="120">

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration to monitor wait times, queue status, stylist lineups, and haircut intervals.

> [!NOTE]
> This integration currently supports **SportClips** locations. Support for other popular hair salons and chains is planned for future releases.

## About

**Haircut Tracker** is a Home Assistant custom component designed to streamline your grooming routine and eliminate the guesswork of timing your salon visits.

Instead of manually checking store apps or showing up to unexpected 90-minute wait times, Haircut Tracker integrates directly into your smart home dashboard and automation engine:

- ⏱️ **Live Waitboard Monitoring**: Keep an eye on real-time store queues and estimated wait times from any Home Assistant dashboard or wall panel.
- 💈 **Preferred Stylist Tracking**: Automatically cross-references your past haircut history to identify your favorite stylists and notify you when they are on the clock.
- 📅 **Intelligent Due Reminders**: Calculates the elapsed days since your last haircut and pairs with your preferred interval (e.g. every 21 or 30 days) to trigger reminders only when a trim is actually needed.
- 🧠 **Best Day Predictor**: Analyzes weekly working schedules across all your preferred stylists to highlight the optimal day(s) to visit.
- ⚡ **Resource-Friendly Smart Polling**: Built with a polite polling algorithm that automatically sleeps when the store is closed and wakes up at opening time, preventing unnecessary network traffic.

---

## Features
* **Choose your own metrics**: Open **Settings ? Devices & Services ? Haircut Tracker ? Configure** and tick only the metrics you want to collect. Unticked metrics are not created (existing entities for them are removed). See the full list below.
* **Full weekly store schedule**: A *Weekly Schedule* sensor exposes every day's open/close time (plus holiday/special-hours flags) and a ready-made `markdown` attribute you can drop into a Markdown card.
* **Store-hours aware polling**: The integration only talks to the API while the store is open. When the store closes it sleeps until 5 minutes after the next opening (using the store's own time zone), and never schedules a poll outside opening hours.
* **Stylist roster cache**: The stylist endpoint only returns people while the store is open, so the last known roster and schedules are kept (and survive restarts).
* **Manual Refresh Button**: Exposes a `button` entity to trigger an adhoc update instantly.
* **Dynamic interval**: Polls every 15 minutes (during open hours) when you are due or within 3 days of due, otherwise about twice per open day. The haircut interval is adjustable in the options.

## Available Metrics
Metrics marked *default* are on out of the box; everything else is opt-in via **Configure**. "Account" metrics need your Haircut Tracker email/password.

| Metric | Platform | Default | Account | State | Notable attributes |
| :--- | :--- | :---: | :---: | :--- | :--- |
| Wait Time | sensor | ? | | Current wait (`HH:MM:SS` / `Closed`) | address, phone, store_open, weekly_hours |
| Queue Size | sensor | ? | | People in line | `queue_list` (client, stylist, wait, status) |
| Store Hours | sensor | ? | | Today's hours | `weekly_hours` |
| Weekly Schedule | sensor | ? | | Total open hours this week | `schedule` (per day), `summary`, `markdown`, special-hours days |
| Status & Next Opening | sensor | ? | | Open / Closed | `next_open`, `pin_text`, store_time |
| Expected Start Time | sensor | | | Next expected service start | |
| Queue Breakdown | sensor | | | Queue length | counts by status and by stylist |
| Check-In Cutoff | sensor | | | Online check-in hard stop (min) | early_arrival_minutes, max_wait_for_checkin_minutes |
| Store Info | sensor | | | Store name | address, phone, lat/long, time zone, website/social links |
| Online Check-In | binary_sensor | ? | | On/Off | see_stylist_enabled |
| See Stylist Enabled | binary_sensor | | | On/Off | |
| Store Open | binary_sensor | | | On/Off | store_state_code |
| Haircut Due Status | sensor | ? | ? | Due / Ok | days_since, days_until_due, last stylist/service |
| Favorite Stylists Status | sensor | ? | ? | First working favorite | favorite_schedules, best_days_to_visit, wait time |
| Best Day to Visit | sensor | ? | ? | Day(s) most favorites work | |
| Stylist Roster | sensor | ? | ? | Number of stylists | `roster`: every stylist's weekly hours |
| Days Since Haircut | sensor | | ? | Days | |
| Next Haircut Due | sensor (date) | | ? | Date | |
| Average Days Between Visits | sensor | | ? | Days | total/avg spend, favorite weekday/hour, stylist & service counts, predicted next visit |
| Stylists Working Today | sensor | | ? | Count | `working_today` with hours |

> [!NOTE]
> The stylist schedule endpoint returns no stylists while the store is closed. Roster-based metrics therefore show the last known data until the store reopens.
## Installation

### Method 1: HACS (Recommended)
1. Open **HACS** in your Home Assistant.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Paste the URL of this repository: `https://github.com/TheBeardedAdmin/ha-haircut_tracker`
4. Choose **Integration** as the Category and click **Add**.
5. Click **Download** on the Haircut Tracker integration card.
6. Restart Home Assistant.

### Method 2: Manual Installation
1. Download the latest release.
2. Copy the `custom_components/haircut_tracker` folder into your Home Assistant's `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration
1. In Home Assistant, go to **Settings** -> **Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Haircut Tracker**.
4. Search for your store by zip code, city, or name.
5. (Optional) Provide your email and password to track haircut history and favorite stylists.
6. Configure your preferred haircut frequency (default: 30 days).
7. Afterwards, use **Configure** on the integration to choose which metrics to collect.

## Example Alert Automation
Get notified on your phone when one of your favorite stylists is working and you are due for a haircut:

```yaml
alias: "Alert when Favorite Stylist is Working and Haircut is Due"
trigger:
  - platform: state
    entity_id: sensor.haircut_tracker_favorite_stylists_status
    not_from: "None Working"
condition:
  - condition: state
    entity_id: sensor.haircut_tracker_haircut_due_status
    state: "Due"
action:
  - service: notify.notify
    data:
      title: "Haircut Due!"
      message: >
        {{ states('sensor.haircut_tracker_favorite_stylists_status') }} is working today. 
        Current wait time: {{ state_attr('sensor.haircut_tracker_favorite_stylists_status', 'favorite_wait_time') }}.
```
