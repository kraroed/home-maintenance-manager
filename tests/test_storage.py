"""Regression tests for maintenance storage defaults and compatibility."""

import pytest

from custom_components.home_maintenance_manager.storage import MaintenanceStorage


class FakeStore:
    stored = None

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return self.stored

    async def async_save(self, data):
        self.stored = data


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
