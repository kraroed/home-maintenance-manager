"""Regression tests for maintenance reminders and daily summaries."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.util import dt as dt_util

from custom_components.home_maintenance_manager.notifications import (
    async_setup_notifications,
)


@pytest.mark.asyncio
async def test_notifications_send_due_reminder_and_daily_summary(hass, monkeypatch):
    """Due tasks trigger an individual reminder and a daily summary."""
    from custom_components.home_maintenance_manager import notifications

    created = []
    monkeypatch.setattr(
        notifications.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None: created.append(
            (title, message, notification_id)
        ),
    )
    monkeypatch.setattr(
        notifications,
        "async_track_time_interval",
        lambda hass, action, interval: lambda: None,
    )

    today = dt_util.now().date()
    due_today = dt_util.as_utc(
        dt_util.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ).isoformat()
    manager = SimpleNamespace(
        data={
            "tasks": {
                "clean_gutters": {
                    "task_id": "clean_gutters",
                    "name": "Clean gutters",
                    "enabled": True,
                    "next_due": due_today,
                },
                "disabled_task": {
                    "task_id": "disabled_task",
                    "name": "Disabled task",
                    "enabled": False,
                    "next_due": due_today,
                },
            }
        },
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": True,
            "notification_lead_days": 7,
            "daily_summary_time": "00:00",
        }
    )

    cancel = await async_setup_notifications(hass, entry, manager)

    assert callable(cancel)
    assert len(created) == 2
    assert created[0][0] == "Home maintenance reminder"
    assert created[0][1].startswith("Clean gutters is due today (due ")
    assert "Disabled task" not in " ".join(item[1] for item in created)
    assert created[1][0] == "Daily home maintenance summary"
    assert "Clean gutters — due today" in created[1][1]
    assert manager.data["notification_state"]["summary_date"] == today.isoformat()
    assert len(manager.data["notification_state"]["individual"]) == 1
    assert manager.async_save.await_count == 2


@pytest.mark.asyncio
async def test_notifications_respect_disabled_options_and_notify_target(hass, monkeypatch):
    """Disabled notifications produce no messages; configured targets use notify."""
    from custom_components.home_maintenance_manager import notifications

    monkeypatch.setattr(
        notifications,
        "async_track_time_interval",
        lambda hass, action, interval: lambda: None,
    )
    notify_calls = []

    async def record_notify(domain, service, service_data, blocking=False):
        notify_calls.append((domain, service, service_data, blocking))

    notify_mock = AsyncMock(side_effect=record_notify)
    monkeypatch.setattr(type(hass.services), "async_call", notify_mock)
    manager = SimpleNamespace(
        data={
            "tasks": {
                "clean_gutters": {
                    "task_id": "clean_gutters",
                    "name": "Clean gutters",
                    "enabled": True,
                    "next_due": dt_util.now().isoformat(),
                }
            }
        },
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        options={
            "individual_notifications_enabled": False,
            "daily_summary_enabled": False,
            "notification_target": "notify.household",
        }
    )

    await async_setup_notifications(hass, entry, manager)

    assert notify_calls == []
    assert manager.async_save.await_count == 0


@pytest.mark.asyncio
async def test_notifications_send_to_configured_notify_target(hass, monkeypatch):
    """A configured notify target receives the reminder through notify.send_message."""
    from custom_components.home_maintenance_manager import notifications

    monkeypatch.setattr(
        notifications,
        "async_track_time_interval",
        lambda hass, action, interval: lambda: None,
    )
    notify_mock = AsyncMock()
    monkeypatch.setattr(type(hass.services), "async_call", notify_mock)
    manager = SimpleNamespace(
        data={
            "tasks": {
                "clean_gutters": {
                    "task_id": "clean_gutters",
                    "name": "Clean gutters",
                    "enabled": True,
                    "next_due": dt_util.now().isoformat(),
                }
            }
        },
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": False,
            "notification_target": "notify.household",
        }
    )

    await async_setup_notifications(hass, entry, manager)

    notify_mock.assert_awaited_once()
    args = notify_mock.await_args
    assert args.args[:2] == ("notify", "send_message")
    assert args.args[2]["target"] == {"entity_id": "notify.household"}
    assert args.args[2]["message"].startswith("Clean gutters is due today (due ")
    assert args.kwargs["blocking"] is True

@pytest.mark.asyncio
async def test_notifications_suppress_repeats_until_task_due_date_changes(
    hass, monkeypatch
):
    """A reminder is sent once per due date while the daily summary is sent once per day."""
    from custom_components.home_maintenance_manager import notifications

    now = dt_util.now().replace(hour=9, minute=0, second=0, microsecond=0)
    monkeypatch.setattr(notifications.dt_util, "now", lambda: now)

    created = []
    monkeypatch.setattr(
        notifications.persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None: created.append(
            (title, message, notification_id)
        ),
    )
    callbacks = []

    def track_interval(hass, action, interval):
        callbacks.append(action)
        return lambda: None

    monkeypatch.setattr(notifications, "async_track_time_interval", track_interval)

    task = {
        "task_id": "clean_gutters",
        "name": "Clean gutters",
        "enabled": True,
        "next_due": now.isoformat(),
    }
    manager = SimpleNamespace(
        data={"tasks": {"clean_gutters": task}},
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": True,
            "notification_lead_days": 7,
            "daily_summary_time": "08:00",
        }
    )

    await async_setup_notifications(hass, entry, manager)
    assert len(created) == 2
    assert len(callbacks) == 1

    await callbacks[0](now)
    assert len(created) == 2

    task["next_due"] = (now + timedelta(days=1)).isoformat()
    await callbacks[0](now)

    reminders = [item for item in created if item[0] == "Home maintenance reminder"]
    summaries = [
        item for item in created if item[0] == "Daily home maintenance summary"
    ]
    assert len(reminders) == 2
    assert len(summaries) == 1
    assert "due in 1 day(s) (due " in reminders[1][1]
    assert manager.async_save.await_count == 3



@pytest.mark.asyncio
async def test_mobile_reminder_includes_complete_and_snooze_actions(hass, monkeypatch):
    """Mobile reminders expose complete, tomorrow, and one-week actions."""
    from custom_components.home_maintenance_manager import notifications

    monkeypatch.setattr(
        notifications, "async_track_time_interval", lambda hass, action, interval: lambda: None
    )
    notify_mock = AsyncMock()
    monkeypatch.setattr(type(hass.services), "async_call", notify_mock)
    now = dt_util.now()
    manager = SimpleNamespace(
        data={"tasks": {"clean_gutters": {
            "task_id": "clean_gutters", "name": "Clean gutters",
            "enabled": True, "next_due": now.isoformat(),
        }}},
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="entry-123",
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": False,
            "notification_target": "notify.mobile_app_phone",
        },
    )

    await async_setup_notifications(hass, entry, manager)

    payload = notify_mock.await_args.args[2]
    actions = payload["data"]["actions"]
    assert [item["title"] for item in actions] == [
        "Mark complete", "Tomorrow", "In 1 week"
    ]
    assert actions[0]["action"] == "HMM|entry-123|clean_gutters|complete"
    assert actions[1]["action"] == "HMM|entry-123|clean_gutters|snooze_1d"
    assert actions[2]["action"] == "HMM|entry-123|clean_gutters|snooze_7d"


@pytest.mark.asyncio
async def test_mobile_notification_complete_action_records_task(hass, monkeypatch):
    """Selecting Mark complete records completion and refreshes the coordinator."""
    from custom_components.home_maintenance_manager import notifications

    monkeypatch.setattr(
        notifications, "async_track_time_interval", lambda hass, action, interval: lambda: None
    )
    monkeypatch.setattr(type(hass.services), "async_call", AsyncMock())
    now = dt_util.now()
    task = {
        "task_id": "clean_gutters", "name": "Clean gutters",
        "enabled": True, "next_due": now.isoformat(),
    }
    manager = SimpleNamespace(
        data={"tasks": {"clean_gutters": task}},
        async_save=AsyncMock(),
        async_complete_task=AsyncMock(),
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    entry = SimpleNamespace(
        entry_id="entry-123",
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": False,
            "notification_target": "notify.mobile_app_phone",
        },
    )

    await async_setup_notifications(hass, entry, manager, coordinator)
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "HMM|entry-123|clean_gutters|complete"},
    )
    await hass.async_block_till_done()

    manager.async_complete_task.assert_awaited_once_with("clean_gutters")
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_mobile_notification_snooze_persists_until_tomorrow(hass, monkeypatch):
    """Snooze actions persist a timestamp and suppress the next reminder."""
    from custom_components.home_maintenance_manager import notifications

    monkeypatch.setattr(
        notifications, "async_track_time_interval", lambda hass, action, interval: lambda: None
    )
    monkeypatch.setattr(type(hass.services), "async_call", AsyncMock())
    now = dt_util.now()
    task = {
        "task_id": "clean_gutters", "name": "Clean gutters",
        "enabled": True, "next_due": now.isoformat(),
    }
    manager = SimpleNamespace(
        data={"tasks": {"clean_gutters": task}},
        async_save=AsyncMock(),
        async_complete_task=AsyncMock(),
    )
    entry = SimpleNamespace(
        entry_id="entry-123",
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": False,
            "notification_target": "notify.mobile_app_phone",
        },
    )

    await async_setup_notifications(hass, entry, manager)
    due_key = f"clean_gutters:{task['next_due']}"
    hass.bus.async_fire(
        "mobile_app_notification_action",
        {"action": "HMM|entry-123|clean_gutters|snooze_1d"},
    )
    await hass.async_block_till_done()

    marker = manager.data["notification_state"]["individual"][due_key]
    assert marker.startswith("snoozed:")
    assert dt_util.parse_datetime(marker.removeprefix("snoozed:")) > now
    assert manager.async_save.await_count >= 2


@pytest.mark.asyncio
async def test_reminders_include_due_date_and_associated_equipment(hass, monkeypatch):
    """Individual reminders include the exact due date and linked equipment."""
    from homeassistant.components import persistent_notification
    from custom_components.home_maintenance_manager import notifications

    created = []
    monkeypatch.setattr(
        persistent_notification,
        "async_create",
        lambda hass, message, title, notification_id=None: created.append(message),
    )
    monkeypatch.setattr(
        notifications,
        "async_track_time_interval",
        lambda hass, action, interval: lambda: None,
    )
    due = dt_util.now().date()
    due_at_midnight = dt_util.now().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    manager = SimpleNamespace(
        data={
            "tasks": {
                "replace_filter": {
                    "task_id": "replace_filter",
                    "name": "Replace furnace filter",
                    "enabled": True,
                    "next_due": dt_util.as_utc(due_at_midnight).isoformat(),
                    "equipment_ids": ["furnace"],
                }
            },
            "equipment": {
                "furnace": {"equipment_id": "furnace", "name": "Main furnace"}
            },
        },
        async_save=AsyncMock(),
    )
    entry = SimpleNamespace(
        options={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": False,
            "notification_lead_days": 7,
        }
    )

    await async_setup_notifications(hass, entry, manager)

    assert len(created) == 1
    assert f"due {due.isoformat()}" in created[0]
    assert "Equipment: Main furnace" in created[0]
