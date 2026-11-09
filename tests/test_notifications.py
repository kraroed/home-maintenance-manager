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
    assert "Clean gutters is due today." == created[0][1]
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

    hass.services.async_call = AsyncMock(side_effect=record_notify)
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
    hass.services.async_call = AsyncMock()
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

    hass.services.async_call.assert_awaited_once()
    args = hass.services.async_call.await_args
    assert args.args[:2] == ("notify", "send_message")
    assert args.args[2]["target"] == {"entity_id": "notify.household"}
    assert args.args[2]["message"] == "Clean gutters is due today."
    assert args.kwargs["blocking"] is True
