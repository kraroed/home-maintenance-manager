# Home Maintenance Manager

A Home Assistant custom integration for planning, tracking, and recording recurring home maintenance.

> **Release status:** The integration is published through GitHub releases and can be installed with HACS as a custom repository.

## Current capabilities

- A built-in library of suggested maintenance tasks, enabled individually.
- A built-in catalog of 120 suggested tasks across HVAC, fire and home safety, plumbing, appliances, electrical, interior, exterior, landscaping, seasonal preparation, and optional home systems.
- Built-in inspection guides for all 120 tasks, with practical steps, warning signs, recommended next actions, and safety precautions.
- Custom inspection guidance for user-created tasks, editable alongside task details.
- User-created recurring maintenance tasks with configurable categories, descriptions, and intervals.
- Custom task editing, including interval, annual calendar-date, and monthly weekday-pattern schedules, while retaining task identity and completion history.
- Custom task removal from active tracking, with completion history preserved.
- Editable intervals for recurring built-in tasks.
- Completion-based scheduling: completing a task restarts its schedule.
- Task rescheduling without marking work complete, with a retained record of the previous due date, new due date, and optional reason.
- Permanent completion history, including optional notes and linked equipment details.
- Complete JSON backup and guarded restore for property configuration, tasks, equipment, settings, reminder state, and completion history.
- Seasonal schedules with configurable date windows.
- Monthly calendar patterns such as the first Saturday, second Tuesday, or last Sunday of each month.
- Household equipment records with name, category, manufacturer, model, installation date, expected lifespan, and notes.
- Associate one or more enabled maintenance tasks with registered equipment, including one designated replacement task when lifespan scheduling is configured.
- Equipment lifespan scheduling calculates a replacement due date from the installation date and expected lifespan. Only the designated replacement task is affected; routine maintenance schedules remain independent.
- Completing a designated replacement task records the completion, resets that equipment item's installation date, and starts its next lifespan period.
- Equipment sensors expose equipment details, associated task IDs, and calculated replacement due dates.
- Home Assistant entities for task status and household maintenance summaries.
- Individual due-soon and overdue reminders, plus a configurable daily summary.
- Configurable reminder lead time and notification destination, with persistent notifications as the fallback. Mobile app reminders include actions to mark a task complete or snooze it until tomorrow or one week later.
- Optional update-triggered JSON backups when selected Home Assistant update entities report a new update, with duplicate prevention by entity and version.
- Optional installation-start tracking for monitored update entities, including a persistent notification that identifies whether a matching update-available backup was recorded. This is an early backup, not a guaranteed pre-install backup.

## Built-in maintenance task library

The built-in catalog contains 120 individually selectable tasks across ten categories: HVAC and ventilation (14), fire and home safety (14), plumbing and water systems (16), appliances and kitchen (14), electrical systems (8), interior maintenance (10), roof, gutters, and exterior (14), landscaping and irrigation (12), seasonal preparation (8), and optional home systems (10). Optional-system tasks cover items such as private wells, septic systems, generators, pools and spas, radon mitigation, crawlspaces, and solar systems.

Each built-in task includes concise homeowner-oriented guidance. Instructions distinguish visual checks and user-serviceable work from tasks that require a qualified professional. Treat the guidance as a starting point and follow the specific product manual and local requirements. The recommended intervals are starting points, not universal service requirements. Review each task against the equipment manufacturer's instructions, local regulations, household conditions, and professional advice. Seasonal tasks use the configurable season windows. Long-term inspections and service reviews use longer editable intervals. All library tasks remain disabled until individually selected for a property.

## Custom maintenance task management

Open the integration's **Configure** options and choose **Manage custom maintenance tasks**. Select a custom task to edit its name, category, description, or recurring schedule. Choose an interval, an annual month/day, or a monthly weekday pattern (first through fourth, or last; Monday through Sunday). Editing keeps the task ID and completion history intact. You can also remove it from active tracking. Removing a task disables it, removes it from the custom task library and enabled-task list, and clears equipment associations; existing task and completion records are retained.

## Equipment tracking

Open the integration's **Configure** options, then choose **Add household equipment**. Enter an equipment name and category; manufacturer, model, installation date, lifespan, and notes are optional. Select any enabled maintenance tasks that apply to that equipment. To enable automatic replacement scheduling, enter all three of: an installation date, expected lifespan in months, and a designated replacement task. The designated task is automatically added to the equipment's task associations, and each equipment record must have its own replacement task. The calculated replacement date makes that task due through the normal dashboard and notification system; other associated routine tasks keep their own schedules. When you complete the replacement task, the equipment's installation date is reset to the completion date and the next replacement date is recalculated. One routine task can still be associated with multiple equipment records.

Each registered item creates an equipment sensor. Its attributes include the equipment metadata and associated task IDs. A summary sensor reports the number of registered equipment records.

Equipment can be added, edited, and removed through the integration options flow. To manage an existing record, open **Configure → Manage household equipment**, select the item, then choose whether to edit its details and task associations or remove it. Removing an equipment record does not delete maintenance tasks or completion history; historical records retain the equipment IDs captured when the task was completed.

## Maintenance notifications

