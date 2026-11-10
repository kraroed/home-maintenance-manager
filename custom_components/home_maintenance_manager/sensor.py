from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import entity_registry as er
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
        self.integration_instance = coordinator.manager.storage.store.key

    @property
    def extra_state_attributes(self):
        return {
            "summary_key": self.value_key,
            "integration_domain": DOMAIN,
            "integration_instance": self.integration_instance,
        }

    @property
    def native_value(self):
        return self.coordinator.data.get(self.value_key, 0)


class TaskStatusSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, task_id, name):
        super().__init__(coordinator)
        self.task_id = task_id
        self.integration_instance = coordinator.manager.storage.store.key
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
            "enabled": task.get("enabled", True),
            "integration_domain": DOMAIN,
            "integration_instance": self.integration_instance,
            "category": task.get("category"),
            "description": task.get("description"),
            "how_to_inspect": task.get("how_to_inspect", []),
            "what_to_look_for": task.get("what_to_look_for", []),
            "what_to_do_if_issue": task.get("what_to_do_if_issue", ""),
            "safety_notes": task.get("safety_notes", ""),
            "schedule_type": task.get("schedule_type"),
            "season_keys": task.get("season_keys", []),
            "annual_month": task.get("annual_month"),
            "annual_day": task.get("annual_day"),
            "monthly_week": task.get("monthly_week"),
            "monthly_weekday": task.get("monthly_weekday"),
            "recommended_interval_days": task.get("recommended_interval_days"),
            "configured_interval_days": task.get("configured_interval_days"),
            "last_completed": task.get("last_completed"),
            "next_due": task.get("next_due"),
            "equipment_id": task.get("equipment_id"),
            "equipment_ids": task.get("equipment_ids", []),
            "completion_history": self.coordinator.data.get("history_by_task", {}).get(
                self.task_id, []
            ),
            "schedule_history": task.get("schedule_history", [])[-10:],
        }


class EquipmentSensor(CoordinatorEntity, SensorEntity):
    CATEGORY_ICONS = {
        "HVAC": "mdi:hvac",
        "Plumbing": "mdi:water-pump",
        "Electrical": "mdi:lightning-bolt",
        "Appliances": "mdi:washing-machine",
        "Water heating": "mdi:water-boiler",
        "Safety and security": "mdi:shield-home",
        "Roofing": "mdi:home-roof",
        "Windows and doors": "mdi:door",
        "Structure": "mdi:home-variant",
        "Outdoor": "mdi:tree",
        "Pool and spa": "mdi:pool",
        "Other": "mdi:tools",
    }

    def __init__(self, coordinator, equipment_id, name):
        super().__init__(coordinator)
        self.equipment_id = equipment_id
        self.integration_instance = coordinator.manager.storage.store.key
        self._attr_unique_id = f"{coordinator.manager.storage.store.key}_{equipment_id}"
        self._attr_name = f"{name} Equipment"
        item = next(
            (record for record in coordinator.data.get("equipment", [])
             if record.get("equipment_id") == equipment_id),
            {},
        )
        self._attr_icon = "mdi:tools"

    def _equipment(self):
        return next(
            (item for item in self.coordinator.data.get("equipment", [])
             if item["equipment_id"] == self.equipment_id),
            None,
        )

    async def async_added_to_hass(self):
        """Apply the configured Home Assistant area to this equipment entity."""
        await super().async_added_to_hass()
        item = self._equipment()
        if item is None:
            return
        area_id = item.get("area_id") or None
        registry = er.async_get(self.hass)
        registry_entry = registry.async_get(self.entity_id)
        if registry_entry and registry_entry.area_id != area_id:
            registry.async_update_entity(self.entity_id, area_id=area_id)

    @property
    def icon(self):
        """Return an icon representing the equipment category."""
        item = self._equipment()
        if item is None:
            return "mdi:tools"
        return item.get("category_icon") or self.CATEGORY_ICONS.get(
            item.get("category"), "mdi:tools"
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
            "equipment_id": self.equipment_id,
            "integration_domain": DOMAIN,
            "integration_instance": self.integration_instance,
            "category_icon": item.get("category_icon") or self.CATEGORY_ICONS.get(
                item.get("category"), "mdi:tools"
            ),
            **{
                key: item.get(key)
                for key in (
                    "category", "area_id", "manufacturer", "model", "installed_date",
                    "lifespan_months", "replacement_task_id", "replacement_due",
                    "notes", "task_ids",
                )
            },
        }
