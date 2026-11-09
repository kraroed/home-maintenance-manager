"""Notification scheduling and actionable reminders for Home Maintenance Manager."""

from datetime import timedelta

from homeassistant.components import persistent_notification
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN

NOTIFICATION_ID = f"{DOMAIN}_summary"
ACTION_PREFIX = "HMM"


def _due_date(task):
    value = task.get("next_due")
    parsed = dt_util.parse_datetime(value) if value else None
    return dt_util.as_local(parsed).date() if parsed else None


def _action_id(entry_id, task_id, action):
    return f"{ACTION_PREFIX}|{entry_id}|{task_id}|{action}"


async def async_setup_notifications(hass, entry, manager, coordinator):
    """Set up periodic reminders and handle mobile notification actions."""
    options = entry.options
    individual_enabled = options.get("individual_notifications_enabled", True)
    summary_enabled = options.get("daily_summary_enabled", True)
    notify_target = options.get("notification_target", "").strip()
    lead_days = int(options.get("notification_lead_days", 7))
    summary_time = options.get("daily_summary_time", "08:00")

    async def send_message(title, message, notification_id=None, data=None):
        if notify_target:
            service_data = {
                "message": message,
                "title": title,
                "target": {"entity_id": notify_target},
            }
            if data:
                service_data["data"] = data
            await hass.services.async_call(
                "notify", "send_message", service_data, blocking=True
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
        individual_state = state.setdefault("individual", {})
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
                marker = individual_state.get(due_key)
                if marker:
                    if marker.startswith("snoozed:"):
                        snooze_until = dt_util.parse_datetime(marker.removeprefix("snoozed:"))
                        if snooze_until and snooze_until > now:
                            continue
                        individual_state.pop(due_key, None)
                        await manager.async_save()
                    else:
                        continue
                if due_date < today:
                    timing = f"overdue by {(today - due_date).days} day(s)"
                elif due_date == today:
                    timing = "due today"
                else:
                    timing = f"due in {(due_date - today).days} day(s)"

                action_data = None
                if notify_target:
                    action_data = {
                        "actions": [
                            {
                                "action": _action_id(entry.entry_id, task["task_id"], "complete"),
                                "title": "Mark complete",
                            },
                            {
                                "action": _action_id(entry.entry_id, task["task_id"], "snooze_1d"),
                                "title": "Tomorrow",
                            },
                            {
                                "action": _action_id(entry.entry_id, task["task_id"], "snooze_7d"),
                                "title": "In 1 week",
                            },
                        ]
                    }
                await send_message(
                    "Home maintenance reminder",
                    f"{task['name']} is {timing}.",
                    data=action_data,
                )
                individual_state[due_key] = now.isoformat()
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

    async def handle_mobile_action(event):
        """Apply actions sent by a Home Assistant mobile app notification."""
        action = event.data.get("action", "")
        parts = action.split("|", 3)
        if len(parts) != 4 or parts[0] != ACTION_PREFIX or parts[1] != entry.entry_id:
            return
        _, _, task_id, command = parts
        task = manager.data.get("tasks", {}).get(task_id)
        if task is None or not task.get("enabled", True):
            return
        due_key = f"{task_id}:{task.get('next_due')}"
        if not task.get("next_due") or due_key not in manager.data.setdefault(
            "notification_state", {}
        ).setdefault("individual", {}):
            return

        if command == "complete":
            await manager.async_complete_task(task_id)
            await coordinator.async_request_refresh()
        elif command in {"snooze_1d", "snooze_7d"}:
            days = 1 if command == "snooze_1d" else 7
            until = dt_util.now() + timedelta(days=days)
            manager.data["notification_state"]["individual"][due_key] = (
                f"snoozed:{until.isoformat()}"
            )
            await manager.async_save()

    cancel_interval = async_track_time_interval(
        hass, check_notifications, timedelta(minutes=1)
    )
    cancel_actions = hass.bus.async_listen(
        "mobile_app_notification_action", handle_mobile_action
    )
    await check_notifications()

    def cancel():
        cancel_interval()
        cancel_actions()

    return cancel
