from .completion_service import (
    async_setup_completion_service,
    async_unload_completion_service,
)
from .const import CONF_ENABLED_TASK_IDS, DOMAIN, PLATFORMS
from .coordinator import MaintenanceCoordinator
from .history_export import async_setup_history_export, async_unload_history_export
from .notifications import async_setup_notifications
from .task_manager import TaskManager


async def async_setup(hass, config):
    await async_setup_history_export(hass)
    return True


async def async_setup_entry(hass, entry):
    enabled_task_ids = entry.options.get(
        CONF_ENABLED_TASK_IDS,
        entry.data.get(CONF_ENABLED_TASK_IDS, []),
    )
    task_intervals = entry.options.get("task_intervals", {})
    custom_tasks = entry.options.get("custom_tasks", [])
    equipment_records = entry.options.get("equipment_records", [])
    manager = TaskManager(
        hass,
        entry.entry_id,
        enabled_task_ids,
        task_intervals,
        custom_tasks,
        equipment_records,
    )
    await manager.async_load()

    coordinator = MaintenanceCoordinator(hass, manager)
    await coordinator.async_config_entry_first_refresh()

    cancel_notifications = await async_setup_notifications(hass, entry, manager)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "manager": manager,
        "coordinator": coordinator,
        "cancel_notifications": cancel_notifications,
        "property_name": entry.data.get("property_name", entry.title),
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_completion_service(hass)

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    entry.async_on_unload(cancel_notifications)
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            await async_unload_history_export(hass)
            await async_unload_completion_service(hass)
    return unload_ok
