"""Notification scheduling for Home Maintenance Manager."""
from datetime import timedelta

from homeassistant.components import persistent_notification
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN

NOTIFICATION_ID = f"{DOMAIN}_summary"


def _due_date(task):
    value = task.get("next_due")
    parsed = dt_util.parse_datetime(value) if value else None
    return dt_util.as_local(parsed).date() if parsed else None


async def async_setup_notifications(hass, entry, manager):
    """Set up periodic maintenance reminders and daily summaries."""
    options = entry.options
    individual_enabled = options.get("individual_notifications_enabled", True)
    summary_enabled = options.get("daily_summary_enabled", True)
    notify_target = options.get("notification_target", "").strip()
    lead_days = int(options.get("notification_lead_days", 7))
    summary_time = options.get("daily_summary_time", "08:00")

    async def send_message(title, message, notification_id=None):
        if notify_target:
            await hass.services.async_call(
                "notify",
                "send_message",
                {
                    "message": message,
                    "title": title,
                    "target": {"entity_id": notify_target},
                },
                blocking=True,
            )
        else:
            persistent_notification.async_create(
                hass, message, title, notification_id=notification_id
            )

    async def check_notifications(now=None):
        now = dt_util.now()
        today = now.date()
        state = manager.data.setdefault(
            "notification_state", {"individual": {}, "summary_date": None}
        )
        tasks = [
            task for task in manager.data.get("tasks", {}).values()
            if task.get("enabled", True) and task.get("next_due")
        ]
        if individual_enabled:
            for task in tasks:
                due_date = _due_date(task)
                if due_date is None or due_date > today + timedelta(days=lead_days):
                    continue
                due_key = f"{task['task_id']}:{task['next_due']}"
                if state.get("individual", {}).get(due_key):
                    continue
                if due_date < today:
                    timing = f"overdue by {(today - due_date).days} day(s)"
                elif due_date == today:
                    timing = "due today"
                else:
                    timing = f"due in {(due_date - today).days} day(s)"
                await send_message(
                    "Home maintenance reminder",
                    f"{task['name']} is {timing}.",
                )
                state.setdefault("individual", {})[due_key] = now.isoformat()
                await manager.async_save()

        if summary_enabled:
            try:
                hour, minute = (int(part) for part in summary_time.split(":"))
            except (ValueError, AttributeError):
                hour, minute = 8, 0
            if (now.hour, now.minute) >= (hour, minute):
                summary_date = today.isoformat()
                if state.get("summary_date") != summary_date:
                    due_tasks = []
                    for task in tasks:
                        due_date = _due_date(task)
                        if due_date is not None and due_date <= today + timedelta(days=lead_days):
                            due_tasks.append((task, due_date))
                    if due_tasks:
                        lines = []
                        for task, due_date in sorted(due_tasks, key=lambda item: item[1]):
                            if due_date < today:
                                status = f"overdue {(today - due_date).days} day(s)"
                            elif due_date == today:
                                status = "due today"
                            else:
                                status = f"due {due_date.isoformat()}"
                            lines.append(f"• {task['name']} — {status}")
                        message = "Maintenance tasks needing attention:\n" + "\n".join(lines)
                    else:
                        message = "There are no maintenance tasks due or coming due in the reminder window."
                    await send_message(
                        "Daily home maintenance summary",
                        message,
                        NOTIFICATION_ID,
                    )
                    state["summary_date"] = summary_date
                    await manager.async_save()

    await check_notifications()
    return async_track_time_interval(
        hass, check_notifications, timedelta(minutes=1)
    )
