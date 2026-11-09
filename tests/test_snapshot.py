"""Regression tests for maintenance coordinator snapshots."""

from datetime import datetime, time, timedelta

import pytest

from homeassistant.util import dt as dt_util

from custom_components.home_maintenance_manager.task_manager import TaskManager


def _task(task_id):
    return {
        "task_id": task_id,
        "name": task_id.replace("_", " ").title(),
        "category": "Testing",
        "description": "A task used by automated tests.",
        "schedule_type": "interval",
        "recommended_interval_days": 30,
    }


@pytest.mark.asyncio
async def test_snapshot_reports_task_status_counts_and_equipment(hass):
    """Summary counts include enabled tasks only and equipment is represented."""
    task_ids = ["overdue_task", "today_task", "soon_task", "later_task", "disabled_task"]
    equipment = [
        {
            "equipment_id": "hvac-main",
            "name": "Main HVAC",
            "category": "HVAC",
            "task_ids": ["soon_task"],
        }
    ]
    manager = TaskManager(
        hass,
        "snapshot-summary-test",
        task_ids,
        custom_tasks=[_task(task_id) for task_id in task_ids],
        equipment_records=equipment,
    )
    await manager.async_load()

    local_now = dt_util.now()
    due_dates = {
        "overdue_task": local_now.date() - timedelta(days=1),
        "today_task": local_now.date(),
        "soon_task": local_now.date() + timedelta(days=3),
        "later_task": local_now.date() + timedelta(days=30),
        "disabled_task": local_now.date(),
    }
    for task_id, due_day in due_dates.items():
        local_due = datetime.combine(due_day, time.min, tzinfo=local_now.tzinfo)
        manager.data["tasks"][task_id]["next_due"] = local_due.isoformat()
    manager.data["tasks"]["disabled_task"]["enabled"] = False

    snapshot = manager.snapshot()

    assert snapshot["total"] == 4
    assert snapshot["overdue"] == 1
    assert snapshot["due_today"] == 1
    assert snapshot["due_soon"] == 1
    assert snapshot["equipment_count"] == 1
    assert snapshot["equipment"][0]["equipment_id"] == "hvac-main"


@pytest.mark.asyncio
async def test_snapshot_limits_per_task_history_but_keeps_full_count(hass):
    """Dashboard history is capped while the summary retains the archive count."""
    manager = TaskManager(
        hass,
        "snapshot-history-test",
        ["clean_gutters"],
    )
    await manager.async_load()
    manager.data["history"] = [
        {
            "history_id": f"clean_gutters:{index}",
            "task_id": "clean_gutters",
            "notes": f"Completion {index}",
        }
        for index in range(12)
    ]

    snapshot = manager.snapshot()

    records = snapshot["history_by_task"]["clean_gutters"]
    assert len(records) == 10
    assert records[0]["notes"] == "Completion 2"
    assert records[-1]["notes"] == "Completion 11"
    assert snapshot["history_count"] == 12
