"""Tests for complete JSON backup and guarded restore behavior."""

import json
from copy import deepcopy
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.home_maintenance_manager.backup import (
    BACKUP_FORMAT,
    BACKUP_SCHEMA_VERSION,
    _build_payload,
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


def test_build_payload_accepts_immutable_config_entry_mappings():
    """ConfigEntry data and options may be mappingproxy objects."""
    entry = SimpleNamespace(
        data=MappingProxyType({
            "property_name": "My Home",
            "enabled_task_ids": ["clean_gutters"],
        }),
        options=MappingProxyType({
            "enabled_task_ids": ["clean_gutters"],
            "task_intervals": {},
        }),
        title="My Home",
    )
    manager = SimpleNamespace(data=deepcopy(_payload()["data"]))
    payload = _build_payload({
        "config_entry": entry,
        "manager": manager,
        "property_name": "My Home",
    })

    assert payload["entry_data"]["property_name"] == "My Home"
    assert payload["options"]["enabled_task_ids"] == ["clean_gutters"]


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


@pytest.mark.asyncio
async def test_automatic_backup_schedule_and_retention(hass, tmp_path, monkeypatch):
    """Scheduled backups run on the selected cadence and prune only auto backups."""
    from datetime import datetime
    from custom_components.home_maintenance_manager import backup

    monkeypatch.setattr(
        hass.config, "path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    callbacks = {}
    monkeypatch.setattr(
        "homeassistant.helpers.event.async_track_time_change",
        lambda hass, action, **kwargs: callbacks.update(action=action, schedule=kwargs) or (lambda: None),
    )
    monkeypatch.setattr(
        backup.persistent_notification,
        "async_create",
        lambda *args, **kwargs: None,
    )
    manager = SimpleNamespace(data=deepcopy(_payload()["data"]))
    entry = SimpleNamespace(
        entry_id="entry-one",
        title="My Home",
        data={"property_name": "My Home", "enabled_task_ids": ["clean_gutters"]},
        options={
            "automatic_backups_enabled": True,
            "automatic_backup_frequency": "weekly",
            "automatic_backup_time": "03:00",
            "automatic_backup_retention": 2,
        },
    )
    entry_data = {
        "config_entry": entry,
        "manager": manager,
        "property_name": "My Home",
    }
    directory = tmp_path / "home_maintenance_manager_backups" / "entry-one"
    directory.mkdir(parents=True)
    for index in range(3):
        path = directory / f"home_maintenance_auto_old{index}.json"
        path.write_text("{}", encoding="utf-8")
        import os
        os.utime(path, (index + 1, index + 1))
    manual = directory / "home_maintenance_backup_manual.json"
    manual.write_text("{}", encoding="utf-8")
    safety = directory / "home_maintenance_pre_restore_safety.json"
    safety.write_text("{}", encoding="utf-8")

    cancel = backup.async_setup_automatic_backup(hass, entry, entry_data)
    assert callable(cancel)
    assert callbacks["schedule"] == {"hour": 3, "minute": 0, "second": 0}

    await callbacks["action"](datetime(2026, 11, 15, 3, 0))
    automatic = list(directory.glob("home_maintenance_auto_*.json"))
    assert len(automatic) == 2
    assert manual.is_file()
    assert safety.is_file()


@pytest.mark.asyncio
async def test_automatic_backups_can_be_disabled(hass, monkeypatch):
    """Disabled automatic backups do not register a time listener."""
    from custom_components.home_maintenance_manager import backup

    def unexpected_listener(*args, **kwargs):
        raise AssertionError("A listener must not be registered when backups are disabled.")

    monkeypatch.setattr(
        "homeassistant.helpers.event.async_track_time_change",
        unexpected_listener,
    )
    entry = SimpleNamespace(
        entry_id="entry-one",
        options={"automatic_backups_enabled": False},
    )
    assert backup.async_setup_automatic_backup(hass, entry, {}) is not None
