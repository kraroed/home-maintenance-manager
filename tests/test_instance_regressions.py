"""Regression coverage for legacy backups and multi-property service routing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.home_maintenance_manager.backup import (
    BACKUP_FORMAT,
    BACKUP_SCHEMA_VERSION,
    SERVICE_PREVIEW_RESTORE,
    SERVICE_RESTORE_BACKUP,
    _write_json_file,
    async_setup_backup_services,
)
from custom_components.home_maintenance_manager.completion_service import (
    SERVICE_COMPLETE_TASK,
    SERVICE_RESCHEDULE_TASK,
    async_setup_completion_service,
)
from custom_components.home_maintenance_manager.const import DOMAIN
from custom_components.home_maintenance_manager.history_export import (
    SERVICE_EXPORT_HISTORY,
    async_setup_history_export,
)


def _legacy_payload(property_name="Property Two Backup"):
    """Represent a valid schema-v1 backup created before newer optional fields."""
    return {
        "format": BACKUP_FORMAT,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": "2026-08-01T12:00:00+00:00",
        "property_name": property_name,
        "entry_data": {
            "property_name": property_name,
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
                    "next_due": "2026-12-01T00:00:00+00:00",
                }
            },
            "equipment": {
                "hvac": {"equipment_id": "hvac", "name": "HVAC system"}
            },
            "history": [
                {
                    "history_id": "legacy-completion",
                    "task_id": "clean_gutters",
                    "task_name": "Clean gutters",
                    "completed_at": "2026-07-01T12:00:00+00:00",
                }
            ],
            "notification_state": {
                "individual": {"clean_gutters:due": "2026-07-31"},
                "summary_date": "2026-07-31",
            },
            "settings": {
                "due_soon_days": 7,
                "daily_summary_enabled": True,
                "individual_notifications_enabled": True,
                "season_windows": {},
            },
        },
    }


def _property(instance, property_name):
    """Build a loaded property with independent manager and coordinator mocks."""
    manager = SimpleNamespace(
        storage=SimpleNamespace(
            store=SimpleNamespace(key=instance),
            async_save=AsyncMock(),
        ),
        data={
            "tasks": {
                "clean_gutters": {
                    "task_id": "clean_gutters",
                    "name": f"{property_name} gutters",
                    "schedule_history": [],
                }
            },
            "equipment": {},
            "history": [
                {"history_id": f"{instance}-history", "task_id": "clean_gutters"}
            ],
            "notification_state": {"individual": {}, "summary_date": None},
            "settings": {
                "due_soon_days": 14,
                "daily_summary_enabled": False,
                "individual_notifications_enabled": True,
                "season_windows": {},
            },
            "backlog_snapshots": [],
        },
        enabled_ids={"clean_gutters"},
        task_intervals={},
        equipment_records=[],
        season_windows={},
        library={},
        async_complete_task=AsyncMock(),
        async_reschedule_task=AsyncMock(),
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    entry = SimpleNamespace(
        entry_id=instance,
        title=property_name,
        data={"property_name": property_name, "enabled_task_ids": ["clean_gutters"]},
        options={"enabled_task_ids": ["clean_gutters"]},
    )
    return {
        "manager": manager,
        "coordinator": coordinator,
        "config_entry": entry,
        "property_name": property_name,
    }


@pytest.mark.asyncio
async def test_reschedule_requires_instance_and_refreshes_only_selected_property(hass):
    """Ambiguous reschedules fail; explicit instance affects only that property."""
    first = _property("property-one", "First Home")
    second = _property("property-two", "Second Home")
    hass.data[DOMAIN] = {"property-one": first, "property-two": second}
    await async_setup_completion_service(hass)

    with pytest.raises(HomeAssistantError, match="More than one matching task"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESCHEDULE_TASK,
            {"task_id": "clean_gutters", "due_date": "2027-04-15"},
            blocking=True,
        )

    first["manager"].async_reschedule_task.assert_not_awaited()
    second["manager"].async_reschedule_task.assert_not_awaited()

    for selected, other in ((first, second), (second, first)):
        # Each iteration independently verifies that only the selected property
        # receives this service call.
        for prop in (first, second):
            prop["manager"].async_reschedule_task.reset_mock()
            prop["coordinator"].async_request_refresh.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_RESCHEDULE_TASK,
            {
                "task_id": "clean_gutters",
                "due_date": "2027-04-15",
                "integration_instance": selected["config_entry"].entry_id,
            },
            blocking=True,
        )
        selected["manager"].async_reschedule_task.assert_awaited_once_with(
            "clean_gutters", "2027-04-15", ""
        )
        selected["coordinator"].async_request_refresh.assert_awaited_once()
        other["manager"].async_reschedule_task.assert_not_awaited()
        other["coordinator"].async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_complete_routes_to_each_selected_property(hass):
    """Completion with either instance key affects only that property's manager."""
    first = _property("property-one", "First Home")
    second = _property("property-two", "Second Home")
    hass.data[DOMAIN] = {"property-one": first, "property-two": second}
    await async_setup_completion_service(hass)

    with pytest.raises(HomeAssistantError, match="More than one matching task"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COMPLETE_TASK,
            {"task_id": "clean_gutters"},
            blocking=True,
        )

    for selected, other in ((first, second), (second, first)):
        # Reset between selections so the unselected property is checked only
        # against the current service invocation.
        for prop in (first, second):
            prop["manager"].async_complete_task.reset_mock()
            prop["coordinator"].async_request_refresh.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COMPLETE_TASK,
            {
                "task_id": "clean_gutters",
                "integration_instance": selected["config_entry"].entry_id,
            },
            blocking=True,
        )
        selected["manager"].async_complete_task.assert_awaited_once_with(
            "clean_gutters", ""
        )
        selected["coordinator"].async_request_refresh.assert_awaited_once()
        other["manager"].async_complete_task.assert_not_awaited()
        other["coordinator"].async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_backup_preview_and_restore_are_instance_scoped(
    hass, tmp_path, monkeypatch
):
    """Older schema-v1 backups preview and restore safely to the selected property."""
    from custom_components.home_maintenance_manager import backup

    monkeypatch.setattr(
        hass.config, "path", lambda *parts: str(tmp_path.joinpath(*parts))
    )
    notifications = []
    monkeypatch.setattr(
        backup.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None: notifications.append(
            (message, title)
        ),
    )
    monkeypatch.setattr(
        hass.config_entries,
        "async_update_entry",
        lambda *args, **kwargs: True,
    )

    first = _property("property-one", "First Home")
    second = _property("property-two", "Second Home")
    first["manager"].data["history"].append(
        {"history_id": "first-only", "task_id": "clean_gutters"}
    )
    second["manager"].data["history"].append(
        {"history_id": "second-current", "task_id": "clean_gutters"}
    )
    second["manager"].data["backlog_snapshots"] = [
        {
            "date": "2026-11-10",
            "overdue": 1,
            "due_today": 0,
            "due_soon": 0,
            "scheduled": 1,
            "not_scheduled": 0,
            "total": 1,
        }
    ]
    hass.data[DOMAIN] = {"property-one": first, "property-two": second}

    payload = _legacy_payload()
    backup_path = (
        tmp_path
        / "home_maintenance_manager_backups"
        / "property-two"
        / "legacy.json"
    )
    _write_json_file(backup_path, payload)
    await async_setup_backup_services(hass)

    with pytest.raises(HomeAssistantError, match="More than one property"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_PREVIEW_RESTORE,
            {"filename": "legacy.json"},
            blocking=True,
        )

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PREVIEW_RESTORE,
        {
            "filename": "legacy.json",
            "integration_instance": "property-two",
        },
        blocking=True,
    )
    assert "Property Two Backup" in notifications[-1][0]
    assert first["manager"].data["history"][0]["history_id"] == "property-one-history"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESTORE_BACKUP,
        {
            "filename": "legacy.json",
            "confirm": True,
            "integration_instance": "property-two",
        },
        blocking=True,
    )

    assert first["manager"].storage.async_save.await_count == 0
    first["coordinator"].async_request_refresh.assert_not_awaited()
    second["manager"].storage.async_save.assert_awaited_once()
    second["coordinator"].async_request_refresh.assert_awaited_once()
    restored = second["manager"].data
    assert restored["tasks"]["clean_gutters"]["name"] == "Clean gutters"
    assert restored["equipment"]["hvac"]["name"] == "HVAC system"
    assert {item["history_id"] for item in restored["history"]} == {
        "property-two-history",
        "second-current",
        "legacy-completion",
    }
    assert [item["date"] for item in restored["backlog_snapshots"]] == [
        "2026-11-10"
    ]
    assert restored["notification_state"]["individual"] == {
        "clean_gutters:due": "2026-07-31"
    }
    assert restored["settings"]["due_soon_days"] == 7
    assert "backlog_snapshots" in restored
    from custom_components.home_maintenance_manager.update_backups import _state_bucket
    assert _state_bucket(second["manager"]) == {
        "available": {}, "installations": {}
    }


