"""Regression tests for maintenance task scheduling and history."""
from datetime import timedelta

import pytest

from homeassistant.util import dt as dt_util

from custom_components.home_maintenance_manager.task_manager import TaskManager


@pytest.mark.asyncio
async def test_seasonal_reschedule_survives_manager_reload(hass):
    """A manual due date must not be replaced during seasonal initialization."""
    entry_id = "seasonal-reschedule-test"
    manager = TaskManager(hass, entry_id, ["clean_gutters"])
    await manager.async_load()

    selected_day = dt_util.now().date() + timedelta(days=45)
    selected_date = selected_day.isoformat()
    await manager.async_reschedule_task("clean_gutters", selected_date, "Avoid bad weather")

    reloaded_manager = TaskManager(hass, entry_id, ["clean_gutters"])
    await reloaded_manager.async_load()

    task = reloaded_manager.data["tasks"]["clean_gutters"]
    assert dt_util.as_local(dt_util.parse_datetime(task["next_due"])).date() == selected_day
    assert task["schedule_history"][-1]["reason"] == "Avoid bad weather"


@pytest.mark.asyncio
async def test_completion_resets_interval_and_preserves_history(hass):
    """Completing an interval task records the event and schedules its next cycle."""
    task_definition = {
        "task_id": "test_interval_task",
        "name": "Test interval task",
        "category": "Testing",
        "description": "A task used by automated tests.",
        "schedule_type": "interval",
        "recommended_interval_days": 30,
    }
    manager = TaskManager(
        hass,
        "interval-completion-test",
        ["test_interval_task"],
        custom_tasks=[task_definition],
    )
    await manager.async_load()

    await manager.async_complete_task(
        "test_interval_task",
        notes="Completed in regression test",
        labor_cost=12.5,
        parts_cost=7.5,
    )

    task = manager.data["tasks"]["test_interval_task"]
    record = manager.data["history"][-1]
    assert task["last_completed"] == record["completed_at"]
    assert task["next_due"] == record["next_due"]
    assert record["notes"] == "Completed in regression test"
    assert record["labor_cost"] == 12.5
    assert record["parts_cost"] == 7.5
    assert record["total_cost"] == 20.0


@pytest.mark.asyncio
async def test_reschedule_rejects_past_date_without_changing_task(hass):
    """An invalid past date must leave the task schedule untouched."""
    manager = TaskManager(hass, "past-date-test", ["clean_gutters"])
    await manager.async_load()
    task = manager.data["tasks"]["clean_gutters"]
    previous_due = task["next_due"]

    past_date = (dt_util.now().date() - timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="cannot be in the past"):
        await manager.async_reschedule_task("clean_gutters", past_date)

    assert task["next_due"] == previous_due
    assert task.get("schedule_history", []) == []


@pytest.mark.asyncio
async def test_reschedule_rejects_impossible_calendar_date(hass):
    """Date-shaped but impossible calendar values must be rejected."""
    manager = TaskManager(hass, "invalid-date-test", ["clean_gutters"])
    await manager.async_load()

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await manager.async_reschedule_task("clean_gutters", "2026-02-30")
