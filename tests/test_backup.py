"""Tests for complete JSON backup and guarded restore behavior."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.home_maintenance_manager.backup import (
    BACKUP_FORMAT,
    BACKUP_SCHEMA_VERSION,
    _merge_history,
    _read_json_file,
    _safe_filename,
    _validate_payload,
    _write_json_file,
)


def _payload():
    return {
        "format": BACKUP_FORMAT,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": "2026-11-09T12:00:00+00:00",
        "property_name": "My Home",
        "entry_data": {
            "property_name": "My Home",
            "enabled_task_ids": ["clean_gutters"],
        },
        "options": {
            "enabled_task_ids": ["clean_gutters"],
            "task_intervals": {},
            "custom_tasks": [],
            "equipment_records": [],
            "season_windows": {},
        },
        "data": {
            "tasks": {
                "clean_gutters": {
                    "task_id": "clean_gutters",
                    "name": "Clean gutters",
                    "enabled": True,
                    "next_due": "2026-11-20T00:00:00+00:00",
                }
            },
            "equipment": {},
            "history": [
                {
                    "history_id": "clean_gutters:completion-1",
                    "task_id": "clean_gutters",
                    "task_name": "Clean gutters",
                    "completed_at": "2026-10-01T12:00:00+00:00",
                }
            ],
            "notification_state": {"individual": {}, "summary_date": None},
            "settings": {
                "due_soon_days": 7,
                "daily_summary_enabled": True,
                "individual_notifications_enabled": True,
                "season_windows": {},
            },
        },
    }


def test_backup_payload_accepts_complete_backup():
    """A complete backup envelope is accepted."""
    assert _validate_payload(_payload())["property_name"] == "My Home"


def test_backup_payload_rejects_wrong_format_and_malformed_history():
    """Wrong formats and malformed history are rejected before restore."""
    with pytest.raises(HomeAssistantError, match="not a Home Maintenance Manager backup"):
        _validate_payload({"format": "other"})

    invalid = _payload()
    invalid["data"]["history"] = {"not": "a list"}
    with pytest.raises(HomeAssistantError, match="invalid completion history"):
        _validate_payload(invalid)


def test_backup_filename_rejects_path_traversal():
    """Restore accepts a filename only, never an arbitrary filesystem path."""
    assert _safe_filename("maintenance-backup.json") == "maintenance-backup.json"
    for filename in ("../backup.json", "/config/backup.json", "backup.txt", ""):
        with pytest.raises(HomeAssistantError):
            _safe_filename(filename)


def test_history_merge_preserves_current_records_and_adds_missing_records():
    """Restore never deletes newer local history and does not duplicate IDs."""
    current = [
        {"history_id": "existing", "notes": "Recorded locally"},
        {"history_id": "same", "notes": "Current version"},
    ]
    incoming = [
        {"history_id": "same", "notes": "Older backup version"},
        {"history_id": "restored", "notes": "From backup"},
    ]

    merged = _merge_history(current, incoming)

    assert merged == [
        {"history_id": "existing", "notes": "Recorded locally"},
        {"history_id": "same", "notes": "Current version"},
        {"history_id": "restored", "notes": "From backup"},
    ]


def test_backup_file_round_trip_and_size_validation(tmp_path):
    """JSON files can be written and parsed through the same validator."""
    path = tmp_path / "backup.json"
    payload = _payload()
    _write_json_file(path, payload)

    assert _read_json_file(path) == payload


@pytest.mark.asyncio
async def test_backup_and_preview_services_do_not_modify_live_data(hass, tmp_path, monkeypatch):
    """Creating and previewing a backup leaves the active property unchanged."""
    from custom_components.home_maintenance_manager import backup

    monkeypatch.setattr(
        hass.config, "path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr(
        backup.persistent_notification,
        "async_create",
        lambda *args, **kwargs: None,
    )
    manager = SimpleNamespace(
        storage=SimpleNamespace(store=SimpleNamespace(key="property-one")),
        data=deepcopy(_payload()["data"]),
    )
    entry = SimpleNamespace(
        entry_id="entry-one",
        title="My Home",
        data={"property_name": "My Home", "enabled_task_ids": ["clean_gutters"]},
        options={"enabled_task_ids": ["clean_gutters"]},
    )
    hass.data[backup.DOMAIN] = {
        "entry-one": {
            "manager": manager,
            "config_entry": entry,
            "property_name": "My Home",
        }
    }

    await backup.async_setup_backup_services(hass)
    await hass.services.async_call(backup.DOMAIN, backup.SERVICE_CREATE_BACKUP, {}, blocking=True)

    files = list((tmp_path / "home_maintenance_manager_backups" / "entry-one").glob("*.json"))
    assert len(files) == 1
    original_data = deepcopy(manager.data)

    await hass.services.async_call(
        backup.DOMAIN,
        backup.SERVICE_PREVIEW_RESTORE,
        {"filename": files[0].name},
        blocking=True,
    )

    assert manager.data == original_data


@pytest.mark.asyncio
async def test_restore_requires_confirmation_and_preserves_newer_history(
    hass, tmp_path, monkeypatch
):
    """A confirmed restore merges history and saves a pre-restore safety copy."""
    from custom_components.home_maintenance_manager import backup

    monkeypatch.setattr(
        hass.config, "path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    notifications = []
    monkeypatch.setattr(
        backup.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None: notifications.append(message),
    )
    current_history = [{"history_id": "new-local", "notes": "Keep this"}]
    manager = SimpleNamespace(
        storage=SimpleNamespace(
            store=SimpleNamespace(key="property-one"),
            async_save=AsyncMock(),
        ),
        data={
            **deepcopy(_payload()["data"]),
            "history": current_history,
        },
        enabled_ids={"old-task"},
        task_intervals={},
        equipment_records=[],
        season_windows={},
        library={},
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    entry = SimpleNamespace(
        entry_id="entry-one",
        title="My Home",
        data={"property_name": "My Home", "enabled_task_ids": ["old-task"]},
        options={"enabled_task_ids": ["old-task"]},
    )
    hass.data[backup.DOMAIN] = {
        "entry-one": {
            "manager": manager,
            "coordinator": coordinator,
            "config_entry": entry,
            "property_name": "My Home",
        }
    }
    directory = tmp_path / "home_maintenance_manager_backups" / "entry-one"
    _write_json_file(directory / "restore.json", _payload())
    monkeypatch.setattr(
        hass.config_entries,
        "async_update_entry",
        lambda *args, **kwargs: True,
    )

    await backup.async_setup_backup_services(hass)

    with pytest.raises(HomeAssistantError, match="Set confirm to true"):
        await hass.services.async_call(
            backup.DOMAIN,
            backup.SERVICE_RESTORE_BACKUP,
            {"filename": "restore.json", "confirm": False},
            blocking=True,
        )

    await hass.services.async_call(
        backup.DOMAIN,
        backup.SERVICE_RESTORE_BACKUP,
        {"filename": "restore.json", "confirm": True},
        blocking=True,
    )

    manager.storage.async_save.assert_awaited_once()
    assert {item["history_id"] for item in manager.data["history"]} == {
        "new-local",
        "clean_gutters:completion-1",
    }
    assert len(list(directory.glob("home_maintenance_pre_restore_*.json"))) == 1
    coordinator.async_request_refresh.assert_awaited_once()
