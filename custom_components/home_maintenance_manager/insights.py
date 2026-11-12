"""Pure reporting calculations for Home Maintenance Manager."""

from datetime import date, datetime, timedelta

from homeassistant.util import dt as dt_util


def _local_date(value):
    """Convert a stored datetime/date into the Home Assistant local date."""
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = dt_util.parse_datetime(value) if isinstance(value, str) else value
    return dt_util.as_local(parsed).date() if parsed else None


def completion_metrics(history, tasks=None, today=None):
    """Summarize completion activity and late completions over rolling windows."""
    today = today or dt_util.now().date()
    windows = {"30_days": 30, "90_days": 90, "365_days": 365}
    result = {}
    for name, days in windows.items():
        start = today - timedelta(days=days - 1)
        records = [
            item for item in history
            if (completed := _local_date(item.get("completed_at"))) is not None
            and start <= completed <= today
        ]
        late = [
            item for item in records
            if (due := _local_date(item.get("previous_due"))) is not None
            and (completed := _local_date(item.get("completed_at"))) is not None
            and completed > due
        ]
        result[name] = {
            "completed": len(records),
            "completed_late": len(late),
            "completed_on_time": len(records) - len(late),
            "late_rate": round(len(late) / len(records) * 100, 1) if records else 0,
        }
    task_categories = {
        task.get("task_id"): task.get("category", "Other")
        for task in (tasks or [])
    }
    by_category = {}
    for record in history:
        # New records retain their category at completion time. Older records
        # without this field fall back to the task's current category.
        category = record.get("category") or task_categories.get(record.get("task_id"), "Other")
        bucket = by_category.setdefault(category, {"completed": 0, "completed_late": 0})
        bucket["completed"] += 1
        due = _local_date(record.get("previous_due"))
        completed = _local_date(record.get("completed_at"))
        if due is not None and completed is not None and completed > due:
            bucket["completed_late"] += 1
    for bucket in by_category.values():
        bucket["completed_on_time"] = bucket["completed"] - bucket["completed_late"]
    return {"windows": result, "by_category": by_category}


def workload_metrics(tasks, today=None):
    """Count enabled scheduled tasks due in the next 7, 30, and 90 days."""
    today = today or dt_util.now().date()
    enabled = [task for task in tasks if task.get("enabled", True)]
    counts = {"overdue": 0, "due_today": 0, "next_7_days": 0,
              "next_30_days": 0, "next_90_days": 0, "unscheduled": 0}
    for task in enabled:
        due = _local_date(task.get("next_due"))
        if due is None:
            counts["unscheduled"] += 1
        elif due < today:
            counts["overdue"] += 1
        elif due == today:
            counts["due_today"] += 1
        else:
            days = (due - today).days
            for window in (7, 30, 90):
                if days <= window:
                    counts[f"next_{window}_days"] += 1
    return counts


def backlog_snapshot(tasks, today=None):
    """Return a compact daily status snapshot for enabled tasks."""
    today = today or dt_util.now().date()
    counts = {"date": today.isoformat(), "overdue": 0, "due_today": 0,
              "due_soon": 0, "scheduled": 0, "not_scheduled": 0, "total": 0}
    for task in tasks:
        if not task.get("enabled", True):
            continue
        counts["total"] += 1
        due = _local_date(task.get("next_due"))
        if due is None:
            key = "not_scheduled"
        elif due < today:
            key = "overdue"
        elif due == today:
            key = "due_today"
        elif due <= today + timedelta(days=7):
            key = "due_soon"
        else:
            key = "scheduled"
        counts[key] += 1
    return counts
