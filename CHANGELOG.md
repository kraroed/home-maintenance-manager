# Changelog

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
- Apply category icons consistently to equipment entities and refresh icons when equipment categories change.

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
