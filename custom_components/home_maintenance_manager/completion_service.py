"""Services for recording maintenance task completions with notes."""

import voluptuous as vol

from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

SERVICE_COMPLETE_TASK = "complete_task"
SERVICE_RESCHEDULE_TASK = "reschedule_task"


async def async_setup_completion_service(hass):
    """Register the task completion service."""
    async def handle_complete(call: ServiceCall):
        entries = hass.data.get(DOMAIN, {})
        task_id = call.data["task_id"]
        instance = call.data.get("integration_instance")
        matches = [
            data for data in entries.values()
            if (instance is None or data["manager"].storage.store.key == instance)
            and task_id in data["manager"].data.get("tasks", {})
        ]
        if not matches:
            raise HomeAssistantError(
                f"No Home Maintenance Manager task found with ID: {task_id}"
            )
        if len(matches) > 1:
            raise HomeAssistantError(
                "More than one matching task exists; provide integration_instance."
            )

        entry_data = matches[0]
        await entry_data["manager"].async_complete_task(
            task_id, call.data.get("notes", "")
        )
        await entry_data["coordinator"].async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_RESCHEDULE_TASK):
        async def handle_reschedule(call: ServiceCall):
            entries = hass.data.get(DOMAIN, {})
            task_id = call.data["task_id"]
            instance = call.data.get("integration_instance")
            matches = [
                data for data in entries.values()
                if (instance is None or data["manager"].storage.store.key == instance)
                and task_id in data["manager"].data.get("tasks", {})
            ]
            if not matches:
                raise HomeAssistantError(
                    f"No Home Maintenance Manager task found with ID: {task_id}"
                )
            if len(matches) > 1:
                raise HomeAssistantError(
                    "More than one matching task exists; provide integration_instance."
                )
            entry_data = matches[0]
            try:
                await entry_data["manager"].async_reschedule_task(
                    task_id, call.data["due_date"], call.data.get("reason", "")
                )
            except ValueError as err:
                raise HomeAssistantError(str(err)) from err
            await entry_data["coordinator"].async_request_refresh()

        hass.services.async_register(
            DOMAIN,
            SERVICE_RESCHEDULE_TASK,
            handle_reschedule,
            schema=vol.Schema({
                vol.Required("task_id"): str,
                vol.Required("due_date"): vol.Match(r"^\d{4}-\d{2}-\d{2}$"),
                vol.Optional("reason", default=""): str,
                vol.Optional("integration_instance"): str,
            }),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK):
        hass.services.async_register(
            DOMAIN,
            SERVICE_COMPLETE_TASK,
            handle_complete,
            schema=vol.Schema({
                vol.Required("task_id"): str,
                vol.Optional("notes", default=""): str,
                vol.Optional("integration_instance"): str,
            }),
        )


async def async_unload_completion_service(hass):
    """Remove task services after the final config entry is unloaded."""
    for service in (SERVICE_COMPLETE_TASK, SERVICE_RESCHEDULE_TASK):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
