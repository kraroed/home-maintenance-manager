# Home Maintenance Manager

A Home Assistant custom integration for planning, tracking, and recording recurring home maintenance.

> **Development status: early development.** This repository is being built incrementally. It is not yet ready for installation or production use.

## Planned capabilities

- A built-in library of suggested maintenance tasks, enabled individually.
- Custom tasks (planned) and editable intervals for recurring built-in tasks.
- Completion-based scheduling: completing a task restarts its schedule.
- Permanent completion history.
- Seasonal schedules with configurable date windows.
- Equipment records and links between equipment and maintenance tasks.
- Individual reminders and a configurable due-task summary.
- Home Assistant entities for task status and household maintenance summaries.
- CSV and JSON history exports.
- A companion Lovelace dashboard card.

## Installation

Installation instructions will be added after the integration passes Home Assistant and HACS validation and has a tested release.

## Recommendations and safety

Built-in intervals are starting suggestions, not professional or manufacturer instructions. Always follow the documentation for the specific appliance, system, material, or safety device, along with applicable local requirements. Smoke and carbon-monoxide alarm testing and replacement must follow the device manufacturer's instructions and local code.

## Development

The integration will live in `custom_components/home_maintenance_manager/`. CI workflows will run HACS and Home Assistant validation on pushes and pull requests.
