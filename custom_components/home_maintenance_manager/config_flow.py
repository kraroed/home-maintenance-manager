import re

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENABLED_TASK_IDS, CONF_PROPERTY_NAME, DOMAIN
from .task_manager import load_library


class HomeMaintenanceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            property_name = user_input[CONF_PROPERTY_NAME].strip()
            if not property_name:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(),
                    errors={"base": "invalid_name"},
                )
            await self.async_set_unique_id(property_name.casefold())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=property_name,
                data={
                    CONF_PROPERTY_NAME: property_name,
                    CONF_ENABLED_TASK_IDS: user_input.get(CONF_ENABLED_TASK_IDS, []),
                },
            )
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema():
        options = [(task_id, item["name"]) for task_id, item in load_library().items()]
        return vol.Schema({
            vol.Required(CONF_PROPERTY_NAME, default="My Home"): str,
            vol.Optional(CONF_ENABLED_TASK_IDS, default=[]): cv.multi_select(options),
        })

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeMaintenanceOptionsFlow(config_entry)


class HomeMaintenanceOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._selected_task_ids = []

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["manage_tasks", "add_custom_task", "add_equipment"],
        )

    async def async_step_manage_tasks(self, user_input=None):
        library = load_library()
        library.update({
            item["task_id"]: item
            for item in self.config_entry.options.get("custom_tasks", [])
        })
        selected = self.config_entry.options.get(
            CONF_ENABLED_TASK_IDS,
            self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []),
        )
        if user_input is not None:
            self._selected_task_ids = user_input.get(CONF_ENABLED_TASK_IDS, [])
            return await self.async_step_intervals()

        options = [(task_id, item["name"]) for task_id, item in library.items()]
        schema = vol.Schema({
            vol.Optional(CONF_ENABLED_TASK_IDS, default=selected): cv.multi_select(options),
        })
        return self.async_show_form(step_id="manage_tasks", data_schema=schema)

    async def async_step_intervals(self, user_input=None):
        library = load_library()
        library.update({
            item["task_id"]: item
            for item in self.config_entry.options.get("custom_tasks", [])
        })
        existing = self.config_entry.options.get("task_intervals", {})
        selected = [
            task_id for task_id in self._selected_task_ids
            if task_id in library
            and library[task_id].get("schedule_type") == "interval"
            and not library[task_id].get("is_custom")
        ]
        if user_input is not None:
            intervals = dict(existing)
            intervals.update({
                task_id: user_input[f"interval_{task_id}"]
                for task_id in selected if f"interval_{task_id}" in user_input
            })
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_ENABLED_TASK_IDS: self._selected_task_ids,
                    "task_intervals": intervals,
                },
            )

        fields = {}
        for task_id in selected:
            default = existing.get(
                task_id, library[task_id].get("recommended_interval_days", 30)
            )
            fields[vol.Required(
                f"interval_{task_id}", default=int(default)
            )] = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))

        if not fields:
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_ENABLED_TASK_IDS: self._selected_task_ids,
                    "task_intervals": existing,
                },
            )
        return self.async_show_form(
            step_id="intervals",
            data_schema=vol.Schema(fields),
        )

    async def async_step_add_custom_task(self, user_input=None):
        if user_input is not None:
            name = user_input["name"].strip()
            slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
            task_id = f"custom_{slug}"
            existing_tasks = self.config_entry.options.get("custom_tasks", [])
            all_ids = set(load_library()) | {
                task["task_id"] for task in existing_tasks
            }
            if not slug or task_id in all_ids:
                return self.async_show_form(
                    step_id="add_custom_task",
                    data_schema=self._custom_task_schema(),
                    errors={"base": "duplicate_task"},
                )

            interval = int(user_input["interval_days"])
            custom_task = {
                "task_id": task_id,
                "name": name,
                "category": user_input["category"].strip().casefold() or "custom",
                "description": user_input.get("description", "").strip(),
                "schedule_type": "interval",
                "recommended_interval_days": interval,
                "priority": "normal",
                "requires_equipment": False,
                "recommendation_note": "Custom task created by the user.",
                "is_custom": True,
            }
            enabled = list(self.config_entry.options.get(
                CONF_ENABLED_TASK_IDS,
                self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []),
            ))
            if task_id not in enabled:
                enabled.append(task_id)

            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    CONF_ENABLED_TASK_IDS: enabled,
                    "custom_tasks": [*existing_tasks, custom_task],
                    "task_intervals": {
                        **self.config_entry.options.get("task_intervals", {}),
                        task_id: interval,
                    },
                },
            )

        return self.async_show_form(
            step_id="add_custom_task",
            data_schema=self._custom_task_schema(),
        )

    async def async_step_add_equipment(self, user_input=None):
        library = load_library()
        library.update({
            item["task_id"]: item
            for item in self.config_entry.options.get("custom_tasks", [])
        })
        enabled = self.config_entry.options.get(
            CONF_ENABLED_TASK_IDS,
            self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []),
        )
        task_options = [
            (task_id, library[task_id]["name"])
            for task_id in enabled if task_id in library
        ]
        if user_input is not None:
            name = user_input["name"].strip()
            slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
            equipment_id = f"equipment_{slug}"
            equipment = list(self.config_entry.options.get("equipment_records", []))
            if not slug or any(item["equipment_id"] == equipment_id for item in equipment):
                return self.async_show_form(
                    step_id="add_equipment",
                    data_schema=self._equipment_schema(task_options),
                    errors={"base": "duplicate_equipment"},
                )
            equipment.append({
                "equipment_id": equipment_id,
                "name": name,
                "category": user_input["category"].strip(),
                "manufacturer": user_input.get("manufacturer", "").strip(),
                "model": user_input.get("model", "").strip(),
                "installed_date": user_input.get("installed_date", "").strip(),
                "notes": user_input.get("notes", "").strip(),
                "task_ids": user_input.get("task_ids", []),
            })
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, "equipment_records": equipment},
            )

        return self.async_show_form(
            step_id="add_equipment",
            data_schema=self._equipment_schema(task_options),
        )

    @staticmethod
    def _custom_task_schema():
        return vol.Schema({
            vol.Required("name"): vol.All(str, vol.Length(min=1, max=80)),
            vol.Required("category", default="general"): vol.All(
                str, vol.Length(min=1, max=40)
            ),
            vol.Optional("description", default=""): vol.All(
                str, vol.Length(max=300)
            ),
            vol.Required("interval_days", default=90): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=3650)
            ),
        })

    @staticmethod
    def _equipment_schema(task_options):
        return vol.Schema({
            vol.Required("name"): vol.All(str, vol.Length(min=1, max=80)),
            vol.Required("category", default="HVAC"): vol.All(
                str, vol.Length(min=1, max=40)
            ),
            vol.Optional("manufacturer", default=""): vol.All(str, vol.Length(max=80)),
            vol.Optional("model", default=""): vol.All(str, vol.Length(max=80)),
            vol.Optional("installed_date", default=""): vol.All(str, vol.Length(max=10)),
            vol.Optional("notes", default=""): vol.All(str, vol.Length(max=500)),
            vol.Optional("task_ids", default=[]): cv.multi_select(task_options),
        })
