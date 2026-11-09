"""Regression tests for Home Maintenance Manager services."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from homeassistant.exceptions import HomeAssistantError

from custom_components.home_maintenance_manager.completion_service import (
    SERVICE_COMPLETE_TASK,
    SERVICE_RESCHEDULE_TASK,
    async_setup_completion_service,
)
from custom_components.home_maintenance_manager.const import DOMAIN


def _entry_data(instance_id="property-one", task_ids=None):
    """Build a minimal loaded integration entry for service tests."""
    manager = SimpleNamespace(
        storage=SimpleNamespace(store=SimpleNamespace(key=instance_id)),
        data={"tasks": {task_id: {} for task_id in (task_ids or ["clean_gutters"])}},
        async_complete_task=AsyncMock(),
        async_reschedule_task=AsyncMock(),
    )
    coordinator = SimpleNamespace(async_request_refresh=AsyncMock())
    return {"manager": manager, "coordinator": coordinator}


@pytest.mark.asyncio
async def test_complete_task_service_forwards_notes_only(hass):
    """Completion service forwards notes without attachment or cost tracking."""
    entry_data = _entry_data()
    hass.data[DOMAIN] = {"property-one": entry_data}
    await async_setup_completion_service(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COMPLETE_TASK,
        {
            "task_id": "clean_gutters",
            "notes": "Cleared leaves and checked downspouts",
        },
        blocking=True,
    )

    entry_data["manager"].async_complete_task.assert_awaited_once_with(
        "clean_gutters", "Cleared leaves and checked downspouts"
    )
    entry_data["coordinator"].async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_complete_task_service_rejects_removed_tracking_fields(hass):
    """The simplified completion service no longer accepts attachment or cost fields."""
    entry_data = _entry_data()
    hass.data[DOMAIN] = {"property-one": entry_data}
    await async_setup_completion_service(hass)

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COMPLETE_TASK,
            {"task_id": "clean_gutters", "attachments": "/local/receipt.jpg"},
            blocking=True,
        )

    entry_data["manager"].async_complete_task.assert_not_awaited()
    entry_data["coordinator"].async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_reschedule_task_service_forwards_date_and_reason(hass):
    """Reschedule service forwards the selected due date and refreshes entities."""
    entry_data = _entry_data()
    hass.data[DOMAIN] = {"property-one": entry_data}
    await async_setup_completion_service(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_RESCHEDULE_TASK,
        {
            "task_id": "clean_gutters",
            "due_date": "2027-04-15",
            "reason": "Move to spring cleanup",
        },
        blocking=True,
    )

    entry_data["manager"].async_reschedule_task.assert_awaited_once_with(
        "clean_gutters", "2027-04-15", "Move to spring cleanup"
    )
    entry_data["coordinator"].async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_service_requires_instance_when_task_id_is_ambiguous(hass):
    """Duplicate task IDs across properties require an explicit instance selector."""
    first = _entry_data("property-one")
    second = _entry_data("property-two")
    hass.data[DOMAIN] = {"property-one": first, "property-two": second}
    await async_setup_completion_service(hass)

    with pytest.raises(HomeAssistantError, match="More than one matching task"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_COMPLETE_TASK,
            {"task_id": "clean_gutters"},
            blocking=True,
        )

    first["manager"].async_complete_task.assert_not_awaited()
    second["manager"].async_complete_task.assert_not_awaited()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_COMPLETE_TASK,
        {
            "task_id": "clean_gutters",
            "integration_instance": "property-two",
        },
        blocking=True,
    )

    first["manager"].async_complete_task.assert_not_awaited()
    second["manager"].async_complete_task.assert_awaited_once()
