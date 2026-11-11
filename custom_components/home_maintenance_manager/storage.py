from datetime import date

from homeassistant.helpers.storage import Store

from .const import STORAGE_VERSION


def _valid_month_day(value):
    """Return whether a value is a valid canonical MM-DD date."""
    if not isinstance(value, str) or len(value) != 5:
        return False
    try:
        month, day = (int(part) for part in value.split("-"))
        return date(2000, month, day).strftime("%m-%d") == value
    except (TypeError, ValueError):
        return False


def _valid_iso_date(value):
    """Return whether a value is a canonical YYYY-MM-DD date."""
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def default_data():
    return {
        "tasks": {},
        "equipment": {},
        "history": [],
        "notification_state": {
            "individual": {},
            "summary_date": None,
        },
        "update_backup_state": {
            "available": {},
            "installations": {},
        },
        "settings": {
            "due_soon_days": 7,
            "daily_summary_enabled": True,
            "individual_notifications_enabled": True,
            "season_windows": {
                "spring": {"start": "03-15", "end": "05-31"},
                "summer": {"start": "06-01", "end": "08-31"},
                "fall": {"start": "09-01", "end": "11-15"},
                "winter": {"start": "11-16", "end": "03-14"},
            },
        },
    }


class MaintenanceStorage:
    def __init__(self, hass, entry_id):
        self.store = Store(
            hass, STORAGE_VERSION, f"home_maintenance_manager_{entry_id}"
        )

    async def async_load(self):
        stored = await self.store.async_load()
        data = default_data()
        if not isinstance(stored, dict):
            return data

        stored_tasks = stored.get("tasks")
        if isinstance(stored_tasks, dict):
            data["tasks"] = {
                task_id: task
                for task_id, task in stored_tasks.items()
                if isinstance(task_id, str) and isinstance(task, dict)
            }

        stored_equipment = stored.get("equipment")
        if isinstance(stored_equipment, dict):
            data["equipment"] = {
                equipment_id: equipment
                for equipment_id, equipment in stored_equipment.items()
                if isinstance(equipment_id, str) and isinstance(equipment, dict)
            }

        stored_history = stored.get("history")
        if isinstance(stored_history, list):
            data["history"] = [
                record for record in stored_history if isinstance(record, dict)
            ]

        stored_notifications = stored.get("notification_state")
        if isinstance(stored_notifications, dict):
            notifications = data["notification_state"]
            individual = stored_notifications.get("individual")
            if isinstance(individual, dict):
                notifications["individual"] = {
                    key: value
                    for key, value in individual.items()
                    if isinstance(key, str) and isinstance(value, str)
                }
            summary_date = stored_notifications.get("summary_date")
            if summary_date is None or _valid_iso_date(summary_date):
                notifications["summary_date"] = summary_date

        stored_update_state = stored.get("update_backup_state")
        if isinstance(stored_update_state, dict):
            update_state = data["update_backup_state"]
            for key in ("available", "installations"):
                records = stored_update_state.get(key)
                if isinstance(records, dict):
                    update_state[key] = {
                        entity_id: record
                        for entity_id, record in records.items()
                        if isinstance(entity_id, str) and isinstance(record, dict)
                    }

        stored_settings = stored.get("settings")
        if isinstance(stored_settings, dict):
            settings = data["settings"]
            due_soon_days = stored_settings.get("due_soon_days")
            if type(due_soon_days) is int and 0 <= due_soon_days <= 90:
                settings["due_soon_days"] = due_soon_days

            for key in (
                "daily_summary_enabled",
                "individual_notifications_enabled",
            ):
                value = stored_settings.get(key)
                if type(value) is bool:
                    settings[key] = value

            season_windows = stored_settings.get("season_windows")
            if isinstance(season_windows, dict):
                for season, defaults in settings["season_windows"].items():
                    window = season_windows.get(season)
                    if not isinstance(window, dict):
                        continue
                    start = window.get("start")
                    end = window.get("end")
                    if _valid_month_day(start):
                        defaults["start"] = start
                    if _valid_month_day(end):
                        defaults["end"] = end

        return data

    async def async_save(self, data):
        await self.store.async_save(data)
