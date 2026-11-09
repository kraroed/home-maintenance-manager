import re
from datetime import date

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENABLED_TASK_IDS, CONF_PROPERTY_NAME, DOMAIN
from .task_manager import load_library


def _validate_month_day(value):
    """Validate a canonical MM-DD date, including leap day."""
    if not isinstance(value, str) or len(value) != 5:
        raise vol.Invalid("Enter a valid date as MM-DD.")
    try:
        parsed = date(2000, int(value[:2]), int(value[3:]))
    except ValueError as err:
        raise vol.Invalid("Enter a valid date as MM-DD.") from err
    if parsed.strftime("%m-%d") != value:
        raise vol.Invalid("Enter a valid date as MM-DD.")
    return value


def _validate_optional_iso_date(value):
    """Accept an empty equipment date or a real canonical YYYY-MM-DD date."""
    if not value:
        return value
    try:
        parsed = date.fromisoformat(value)
    except ValueError as err:
        raise vol.Invalid("Enter a valid date as YYYY-MM-DD.") from err
    if parsed.isoformat() != value:
        raise vol.Invalid("Enter a valid date as YYYY-MM-DD.")
    return value


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
            vol.Optional(CONF_ENABLED_TASK_IDS, default=[]): cv.multi_select(dict(options)),
        })

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return HomeMaintenanceOptionsFlow(config_entry)


class HomeMaintenanceOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._config_entry = config_entry
        self._selected_task_ids = []

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["manage_tasks", "add_custom_task", "manage_custom_tasks", "add_equipment", "manage_equipment", "configure_notifications", "configure_season_windows"],
        )

    async def async_step_configure_notifications(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "individual_notifications_enabled": user_input["individual_notifications_enabled"],
                    "daily_summary_enabled": user_input["daily_summary_enabled"],
                    "notification_target": user_input.get("notification_target", "").strip(),
                    "notification_lead_days": user_input["notification_lead_days"],
                    "daily_summary_time": user_input["daily_summary_time"],
                },
            )

        options = self.config_entry.options
        schema = vol.Schema({
            vol.Optional(
                "individual_notifications_enabled",
                default=options.get("individual_notifications_enabled", True),
            ): bool,
            vol.Optional(
                "daily_summary_enabled",
                default=options.get("daily_summary_enabled", True),
            ): bool,
            vol.Optional(
                "notification_target",
                default=options.get("notification_target", ""),
            ): vol.All(str, vol.Length(max=255)),
            vol.Required(
                "notification_lead_days",
                default=options.get("notification_lead_days", 7),
            ): vol.All(vol.Coerce(int), vol.Range(min=0, max=90)),
            vol.Required(
                "daily_summary_time",
                default=options.get("daily_summary_time", "08:00"),
            ): vol.Match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$"),
        })
        return self.async_show_form(
            step_id="configure_notifications",
            data_schema=schema,
        )

    async def async_step_configure_season_windows(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "season_windows": {
                        season: {
                            "start": user_input[f"{season}_start"],
                            "end": user_input[f"{season}_end"],
                        }
                        for season in ("spring", "summer", "fall", "winter")
                    },
                },
            )

        defaults = {
            "spring": {"start": "03-15", "end": "05-31"},
            "summer": {"start": "06-01", "end": "08-31"},
            "fall": {"start": "09-01", "end": "11-15"},
            "winter": {"start": "11-16", "end": "03-14"},
        }
        configured = self.config_entry.options.get("season_windows", {})
        fields = {}
        for season, window in defaults.items():
            current = configured.get(season, window)
            fields[vol.Required(
                f"{season}_start", default=current.get("start", window["start"])
            )] = vol.All(str, _validate_month_day)
            fields[vol.Required(
                f"{season}_end", default=current.get("end", window["end"])
            )] = vol.All(str, _validate_month_day)
        return self.async_show_form(
            step_id="configure_season_windows",
            data_schema=vol.Schema(fields),
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
                    data_schema=self._custom_task_schema(user_input),
                    errors={"base": "duplicate_task"},
                )

            schedule_type = user_input["schedule_type"]
            interval = int(user_input["interval_days"])
            annual_month = int(user_input["annual_month"])
            annual_day = int(user_input["annual_day"])
            monthly_week = user_input["monthly_week"]
            monthly_weekday = int(user_input["monthly_weekday"])
            if schedule_type == "annual":
                try:
                    date(2000, annual_month, annual_day)
                except ValueError:
                    return self.async_show_form(
                        step_id="add_custom_task",
                        data_schema=self._custom_task_schema(user_input),
                        errors={"base": "invalid_annual_date"},
                    )
            custom_task = {
                "task_id": task_id,
                "name": name,
                "category": user_input["category"].strip().casefold() or "custom",
                "description": user_input.get("description", "").strip(),
                "schedule_type": schedule_type,
                "recommended_interval_days": interval,
                **(
                    {"annual_month": annual_month, "annual_day": annual_day}
                    if schedule_type == "annual" else {}
                ),
                **(
                    {"monthly_week": monthly_week, "monthly_weekday": monthly_weekday}
                    if schedule_type == "monthly" else {}
                ),
                "priority": "normal",
                "requires_equipment": False,
                "recommendation_note": "Custom task created by the user.",
                "how_to_inspect": [line.strip() for line in user_input.get("how_to_inspect", "").splitlines() if line.strip()],
                "what_to_look_for": [line.strip() for line in user_input.get("what_to_look_for", "").splitlines() if line.strip()],
                "what_to_do_if_issue": user_input.get("what_to_do_if_issue", "").strip(),
                "safety_notes": user_input.get("safety_notes", "").strip(),
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
                        **{
                            key: value
                            for key, value in self.config_entry.options.get(
                                "task_intervals", {}
                            ).items()
                            if key != task_id
                        },
                        **({task_id: interval} if schedule_type == "interval" else {}),
                    },
                },
            )

        return self.async_show_form(
            step_id="add_custom_task",
            data_schema=self._custom_task_schema(),
        )

    async def async_step_manage_custom_tasks(self, user_input=None):
        custom_tasks = self.config_entry.options.get("custom_tasks", [])
        if not custom_tasks:
            return self.async_abort(reason="no_custom_tasks")
        if user_input is not None:
            self._selected_custom_task_id = user_input["task_id"]
            return self.async_show_menu(
                step_id="custom_task_actions",
                menu_options=["edit_custom_task", "remove_custom_task"],
            )
        options = [(item["task_id"], item["name"]) for item in custom_tasks]
        return self.async_show_form(
            step_id="manage_custom_tasks",
            data_schema=vol.Schema({
                vol.Required("task_id"): vol.In(dict(options)),
            }),
        )

    async def async_step_custom_task_actions(self, user_input=None):
        return self.async_show_menu(
            step_id="custom_task_actions",
            menu_options=["edit_custom_task", "remove_custom_task"],
        )

    async def async_step_edit_custom_task(self, user_input=None):
        custom_tasks = list(self.config_entry.options.get("custom_tasks", []))
        current = next(
            (item for item in custom_tasks
             if item["task_id"] == getattr(self, "_selected_custom_task_id", None)),
            None,
        )
        if current is None:
            return self.async_abort(reason="custom_task_not_found")
        if user_input is not None:
            name = user_input["name"].strip()
            slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
            proposed_id = f"custom_{slug}"
            if not slug or (
                proposed_id != current["task_id"]
                and (proposed_id in load_library()
                     or any(item["task_id"] == proposed_id for item in custom_tasks))
            ):
                return self.async_show_form(
                    step_id="edit_custom_task",
                    data_schema=self._custom_task_schema({**current, **user_input}),
                    errors={"base": "duplicate_task"},
                )
            # Keep the ID stable so existing task state and completion history
            # remain attached to this custom task when its display name changes.
            schedule_type = user_input["schedule_type"]
            interval = int(user_input["interval_days"])
            annual_month = int(user_input["annual_month"])
            annual_day = int(user_input["annual_day"])
            monthly_week = user_input["monthly_week"]
            monthly_weekday = int(user_input["monthly_weekday"])
            if schedule_type == "annual":
                try:
                    date(2000, annual_month, annual_day)
                except ValueError:
                    return self.async_show_form(
                        step_id="edit_custom_task",
                        data_schema=self._custom_task_schema({**current, **user_input}),
                        errors={"base": "invalid_annual_date"},
                    )
            replacement_task_id = user_input.get("replacement_task_id") or ""
            lifespan_months = int(user_input.get("lifespan_months", 0) or 0)
            if len({bool(lifespan_months), bool(replacement_task_id), bool(user_input.get("installed_date", "").strip())}) != 1:
                return self.async_show_form(
                    step_id="edit_equipment",
                    data_schema=self._equipment_schema(task_options, current),
                    errors={"base": "incomplete_lifespan"},
                )
            if replacement_task_id and any(
                item.get("equipment_id") != current["equipment_id"]
                and item.get("replacement_task_id") == replacement_task_id
                for item in equipment
            ):
                return self.async_show_form(
                    step_id="edit_equipment",
                    data_schema=self._equipment_schema(task_options, current),
                    errors={"base": "duplicate_replacement_task"},
                )
            task_ids = list(user_input.get("task_ids", []))
            if replacement_task_id and replacement_task_id not in task_ids:
                task_ids.append(replacement_task_id)
            updated = {
                **current,
                "name": name,
                "category": user_input["category"].strip().casefold() or "custom",
                "description": user_input.get("description", "").strip(),
                "schedule_type": schedule_type,
                "how_to_inspect": [line.strip() for line in user_input.get("how_to_inspect", "").splitlines() if line.strip()],
                "what_to_look_for": [line.strip() for line in user_input.get("what_to_look_for", "").splitlines() if line.strip()],
                "what_to_do_if_issue": user_input.get("what_to_do_if_issue", "").strip(),
                "safety_notes": user_input.get("safety_notes", "").strip(),
                "recommended_interval_days": interval,
            }
            if schedule_type == "annual":
                updated["annual_month"] = annual_month
                updated["annual_day"] = annual_day
            else:
                updated.pop("annual_month", None)
                updated.pop("annual_day", None)
            if schedule_type == "monthly":
                updated["monthly_week"] = monthly_week
                updated["monthly_weekday"] = monthly_weekday
            else:
                updated.pop("monthly_week", None)
                updated.pop("monthly_weekday", None)
            custom_tasks = [
                updated if item["task_id"] == current["task_id"] else item
                for item in custom_tasks
            ]
            intervals = dict(self.config_entry.options.get("task_intervals", {}))
            if schedule_type == "interval":
                intervals[current["task_id"]] = interval
            else:
                intervals.pop(current["task_id"], None)
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "custom_tasks": custom_tasks,
                    "task_intervals": intervals,
                },
            )
        return self.async_show_form(
            step_id="edit_custom_task",
            data_schema=self._custom_task_schema(current),
        )

    async def async_step_remove_custom_task(self, user_input=None):
        custom_tasks = list(self.config_entry.options.get("custom_tasks", []))
        current = next(
            (item for item in custom_tasks
             if item["task_id"] == getattr(self, "_selected_custom_task_id", None)),
            None,
        )
        if current is None:
            return self.async_abort(reason="custom_task_not_found")
        if user_input is not None:
            if not user_input.get("confirm"):
                return self.async_abort(reason="remove_cancelled")
            custom_tasks = [
                item for item in custom_tasks
                if item["task_id"] != current["task_id"]
            ]
            enabled = list(self.config_entry.options.get(
                CONF_ENABLED_TASK_IDS,
                self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []),
            ))
            enabled = [task_id for task_id in enabled if task_id != current["task_id"]]
            intervals = dict(self.config_entry.options.get("task_intervals", {}))
            intervals.pop(current["task_id"], None)
            equipment = [
                {
                    **item,
                    "task_ids": [
                        task_id for task_id in item.get("task_ids", [])
                        if task_id != current["task_id"]
                    ],
                }
                for item in self.config_entry.options.get("equipment_records", [])
            ]
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "custom_tasks": custom_tasks,
                    CONF_ENABLED_TASK_IDS: enabled,
                    "task_intervals": intervals,
                    "equipment_records": equipment,
                },
            )
        return self.async_show_form(
            step_id="remove_custom_task",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={"task_name": current["name"]},
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
            try:
                _validate_optional_iso_date(user_input.get("installed_date", "").strip())
            except vol.Invalid:
                return self.async_show_form(
                    step_id="add_equipment",
                    data_schema=self._equipment_schema(task_options),
                    errors={"installed_date": "invalid_date"},
                )
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
            replacement_task_id = user_input.get("replacement_task_id") or ""
            lifespan_months = int(user_input.get("lifespan_months", 0) or 0)
            if bool(lifespan_months) != bool(replacement_task_id and user_input.get("installed_date", "").strip()):
                return self.async_show_form(
                    step_id="add_equipment",
                    data_schema=self._equipment_schema(task_options),
                    errors={"base": "incomplete_lifespan"},
                )
            if replacement_task_id and any(
                item.get("replacement_task_id") == replacement_task_id
                for item in equipment
            ):
                return self.async_show_form(
                    step_id="add_equipment",
                    data_schema=self._equipment_schema(task_options),
                    errors={"base": "duplicate_replacement_task"},
                )
            task_ids = list(user_input.get("task_ids", []))
            if replacement_task_id and replacement_task_id not in task_ids:
                task_ids.append(replacement_task_id)
            equipment.append({
                "equipment_id": equipment_id,
                "name": name,
                "category": user_input["category"].strip(),
                "manufacturer": user_input.get("manufacturer", "").strip(),
                "model": user_input.get("model", "").strip(),
                "installed_date": user_input.get("installed_date", "").strip(),
                "lifespan_months": lifespan_months,
                "replacement_task_id": replacement_task_id or None,
                "notes": user_input.get("notes", "").strip(),
                "task_ids": task_ids,
            })
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, "equipment_records": equipment},
            )

        return self.async_show_form(
            step_id="add_equipment",
            data_schema=self._equipment_schema(task_options),
        )

    async def async_step_manage_equipment(self, user_input=None):
        equipment = self.config_entry.options.get("equipment_records", [])
        if not equipment:
            return self.async_abort(reason="no_equipment")
        if user_input is not None:
            self._selected_equipment_id = user_input["equipment_id"]
            return self.async_show_menu(
                step_id="equipment_actions",
                menu_options=["edit_equipment", "remove_equipment"],
            )
        options = [(item["equipment_id"], item["name"]) for item in equipment]
        return self.async_show_form(
            step_id="manage_equipment",
            data_schema=vol.Schema({
                vol.Required("equipment_id"): vol.In(dict(options)),
            }),
        )

    async def async_step_equipment_actions(self, user_input=None):
        return self.async_show_menu(
            step_id="equipment_actions",
            menu_options=["edit_equipment", "remove_equipment"],
        )

    async def async_step_edit_equipment(self, user_input=None):
        equipment = list(self.config_entry.options.get("equipment_records", []))
        current = next(
            (item for item in equipment
             if item["equipment_id"] == getattr(self, "_selected_equipment_id", None)),
            None,
        )
        if current is None:
            return self.async_abort(reason="equipment_not_found")

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
            try:
                _validate_optional_iso_date(user_input.get("installed_date", "").strip())
            except vol.Invalid:
                return self.async_show_form(
                    step_id="edit_equipment",
                    data_schema=self._equipment_schema(task_options, current),
                    errors={"installed_date": "invalid_date"},
                )
            updated = {
                **current,
                "name": user_input["name"].strip(),
                "category": user_input["category"].strip(),
                "manufacturer": user_input.get("manufacturer", "").strip(),
                "model": user_input.get("model", "").strip(),
                "installed_date": user_input.get("installed_date", "").strip(),
                "lifespan_months": lifespan_months,
                "replacement_task_id": replacement_task_id or None,
                "notes": user_input.get("notes", "").strip(),
                "task_ids": task_ids,
            }
            equipment = [
                updated if item["equipment_id"] == current["equipment_id"] else item
                for item in equipment
            ]
            return self.async_create_entry(
                title="",
                data={**self.config_entry.options, "equipment_records": equipment},
            )

        schema = self._equipment_schema(task_options, current)
        return self.async_show_form(step_id="edit_equipment", data_schema=schema)

    async def async_step_remove_equipment(self, user_input=None):
        equipment = list(self.config_entry.options.get("equipment_records", []))
        current = next(
            (item for item in equipment
             if item["equipment_id"] == getattr(self, "_selected_equipment_id", None)),
            None,
        )
        if current is None:
            return self.async_abort(reason="equipment_not_found")
        if user_input is not None:
            if user_input.get("confirm"):
                equipment = [
                    item for item in equipment
                    if item["equipment_id"] != current["equipment_id"]
                ]
                return self.async_create_entry(
                    title="",
                    data={**self.config_entry.options, "equipment_records": equipment},
                )
            return self.async_abort(reason="remove_cancelled")
        return self.async_show_form(
            step_id="remove_equipment",
            data_schema=vol.Schema({
                vol.Required("confirm", default=False): bool,
            }),
            description_placeholders={"equipment_name": current["name"]},
        )

    @staticmethod
    def _custom_task_schema(current=None):
        current = current or {}
        how_to_inspect = current.get("how_to_inspect", [])
        what_to_look_for = current.get("what_to_look_for", [])
        if isinstance(how_to_inspect, list):
            how_to_inspect = "\n".join(how_to_inspect)
        if isinstance(what_to_look_for, list):
            what_to_look_for = "\n".join(what_to_look_for)
        return vol.Schema({
            vol.Required("name", default=current.get("name", "")): vol.All(
                str, vol.Length(min=1, max=80)
            ),
            vol.Required("category", default=current.get("category", "general")): vol.All(
                str, vol.Length(min=1, max=40)
            ),
            vol.Optional("description", default=current.get("description", "")): vol.All(
                str, vol.Length(max=300)
            ),
            vol.Optional("how_to_inspect", default=how_to_inspect): vol.All(str, vol.Length(max=1200)),
            vol.Optional("what_to_look_for", default=what_to_look_for): vol.All(str, vol.Length(max=1200)),
            vol.Optional("what_to_do_if_issue", default=current.get("what_to_do_if_issue", "")): vol.All(str, vol.Length(max=600)),
            vol.Optional("safety_notes", default=current.get("safety_notes", "")): vol.All(str, vol.Length(max=600)),
            vol.Required(
                "schedule_type",
                default=current.get("schedule_type", "interval"),
            ): vol.In({
                "interval": "Repeat by interval",
                "annual": "Repeat annually on a calendar date",
                "monthly": "Repeat monthly on a weekday pattern",
            }),
            vol.Required(
                "interval_days",
                default=current.get("recommended_interval_days", 90),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)),
            vol.Required(
                "annual_month",
                default=current.get("annual_month", 1),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
            vol.Required(
                "annual_day",
                default=current.get("annual_day", 1),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
            vol.Required(
                "monthly_week",
                default=current.get("monthly_week", "first"),
            ): vol.In({
                "first": "First",
                "second": "Second",
                "third": "Third",
                "fourth": "Fourth",
                "last": "Last",
            }),
            vol.Required(
                "monthly_weekday",
                default=current.get("monthly_weekday", 5),
            ): vol.In({
                0: "Monday",
                1: "Tuesday",
                2: "Wednesday",
                3: "Thursday",
                4: "Friday",
                5: "Saturday",
                6: "Sunday",
            }),
        })

    @staticmethod
    def _equipment_schema(task_options, current=None):
        current = current or {}
        return vol.Schema({
            vol.Required("name", default=current.get("name", "")): vol.All(
                str, vol.Length(min=1, max=80)
            ),
            vol.Required("category", default=current.get("category", "HVAC")): vol.All(
                str, vol.Length(min=1, max=40)
            ),
            vol.Optional("manufacturer", default=current.get("manufacturer", "")): vol.All(
                str, vol.Length(max=80)
            ),
            vol.Optional("model", default=current.get("model", "")): vol.All(
                str, vol.Length(max=80)
            ),
            vol.Optional("installed_date", default=current.get("installed_date", "")): vol.All(
                str, vol.Length(max=10), vol.Match(r"^$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
            ),
            vol.Optional("lifespan_months", default=current.get("lifespan_months", 0)): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=1200)
            ),
            vol.Optional(
                "replacement_task_id",
                default=current.get("replacement_task_id") or "",
            ): vol.In({"": "None", **dict(task_options)}),
            vol.Optional("notes", default=current.get("notes", "")): vol.All(
                str, vol.Length(max=500)
            ),
            vol.Optional("task_ids", default=current.get("task_ids", [])): cv.multi_select(
                dict(task_options)
            ),
        })
