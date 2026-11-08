import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from homeassistant.util import dt as dt_util

from .storage import MaintenanceStorage


def load_library():
    path = Path(__file__).with_name("task_library.json")
    with path.open(encoding="utf-8") as handle:
        items = json.load(handle)
    return {item["task_id"]: item for item in items}


class TaskManager:
    def __init__(self, hass, entry_id, enabled_ids):
        self.storage = MaintenanceStorage(hass, entry_id)
        self.library = load_library()
        self.data = None
        self.enabled_ids = set(enabled_ids)

    async def async_load(self):
        self.data = await self.storage.async_load()
        now = dt_util.utcnow()
        for task_id in self.enabled_ids:
            definition = self.library.get(task_id)
            if definition and task_id not in self.data["tasks"]:
                interval = int(definition.get("recommended_interval_days") or 0)
                next_due = now + timedelta(days=interval) if interval else None
                self.data["tasks"][task_id] = {
                    **deepcopy(definition),
                    "configured_interval_days": interval,
                    "enabled": True,
                    "last_completed": None,
                    "next_due": next_due.isoformat() if next_due else None,
                    "equipment_id": None,
                    "notes": "",
                    "created_at": now.isoformat(),
                }
        await self.async_save()

    async def async_save(self):
        await self.storage.async_save(self.data)

    def task_status(self, task):
        if not task.get("enabled", True):
            return "disabled"
        due_value = task.get("next_due")
        if not due_value:
            return "not_scheduled"
        due = dt_util.parse_datetime(due_value)
        if due is None:
            return "not_scheduled"
        today = dt_util.now().date()
        due_day = dt_util.as_local(due).date()
        if due_day < today:
            return "overdue"
        if due_day == today:
            return "due_today"
        days = int(self.data["settings"].get("due_soon_days", 7))
        if due_day <= today + timedelta(days=days):
            return "due_soon"
        return "scheduled"

    async def async_complete_task(self, task_id, notes=""):
        task = self.data["tasks"].get(task_id)
        if task is None:
            raise ValueError(f"Unknown maintenance task: {task_id}")
        now = dt_util.utcnow()
        interval = int(task.get("configured_interval_days") or 0)
        next_due = now + timedelta(days=interval) if interval > 0 else None
        self.data["history"].append({
            "history_id": f"{task_id}:{now.isoformat()}",
            "task_id": task_id,
            "task_name": task["name"],
            "completed_at": now.isoformat(),
            "previous_due": task.get("next_due"),
            "next_due": next_due.isoformat() if next_due else None,
            "notes": notes,
        })
        task["last_completed"] = now.isoformat()
        task["next_due"] = next_due.isoformat() if next_due else None
        if notes:
            task["notes"] = notes
        await self.async_save()

    def snapshot(self):
        tasks = []
        for stored_task in self.data.get("tasks", {}).values():
            task = deepcopy(stored_task)
            task["status"] = self.task_status(stored_task)
            tasks.append(task)
        return {
            "tasks": tasks,
            "total": sum(bool(t.get("enabled", True)) for t in tasks),
            "overdue": sum(t["status"] == "overdue" for t in tasks),
            "due_today": sum(t["status"] == "due_today" for t in tasks),
            "due_soon": sum(t["status"] == "due_soon" for t in tasks),
            "history_count": len(self.data.get("history", [])),
        }
