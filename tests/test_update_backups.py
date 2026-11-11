"""Tests for update-triggered JSON backups and installation tracking."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.core import Event, State

from custom_components.home_maintenance_manager import update_backups


def _entry_data():
    from custom_components.home_maintenance_manager.backup import (
        BACKUP_FORMAT,
        BACKUP_SCHEMA_VERSION,
    )

    manager = SimpleNamespace(
        data={
            "tasks": {},
            "equipment": {},
            "history": [],
            "notification_state": {"individual": {}, "summary_date": None},
            "settings": {"due_soon_days": 7, "season_windows": {}},
            "update_backup_state": {"available": {}, "installations": {}},
        },
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="property-one",
        title="My Home",
        data={"property_name": "My Home", "enabled_task_ids": []},
        options={},
    )
    return {
        "manager": manager,
        "config_entry": entry,
        "property_name": "My Home",
    }


def _state_event(entity_id, old_state, new_state):
    return Event(
        "state_changed",
        {
            "entity_id": entity_id,
            "old_state": old_state,
            "new_state": new_state,
        },
    )


@pytest.mark.asyncio
async def test_update_available_creates_one_backup_per_version(
    hass, tmp_path, monkeypatch
):
    """Availability creates a backup once and ignores duplicate state updates."""
    monkeypatch.setattr(
        hass.config, "path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    callbacks = {}
    monkeypatch.setattr(
        "homeassistant.helpers.event.async_track_state_change_event",
        lambda hass, entity_ids, action: callbacks.update(
            entity_ids=entity_ids, action=action
        ) or (lambda: None),
    )
    notifications = []
    monkeypatch.setattr(
        update_backups.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None:
            notifications.append((message, title, notification_id)),
    )

    entry_data = _entry_data()
    entry = entry_data["config_entry"]
    entry.options = {
        "update_backup_on_available": True,
        "update_install_tracking_enabled": True,
        "update_backup_entities": [],
    }

    cancel = update_backups.async_setup_update_backups(hass, entry, entry_data)
    assert callable(cancel)
    assert callbacks["entity_ids"] is None

    old = State("update.home_assistant_core_update", "off", {})
    available = State(
        "update.home_assistant_core_update",
        "on",
        {
            "friendly_name": "Home Assistant Core",
            "latest_version": "2026.11.1",
            "installed_version": "2026.11.0",
            "in_progress": False,
        },
    )
    event = _state_event("update.home_assistant_core_update", old, available)
    await callbacks["action"](event)
    await callbacks["action"](event)

    directory = (
        tmp_path / "home_maintenance_manager_backups" / "property-one"
    )
    backups = list(directory.glob("home_maintenance_update_*.json"))
    assert len(backups) == 1
    assert "2026.11.1" in notifications[0][0]
    assert entry_data["manager"].data["update_backup_state"]["available"][
        "update.home_assistant_core_update"
    ]["filename"] == backups[0].name
    entry_data["manager"].async_save.assert_awaited_once()

    installing = State(
        "update.home_assistant_core_update",
        "on",
        {
            "friendly_name": "Home Assistant Core",
            "latest_version": "2026.11.1",
            "installed_version": "2026.11.0",
            "in_progress": True,
        },
    )
    await callbacks["action"](
        _state_event("update.home_assistant_core_update", available, installing)
    )

    assert len(list(directory.glob("home_maintenance_update_*.json"))) == 1
    assert any("matching Home Maintenance Manager backup" in item[0] for item in notifications)
    installation = entry_data["manager"].data["update_backup_state"]["installations"][
        "update.home_assistant_core_update"
    ]
    assert installation["version"] == "2026.11.1"
    assert installation["backup_file"] == backups[0].name


@pytest.mark.asyncio
async def test_installation_start_without_earlier_backup_is_reported(
    hass, monkeypatch
):
    """An in-progress event never creates a late backup and warns if none exists."""
    callbacks = {}
    monkeypatch.setattr(
        "homeassistant.helpers.event.async_track_state_change_event",
        lambda hass, entity_ids, action: callbacks.update(action=action) or (lambda: None),
    )
    notifications = []
    monkeypatch.setattr(
        update_backups.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None:
            notifications.append(message),
    )

    entry_data = _entry_data()
    entry = entry_data["config_entry"]
    entry.options = {
        "update_backup_on_available": True,
        "update_install_tracking_enabled": True,
    }
    update_backups.async_setup_update_backups(hass, entry, entry_data)

    installing = State(
        "update.some_addon_update",
        "on",
        {"latest_version": "3.2.0", "in_progress": True},
    )
    await callbacks["action"](
        _state_event("update.some_addon_update", None, installing)
    )

    assert "no matching update-available backup" in notifications[0]
    assert entry_data["manager"].data["update_backup_state"]["available"] == {}
    assert entry_data["manager"].data["update_backup_state"]["installations"][
        "update.some_addon_update"
    ]["backup_file"] is None


@pytest.mark.asyncio
async def test_update_backup_listener_respects_selected_entities(hass, monkeypatch):
    """When entity IDs are selected, other update entities are ignored."""
    callbacks = {}
    monkeypatch.setattr(
        "homeassistant.helpers.event.async_track_state_change_event",
        lambda hass, entity_ids, action: callbacks.update(action=action) or (lambda: None),
    )
    entry_data = _entry_data()
    entry = entry_data["config_entry"]
    entry.options = {
        "update_backup_on_available": True,
        "update_install_tracking_enabled": False,
        "update_backup_entities": ["update.home_assistant_core_update"],
    }
    update_backups.async_setup_update_backups(hass, entry, entry_data)

    state = State(
        "update.some_addon_update",
        "on",
        {"latest_version": "3.2.0", "in_progress": False},
    )
    await callbacks["action"](_state_event("update.some_addon_update", None, state))

    assert entry_data["manager"].data["update_backup_state"]["available"] == {}
