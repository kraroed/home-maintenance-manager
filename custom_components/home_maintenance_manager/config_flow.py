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
                return self.async_show_form(step_id="user", data_schema=self._schema(), errors={"base": "invalid_name"})
            await self.async_set_unique_id(property_name.casefold())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=property_name, data={CONF_PROPERTY_NAME: property_name, CONF_ENABLED_TASK_IDS: user_input.get(CONF_ENABLED_TASK_IDS, [])})
        return self.async_show_form(step_id="user", data_schema=self._schema())

    @staticmethod
    def _schema():
        options = [(task_id, item["name"]) for task_id, item in load_library().items()]
        return vol.Schema({vol.Required(CONF_PROPERTY_NAME, default="My Home"): str, vol.Optional(CONF_ENABLED_TASK_IDS, default=[]): cv.multi_select(options)})

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeMaintenanceOptionsFlow(config_entry)


class HomeMaintenanceOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._selected_task_ids = []

    async def async_step_init(self, user_input=None):
        library = load_library()
        selected = self.config_entry.options.get(CONF_ENABLED_TASK_IDS, self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []))
        if user_input is not None:
            self._selected_task_ids = user_input.get(CONF_ENABLED_TASK_IDS, [])
            return await self.async_step_intervals()
        options = [(task_id, item["name"]) for task_id, item in library.items()]
        schema = vol.Schema({vol.Optional(CONF_ENABLED_TASK_IDS, default=selected): cv.multi_select(options)})
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_intervals(self, user_input=None):
        library = load_library()
        existing = self.config_entry.options.get("task_intervals", {})
        selected = [task_id for task_id in self._selected_task_ids if task_id in library and library[task_id].get("schedule_type") == "interval"]
        if user_input is not None:
            intervals = dict(existing)
            intervals.update({task_id: user_input[f"interval_{task_id}"] for task_id in selected if f"interval_{task_id}" in user_input})
            return self.async_create_entry(title="", data={CONF_ENABLED_TASK_IDS: self._selected_task_ids, "task_intervals": intervals})
        fields = {}
        for task_id in selected:
            default = existing.get(task_id, library[task_id].get("recommended_interval_days", 30))
            fields[vol.Required(f"interval_{task_id}", default=int(default))] = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))
        if not fields:
            return self.async_create_entry(title="", data={CONF_ENABLED_TASK_IDS: self._selected_task_ids, "task_intervals": {}})
        return self.async_show_form(step_id="intervals", data_schema=vol.Schema(fields))
