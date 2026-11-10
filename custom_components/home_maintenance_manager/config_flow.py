import re
from datetime import date

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import CONF_ENABLED_TASK_IDS, CONF_PROPERTY_NAME, DOMAIN
from .task_manager import load_library

TASK_SELECTION_CATEGORIES = (
    "hvac", "safety", "appliances", "exterior", "landscape",
    "plumbing", "electrical", "interior", "seasonal", "systems",
)

EQUIPMENT_CATEGORY_ICONS = {
    "HVAC": "mdi:hvac", "Plumbing": "mdi:water-pump",
    "Electrical": "mdi:lightning-bolt", "Appliances": "mdi:washing-machine",
    "Water heating": "mdi:water-boiler", "Safety and security": "mdi:shield-home",
    "Roofing": "mdi:home-roof", "Windows and doors": "mdi:door",
    "Structure": "mdi:home-variant", "Outdoor": "mdi:tree",
    "Pool and spa": "mdi:pool", "Other": "mdi:tools",
}

def _resolve_equipment_category(options, user_input):
    """Resolve a built-in or reusable custom equipment category and icon."""
    custom_categories = [
        dict(item) for item in options.get("equipment_categories", [])
        if isinstance(item, dict) and item.get("name")
    ]
    category = user_input["category"]
    custom_name = user_input.get("custom_category_name", "").strip()
    if category == "Other" and custom_name:
        category = custom_name
    if category in EQUIPMENT_CATEGORY_ICONS:
        return category, custom_categories, EQUIPMENT_CATEGORY_ICONS[category]
    if not category or len(category) > 40 or category.casefold() in {
        name.casefold() for name in EQUIPMENT_CATEGORY_ICONS
    }:
        return None, custom_categories, None
    existing = next(
        (item for item in custom_categories
         if item["name"].casefold() == category.casefold()),
        None,
    )
    selected_icon = user_input.get("custom_category_icon")
    # The add-equipment form initially defaults its icon selector to the
    # built-in HVAC icon. When a user selects an existing custom category,
    # that untouched form default must not overwrite the category's saved icon.
    icon = (
        existing.get("icon") if existing and selected_icon in (None, "", "mdi:hvac")
        else selected_icon or (existing.get("icon") if existing else "mdi:tools")
    )
    if existing:
        existing["name"], existing["icon"] = category, icon
    else:
        custom_categories.append({"name": category, "icon": icon})
    return category, custom_categories, icon



def _is_valid_month_day(value):
    """Return whether value is a real canonical MM-DD date (leap day allowed)."""
    if not isinstance(value, str):
        return False
    try:
        parsed = date(2000, int(value[:2]), int(value[3:]))
    except (TypeError, ValueError):
        return False
    return len(value) == 5 and parsed.strftime("%m-%d") == value


