import calendar
import json
from copy import deepcopy
from datetime import date, datetime, time, timedelta
from pathlib import Path

from homeassistant.util import dt as dt_util

from .storage import MaintenanceStorage


def load_library():
    path = Path(__file__).with_name("task_library.json")
    with path.open(encoding="utf-8") as handle:
        items = json.load(handle)
    return {item["task_id"]: item for item in items}


def _add_months(day, months):
    """Add calendar months while clamping to the target month's last day."""
    month_index = day.year * 12 + day.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _season_contains(day, start, end):
    month_day = (day.month, day.day)
    start_month_day = tuple(int(part) for part in start.split("-"))
    end_month_day = tuple(int(part) for part in end.split("-"))
    if start_month_day <= end_month_day:
        return start_month_day <= month_day <= end_month_day
    return month_day >= start_month_day or month_day <= end_month_day


def _next_annual_due(task, reference, include_active=False):
    """Return the next occurrence of an annual month/day schedule.

    February 29 is observed only in leap years; invalid occurrences are skipped.
    """
    try:
        month = int(task.get("annual_month"))
        day = int(task.get("annual_day"))
        date(2000, month, day)
    except (TypeError, ValueError):
        return None

    local_now = dt_util.as_local(reference)
    local_day = local_now.date()
    for year in range(local_day.year, local_day.year + 9):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate < local_day or (candidate == local_day and not include_active):
            continue
        if candidate == local_day and include_active:
            return reference.isoformat()
        local_due = datetime.combine(candidate, time.min, tzinfo=local_now.tzinfo)
        return dt_util.as_utc(local_due).isoformat()
    return None


def _next_monthly_due(task, reference, include_active=False):
    """Return the next occurrence of an ordinal weekday in a month."""
    week = task.get("monthly_week")
    try:
        weekday = int(task.get("monthly_weekday"))
    except (TypeError, ValueError):
        return None
    ordinals = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    if week not in {*ordinals, "last"} or not 0 <= weekday <= 6:
        return None

    local_now = dt_util.as_local(reference)
    local_day = local_now.date()
    for offset in range(0, 25):
        month_index = local_day.year * 12 + local_day.month - 1 + offset
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        first_weekday, days_in_month = calendar.monthrange(year, month)
        if week == "last":
            day = days_in_month - (
                calendar.weekday(year, month, days_in_month) - weekday
            ) % 7
        else:
            day = 1 + (weekday - first_weekday) % 7 + 7 * (ordinals[week] - 1)
        if day > days_in_month:
            continue
        candidate = date(year, month, day)
        if candidate < local_day or (candidate == local_day and not include_active):
            continue
        if candidate == local_day and include_active:
            return reference.isoformat()
        local_due = datetime.combine(candidate, time.min, tzinfo=local_now.tzinfo)
        return dt_util.as_utc(local_due).isoformat()
    return None


def _next_season_due(task, reference, include_active=False, settings=None):
    settings = settings or {}
    windows = settings.get("season_windows", {})
    season_keys = task.get("season_keys", [])
    local_now = dt_util.as_local(reference)
    local_day = local_now.date()

    if include_active:
        for season in season_keys:
            window = windows.get(season)
            if window and _season_contains(local_day, window["start"], window["end"]):
                return reference.isoformat()

    candidates = []
    for year in range(local_day.year - 1, local_day.year + 6):
        for season in season_keys:
            window = windows.get(season)
            if not window:
                continue
            month, day = (int(part) for part in window["start"].split("-"))
            try:
                start_day = local_day.replace(year=year, month=month, day=day)
            except ValueError:
                continue
            if start_day > local_day:
                candidates.append(start_day)

    if not candidates:
        return None

    due_day = min(candidates)
    local_due = datetime.combine(due_day, time.min, tzinfo=local_now.tzinfo)
    return dt_util.as_utc(local_due).isoformat()


