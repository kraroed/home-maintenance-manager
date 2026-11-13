"""Regression tests for maintenance history exports."""

import csv
import json

from custom_components.home_maintenance_manager.history_export import (
    _write_history_files,
)


def test_history_export_writes_csv_and_json_with_completion_details(tmp_path):
    """Both completion exports retain core details and omit removed fields."""
    history = [
        {
            "history_id": "replace_filter:2026-11-08T12:00:00+00:00",
            "task_id": "replace_filter",
            "task_name": "Replace HVAC filter",
            "completed_at": "2026-11-08T12:00:00+00:00",
            "previous_due": "2026-11-08T00:00:00+00:00",
            "next_due": "2027-02-06T12:00:00+00:00",
            "notes": "Installed a new filter",
            "attachments": ["/local/filter-before.jpg"],
            "labor_cost": 25.0,
            "parts_cost": 18.5,
            "total_cost": 43.5,
            "currency": "USD",
            "equipment_ids": ["hvac-main", "hvac-upstairs"],
        }
    ]

    filenames = _write_history_files(
        tmp_path, history, "Primary Residence", "both"
    )

    assert filenames == [
        "maintenance_history.csv",
        "maintenance_schedule_history.csv",
        "maintenance_history.json",
        "maintenance_schedule_history.json",
    ]

    with (tmp_path / "maintenance_history.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 1
    assert rows[0]["property_name"] == "Primary Residence"
    assert rows[0]["task_name"] == "Replace HVAC filter"
    assert rows[0]["notes"] == "Installed a new filter"
    assert json.loads(rows[0]["equipment_ids"]) == history[0]["equipment_ids"]
    assert not {"attachments", "labor_cost", "parts_cost", "total_cost", "currency"} & rows[0].keys()

    payload = json.loads(
        (tmp_path / "maintenance_history.json").read_text(encoding="utf-8")
    )
    assert payload["property_name"] == "Primary Residence"
    assert payload["history_count"] == 1
    exported_record = payload["history"][0]
    assert exported_record["notes"] == "Installed a new filter"
    assert exported_record["equipment_ids"] == history[0]["equipment_ids"]
    assert not {"attachments", "labor_cost", "parts_cost", "total_cost", "currency"} & exported_record.keys()


def test_schedule_history_export_includes_schedule_definitions_and_due_dates(tmp_path):
    """Schedule exports retain old/new definitions, dates, and audit reason."""
    schedule_history = [
        {
            "task_id": "replace_filter",
            "task_name": "Replace HVAC filter",
            "adjusted_at": "2026-11-10T12:00:00+00:00",
            "change_type": "configuration",
            "reason": "Schedule configuration changed",
            "previous_due": "2026-12-01T00:00:00+00:00",
            "next_due": "2027-01-01T00:00:00+00:00",
            "previous_schedule": {"schedule_type": "interval", "interval_days": 90},
            "new_schedule": {"schedule_type": "interval", "interval_days": 120},
        }
    ]

    filenames = _write_history_files(
        tmp_path, [], "Primary Residence", "both", schedule_history
    )

    assert "maintenance_schedule_history.csv" in filenames
    with (tmp_path / "maintenance_schedule_history.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["property_name"] == "Primary Residence"
    assert rows[0]["reason"] == "Schedule configuration changed"
    assert rows[0]["previous_due"] == "2026-12-01T00:00:00+00:00"
    assert json.loads(rows[0]["previous_schedule"]) == {
        "schedule_type": "interval", "interval_days": 90
    }
    assert json.loads(rows[0]["new_schedule"]) == {
        "schedule_type": "interval", "interval_days": 120
    }

    payload = json.loads(
        (tmp_path / "maintenance_schedule_history.json").read_text(encoding="utf-8")
    )
    assert payload["property_name"] == "Primary Residence"
    assert payload["schedule_history_count"] == 1
    assert payload["schedule_history"][0]["task_id"] == "replace_filter"
    assert payload["schedule_history"][0]["new_schedule"]["interval_days"] == 120


def test_history_export_can_write_only_json(tmp_path):
    """The format option creates only the requested CSV or JSON formats."""
    filenames = _write_history_files(tmp_path, [], "Primary Residence", "json")

    assert filenames == [
        "maintenance_history.json",
        "maintenance_schedule_history.json",
    ]
    assert (tmp_path / "maintenance_history.json").exists()
    assert (tmp_path / "maintenance_schedule_history.json").exists()
    assert not (tmp_path / "maintenance_history.csv").exists()
    assert not (tmp_path / "maintenance_schedule_history.csv").exists()