def _season_window_schema(configured):
    """Build a frontend-serializable schema for the eight season dates."""
    defaults = {
        "spring": {"start": "03-15", "end": "05-31"},
        "summer": {"start": "06-01", "end": "08-31"},
        "fall": {"start": "09-01", "end": "11-15"},
        "winter": {"start": "11-16", "end": "03-14"},
    }
    fields = {}
    for season, window in defaults.items():
        current = configured.get(season, window)
        for edge in ("start", "end"):
            key = f"{season}_{edge}"
            fields[vol.Required(
                key, default=current.get(edge, window[edge])
            )] = vol.Match(
                r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
            )
    return vol.Schema(fields)


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
                library = await self.hass.async_add_executor_job(load_library)
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._schema(library),
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
        library = await self.hass.async_add_executor_job(load_library)
        return self.async_show_form(
            step_id="user", data_schema=self._schema(library)
        )

    @staticmethod
    def _schema(library):
        options = [(task_id, item["name"]) for task_id, item in library.items()]
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
            menu_options=["manage_tasks", "add_custom_task", "manage_custom_tasks", "add_equipment", "manage_equipment", "create_area", "configure_notifications", "configure_season_windows"],
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
        # Discover Home Assistant mobile-app notification services on this
        # installation. These are services (notify.mobile_app_*), not entities.
        notify_services = self.hass.services.async_services().get("notify", {})
        mobile_app_services = sorted(
            f"notify.{service}"
            for service in notify_services
            if service.startswith("mobile_app_")
        )
        current_target = options.get("notification_target", "")
        if current_target and current_target not in mobile_app_services:
            # Keep an existing setting selectable if its service is temporarily
            # unavailable or has been renamed; users can still clear/change it.
            mobile_app_services.append(current_target)

        if mobile_app_services:
            notification_target_schema = vol.In({
                "": "Home Assistant persistent notifications",
                **{service: service for service in mobile_app_services},
            })
        else:
            # Some installations may not have the Companion App integration.
            # Preserve manual configuration as a fallback in that case.
            notification_target_schema = vol.All(str, vol.Length(max=255))

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
                default=current_target,
            ): notification_target_schema,
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
        configured = self.config_entry.options.get("season_windows", {})
        if user_input is not None:
            invalid_fields = [
                f"{season}_{edge}"
                for season in ("spring", "summer", "fall", "winter")
                for edge in ("start", "end")
                if not _is_valid_month_day(user_input[f"{season}_{edge}"])
            ]
            if invalid_fields:
                return self.async_show_form(
                    step_id="configure_season_windows",
                    data_schema=_season_window_schema(user_input),
                    errors={"base": "invalid_season_date"},
                )
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

        return self.async_show_form(
            step_id="configure_season_windows",
            data_schema=_season_window_schema(configured),
        )

    async def async_step_manage_tasks(self, user_input=None):
        """Show bulk actions and expandable task categories."""
        library = await self.hass.async_add_executor_job(load_library)
        library.update({
            item["task_id"]: item
            for item in self.config_entry.options.get("custom_tasks", [])
        })
        if not getattr(self, "_task_selection_initialized", False):
            selected = self.config_entry.options.get(
                CONF_ENABLED_TASK_IDS,
                self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []),
            )
            self._selected_task_ids = [
                task_id for task_id in library if task_id in selected
            ]
            self._task_selection_initialized = True
        return await self._async_show_task_selection_menu(library)

    async def _async_show_task_selection_menu(self, library=None):
        """Show bulk actions first, followed by available task categories."""
        if library is None:
            library = await self.hass.async_add_executor_job(load_library)
            library.update({
                item["task_id"]: item
                for item in self.config_entry.options.get("custom_tasks", [])
            })
        menu_options = ["select_all_tasks", "clear_all_tasks"]
        for category in TASK_SELECTION_CATEGORIES:
            if any(
                item.get("category", "").casefold() == category
                for item in library.values()
            ):
                menu_options.append(f"task_category_{category}")
        if any(item.get("is_custom") for item in library.values()):
            menu_options.append("task_category_custom")
        menu_options.append("finish_task_selection")
        return self.async_show_menu(
            step_id="manage_tasks",
            menu_options=menu_options,
        )

    async def async_step_select_all_tasks(self, user_input=None):
        """Enable every built-in and custom maintenance task."""
        library = await self.hass.async_add_executor_job(load_library)
        library.update({
            item["task_id"]: item
            for item in self.config_entry.options.get("custom_tasks", [])
        })
        self._selected_task_ids = list(library)
        return await self._async_show_task_selection_menu(library)

    async def async_step_clear_all_tasks(self, user_input=None):
        """Clear every selected maintenance task."""
        self._selected_task_ids = []
        return await self._async_show_task_selection_menu()

    async def async_step_finish_task_selection(self, user_input=None):
        """Save the chosen task set and continue to interval configuration."""
        return await self.async_step_intervals()

    async def _async_step_task_category(self, category, user_input=None):
        """Edit selections in one category without changing other categories."""
        library = await self.hass.async_add_executor_job(load_library)
        library.update({
            item["task_id"]: item
            for item in self.config_entry.options.get("custom_tasks", [])
        })
        tasks = {
            task_id: item
            for task_id, item in library.items()
            if (
                item.get("is_custom")
                if category == "custom"
                else item.get("category", "").casefold() == category
            )
        }
        if user_input is not None:
            category_ids = set(tasks)
            selected_ids = set(self._selected_task_ids) - category_ids
            selected_ids.update(user_input.get(CONF_ENABLED_TASK_IDS, []))
            self._selected_task_ids = [
                task_id for task_id in library if task_id in selected_ids
            ]
            return await self._async_show_task_selection_menu(library)

        options = [
            (task_id, item["name"])
            for task_id, item in sorted(
                tasks.items(), key=lambda pair: pair[1]["name"].casefold()
            )
        ]
        schema = vol.Schema({
            vol.Optional(
                CONF_ENABLED_TASK_IDS,
                default=[
                    task_id for task_id in tasks
                    if task_id in self._selected_task_ids
                ],
            ): cv.multi_select(dict(options)),
        })
        return self.async_show_form(
            step_id=f"task_category_{category}",
            data_schema=schema,
        )

    async def async_step_task_category_hvac(self, user_input=None):
        return await self._async_step_task_category("hvac", user_input)

    async def async_step_task_category_safety(self, user_input=None):
        return await self._async_step_task_category("safety", user_input)

    async def async_step_task_category_appliances(self, user_input=None):
        return await self._async_step_task_category("appliances", user_input)

    async def async_step_task_category_exterior(self, user_input=None):
        return await self._async_step_task_category("exterior", user_input)

    async def async_step_task_category_landscape(self, user_input=None):
        return await self._async_step_task_category("landscape", user_input)

    async def async_step_task_category_plumbing(self, user_input=None):
        return await self._async_step_task_category("plumbing", user_input)

    async def async_step_task_category_electrical(self, user_input=None):
        return await self._async_step_task_category("electrical", user_input)

    async def async_step_task_category_interior(self, user_input=None):
        return await self._async_step_task_category("interior", user_input)

    async def async_step_task_category_seasonal(self, user_input=None):
        return await self._async_step_task_category("seasonal", user_input)

    async def async_step_task_category_systems(self, user_input=None):
        return await self._async_step_task_category("systems", user_input)

    async def async_step_task_category_custom(self, user_input=None):
        return await self._async_step_task_category("custom", user_input)

    async def async_step_intervals(self, user_input=None):
        library = await self.hass.async_add_executor_job(load_library)
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
            library = await self.hass.async_add_executor_job(load_library)
            all_ids = set(library) | {
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
            library = await self.hass.async_add_executor_job(load_library)
            if not slug or (
                proposed_id != current["task_id"]
                and (proposed_id in library
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
            if (lifespan_months or replacement_task_id) and not (
                lifespan_months and replacement_task_id
                and user_input.get("installed_date", "").strip()
            ):
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

    async def async_step_create_area(self, user_input=None):
        """Create a Home Assistant area for household equipment."""
        registry = ar.async_get(self.hass)
        if user_input is not None:
            name = user_input["name"].strip()
            if any(area.name.casefold() == name.casefold()
                   for area in registry.async_list_areas()):
                return self.async_show_form(
                    step_id="create_area",
                    data_schema=vol.Schema({
                        vol.Required("name", default=name): vol.All(
                            str, vol.Length(min=1, max=80)
                        ),
                    }),
                    errors={"base": "area_exists"},
                )
            registry.async_create(name)
            return self.async_show_menu(
                step_id="init",
                menu_options=["manage_tasks", "add_custom_task", "manage_custom_tasks", "add_equipment", "manage_equipment", "create_area", "configure_notifications", "configure_season_windows"],
            )
        return self.async_show_form(
            step_id="create_area",
            data_schema=vol.Schema({
                vol.Required("name"): vol.All(str, vol.Length(min=1, max=80)),
            }),
        )

    async def async_step_add_equipment(self, user_input=None):
        library = await self.hass.async_add_executor_job(load_library)
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
            category, equipment_categories, category_icon = _resolve_equipment_category(
                self.config_entry.options, user_input
            )
            if category is None:
                return self.async_show_form(
                    step_id="add_equipment",
                    data_schema=self._equipment_schema(task_options),
                    errors={"base": "invalid_custom_category"},
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
            if (lifespan_months or replacement_task_id) and not (
                lifespan_months and replacement_task_id
                and user_input.get("installed_date", "").strip()
            ):
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
                "category": category,
                "category_icon": category_icon,
                "area_id": user_input.get("area_id") or None,
                "manufacturer": user_input.get("manufacturer", "").strip(),
                "model": user_input.get("model", "").strip(),
                "installed_date": user_input.get("installed_date", "").strip(),
                "lifespan_months": lifespan_months,
                "replacement_task_id": replacement_task_id or None,
                "notes": user_input.get("notes", "").strip(),
                "task_ids": task_ids,
            })
            equipment = [
                {**item, "category_icon": category_icon}
                if item.get("category") == category else item
                for item in equipment
            ]
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "equipment_records": equipment,
                    "equipment_categories": equipment_categories,
                },
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

        library = await self.hass.async_add_executor_job(load_library)
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
            category, equipment_categories, category_icon = _resolve_equipment_category(
                self.config_entry.options, user_input
            )
            if category is None:
                return self.async_show_form(
                    step_id="edit_equipment",
                    data_schema=self._equipment_schema(task_options, current),
                    errors={"base": "invalid_custom_category"},
                )
            replacement_task_id = user_input.get("replacement_task_id") or ""
            lifespan_months = int(user_input.get("lifespan_months", 0) or 0)
            if (lifespan_months or replacement_task_id) and not (
                lifespan_months and replacement_task_id
                and user_input.get("installed_date", "").strip()
            ):
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
                "name": user_input["name"].strip(),
                "category": category,
                "category_icon": category_icon,
                "area_id": user_input.get("area_id") or None,
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
            equipment = [
                {**item, "category_icon": category_icon}
                if item.get("category") == category else item
                for item in equipment
            ]
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "equipment_records": equipment,
                    "equipment_categories": equipment_categories,
                },
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

    def _equipment_schema(self, task_options, current=None):
        current = current or {}
        area_options = {
            "": "No area",
            **{
                area.id: area.name
                for area in ar.async_get(self.hass).async_list_areas()
            },
        }
        current_area_id = current.get("area_id") or ""
        if current_area_id and current_area_id not in area_options:
            area_options[current_area_id] = "Previously assigned area (unavailable)"
        custom_categories = self._config_entry.options.get("equipment_categories", [])
        category_options = {name: name for name in EQUIPMENT_CATEGORY_ICONS}
        category_options.update({
            item["name"]: item["name"] for item in custom_categories
            if isinstance(item, dict) and item.get("name")
        })
        current_category = current.get("category", "HVAC")
        if current_category and current_category not in category_options:
            category_options[current_category] = f"Legacy category: {current_category}"
        saved_custom_category = next(
            (
                item for item in custom_categories
                if item.get("name", "").casefold() == current_category.casefold()
            ),
            None,
        )
        default_icon = (
            current.get("category_icon")
            or (saved_custom_category.get("icon") if saved_custom_category else None)
            or EQUIPMENT_CATEGORY_ICONS.get(current_category, "mdi:tools")
        )
        return vol.Schema({
            vol.Required("name", default=current.get("name", "")): vol.All(
                str, vol.Length(min=1, max=80)
            ),
            vol.Required("category", default=current_category): vol.In(category_options),
            vol.Optional("custom_category_name", default=""): vol.All(
                str, vol.Length(max=40)
            ),
            vol.Optional(
                "custom_category_icon", default=default_icon
            ): selector.IconSelector(selector.IconSelectorConfig()),
            vol.Optional("area_id", default=current_area_id): vol.In(area_options),
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
