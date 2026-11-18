# HouseKeeper

*Maintenance for home, garage & gear.*

Garage (vehicles, service history, photos, parts & tools), home maintenance, and seasonal checklists — running locally in Home Assistant.

## First run

1. Start the app and open **HouseKeeper** from the sidebar.
2. Go to **⚙ Settings → Import backup…** and pick your `family-tracker-backup-*.json` file. Everything (records and photos) loads in one step.

New here? Import [`samples/starter-backup.json`](https://raw.githubusercontent.com/bniemeyer/housekeeper-ha/main/samples/starter-backup.json). It has one car, a few parts, home tasks and checklists so you can see how things fit together. An import **replaces** all existing data, so only use it on a fresh install. See the [README](https://github.com/bniemeyer/housekeeper-ha#readme) for the full guide.

## Reminders

Once a day (at **Daily check time**) the app looks for anything due within the **due window**, overdue, or low on stock, and:

- posts a Home Assistant notification (if **Persistent notification** is on),
- sends a push to your phone if you set **Notify service** (for example `mobile_app_brads_phone`),
- fires an event `family_tracker_reminder` you can use in automations.

The same item is repeated every **Repeat every (days)** until you update it.

## Entities

| Entity | State |
|---|---|
| `sensor.family_tracker_overdue` | number of overdue items (list in `items` attribute) |
| `sensor.family_tracker_due_soon` | number of items coming up |
| `sensor.family_tracker_low_stock` | parts at or below their minimum |
| `sensor.family_tracker_next_due` | date of the next due item |

These are refreshed every 5 minutes and right after any change.

## Calendar

Add the **Remote Calendar** integration with the URL shown in the app's Settings
(`http://<app hostname>:8100/calendar.ics`) to put every registration, oil change,
home task and seasonal checklist on the HA calendar.

## Data

Everything lives in the app's `/data` folder (SQLite + photos) and is included in Home Assistant backups.
Settings → **Download backup** gives you a single portable file as well.
