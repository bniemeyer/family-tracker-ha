# HouseKeeper for Home Assistant

*Maintenance for home, garage & gear.*

[![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbniemeyer%2Fhousekeeper-ha)

A Home Assistant app (formerly called an add-on) that keeps track of everything the household owns and has to maintain:

- **Garage**: vehicles, boats, trailers, mowers and UTVs, with photos, registration and insurance dates, oil-change tracking (by date, miles or hours), tires, batteries and a full service history.
- **Parts & tools**: part numbers, cross-references, which vehicles each part fits, how many you have on hand, and a minimum stock level that flags when you're running low.
- **Home maintenance**: recurring tasks such as filters, detector tests and annual service, plus an equipment list with brand, model, serial, filter size, install date and warranty.
- **Seasonal checklists**: fall and spring checklists, either general or tied to one vehicle (winterize the boat, swap the Jeep top). Each one reopens every year.

Everything runs locally on your Home Assistant box. There's no cloud account and nothing leaves your network. Home Assistant gets sensors, a daily reminder (in the sidebar and as a phone push), an automation event and a calendar feed.

---

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [Getting started](#getting-started)
- [Using the app](#using-the-app)
- [Configuration](#configuration)
- [Home Assistant integration](#home-assistant-integration)
- [Backups and data](#backups-and-data)
- [Backup file format](#backup-file-format)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Repository layout](#repository-layout)

---

## Requirements

- Home Assistant **OS** or **Supervised**, because apps need the Supervisor. Container and Core installs can't run apps.
- An `amd64` or `aarch64` machine, such as a Proxmox VM, NUC, Home Assistant Green or Yellow, or a Raspberry Pi 4 or 5.
- About 60 MB of disk for the image, plus your data. Photos take up most of the space.

## Install

1. In Home Assistant go to **Settings → Apps → Install app**. On older versions this is **Settings → Add-ons → Add-on Store**.
2. Open the **⋮** menu → **Repositories** and add:
   ```
   https://github.com/bniemeyer/housekeeper-ha
   ```
   You can also click the **Add repository** badge at the top of this page.
3. Find **HouseKeeper** in the list → **Install**.
4. On the **Info** tab, turn on **Start on boot** and **Show in sidebar**, then click **Start**.
5. Open **HouseKeeper** from the sidebar.

## Getting started

When you open the app for the first time it's empty. Pick one of these:

### Option A: Start from scratch

- **Garage → + Add vehicle**: enter the year, make, model, type, VIN, plate, registration month and mileage. Open the vehicle to fill in insurance, oil interval, tires and the rest, and to add a photo. You can paste or drop a photo onto the page.
- **Home → + Add task** and **+ Add equipment** for the house.
- **Seasonal → + New checklist** for fall or spring jobs.

### Option B: Load the sample data

[`samples/starter-backup.json`](samples/starter-backup.json) is a small example file (about 6 KB) so you can see how everything fits together. It contains:

| Section | Sample content |
|---|---|
| Garage | A 2018 Honda Civic with registration, insurance, tires, an oil interval and 3 service records |
| Parts | An oil filter, and engine oil set below its minimum so it shows as **low stock** |
| Home | A furnace (equipment), a furnace-filter task and a smoke/CO detector test (overdue) |
| Seasonal | "Get the Civic ready for winter" (fall) and "Spring yard & house" |

The dates are set so that the Overview, sensors and reminders all show items right away.

To load it:

1. Download the file. Open [the raw file](https://raw.githubusercontent.com/bniemeyer/housekeeper-ha/main/samples/starter-backup.json), then **right-click → Save as…**.
2. In the app go to **⚙ Settings → Import backup…** and choose the file.

> ⚠️ **Importing replaces everything.** An import erases the app's current data and loads the file. Only import the sample into a fresh install, or download a backup first.

When you're done looking around, you have two ways to clear the sample out. You can edit the sample records into your own, or remove them with each record's **Delete** button. The car has no Delete button, so mark it as sold instead (**Mark as sold / gone**).

### Option C: Restore your own backup

Go to **⚙ Settings → Import backup…** and choose a `family-tracker-backup-*.json` file from **Download backup**. The file can come from this app or from the original Claude artifact version. Records and photos are restored together.

## Using the app

| Tab | What's there |
|---|---|
| **Overview** | Everything overdue, due soon or low on stock, across every section. Click an item to go to it. |
| **Garage** | Cards for active vehicles with **Reg** and **Oil** badges. Sold or retired vehicles are in a collapsed *Sold / gone* group. Open a vehicle to see its details, photo, parts that fit it, its checklists and its service log. |
| **Parts** | Your inventory, grouped by vehicle. **+ / −** buttons adjust the quantity. A part at or below its **Min qty** is marked low. A part can fit several vehicles. |
| **Home** | Recurring tasks with interval, last done and next due, plus your equipment list. Marking a task done logs it and moves the next due date forward. |
| **Seasonal** | Fall and spring checklists. Each one opens in its start month and is due in its due month. Check items off as you go. When every item is checked, or you use **Mark whole list done**, it's done for the year. The checks clear on their own when that season comes around again. |
| **⚙ Settings** | Home Assistant connection status, your reminder settings, the calendar URL, and backup download and import. |

How some of it works:

- **Logging a service updates the vehicle.** For example, an *Oil change* entry sets *Last oil change* and the mileage at that change, and the next due date is worked out from your interval.
- **Hours or miles.** UTVs, mowers and boats default to **hours**; everything else uses **miles**. You can change this per vehicle under *Track usage in*.
- **Oil due.** Oil is due at whichever comes first: the month interval or the miles/hours interval.
- **Linking.** A home task can be linked to a piece of equipment, such as a furnace filter to the furnace. A checklist can be linked to a vehicle.

## Configuration

The app's settings are on its **Configuration** tab (**Settings → Apps → HouseKeeper → Configuration**):

| Option | Default | Description |
|---|---|---|
| **Notify service** | *(blank)* | Optional phone push. Enter the notify service name without `notify.`, for example `mobile_app_brads_phone`. You can find it under **Developer tools → Actions** by searching for `notify.`. |
| **Persistent notification** | on | Posts the daily reminder as a notification in the HA sidebar. |
| **Daily check time** | `06:30` | Local time (24-hour `HH:MM`) when the app checks for due items. It uses Home Assistant's time zone. |
| **Due window (days)** | `14` | Items due within this many days count as *due soon*. |
| **Repeat every (days)** | `7` | How often a reminder is sent again for the same item until you update it. |

Restart the app after you change these settings.

## Home Assistant integration

### Sensors

The app creates these sensors and updates them every 5 minutes and after any change:

| Entity | State | Attributes |
|---|---|---|
| `sensor.family_tracker_overdue` | Number of overdue items | `items`: section, description and due date of each |
| `sensor.family_tracker_due_soon` | Number of items due within the due window | `items` |
| `sensor.family_tracker_low_stock` | Number of parts at or below their minimum | `items` |
| `sensor.family_tracker_next_due` | Date of the next due item | `item`, `as_of` |

The app pushes these states to Home Assistant through its API; they don't come from an integration. After a Home Assistant restart they show *unknown* until the app's next update, which is within 5 minutes. **Settings → Update sensors now** refreshes them right away.

Example dashboard card:

```yaml
type: entities
title: HouseKeeper
entities:
  - sensor.family_tracker_overdue
  - sensor.family_tracker_due_soon
  - sensor.family_tracker_low_stock
  - sensor.family_tracker_next_due
```

### Daily reminder

At the **Daily check time** the app collects everything overdue, due soon or low on stock. It then sends one grouped reminder:

- as a sidebar notification (`notification_id: family_tracker_due`), if **Persistent notification** is on;
- as a push to `notify.<your service>`, if **Notify service** is set. Tapping the push opens the app;
- as the event `family_tracker_reminder`.

An item isn't repeated until **Repeat every (days)** has passed. If nothing new is due, nothing is sent. **Settings → Send reminder now** sends a reminder immediately so you can test it.

### Automation event

`family_tracker_reminder` has this data:

```json
{ "count": 3, "items": ["2018 Honda Civic — Oil change — due Nov 20, 2026 (due in 4 days), 2,200 mi left", "..."] }
```

Example: flash a light when anything is overdue.

```yaml
automation:
  - alias: HouseKeeper – overdue light
    triggers:
      - trigger: numeric_state
        entity_id: sensor.family_tracker_overdue
        above: 0
    actions:
      - action: light.turn_on
        target:
          entity_id: light.garage
        data:
          flash: long
```

Example: send the reminder to a second phone.

```yaml
automation:
  - alias: HouseKeeper – forward reminder
    triggers:
      - trigger: event
        event_type: family_tracker_reminder
    actions:
      - action: notify.mobile_app_amys_phone
        data:
          title: "HouseKeeper: {{ trigger.event.data.count }} due"
          message: "{{ trigger.event.data['items'] | join('\n') }}"
```

### Calendar

The app also serves an iCalendar feed on port **8100**. It includes registrations, oil changes, insurance terms, home tasks, warranty end dates and seasonal checklists. To add it to the HA calendar:

1. Copy the URL shown in **⚙ Settings → Calendar**. It looks like `http://<app hostname>:8100/calendar.ics`.
2. Go to **Settings → Devices & services → Add integration → Remote Calendar** and paste the URL.

The feed can only be reached from inside Home Assistant's internal network, and it's read-only.

## Backups and data

- All data is in the app's `/data` folder: a SQLite database (`tracker.db`) and a `blobs/` folder of photos.
- **Home Assistant backups include it automatically.** The app uses `backup: hot`, so it doesn't stop during a backup.
- **⚙ Settings → Download backup** saves one portable `.json` file with every record and photo, which you can keep anywhere. **Import backup…** restores it, and the restore *replaces* all current data.
- Uninstalling the app deletes `/data`, so download a backup first.

## Backup file format

You can write or generate a backup file yourself to bulk-load data. Use `samples/starter-backup.json` as a reference.

```json
{
  "format": "family-tracker-backup",
  "version": 1,
  "exportedAt": "2026-11-16T06:00:00-06:00",
  "docs": {
    "vehicles/<id>": { ... },
    "vehicles/<id>/service/<id>": { ... },
    "parts/<id>": { ... },
    "equipment/<id>": { ... },
    "home/<id>": { ... },
    "home/<id>/log/<id>": { ... },
    "checklists/<id>": { ... }
  },
  "blobs": { "<photoId>": { "type": "image/jpeg", "data": "<base64>" } }
}
```

`format` and `docs` are required. IDs can be any short slug using letters, numbers, `-` and `_`. Dates are written `YYYY-MM-DD`; registration month is `YYYY-MM`. Blank fields can be `""` or left out.

| Collection | Main fields |
|---|---|
| `vehicles` | `status` (`active`/`gone`), `order`, `year`, `make`, `model`, `trim`, `type` (`ICE`, `EV`, `UTV`, `Mower`, `Trailer`, `Watercraft`), `vin`, `plate`, `regDue`, `mileage`, `usageUnit` (`mi`/`hrs`), `oilTracked`, `lastOil`, `lastOilMiles`, `oilIntervalMonths`, `oilIntervalMiles`, `battery`, `tireSize`, `tiresReplacedDate`, `tiresReplacedMiles`, `tiresRotatedMiles`, `purchaseDate`, `purchasePrice`, `driver`, `insuranceCarrier`, `insurancePolicy`, `insuranceExpires`, `photoId`, `notes` |
| `vehicles/<id>/service` | `date`, `mileage`, `category` (`Oil change`, `Maintenance`, `Repair`, `Tires replaced`, `12V battery`, `Inspection`, `Recall / FSA`, `Damage`), `title`, `shop`, `details`, `payType` |
| `parts` | `kind` (`Part`, `Fluid`, `Tool`), `category`, `name`, `brand`, `partNumber`, `altNumbers`, `fits` (list of vehicle IDs), `qty`, `minQty`, `unit`, `location`, `vendor`, `price`, `url`, `notes` |
| `equipment` | `name`, `area`, `brand`, `model`, `serial`, `specs`, `installDate`, `warrantyEnds`, `filterSize`, `location`, `installer`, `notes` |
| `home` | `name`, `area`, `intervalMonths`, `equipmentId`, `howTo`, `status` (`active`/`archived`), `lastDone`, `nextDue` (overrides the calculated date), `notes` |
| `home/<id>/log` | `date`, `who`, `note` |
| `checklists` | `name`, `season` (`Fall`/`Spring`), `startMonth`, `dueMonth`, `vehicleId`, `notes`, `items` (list of `{id, text, doneAt}`) |

## Updating

When a new version is pushed here, Home Assistant shows an update for the app. To check sooner, go to **Settings → Apps → ⋮ → Check for updates**. Your data stays in `/data` and isn't touched by updates. Changes are listed in [CHANGELOG.md](family_tracker/CHANGELOG.md).

## Troubleshooting

| Problem | What to check |
|---|---|
| Settings says **Not connected** | The Home Assistant API can't be reached. Restart the app. If it continues, check the app **Log** tab for `HA API` errors. |
| Sensors show *unknown* | Normal right after HA restarts. Wait up to 5 minutes or press **Update sensors now**. |
| No phone push | Check that **Notify service** has no `notify.` prefix and matches **Developer tools → Actions**. Use **Send reminder now** and check **Last check** in Settings for the error. |
| No reminder arrived | Reminders are only sent when something is new or due to repeat. **Last check** in Settings shows what happened. |
| Import fails: *"That isn't a HouseKeeper backup file"* | The file needs `"format": "family-tracker-backup"` and a `docs` object at the top level. |
| Calendar doesn't load | Use the exact URL from Settings, including the app hostname and port 8100, not `localhost`. |
| Blank page in the sidebar | Hard-refresh the browser (Ctrl/Cmd+Shift+R). Then check the app's **Log** tab. |

## Development

The server is pure Python standard library, and the front end is a single HTML file, so you can run it locally without Home Assistant:

```bash
mkdir -p /tmp/ft-data
FT_DATA=/tmp/ft-data FT_OPEN_ACCESS=1 python3 family_tracker/app/server.py
# open http://localhost:8099   (calendar: http://localhost:8100/calendar.ics)

# load the sample data
curl -X POST --data-binary @samples/starter-backup.json http://localhost:8099/api/import
```

When it runs outside Home Assistant there's no Supervisor token, so sensors and notifications are skipped and Settings shows *Not connected*. Everything else works.

| Variable | Default | Purpose |
|---|---|---|
| `FT_DATA` | `/data` | Data folder (database, photos, `options.json`) |
| `FT_PORT` | `8099` | UI and API port (Ingress) |
| `FT_ICS_PORT` | `8100` | Calendar feed port |
| `FT_OPEN_ACCESS` | — | Set to `1` to allow any client. By default only the HA Ingress proxy can connect. Use this for local testing only. |

API endpoints (all relative to the Ingress root):

| Method | Path | Purpose |
|---|---|---|
| GET | `api/col?path=…` · `api/doc?path=…` | Read a collection or a document |
| PUT / DELETE | `api/doc?path=…` | Write or delete a document |
| POST | `api/col?path=…` | Add a document with a generated ID |
| GET | `api/changes?since=…` | Long-poll change feed used for live updates |
| POST | `api/blob` · GET `_blob/<id>` | Upload or fetch a photo |
| GET | `api/status` · `api/export` | Status and due items · full backup |
| POST | `api/import` · `api/remind` · `api/publish` | Restore a backup · send a reminder now · update sensors now |

## Repository layout

```
repository.yaml              Home Assistant app repository metadata
samples/
  starter-backup.json        Small sample data set for new users
family_tracker/
  config.yaml                App manifest (version, Ingress, options)
  Dockerfile                 python:3.12-alpine image
  DOCS.md                    Docs shown on the app's Documentation tab
  CHANGELOG.md
  translations/en.yaml       Labels for the Configuration tab
  app/server.py              Backend: document store, API, reminders, sensors, calendar
  app/static/index.html      Front end
```
