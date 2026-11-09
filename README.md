# Home Maintenance Manager

A Home Assistant custom integration for planning, tracking, and recording recurring home maintenance.

> **Development status: early development.** This repository is being built incrementally. It is not yet ready for installation or production use.

## Current capabilities

- A built-in library of suggested maintenance tasks, enabled individually.
- An expanded starter library covering HVAC, plumbing, appliances, electrical safety, fire safety, interior, exterior, and seasonal upkeep.
- User-created recurring maintenance tasks with configurable categories, descriptions, and intervals.
- Custom task editing, including changing the recurring interval while retaining the task's identity and completion history.
- Custom task removal from active tracking, with completion history preserved.
- Editable intervals for recurring built-in tasks.
- Completion-based scheduling: completing a task restarts its schedule.
- Permanent completion history, including optional notes, photo/receipt references, and per-completion labor/parts costs (USD).
- Seasonal schedules with configurable date windows.
- Household equipment records with name, category, manufacturer, model, installation date, and notes.
- Associate one or more enabled maintenance tasks with registered equipment.
- Equipment sensors expose equipment details and associated task IDs.
- Home Assistant entities for task status and household maintenance summaries.
- Individual due-soon and overdue reminders, plus a configurable daily summary.
- Configurable reminder lead time and notification destination, with persistent notifications as the fallback.

## Custom maintenance task management

Open the integration's **Configure** options and choose **Manage custom maintenance tasks**. Select a custom task to edit its name, category, description, or repeat interval, or remove it from active tracking. Editing keeps the task ID stable so its existing schedule and completion history remain associated with it. Removing a task disables it, removes it from the custom task library and enabled-task list, and clears equipment associations; existing task and completion records are retained.

## Equipment tracking

Open the integration's **Configure** options, then choose **Add household equipment**. Enter an equipment name and category; manufacturer, model, installation date, and notes are optional. Select any enabled maintenance tasks that apply to that equipment. One task can be associated with multiple equipment records.

Each registered item creates an equipment sensor. Its attributes include the equipment metadata and associated task IDs. A summary sensor reports the number of registered equipment records.

Equipment can be added, edited, and removed through the integration options flow. To manage an existing record, open **Configure → Manage household equipment**, select the item, then choose whether to edit its details and task associations or remove it. Removing an equipment record does not delete maintenance tasks or completion history; historical records retain the equipment IDs captured when the task was completed.

## Maintenance notifications

Open **Configure → Configure maintenance notifications** to enable individual task reminders and/or a daily summary. Set how many days ahead to remind, choose the summary time in 24-hour `HH:MM` format, and optionally enter a Home Assistant notify entity ID (for example, `notify.mobile_app_your_phone`). If no target is configured, the integration creates Home Assistant persistent notifications instead. Reminder delivery is tracked in integration storage so a task is not repeatedly announced for the same due date, and the daily summary is sent once per day.

## Maintenance history export

Call **`home_maintenance_manager.export_history`** from Developer Tools → Actions, or use it in an automation. Choose `csv`, `json`, or `both` (the default). The integration writes the files under `/config/www/home_maintenance_manager/<entry_id>/` and creates a persistent notification with links to open each export through Home Assistant. CSV includes one row per completion; JSON includes the full completion records and property name. Export files are overwritten by the next export in the same format.

## Lovelace dashboard card

The repository includes a companion card at `www/home-maintenance-manager-card.js`. The card discovers this integration's task, summary, equipment, and completion-button entities by their attributes, so you do not need to enter individual entity IDs.

### Install the card

1. Copy `www/home-maintenance-manager-card.js` from this repository into your Home Assistant `/config/www/` folder.
2. In Settings → Dashboards → Resources, add `/local/home-maintenance-manager-card.js` as a JavaScript module. If Resources is not visible, enable Advanced Mode in your user profile.
3. Add a Manual card to a dashboard and use:

```yaml
type: custom:home-maintenance-manager-card
title: Home Maintenance
show_equipment: true
show_history: true
```

The card shows active-task totals, overdue and due-today counts, upcoming work, equipment records, and completion-history count. Use the status filters and dynamically generated category filters to narrow the task list. Expand **Details** on any task to see its last completion, next due date, repeat interval or seasonal schedule, linked equipment, and up to five recent completion records with notes. Equipment records show their associated enabled maintenance tasks; selecting one filters the task list to that task, with a clear control to return to the full list. The **Mark complete** action asks for optional completion notes and photo/receipt references, then calls the integration's `complete_task` service. Attachments are stored as links in the permanent completion record, displayed in task detail history, and included in CSV/JSON exports. The completion prompt also records optional labor/service cost and parts/materials cost in USD. Each history record stores both amounts and the total, which appear with that individual completion in task history and CSV/JSON exports. Existing historical records without cost fields are treated as $0. For local files, first upload the photo or receipt into `/config/www/` using your preferred Home Assistant file-management method, then enter its `/local/` path (for example, `/local/maintenance/boiler-service.jpg`). You can also supply HTTP(S) links. Enter one attachment per line. The integration stores references only; it does not upload files itself. You can call `home_maintenance_manager.complete_task` from Developer Tools → Actions or an automation with `task_id`, optional `notes`, optional newline-separated `attachments`, and (when multiple entries contain the same task ID) `integration_instance`. Entity discovery is scoped to this integration and pairs each task with its completion button by configuration entry, so multiple Home Maintenance Manager entries can be shown together without cross-linking their tasks. Summary counts are aggregated across those entries.

After updating the JavaScript file, refresh the browser or clear its frontend cache if the old card remains loaded. The card is a separate manual frontend resource; installing the HACS integration does not automatically copy the JavaScript file into `/config/www/`.

## Installation

Installation instructions will be added after the integration passes Home Assistant and HACS validation and has a tested release.

## Recommendations and safety

Built-in intervals are starting suggestions, not professional or manufacturer instructions. Always follow the documentation for the specific appliance, system, material, or safety device, along with applicable local requirements. Smoke and carbon-monoxide alarm testing and replacement must follow the device manufacturer's instructions and local code.

## Development

The integration lives in `custom_components/home_maintenance_manager/`. CI workflows run HACS and Home Assistant validation on pushes and pull requests.
