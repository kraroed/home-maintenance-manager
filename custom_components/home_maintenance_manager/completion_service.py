"""Services for recording maintenance task completions with notes and attachments."""
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

SERVICE_COMPLETE_TASK = "complete_task"


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

        attachments = [
            item.strip()
            for item in call.data.get("attachments", "").splitlines()
            if item.strip()
        ]
        for attachment in attachments:
            parsed = urlparse(attachment)
            if not (
                (parsed.scheme in ("http", "https") and parsed.netloc)
                or attachment.startswith("/local/")
            ):
                raise HomeAssistantError(
                    "Attachments must be HTTP(S) URLs or Home Assistant /local/ paths."
                )

        entry_data = matches[0]
        await entry_data["manager"].async_complete_task(
            task_id, call.data.get("notes", ""), attachments
        )
        await entry_data["coordinator"].async_request_refresh()

    if not hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK):
        hass.services.async_register(
            DOMAIN,
            SERVICE_COMPLETE_TASK,
            handle_complete,
            schema=vol.Schema({
                vol.Required("task_id"): str,
                vol.Optional("notes", default=""): str,
                vol.Optional("attachments", default=""): str,
                vol.Optional("integration_instance"): str,
            }),
        )