@pytest.mark.asyncio
async def test_history_export_writes_each_loaded_property_separately(
    hass, tmp_path, monkeypatch
):
    """The export service keeps completion and schedule history property-scoped."""
    from custom_components.home_maintenance_manager import history_export

    monkeypatch.setattr(
        hass.config, "path", lambda *parts: str(tmp_path.joinpath(*parts))
    )
    notifications = []
    monkeypatch.setattr(
        history_export.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None: notifications.append(
            message
        ),
    )

    first = _property("property-one", "First Home")
    second = _property("property-two", "Second Home")
    first["manager"].data["history"] = [
        {"history_id": "first-record", "task_id": "clean_gutters"}
    ]
    second["manager"].data["history"] = [
        {"history_id": "second-record", "task_id": "clean_gutters"}
    ]
    first["manager"].data["tasks"]["clean_gutters"]["schedule_history"] = [
        {"adjusted_at": "2026-11-01T12:00:00+00:00", "reason": "First property"}
    ]
    second["manager"].data["tasks"]["clean_gutters"]["schedule_history"] = [
        {"adjusted_at": "2026-11-02T12:00:00+00:00", "reason": "Second property"}
    ]
    hass.data[DOMAIN] = {"property-one": first, "property-two": second}
    await async_setup_history_export(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_EXPORT_HISTORY, {"format": "json"}, blocking=True
    )

    first_file = (
        tmp_path / "www" / DOMAIN / "property-one" / "maintenance_history.json"
    )
    second_file = (
        tmp_path / "www" / DOMAIN / "property-two" / "maintenance_history.json"
    )
    first_payload = json.loads(first_file.read_text(encoding="utf-8"))
    second_payload = json.loads(second_file.read_text(encoding="utf-8"))
    assert first_payload["property_name"] == "First Home"
    assert [row["history_id"] for row in first_payload["history"]] == ["first-record"]
    assert second_payload["property_name"] == "Second Home"
    assert [row["history_id"] for row in second_payload["history"]] == [
        "second-record"
    ]

    first_schedule = json.loads(
        (
            tmp_path
            / "www"
            / DOMAIN
            / "property-one"
            / "maintenance_schedule_history.json"
        ).read_text(encoding="utf-8")
    )
    second_schedule = json.loads(
        (
            tmp_path
            / "www"
            / DOMAIN
            / "property-two"
            / "maintenance_schedule_history.json"
        ).read_text(encoding="utf-8")
    )
    assert first_schedule["schedule_history"][0]["reason"] == "First property"
    assert second_schedule["schedule_history"][0]["reason"] == "Second property"
    assert len(notifications) == 1
