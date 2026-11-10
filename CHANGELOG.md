# Changelog

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
