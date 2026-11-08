from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    manager = data["manager"]

    entities = [
        SummarySensor(coordinator, "total", "Total tasks", "total"),
        SummarySensor(coordinator, "overdue", "Overdue tasks", "overdue"),
        SummarySensor(coordinator, "due_today", "Tasks due today", "due_today"),
        SummarySensor(coordinator, "due_soon", "Tasks due soon", "due_soon"),
        SummarySensor(coordinator, "history_count", "Completion history records", "history_count"),
        SummarySensor(coordinator, "equipment_count", "Equipment records", "equipment_count"),
    ]
    entities.extend(
        TaskStatusSensor(coordinator, task["task_id"], task["name"])
        for task in manager.data["tasks"].values()
    )
    entities.extend(
        EquipmentSensor(coordinator, item["equipment_id"], item["name"])
        for item in manager.data.get("equipment", {}).values()
    )
    async_add_entities(entities)


class SummarySensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, key, name, value_key):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.manager.storage.store.key}_{key}"
        self._attr_name = name
        self.value_key = value_key

    @property
    def native_value(self):
        return self.coordinator.data.get(self.value_key, 0)


class TaskStatusSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, task_id, name):
        super().__init__(coordinator)
        self.task_id = task_id
        self._attr_unique_id = f"{coordinator.manager.storage.store.key}_{task_id}_status"
        self._attr_name = f"{name} Status"
        self._attr_icon = "mdi:home-wrench"

    def _task(self):
        return next(
            (task for task in self.coordinator.data["tasks"] if task["task_id"] == self.task_id),
            None,
        )

    @property
    def native_value(self):
        task = self._task()
        return task["status"] if task else "unavailable"

    @property
    def extra_state_attributes(self):
        task = self._task()
        if task is None:
            return {}
        return {
            "task_id": task["task_id"],
            "category": task.get("category"),
            "description": task.get("description"),
            "schedule_type": task.get("schedule_type"),
            "season_keys": task.get("season_keys", []),
            "recommended_interval_days": task.get("recommended_interval_days"),
            "configured_interval_days": task.get("configured_interval_days"),
            "last_completed": task.get("last_completed"),
            "next_due": task.get("next_due"),
            "equipment_id": task.get("equipment_id"),
            "equipment_ids": task.get("equipment_ids", []),
        }


class EquipmentSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, equipment_id, name):
        super().__init__(coordinator)
        self.equipment_id = equipment_id
        self._attr_unique_id = f"{coordinator.manager.storage.store.key}_{equipment_id}"
        self._attr_name = f"{name} Equipment"
        self._attr_icon = "mdi:tools"

    def _equipment(self):
        return next(
            (item for item in self.coordinator.data.get("equipment", [])
             if item["equipment_id"] == self.equipment_id),
            None,
        )

    @property
    def native_value(self):
        item = self._equipment()
        return item.get("name") if item else "unavailable"

    @property
    def extra_state_attributes(self):
        item = self._equipment()
        if item is None:
            return {}
        return {
            key: item.get(key)
            for key in ("category", "manufacturer", "model", "installed_date", "notes", "task_ids")
        }
