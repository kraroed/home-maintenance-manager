# Home Maintenance Manager

A Home Assistant custom integration for planning, tracking, and recording recurring home maintenance.

> **Development status: early development.** This repository is being built incrementally. It is not yet ready for installation or production use.

## Current capabilities

- A built-in library of suggested maintenance tasks, enabled individually.
- User-created recurring maintenance tasks with configurable categories, descriptions, and intervals.
- Custom task editing, including changing the recurring interval while retaining the task's identity and completion history.
- Custom task removal from active tracking, with completion history preserved.
- Editable intervals for recurring built-in tasks.
- Completion-based scheduling: completing a task restarts its schedule.
- Permanent completion history.
- Seasonal schedules with configurable date windows.
- Household equipment records with name, category, manufacturer, model, installation date, and notes.
- Associate one or more enabled maintenance tasks with registered equipment.
- Equipment sensors expose equipment details and associated task IDs.
- Home Assistant entities for task status and household maintenance summaries.\n- Individual due-soon and overdue reminders, plus a configurable daily summary.\n- Configurable reminder lead time and notification destination, with persistent notifications as the fallback.

## Custom maintenance task management

Open the integration's **Configure** options and choose **Manage custom maintenance tasks**. Select a custom task to edit its name, category, description, or repeat interval, or remove it from active tracking. Editing keeps the task ID stable so its existing schedule and completion history remain associated with it. Removing a task disables it, removes it from the custom task library and enabled-task list, and clears equipment associations; existing task and completion records are retained.

## Equipment tracking

Open the integration's **Configure** options, then choose **Add household equipment**. Enter an equipment name and category; manufacturer, model, installation date, and notes are optional. Select any enabled maintenance tasks that apply to that equipment. One task can be associated with multiple equipment records.

Each registered item creates an equipment sensor. Its attributes include the equipment metadata and associated task IDs. A summary sensor reports the number of registered equipment records.

Equipment can be added, edited, and removed through the integration options flow. To manage an existing record, open **Configure → Manage household equipment**, select the item, then choose whether to edit its details and task associations or remove it. Removing an equipment record does not delete maintenance tasks or completion history; historical records retain the equipment IDs captured when the task was completed.

## Planned capabilities

- Individual reminders and a configurable due-task summary.
- CSV and JSON history exports.
- A companion Lovelace dashboard card.

## Installation

Installation instructions will be added after the integration passes Home Assistant and HACS validation and has a tested release.

## Recommendations and safety

Built-in intervals are starting suggestions, not professional or manufacturer instructions. Always follow the documentation for the specific appliance, system, material, or safety device, along with applicable local requirements. Smoke and carbon-monoxide alarm testing and replacement must follow the device manufacturer's instructions and local code.

## Development

The integration lives in `custom_components/home_maintenance_manager/`. CI workflows run HACS and Home Assistant validation on pushes and pull requests.