Open **Configure → Configure maintenance notifications** to enable individual task reminders and/or a daily summary. Set how many days ahead to remind, choose the summary time in 24-hour `HH:MM` format, and optionally select an available Home Assistant mobile app notify service from the discovered list (or enter one manually if none are registered). The selection is stored in this integration's options and is not tied to a particular phone. The integration calls that service directly, including mobile notification action data. Individual reminders include the exact due date and associated equipment names when available. Daily summaries group overdue tasks separately from upcoming tasks and include due dates and equipment context. When the target is a Home Assistant mobile app notification service, each individual reminder includes actions to **Mark complete**, **Tomorrow**, or **In 1 week**. Completing a task records it in permanent history and refreshes the integration; snoozing delays that reminder without changing the task's due date. If no target is configured, the integration creates Home Assistant persistent notifications instead (these do not include mobile action buttons). Reminder delivery and snooze state are tracked in integration storage so a task is not repeatedly announced for the same due date, and the daily summary is sent once per day.

## Maintenance history export

Call **`home_maintenance_manager.export_history`** from Developer Tools → Actions, or use it in an automation. Choose `csv`, `json`, or `both` (the default). The integration writes completion-history files (`maintenance_history.csv` and/or `maintenance_history.json`) and separate schedule-change audit files (`maintenance_schedule_history.csv` and/or `maintenance_schedule_history.json`) under `/config/www/home_maintenance_manager/<entry_id>/`. A persistent notification provides links to each file. Schedule-change exports include the task ID and name, change timestamp and type, reason, previous and new due dates, and previous and new schedule definitions. JSON exports include the property name and record count. Export files are overwritten by the next export in the same format.

## JSON backup and restore

Use **Developer Tools → Actions** to run the backup services:

1. Run `home_maintenance_manager.create_backup`. With one configured property, no additional fields are needed. With multiple properties, leave `integration_instance` empty to back up all properties or specify one config entry ID/storage key.
2. The integration creates a complete JSON file in the protected folder `/config/home_maintenance_manager_backups/<entry_id>/` and displays the saved path in a persistent notification. This folder is outside `www`, so backup contents are not exposed as public Home Assistant static files.
3. To restore a backup, use File Editor to place the JSON file in that property's backup folder.
4. Run `home_maintenance_manager.preview_restore` with the JSON **filename** (not its full path). The preview validates the file and reports task, equipment, and history counts. Preview does not change live data.
5. After reviewing the preview, run `home_maintenance_manager.restore_backup` with the same filename and set `confirm: true`.

A restore first writes an automatic pre-restore backup beside the uploaded file. Tasks, equipment, settings, reminder state, and property options are restored from the selected backup. Completion history is merged by `history_id`: records already on the current system are retained, and missing records from the backup are added without duplicates. A malformed, unsupported, oversized (over 10 MB), or unsafe filename is rejected before live data is changed. Restore is limited to one selected property at a time; when multiple properties are configured, provide `integration_instance` to both preview and restore.

## Update-triggered backups

Open **Configure → Configure update-triggered backups** to optionally create a property JSON backup when an update becomes available and/or receive a notification when an update starts installing. Select specific update entities, or leave the entity list empty to monitor all update entities. Update-triggered backup files are stored in the same protected property backup folder as manual and scheduled backups. They are not included in scheduled-backup retention cleanup. A backup is created when the update first becomes available, which may be hours or days before installation; installation-start tracking cannot pause the update or guarantee that a backup finishes before installation begins. Keep Home Assistant's own backup-before-update option enabled for full-system protection.

## Lovelace dashboard card

The Lovelace dashboard card is maintained separately from this integration so that frontend updates can be released independently.

- **Standalone card repository:** https://github.com/kraroed/lovelace-home-maintenance-manager-card
- Install and update the card through HACS as a Dashboard repository.
- The card requires this Home Maintenance Manager integration to be installed and configured.

For card features, configuration, and installation instructions, see the standalone card repository's README.

## Installation

1. In Home Assistant, open **HACS → Integrations**.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add `https://github.com/kraroed/home-maintenance-manager` and select **Integration** as the category.
4. Find **Home Maintenance Manager** in HACS and select **Download**.
5. Restart Home Assistant, then go to **Settings → Devices & services → Add integration** and search for **Home Maintenance Manager**.

For updates, use HACS and restart Home Assistant when prompted. Back up your Home Assistant configuration before installing updates.

## Recommendations and safety

Built-in intervals are starting suggestions, not professional or manufacturer instructions. Always follow the documentation for the specific appliance, system, material, or safety device, along with applicable local requirements. Smoke and carbon-monoxide alarm testing and replacement must follow the device manufacturer's instructions and local code.

## Development

The integration lives in `custom_components/home_maintenance_manager/`. CI workflows run HACS and Home Assistant validation on pushes and pull requests.


## Maintenance insights and reporting

The integration exposes additional summary sensors for maintenance activity:

- Completion totals and late-completion counts over the previous 30, 90, and 365 days.
- Completion breakdowns by maintenance category, including on-time and late totals.
- Upcoming workload counts for the next 7, 30, and 90 days. Overdue and due-today tasks are reported separately.
- An overdue-backlog trend based on one local-calendar-day snapshot.

Backlog snapshots are recorded after startup and shortly after local midnight, with at most one snapshot per day. The integration retains the most recent 365 daily snapshots in its storage and includes them in JSON backups. Existing completion history remains the source for late-completion trends; no duplicate completion archive is created. The first snapshot establishes a baseline, so historical backlog values are not fabricated.
