"""Regression tests for maintenance task scheduling and history."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone

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
    )

    task = manager.data["tasks"]["test_interval_task"]
    record = manager.data["history"][-1]
    assert task["last_completed"] == record["completed_at"]
    assert task["next_due"] == record["next_due"]
    assert record["notes"] == "Completed in regression test"
    assert not {"attachments", "labor_cost", "parts_cost", "total_cost", "currency"} & record.keys()


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



@pytest.mark.asyncio
async def test_equipment_associations_are_saved_in_completion_history(hass):
    """A completion record should retain all equipment linked to its task."""
    task_definition = {
        "task_id": "test_equipment_task",
        "name": "Test equipment task",
        "category": "Testing",
        "description": "A task used by automated tests.",
        "schedule_type": "interval",
        "recommended_interval_days": 90,
    }
    equipment_records = [
        {
            "equipment_id": "hvac-main",
            "name": "Main HVAC",
            "category": "HVAC",
            "task_ids": ["test_equipment_task"],
        },
        {
            "equipment_id": "hvac-upstairs",
            "name": "Upstairs HVAC",
            "category": "HVAC",
            "task_ids": ["test_equipment_task"],
        },
    ]
    manager = TaskManager(
        hass,
        "equipment-history-test",
        ["test_equipment_task"],
        custom_tasks=[task_definition],
        equipment_records=equipment_records,
    )
    await manager.async_load()

    task = manager.data["tasks"]["test_equipment_task"]
    assert task["equipment_ids"] == ["hvac-main", "hvac-upstairs"]
    assert task["equipment_id"] == "hvac-main"

    await manager.async_complete_task("test_equipment_task")
    record = manager.data["history"][-1]
    assert record["equipment_ids"] == ["hvac-main", "hvac-upstairs"]



@pytest.mark.asyncio
async def test_custom_task_edit_updates_interval_and_preserves_history(hass):
    """Editing a custom task updates its interval without losing its history."""
    original_definition = {
        "task_id": "custom_filter_replacement",
        "name": "Replace HVAC filter",
        "category": "HVAC",
        "description": "Original description.",
        "schedule_type": "interval",
        "recommended_interval_days": 90,
        "how_to_inspect": ["Check the filter and frame."],
        "what_to_look_for": ["Dust buildup or damage."],
        "what_to_do_if_issue": "Replace a damaged filter.",
        "safety_notes": "Turn the system off first.",
        "is_custom": True,
    }
    equipment_records = [{
        "equipment_id": "hvac-upstairs",
        "name": "Upstairs HVAC",
        "category": "HVAC",
        "task_ids": ["custom_filter_replacement"],
    }]
    manager = TaskManager(
        hass,
        "custom-task-edit-test",
        ["custom_filter_replacement"],
        custom_tasks=[original_definition],
        equipment_records=equipment_records,
    )
    await manager.async_load()
    await manager.async_complete_task(
        "custom_filter_replacement",
        notes="Replaced the filter",
    )
    original_task = manager.data["tasks"]["custom_filter_replacement"]
    original_last_completed = original_task["last_completed"]
    original_next_due = original_task["next_due"]
    original_history = deepcopy(manager.data["history"][-1])
    assert original_history["task_name"] == "Replace HVAC filter"
    assert original_history["equipment_ids"] == ["hvac-upstairs"]

    edited_definition = {
        **original_definition,
        "name": "Replace upstairs HVAC filter",
        "category": "heating and cooling",
        "description": "Updated description.",
        "recommended_interval_days": 120,
        "how_to_inspect": ["Check the filter and frame.", "Confirm airflow direction."],
        "what_to_look_for": ["Dust buildup or damage."],
        "what_to_do_if_issue": "Replace a damaged filter.",
        "safety_notes": "Turn the system off first.",
    }
    reloaded_manager = TaskManager(
        hass,
        "custom-task-edit-test",
        ["custom_filter_replacement"],
        custom_tasks=[edited_definition],
        equipment_records=equipment_records,
        task_intervals={"custom_filter_replacement": 120},
    )
    await reloaded_manager.async_load()

    edited_task = reloaded_manager.data["tasks"]["custom_filter_replacement"]
    assert edited_task["name"] == "Replace upstairs HVAC filter"
    assert edited_task["category"] == "heating and cooling"
    assert edited_task["description"] == "Updated description."
    assert edited_task["how_to_inspect"] == [
        "Check the filter and frame.",
        "Confirm airflow direction.",
    ]
    assert edited_task["what_to_look_for"] == ["Dust buildup or damage."]
    assert edited_task["what_to_do_if_issue"] == "Replace a damaged filter."
    assert edited_task["safety_notes"] == "Turn the system off first."
    assert edited_task["last_completed"] == original_last_completed
    expected_next_due = (
        dt_util.parse_datetime(original_last_completed) + timedelta(days=120)
    ).isoformat()
    assert edited_task["next_due"] == expected_next_due
    assert edited_task["next_due"] != original_next_due
    assert reloaded_manager.data["history"][-1] == original_history
    assert edited_task["equipment_ids"] == ["hvac-upstairs"]

@pytest.mark.asyncio
async def test_seasonal_completion_schedules_the_next_configured_window(
    hass, monkeypatch
):
    """Completing a seasonal task schedules its next season, not a fixed interval."""
    task_definition = {
        "task_id": "test_spring_task",
        "name": "Test spring task",
        "category": "Testing",
        "description": "A seasonal task used by automated tests.",
        "schedule_type": "seasonal",
        "season_keys": ["spring"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        "seasonal-completion-test",
        ["test_spring_task"],
        custom_tasks=[task_definition],
    )
    await manager.async_load()

    fixed_now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)

    await manager.async_complete_task("test_spring_task")

    task = manager.data["tasks"]["test_spring_task"]
    record = manager.data["history"][-1]
    next_due = dt_util.as_local(dt_util.parse_datetime(task["next_due"]))

    assert task["last_completed"] == fixed_now.isoformat()
    assert next_due.date() == date(2027, 3, 15)
    assert record["next_due"] == task["next_due"]


@pytest.mark.asyncio
async def test_completion_rejects_disabled_task_without_recording_history(hass):
    """Disabled tasks cannot be completed through the task manager."""
    manager = TaskManager(hass, "disabled-completion-test", ["clean_gutters"])
    await manager.async_load()
    task = manager.data["tasks"]["clean_gutters"]
    previous_due = task["next_due"]
    task["enabled"] = False

    with pytest.raises(ValueError, match="disabled"):
        await manager.async_complete_task("clean_gutters")

    assert task["next_due"] == previous_due
    assert task.get("last_completed") is None
    assert manager.data["history"] == []


@pytest.mark.asyncio
async def test_completion_rejects_unknown_task_without_recording_history(hass):
    """Unknown task IDs do not create completion records."""
    manager = TaskManager(hass, "unknown-completion-test", [])
    await manager.async_load()

    with pytest.raises(ValueError, match="Unknown maintenance task"):
        await manager.async_complete_task("does_not_exist")

    assert manager.data["history"] == []

@pytest.mark.asyncio
async def test_reschedule_rejects_noncanonical_iso_date_format(hass):
    """Date-only values must use the documented YYYY-MM-DD representation."""
    manager = TaskManager(hass, "noncanonical-date-test", ["clean_gutters"])
    await manager.async_load()
    task = manager.data["tasks"]["clean_gutters"]
    previous_due = task["next_due"]

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        await manager.async_reschedule_task("clean_gutters", "20261109")

    assert task["next_due"] == previous_due
    assert task.get("schedule_history", []) == []



@pytest.mark.asyncio
async def test_configured_season_windows_override_storage_defaults(hass):
    """Configured season windows are applied before seasonal scheduling."""
    windows = {
        "spring": {"start": "03-10", "end": "05-25"},
    }
    manager = TaskManager(
        hass,
        "custom-season-window-test",
        ["clean_gutters"],
        season_windows=windows,
    )
    await manager.async_load()

    assert manager.data["settings"]["season_windows"]["spring"] == windows["spring"]
    assert manager.data["settings"]["season_windows"]["summer"] == {
        "start": "06-01",
        "end": "08-31",
    }

@pytest.mark.parametrize("completion_day", ["2027-01-15", "2027-03-14"])
@pytest.mark.asyncio
async def test_winter_completion_across_year_boundary_schedules_next_winter(
    hass, monkeypatch, completion_day
):
    """Completing a cross-year winter task schedules the next November window."""
    task_definition = {
        "task_id": "test_winter_task",
        "name": "Test winter task",
        "category": "Testing",
        "description": "A winter task used by automated tests.",
        "schedule_type": "seasonal",
        "season_keys": ["winter"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        f"winter-boundary-{completion_day}",
        ["test_winter_task"],
        custom_tasks=[task_definition],
        season_windows={
            "winter": {"start": "11-16", "end": "03-14"},
        },
    )
    await manager.async_load()

    fixed_now = datetime.fromisoformat(f"{completion_day}T12:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)

    await manager.async_complete_task("test_winter_task")

    task = manager.data["tasks"]["test_winter_task"]
    next_due = dt_util.as_local(dt_util.parse_datetime(task["next_due"]))
    assert next_due.date() == date(2027, 11, 16)
    assert manager.data["history"][-1]["next_due"] == task["next_due"]

@pytest.mark.parametrize(
    "active_day",
    ["2026-11-16", "2027-01-15", "2027-03-14"],
)
@pytest.mark.asyncio
async def test_new_winter_task_is_due_immediately_when_winter_is_active(
    hass, monkeypatch, active_day
):
    """Initial seasonal scheduling includes both boundaries of a cross-year season."""
    fixed_now = datetime.fromisoformat(f"{active_day}T18:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_initial_winter_task",
        "name": "Test initial winter task",
        "category": "Testing",
        "description": "A winter task used by automated tests.",
        "schedule_type": "seasonal",
        "season_keys": ["winter"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        f"initial-winter-{active_day}",
        ["test_initial_winter_task"],
        custom_tasks=[task_definition],
        season_windows={
            "winter": {"start": "11-16", "end": "03-14"},
        },
    )

    await manager.async_load()

    task = manager.data["tasks"]["test_initial_winter_task"]
    assert task["next_due"] == fixed_now.isoformat()

@pytest.mark.parametrize(
    ("reference_day", "expected_due"),
    [
        ("2027-03-11", "2028-02-29"),
        ("2028-02-29", "2028-02-29"),
    ],
)
@pytest.mark.asyncio
async def test_leap_day_seasonal_window_schedules_valid_due_date(
    hass, monkeypatch, reference_day, expected_due
):
    """Leap-day season starts are scheduled only on real calendar dates."""
    fixed_now = datetime.fromisoformat(f"{reference_day}T12:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_leap_day_task",
        "name": "Test leap-day task",
        "category": "Testing",
        "description": "A seasonal task with a leap-day start.",
        "schedule_type": "seasonal",
        "season_keys": ["spring"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        f"leap-day-season-{reference_day}",
        ["test_leap_day_task"],
        custom_tasks=[task_definition],
        season_windows={
            "spring": {"start": "02-29", "end": "03-10"},
        },
    )

    await manager.async_load()

    task = manager.data["tasks"]["test_leap_day_task"]
    due = dt_util.as_local(dt_util.parse_datetime(task["next_due"]))
    assert due.date() == date.fromisoformat(expected_due)

@pytest.mark.parametrize(
    ("reference_day", "expected_due"),
    [
        ("2026-05-31", "2026-05-31"),
        ("2026-06-01", "2027-03-15"),
    ],
)
@pytest.mark.asyncio
async def test_seasonal_window_end_date_is_inclusive(
    hass, monkeypatch, reference_day, expected_due
):
    """A season includes its final day and rolls forward immediately afterward."""
    fixed_now = datetime.fromisoformat(f"{reference_day}T12:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_spring_boundary_task",
        "name": "Test spring boundary task",
        "category": "Testing",
        "description": "A task for seasonal end-boundary coverage.",
        "schedule_type": "seasonal",
        "season_keys": ["spring"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        f"spring-end-boundary-{reference_day}",
        ["test_spring_boundary_task"],
        custom_tasks=[task_definition],
        season_windows={
            "spring": {"start": "03-15", "end": "05-31"},
        },
    )

    await manager.async_load()

    due = dt_util.as_local(
        dt_util.parse_datetime(
            manager.data["tasks"]["test_spring_boundary_task"]["next_due"]
        )
    )
    assert due.date() == date.fromisoformat(expected_due)
    if reference_day == expected_due:
        assert manager.data["tasks"]["test_spring_boundary_task"]["next_due"] == fixed_now.isoformat()

@pytest.mark.parametrize(
    ("reference_day", "expected_due"),
    [
        ("2026-07-01", "2026-09-01"),
        ("2026-11-16", "2027-03-15"),
    ],
)
@pytest.mark.asyncio
async def test_multi_season_task_uses_nearest_upcoming_window(
    hass, monkeypatch, reference_day, expected_due
):
    """Tasks assigned to multiple seasons use the nearest future season start."""
    fixed_now = datetime.fromisoformat(f"{reference_day}T12:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_multi_season_task",
        "name": "Test multi-season task",
        "category": "Testing",
        "description": "A task that can be performed in spring or fall.",
        "schedule_type": "seasonal",
        "season_keys": ["spring", "fall"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        f"multi-season-{reference_day}",
        ["test_multi_season_task"],
        custom_tasks=[task_definition],
        season_windows={
            "spring": {"start": "03-15", "end": "05-31"},
            "fall": {"start": "09-01", "end": "11-15"},
        },
    )

    await manager.async_load()

    due = dt_util.as_local(
        dt_util.parse_datetime(
            manager.data["tasks"]["test_multi_season_task"]["next_due"]
        )
    )
    assert due.date() == date.fromisoformat(expected_due)

@pytest.mark.parametrize(
    ("completion_day", "expected_due"),
    [
        ("2026-07-01", "2026-09-01"),
        ("2026-10-01", "2027-03-15"),
    ],
)
@pytest.mark.asyncio
async def test_multi_season_completion_moves_to_next_season_window(
    hass, monkeypatch, completion_day, expected_due
):
    """Completing a multi-season task schedules the next eligible window."""
    fixed_now = datetime.fromisoformat(f"{completion_day}T12:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_multi_season_completion",
        "name": "Test multi-season completion",
        "category": "Testing",
        "description": "A task that can be completed in spring or fall.",
        "schedule_type": "seasonal",
        "season_keys": ["spring", "fall"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        f"multi-season-completion-{completion_day}",
        ["test_multi_season_completion"],
        custom_tasks=[task_definition],
        season_windows={
            "spring": {"start": "03-15", "end": "05-31"},
            "fall": {"start": "09-01", "end": "11-15"},
        },
    )
    await manager.async_load()

    await manager.async_complete_task("test_multi_season_completion")

    task = manager.data["tasks"]["test_multi_season_completion"]
    due = dt_util.as_local(dt_util.parse_datetime(task["next_due"]))
    assert due.date() == date.fromisoformat(expected_due)
    assert manager.data["history"][-1]["next_due"] == task["next_due"]

@pytest.mark.asyncio
async def test_configured_season_window_controls_initial_due_date(hass, monkeypatch):
    """A custom season start is used when initially scheduling a seasonal task."""
    fixed_now = datetime.fromisoformat("2027-02-01T12:00:00+00:00")
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_custom_spring_window",
        "name": "Test custom spring window",
        "category": "Testing",
        "description": "A task using a customized spring window.",
        "schedule_type": "seasonal",
        "season_keys": ["spring"],
        "recommended_interval_days": 365,
    }
    manager = TaskManager(
        hass,
        "custom-spring-initial-due-test",
        ["test_custom_spring_window"],
        custom_tasks=[task_definition],
        season_windows={
            "spring": {"start": "04-10", "end": "06-15"},
        },
    )

    await manager.async_load()

    task = manager.data["tasks"]["test_custom_spring_window"]
    due = dt_util.as_local(dt_util.parse_datetime(task["next_due"]))
    assert due.date() == date(2027, 4, 10)

@pytest.mark.asyncio
async def test_removing_equipment_preserves_existing_completion_history(hass):
    """Removing equipment does not rewrite historical equipment references."""
    task_definition = {
        "task_id": "test_removed_equipment_task",
        "name": "Test removed equipment task",
        "category": "Testing",
        "description": "A task used to verify permanent equipment history.",
        "schedule_type": "interval",
        "recommended_interval_days": 90,
    }
    equipment_records = [{
        "equipment_id": "hvac-removed",
        "name": "Removed HVAC",
        "category": "HVAC",
        "task_ids": ["test_removed_equipment_task"],
    }]
    entry_id = "removed-equipment-history-test"
    manager = TaskManager(
        hass,
        entry_id,
        ["test_removed_equipment_task"],
        custom_tasks=[task_definition],
        equipment_records=equipment_records,
    )
    await manager.async_load()
    await manager.async_complete_task("test_removed_equipment_task")

    # Reload with the updated config-entry equipment list after removal.
    reloaded_manager = TaskManager(
        hass,
        entry_id,
        ["test_removed_equipment_task"],
        custom_tasks=[task_definition],
        equipment_records=[],
    )
    await reloaded_manager.async_load()

    assert reloaded_manager.data["equipment"] == {}
    assert reloaded_manager.data["tasks"]["test_removed_equipment_task"]["equipment_ids"] == []
    assert reloaded_manager.data["history"][-1]["equipment_ids"] == ["hvac-removed"]
    assert reloaded_manager.data["history"][-1]["task_name"] == "Test removed equipment task"



@pytest.mark.asyncio
async def test_annual_task_is_due_on_configured_month_and_day(hass, monkeypatch):
    """A new annual task is due immediately when its calendar date is today."""
    fixed_now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_annual_task",
        "name": "Test annual task",
        "category": "Testing",
        "description": "An annual task used by automated tests.",
        "schedule_type": "annual",
        "annual_month": 4,
        "annual_day": 15,
    }
    manager = TaskManager(
        hass,
        "annual-initial-due-test",
        ["test_annual_task"],
        custom_tasks=[task_definition],
    )

    await manager.async_load()

    assert manager.data["tasks"]["test_annual_task"]["next_due"] == fixed_now.isoformat()


@pytest.mark.asyncio
async def test_annual_completion_advances_to_next_year_and_preserves_history(
    hass, monkeypatch
):
    """Completing an annual task schedules its next calendar-year occurrence."""
    fixed_now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_annual_completion",
        "name": "Test annual completion",
        "category": "Testing",
        "description": "An annual task used by automated tests.",
        "schedule_type": "annual",
        "annual_month": 4,
        "annual_day": 15,
    }
    manager = TaskManager(
        hass,
        "annual-completion-test",
        ["test_annual_completion"],
        custom_tasks=[task_definition],
    )
    await manager.async_load()

    await manager.async_complete_task("test_annual_completion")

    task = manager.data["tasks"]["test_annual_completion"]
    record = manager.data["history"][-1]
    next_due = dt_util.as_local(dt_util.parse_datetime(task["next_due"]))
    assert next_due.date() == date(2027, 4, 15)
    assert record["next_due"] == task["next_due"]
    assert record["completed_at"] == fixed_now.isoformat()


@pytest.mark.asyncio
async def test_annual_february_29_skips_non_leap_years(hass, monkeypatch):
    """A February 29 annual task moves to the next real leap-day occurrence."""
    fixed_now = datetime(2027, 3, 1, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(dt_util, "utcnow", lambda: fixed_now)
    task_definition = {
        "task_id": "test_annual_leap_day",
        "name": "Test annual leap-day task",
        "category": "Testing",
        "description": "An annual leap-day task used by automated tests.",
        "schedule_type": "annual",
        "annual_month": 2,
        "annual_day": 29,
    }
    manager = TaskManager(
        hass,
        "annual-leap-day-test",
        ["test_annual_leap_day"],
        custom_tasks=[task_definition],
    )

    await manager.async_load()

    due = dt_util.as_local(
        dt_util.parse_datetime(manager.data["tasks"]["test_annual_leap_day"]["next_due"])
    )
    assert due.date() == date(2028, 2, 29)
