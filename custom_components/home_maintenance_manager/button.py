from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    manager = data["manager"]
    async_add_entities([
        CompleteTaskButton(coordinator, task["task_id"], task["name"])
        for task in manager.data["tasks"].values()
    ])


class CompleteTaskButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, task_id, name):
        super().__init__(coordinator)
        self.task_id = task_id
        self._attr_unique_id = (
            f"{coordinator.manager.storage.store.key}_{task_id}_complete"
        )
        self._attr_name = f"{name} Mark Complete"
        self._attr_icon = "mdi:check-circle"

    @property
    def available(self):
        task = self.coordinator.manager.data["tasks"].get(self.task_id)
        return super().available and bool(task and task.get("enabled", True))

    @property
    def extra_state_attributes(self):
        return {"task_id": self.task_id}

    async def async_press(self):
        await self.coordinator.manager.async_complete_task(self.task_id)
        await self.coordinator.async_request_refresh()
