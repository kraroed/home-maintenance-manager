"""Tests for maintenance insights calculations."""

from datetime import date

from custom_components.home_maintenance_manager.insights import (
    backlog_snapshot,
    completion_metrics,
    workload_metrics,
)


def test_completion_metrics_reports_late_and_category_counts():
    history = [
        {"task_id": "filter", "completed_at": "2026-11-10T12:00:00+00:00",
         "previous_due": "2026-11-08T00:00:00+00:00"},
        {"task_id": "filter", "completed_at": "2026-11-11T12:00:00+00:00",
         "previous_due": "2026-11-12T00:00:00+00:00"},
    ]
    tasks = [{"task_id": "filter", "category": "HVAC"}]

    result = completion_metrics(history, tasks, date(2026, 11, 11))

    assert result["windows"]["30_days"]["completed"] == 2
    assert result["windows"]["30_days"]["completed_late"] == 1
    assert result["windows"]["30_days"]["completed_on_time"] == 1
    assert result["windows"]["30_days"]["late_rate"] == 50
    assert result["by_category"]["HVAC"]["completed_late"] == 1


def test_workload_metrics_keeps_overdue_and_due_today_separate():
    tasks = [
        {"enabled": True, "next_due": "2026-11-10T00:00:00+00:00"},
        {"enabled": True, "next_due": "2026-11-11T00:00:00+00:00"},
        {"enabled": True, "next_due": "2026-11-18T00:00:00+00:00"},
        {"enabled": True, "next_due": "2027-01-01T00:00:00+00:00"},
        {"enabled": False, "next_due": "2026-11-12T00:00:00+00:00"},
    ]

    result = workload_metrics(tasks, date(2026, 11, 11))

    assert result["overdue"] == 1
    assert result["due_today"] == 1
    assert result["next_7_days"] == 1
    assert result["next_30_days"] == 1
    assert result["next_90_days"] == 1


def test_backlog_snapshot_records_enabled_task_statuses():
    tasks = [
        {"enabled": True, "next_due": "2026-11-10T00:00:00+00:00"},
        {"enabled": True, "next_due": "2026-11-11T00:00:00+00:00"},
        {"enabled": True, "next_due": "2026-11-15T00:00:00+00:00"},
        {"enabled": True, "next_due": None},
        {"enabled": False, "next_due": "2026-11-10T00:00:00+00:00"},
    ]

    result = backlog_snapshot(tasks, date(2026, 11, 11))

    assert result == {
        "date": "2026-11-11",
        "overdue": 1,
        "due_today": 1,
        "due_soon": 1,
        "scheduled": 0,
        "not_scheduled": 1,
        "total": 4,
    }
