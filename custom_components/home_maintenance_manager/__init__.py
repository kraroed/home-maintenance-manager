from .const import CONF_ENABLED_TASK_IDS, DOMAIN, PLATFORMS
from .coordinator import MaintenanceCoordinator
from .task_manager import TaskManager


async def async_setup_entry(hass, entry):
    manager = TaskManager(
        hass,
        entry.entry_id,
        entry.data.get(CONF_ENABLED_TASK_IDS, []),
    )
    await manager.async_load()

    coordinator = MaintenanceCoordinator(hass, manager)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "manager": manager,
        "coordinator": coordinator,
    }
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        entry.add_update_listener(async_reload_entry)
    )
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