class TaskManager:
    def __init__(
        self, hass, entry_id, enabled_ids, task_intervals=None,
        custom_tasks=None, equipment_records=None, season_windows=None
    ):
        self.hass = hass
        self.entry_id = entry_id
        self.storage = MaintenanceStorage(hass, entry_id)
        self.library = load_library()
        self.library.update({item["task_id"]: deepcopy(item) for item in (custom_tasks or [])})
        self.equipment_records = equipment_records or []
        self.data = None
        self.enabled_ids = set(enabled_ids)
        self.task_intervals = task_intervals or {}
        self.season_windows = season_windows or {}

    def _initial_due(self, task, now):
        if task.get("schedule_type") == "seasonal":
            return _next_season_due(
                task, now, include_active=True, settings=self.data["settings"]
            )
        if task.get("schedule_type") == "annual":
            return _next_annual_due(task, now, include_active=True)
        if task.get("schedule_type") == "monthly":
            return _next_monthly_due(task, now, include_active=True)
        interval = int(task.get("configured_interval_days") or 0)
        return (now + timedelta(days=interval)).isoformat() if interval else None

    async def async_load(self):
        self.data = await self.storage.async_load()
        for season, window in self.season_windows.items():
            if season in self.data["settings"]["season_windows"]:
                self.data["settings"]["season_windows"][season] = deepcopy(window)
        now = dt_util.utcnow()

        # The config entry options are the source of truth for equipment
        # records, so edits and removals are reflected after a reload.
        self.data["equipment"] = {}
        for record in self.equipment_records:
            equipment_id = record["equipment_id"]
            self.data["equipment"][equipment_id] = deepcopy(record)

        for task_id, task in self.data["tasks"].items():
            task["enabled"] = task_id in self.enabled_ids

        for task_id in self.enabled_ids:
            definition = self.library.get(task_id)
            if definition is None:
                continue
            if task_id not in self.data["tasks"]:
                interval = int(self.task_intervals.get(task_id, definition.get("recommended_interval_days")) or 0)
                task = {
                    **deepcopy(definition),
                    "configured_interval_days": interval,
                    "enabled": True,
                    "last_completed": None,
                    "next_due": None,
                    "schedule_next_due": None,
                    "equipment_id": None,
                    "equipment_ids": [],
                    "notes": "",
                    "created_at": now.isoformat(),
                }
                task["schedule_next_due"] = self._initial_due(task, now)
                task["next_due"] = task["schedule_next_due"]
                self.data["tasks"][task_id] = task
            else:
                task = self.data["tasks"][task_id]
                task["enabled"] = True
                previous_schedule = (
                    task.get("schedule_type"),
                    task.get("annual_month"),
                    task.get("annual_day"),
                    task.get("monthly_week"),
                    task.get("monthly_weekday"),
                )
                for key, value in definition.items():
                    if task.get("is_custom") and key in {
                        "name", "category", "description",
                        "schedule_type", "annual_month", "annual_day",
                        "monthly_week", "monthly_weekday",
                        "recommended_interval_days", "recommendation_note",
                        "how_to_inspect", "what_to_look_for",
                        "what_to_do_if_issue", "safety_notes",
                    }:
                        task[key] = deepcopy(value)
                    else:
                        task.setdefault(key, deepcopy(value))

                if task.get("schedule_type") != "annual":
                    task.pop("annual_month", None)
                    task.pop("annual_day", None)
                if task.get("schedule_type") != "monthly":
                    task.pop("monthly_week", None)
                    task.pop("monthly_weekday", None)
                current_schedule = (
                    task.get("schedule_type"),
                    task.get("annual_month"),
                    task.get("annual_day"),
                    task.get("monthly_week"),
                    task.get("monthly_weekday"),
                )
                schedule_changed = previous_schedule != current_schedule
                configured_interval = self.task_intervals.get(task_id)
                interval_changed = False
                if configured_interval is not None and task.get("schedule_type") == "interval":
                    configured_interval = int(configured_interval)
                    if configured_interval != int(task.get("configured_interval_days") or 0):
                        task["configured_interval_days"] = configured_interval
                        interval_changed = True

                if "schedule_next_due" not in task:
                    task["schedule_next_due"] = task.get("next_due")
                if schedule_changed:
                    task["schedule_next_due"] = self._initial_due(task, now)
                    task["next_due"] = task["schedule_next_due"]
                elif interval_changed:
                    anchor = task.get("last_completed") or task.get("created_at")
                    anchor_dt = dt_util.parse_datetime(anchor) if anchor else now
                    if anchor_dt is None:
                        anchor_dt = now
                    task["schedule_next_due"] = (
                        anchor_dt + timedelta(days=configured_interval)
                    ).isoformat()
                    task["next_due"] = task["schedule_next_due"]

                if (
                    task.get("schedule_type") == "seasonal"
                    and not task.get("last_completed")
                    and not task.get("next_due")
                ):
                    task["schedule_next_due"] = self._initial_due(task, now)
                    task["next_due"] = task["schedule_next_due"]

        # Apply equipment links from the configuration options to task records.
        links = {}
        for equipment in self.data["equipment"].values():
            for task_id in equipment.get("task_ids", []):
                links.setdefault(task_id, []).append(equipment["equipment_id"])
        for task_id, task in self.data["tasks"].items():
            task["equipment_ids"] = links.get(task_id, [])
            task["equipment_id"] = task["equipment_ids"][0] if task["equipment_ids"] else None

        self._refresh_equipment_lifespan_due()
        await self.async_save()

    def _refresh_equipment_lifespan_due(self):
        """Combine normal task schedules with designated equipment replacement dates."""
        replacement_dates = {}
        for equipment in self.data["equipment"].values():
            task_id = equipment.get("replacement_task_id")
            installed = equipment.get("installed_date")
            months = int(equipment.get("lifespan_months") or 0)
            if not task_id or not installed or months <= 0:
                equipment.pop("replacement_due", None)
                continue
            try:
                installed_day = date.fromisoformat(installed)
                due_day = _add_months(installed_day, months)
            except (TypeError, ValueError):
                equipment.pop("replacement_due", None)
                continue
            due_value = due_day.isoformat()
            equipment["replacement_due"] = due_value
            replacement_dates.setdefault(task_id, []).append(due_value)

        for task_id, task in self.data["tasks"].items():
            lifecycle_dates = replacement_dates.get(task_id, [])
            if lifecycle_dates:
                task["next_due"] = f"{min(lifecycle_dates)}T00:00:00"
            else:
                task["next_due"] = task.get("schedule_next_due")

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
        if not task.get("enabled", True):
            raise ValueError(f"Maintenance task is disabled: {task_id}")

        now = dt_util.utcnow()
        previous_due = task.get("next_due")
        if task.get("schedule_type") == "seasonal":
            next_due_value = _next_season_due(task, now, settings=self.data["settings"])
        elif task.get("schedule_type") == "annual":
            next_due_value = _next_annual_due(task, now)
        elif task.get("schedule_type") == "monthly":
            next_due_value = _next_monthly_due(task, now)
        else:
            interval = int(task.get("configured_interval_days") or 0)
            next_due_value = (now + timedelta(days=interval)).isoformat() if interval > 0 else None

        task["schedule_next_due"] = next_due_value
        replaced_equipment = [
            equipment for equipment in self.data["equipment"].values()
            if equipment.get("replacement_task_id") == task_id
        ]
        if replaced_equipment:
            replacement_day = dt_util.as_local(now).date().isoformat()
            for equipment in replaced_equipment:
                equipment["installed_date"] = replacement_day
            entry = self.hass.config_entries.async_get_entry(self.entry_id)
            if entry is not None:
                updated_records = [
                    deepcopy(item) for item in self.data["equipment"].values()
                ]
                self.hass.config_entries.async_update_entry(
                    entry,
                    options={**entry.options, "equipment_records": updated_records},
                )
                self.equipment_records = updated_records

        self._refresh_equipment_lifespan_due()
        next_due_value = task.get("next_due")
        self.data["history"].append({
            "history_id": f"{task_id}:{now.isoformat()}",
            "task_id": task_id,
            "task_name": task["name"],
            "completed_at": now.isoformat(),
            "previous_due": previous_due,
            "next_due": next_due_value,
            "notes": notes,
            "equipment_ids": task.get("equipment_ids", []),
        })
        task["last_completed"] = now.isoformat()
        task["next_due"] = next_due_value
        if notes:
            task["notes"] = notes
        await self.async_save()

    async def async_reschedule_task(self, task_id, due_date, reason=""):
        """Move a task's next due date without recording a completion."""
        task = self.data["tasks"].get(task_id)
        if task is None:
            raise ValueError(f"Unknown maintenance task: {task_id}")
        if not task.get("enabled", True):
            raise ValueError(f"Maintenance task is disabled: {task_id}")
        if any(
            item.get("replacement_task_id") == task_id
            for item in self.data.get("equipment", {}).values()
        ):
            raise ValueError(
                "This task's due date is managed by its equipment lifespan."
            )
        try:
            selected_day = date.fromisoformat(due_date)
            if selected_day.isoformat() != due_date:
                raise ValueError("Due date must use YYYY-MM-DD format.")
        except (TypeError, ValueError) as err:
            raise ValueError("Due date must use YYYY-MM-DD format.") from err
        local_now = dt_util.now()
        if selected_day < local_now.date():
            raise ValueError("The new due date cannot be in the past.")
        previous_due = task.get("next_due")
        local_due = datetime.combine(selected_day, time.min, tzinfo=local_now.tzinfo)
        next_due = dt_util.as_utc(local_due).isoformat()
        now = dt_util.utcnow()
        task.setdefault("schedule_history", []).append({
            "adjusted_at": now.isoformat(),
            "previous_due": previous_due,
            "next_due": next_due,
            "reason": reason.strip(),
        })
        task["schedule_next_due"] = next_due
        task["next_due"] = next_due
        await self.async_save()

    def snapshot(self):
        tasks = []
        for stored_task in self.data.get("tasks", {}).values():
            task = deepcopy(stored_task)
            task["status"] = self.task_status(stored_task)
            tasks.append(task)
        enabled_tasks = [task for task in tasks if task.get("enabled", True)]
        history_by_task = {}
        for record in self.data.get("history", []):
            history_by_task.setdefault(record.get("task_id"), []).append({
                key: deepcopy(value)
                for key, value in record.items()
                if key not in {"attachments", "labor_cost", "parts_cost", "total_cost", "currency"}
            })
        return {
            "tasks": tasks,
            "history_by_task": {
                task_id: records[-10:]
                for task_id, records in history_by_task.items()
            },
            "equipment": list(self.data.get("equipment", {}).values()),
            "equipment_count": len(self.data.get("equipment", {})),
            "total": len(enabled_tasks),
            "overdue": sum(t["status"] == "overdue" for t in enabled_tasks),
            "due_today": sum(t["status"] == "due_today" for t in enabled_tasks),
            "due_soon": sum(t["status"] == "due_soon" for t in enabled_tasks),
            "history_count": len(self.data.get("history", [])),
        }
