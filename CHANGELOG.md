# Changelog

## Unreleased

## 0.11.3

### Configuration
- Add clear field-level explanations across 19 configuration forms, covering notifications, custom schedules, equipment, seasonal windows, and backup settings.
- Clarify update monitoring behavior, including what an empty entity selection means and the limitations of installation tracking.
- Return to the complete options menu after creating a Home Assistant area.

### Testing
- Add regression coverage for configuration translation completeness, backup-setting guidance, and options-menu navigation.

## 0.11.2

### Fixes
- Fix update backup monitoring setup by registering a supported Home Assistant state-change event listener.
- Prevent the integration config entry from failing to load when update backup or installation tracking is enabled.

### Testing
- Add regression coverage for listener registration, update availability, duplicate prevention, installation tracking, and entity filtering.

## 0.11.0

### Improvements
- Add optional JSON backups when selected Home Assistant update entities report a new update.
- Track installation starts and notify whether a matching update-available backup was recorded.
- Keep update-triggered backups outside scheduled-backup retention cleanup.

### Testing
- Add regression coverage for update availability, duplicate prevention, installation tracking, and entity filtering.

## 0.10.0

### Improvements
- Add configurable automatic JSON backups with daily, weekly, or monthly scheduling.
- Allow backup time and automatic-backup retention to be configured per property.
- Prune only older automatic backups; preserve manual backups and pre-restore safety backups.
- Keep automatic backup scheduling tied to the config entry lifecycle.

### Testing
- Add regression coverage for backup scheduling, retention, and disabling automatic backups.

## 0.9.9

### Fixes
- Complete manual reschedule audit records with an explicit change type and previous/new recurrence definitions.
- Preserve the unchanged recurrence definition in schedule history when only the next due date is manually adjusted.
- Clarify that history export includes both completion records and schedule-change audit history.

### Testing
- Add regression coverage for manual reschedule audit details, including seasonal schedules and persistence after reload.

## 0.9.8

### Improvements
- Display selected maintenance tasks as individual bullet points grouped by category on the initial setup review page.

### Testing
- Cover single-category and multi-category setup review formatting with regression tests.

## 0.9.7

### Configuration
- Show multi-select maintenance task choices as visible checklists instead of collapsed dropdowns.
- Add a grouped review of selected maintenance tasks before completing initial setup, with a way to return to selection.
- Add Back and Continue navigation throughout equipment, seasonal scheduling, notification, and custom-task configuration wizards.
- Preserve entered values and selections when navigating backward and forward through guided configuration.

### Fixes
- Preserve notification delivery settings when changing notification choices in the guided flow.
- Remove obsolete annual or monthly schedule fields when changing a custom task's recurrence type.

### Testing
- Add regression tests for wizard navigation, draft preservation, setup review, and custom task schedule changes.

## 0.9.6

### Configuration
- Add a guided initial setup flow with categorized maintenance task selection, including Select All and Clear All.
- Split notification setup into notification choices and a focused delivery/timing step.
- Configure spring, summer, fall, and winter maintenance windows in separate steps, with calendar-date validation.
- Guide equipment registration and editing through identity, installation/lifespan details, and linked maintenance tasks.
- Guide custom maintenance task creation and editing through category, schedule, and inspection guidance steps.
- Organize recurring maintenance interval settings by task category.

### Improvements
- Run maintenance task library reads outside Home Assistant's event loop to avoid blocking calls.
- Improve custom task category creation and reuse.
- Preserve existing equipment details, task associations, custom task identity, and completion history while editing.
- Add regression coverage and translations for the guided configuration flows.

## 0.9.5

### Equipment
- Use the native Home Assistant icon selector so any available Home Assistant icon can be selected for custom equipment categories.
- Preserve saved custom category icons when adding additional equipment that uses the same category.
- Apply category-specific icons to equipment entities and refresh icons when equipment categories change.
- Add reusable custom equipment categories with user-selectable icons; saved categories can be reused across equipment.

## 0.9.4

### Equipment
- Allow equipment to be assigned to an existing Home Assistant area or create a new area from the integration options.
- Replace free-text equipment categories with a selectable list of built-in categories.
- Assign category-specific icons to equipment.
- Add reusable custom equipment categories with user-selectable icons; saved categories can be reused across equipment.

## 0.9.3

### Fixes
- Fix seasonal date configuration forms by replacing a non-serializable custom schema validator with a Home Assistant-compatible validator.
- Validate real calendar dates after form submission, including support for February 29, and show a clear error for impossible dates.
- Load the built-in task library asynchronously to avoid blocking file I/O in the Home Assistant event loop.

## 0.9.2

### Fixes
- Add the missing English translations for the configurable seasonal date-window options flow.

## 0.9.1

### Notifications
- Send mobile reminders directly through the configured Home Assistant mobile app notify service.
- Discover available mobile app notify services in the notification options and allow selecting the destination per integration instance.
- Preserve actionable reminder buttons for marking tasks complete or snoozing reminders.

### Fixes
- Correct mobile notification service delivery so notifications are sent to the selected device service without an invalid target entity.

## 0.9.0

### Notifications
- Include the exact due date in individual maintenance reminders.
- Include associated equipment names in reminders when available.
- Organize daily summaries into separate overdue and due-soon sections.
- Include due dates and equipment context in daily summaries.

### Documentation
- Updated HACS installation instructions.
- Clarified the published release status.
