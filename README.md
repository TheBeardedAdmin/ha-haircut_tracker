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
* **Wait Time Sensor**: Tracks the current estimated wait time at your local store.
* **Queue Size Sensor**: Tracks the number of checked-in clients and shows the live lineup status in its attributes.
* **Store Hours Sensor**: Shows today's store hours at a glance, with the full weekly hours schedule in its attributes.
* **Online Check-In Status (Binary Sensor)**: Shows if online check-in is currently open/enabled.
* **Haircut Due Status (Authenticated)**: Uses your Haircut Tracker history to calculate the days since your last haircut and lets you know when you are due based on your preferred interval.
* **Favorite Stylist Sensor (Authenticated)**: Monitors if your preferred stylists (extracted from your haircut history) are working today and shows their active wait times.
* **Best Day to Visit Sensor (Authenticated)**: Compares the weekly working schedules of all your favorite stylists and predicts the best day(s) to visit.
* **Manual Refresh Button**: Exposes a `button` entity to trigger an adhoc update of all sensors instantly.
* **Smart Polling & Hammering Prevention**: Auto-adjusts API polling intervals dynamically based on whether you are due, and polls only during store hours. Polling frequency (threshold) can be adjusted dynamically in the integration options.

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
