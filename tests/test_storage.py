"""Regression tests for maintenance storage defaults and compatibility."""

import pytest

from custom_components.home_maintenance_manager.storage import MaintenanceStorage


class FakeStore:
    stored = None
    saved = {}

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return self.saved.get(self.key, type(self).stored)

    async def async_save(self, data):
        self.saved[self.key] = data


@pytest.mark.asyncio
async def test_storage_merges_new_defaults_into_existing_settings(hass, monkeypatch):
    """Older saved settings retain defaults added by newer integration versions."""
    FakeStore.stored = {
        "tasks": {"clean_gutters": {"task_id": "clean_gutters"}},
        "equipment": {},
        "history": [],
        "settings": {"due_soon_days": 14},
        "notification_state": {"individual": {"clean_gutters": "overdue"}},
    }
    monkeypatch.setattr(
        "custom_components.home_maintenance_manager.storage.Store", FakeStore
    )

    storage = MaintenanceStorage(hass, "legacy-settings")
    data = await storage.async_load()

    assert data["settings"]["due_soon_days"] == 14
    assert data["settings"]["daily_summary_enabled"] is True
    assert data["settings"]["individual_notifications_enabled"] is True
    assert data["settings"]["season_windows"]["spring"] == {
        "start": "03-15",
        "end": "05-31",
    }
    assert data["notification_state"]["individual"] == {
        "clean_gutters": "overdue"
    }
    assert data["notification_state"]["summary_date"] is None
    assert data["update_backup_state"] == {"available": {}, "installations": {}}
    assert data["tasks"]["clean_gutters"]["task_id"] == "clean_gutters"


@pytest.mark.asyncio
async def test_storage_ignores_malformed_nested_settings(hass, monkeypatch):
    """Malformed optional nested values fall back to safe defaults."""
    FakeStore.stored = {
        "settings": {
            "due_soon_days": "soon",
            "daily_summary_enabled": "yes",
            "season_windows": "invalid",
        },
        "notification_state": {
            "individual": [],
            "summary_date": 123,
        },
        "history": {},
    }
    monkeypatch.setattr(
        "custom_components.home_maintenance_manager.storage.Store", FakeStore
    )

    storage = MaintenanceStorage(hass, "malformed-settings")
    data = await storage.async_load()

    assert data["settings"]["due_soon_days"] == 7
    assert data["settings"]["daily_summary_enabled"] is True
    assert data["settings"]["season_windows"]["winter"] == {
        "start": "11-16",
        "end": "03-14",
    }
    assert data["notification_state"] == {
        "individual": {},
        "summary_date": None,
    }
    assert data["history"] == []


@pytest.mark.asyncio
async def test_storage_filters_malformed_task_and_history_records(hass, monkeypatch):
    """Invalid record shapes are ignored without discarding valid records."""
    valid_task = {"task_id": "clean_gutters", "name": "Clean gutters"}
    valid_history = {"history_id": "clean_gutters:one", "task_id": "clean_gutters"}
    FakeStore.stored = {
        "tasks": {
            "clean_gutters": valid_task,
            "broken_task": "not a task object",
            42: {"task_id": "invalid-key"},
        },
        "equipment": {
            "furnace": {"equipment_id": "furnace"},
            "broken_equipment": None,
        },
        "history": [valid_history, "not a history record", None],
    }
    monkeypatch.setattr(
        "custom_components.home_maintenance_manager.storage.Store", FakeStore
    )

    storage = MaintenanceStorage(hass, "malformed-records")
    data = await storage.async_load()

    assert data["tasks"] == {"clean_gutters": valid_task}
    assert data["equipment"] == {"furnace": {"equipment_id": "furnace"}}
    assert data["history"] == [valid_history]

@pytest.mark.asyncio
async def test_storage_validates_notification_state_and_numeric_settings(
    hass, monkeypatch
):
    """Out-of-range settings and malformed notification markers use defaults."""
    FakeStore.stored = {
        "settings": {
            "due_soon_days": 999,
            "daily_summary_enabled": False,
            "individual_notifications_enabled": True,
        },
        "notification_state": {
            "individual": {
                "clean_gutters:2026-11-09": "2026-11-09T08:00:00+00:00",
                "bad_key": None,
                7: "not-a-key",
            },
            "summary_date": "2026-02-30",
        },
    }
    monkeypatch.setattr(
        "custom_components.home_maintenance_manager.storage.Store", FakeStore
    )

    storage = MaintenanceStorage(hass, "notification-validation")
    data = await storage.async_load()

    assert data["settings"]["due_soon_days"] == 7
    assert data["settings"]["daily_summary_enabled"] is False
    assert data["settings"]["individual_notifications_enabled"] is True
    assert data["notification_state"] == {
        "individual": {
            "clean_gutters:2026-11-09": "2026-11-09T08:00:00+00:00"
        },
        "summary_date": None,
    }

@pytest.mark.asyncio
async def test_storage_save_and_reload_round_trip(hass, monkeypatch):
    """A save followed by a fresh storage load preserves complete valid data."""
    monkeypatch.setattr(
        "custom_components.home_maintenance_manager.storage.Store", FakeStore
    )
    original = {
        "tasks": {
            "clean_gutters": {
                "task_id": "clean_gutters",
                "next_due": "2026-11-20T00:00:00+00:00",
                "schedule_history": [
                    {
                        "previous_due": "2026-11-15T00:00:00+00:00",
                        "next_due": "2026-11-20T00:00:00+00:00",
                        "reason": "Weather",
                    }
                ],
            }
        },
        "equipment": {
            "furnace": {
                "equipment_id": "furnace",
                "task_ids": ["replace_filter"],
            }
        },
        "history": [
            {
                "history_id": "clean_gutters:completion",
                "task_id": "clean_gutters",
                "notes": "Completed after the storm",
                "attachments": ["/local/maintenance/photo.jpg"],
            }
        ],
        "notification_state": {
            "individual": {
                "clean_gutters:2026-11-20T00:00:00+00:00":
                    "2026-11-09T08:00:00+00:00"
            },
            "summary_date": "2026-11-09",
        },
        "update_backup_state": {
            "available": {
                "update.home_assistant_core_update": {
                    "version": "2026.11.1",
                    "filename": "home_maintenance_update_core.json",
                    "created_at": "2026-11-09T08:00:00+00:00",
                }
            },
            "installations": {},
        },
        "settings": {
            "due_soon_days": 14,
            "daily_summary_enabled": False,
            "individual_notifications_enabled": True,
            "season_windows": {
                "spring": {"start": "03-10", "end": "05-25"},
                "summer": {"start": "06-01", "end": "08-31"},
                "fall": {"start": "09-01", "end": "11-15"},
                "winter": {"start": "11-16", "end": "03-14"},
            },
        },
    }

    writer = MaintenanceStorage(hass, "round-trip")
    await writer.async_save(original)

    reader = MaintenanceStorage(hass, "round-trip")
    restored = await reader.async_load()

    assert restored == original
