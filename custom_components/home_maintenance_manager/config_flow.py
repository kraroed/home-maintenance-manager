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


def _multi_select_checklist(options):
    """Render multi-select choices as an always-visible checklist."""
    items = options.items() if isinstance(options, dict) else options
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[{"value": value, "label": label} for value, label in items],
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )


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
        """Collect the property name before choosing tasks by category."""
        if user_input is not None:
            property_name = user_input[CONF_PROPERTY_NAME].strip()
            if not property_name:
                return self.async_show_form(
                    step_id="user",
                    data_schema=self._property_schema(property_name),
                    errors={"base": "invalid_name"},
                )
            self._setup_property_name = property_name
            self._setup_selected_task_ids = []
            return await self._async_show_setup_task_menu()
        return self.async_show_form(
            step_id="user", data_schema=self._property_schema("My Home")
        )

    @staticmethod
    def _property_schema(default="My Home"):
        return vol.Schema({
            vol.Required(CONF_PROPERTY_NAME, default=default): vol.All(
                str, vol.Length(min=1, max=80)
            ),
        })

    async def async_step_setup_tasks(self, user_input=None):
        """Display the task-category selection menu during initial setup."""
        return await self._async_show_setup_task_menu()

    async def _async_show_setup_task_menu(self):
        """Show task categories for initial setup."""
        library = await self.hass.async_add_executor_job(load_library)
        categories = sorted({
            item.get("category", "").casefold()
            for item in library.values() if item.get("category")
        })
        menu_options = ["select_all_setup_tasks", "clear_all_setup_tasks"]
        menu_options.extend(
            f"setup_category_{category}" for category in categories
        )
        menu_options.append("finish_setup")
        return self.async_show_menu(
            step_id="setup_tasks", menu_options=menu_options
        )

    async def async_step_select_all_setup_tasks(self, user_input=None):
        library = await self.hass.async_add_executor_job(load_library)
        self._setup_selected_task_ids = list(library)
        return await self._async_show_setup_task_menu()

    async def async_step_clear_all_setup_tasks(self, user_input=None):
        self._setup_selected_task_ids = []
        return await self._async_show_setup_task_menu()

    async def _async_step_setup_category(self, category, user_input=None):
        library = await self.hass.async_add_executor_job(load_library)
        tasks = {
            task_id: item for task_id, item in library.items()
            if item.get("category", "").casefold() == category
        }
        if user_input is not None:
            selected = set(self._setup_selected_task_ids) - set(tasks)
            selected.update(user_input.get(CONF_ENABLED_TASK_IDS, []))
            self._setup_selected_task_ids = [
                task_id for task_id in library if task_id in selected
            ]
            return await self._async_show_setup_task_menu()
        options = {
            task_id: item["name"] for task_id, item in sorted(
                tasks.items(), key=lambda pair: pair[1]["name"].casefold()
            )
        }
        return self.async_show_form(
            step_id=f"setup_category_{category}",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_ENABLED_TASK_IDS,
                    default=[
                        task_id for task_id in tasks
                        if task_id in self._setup_selected_task_ids
                    ],
                ): _multi_select_checklist(options),
            }),
        )

    async def async_step_setup_category_hvac(self, user_input=None):
        return await self._async_step_setup_category("hvac", user_input)

    async def async_step_setup_category_safety(self, user_input=None):
        return await self._async_step_setup_category("safety", user_input)

    async def async_step_setup_category_appliances(self, user_input=None):
        return await self._async_step_setup_category("appliances", user_input)

    async def async_step_setup_category_exterior(self, user_input=None):
        return await self._async_step_setup_category("exterior", user_input)

    async def async_step_setup_category_landscape(self, user_input=None):
        return await self._async_step_setup_category("landscape", user_input)

    async def async_step_setup_category_plumbing(self, user_input=None):
        return await self._async_step_setup_category("plumbing", user_input)

    async def async_step_setup_category_electrical(self, user_input=None):
        return await self._async_step_setup_category("electrical", user_input)

    async def async_step_setup_category_interior(self, user_input=None):
        return await self._async_step_setup_category("interior", user_input)

    async def async_step_setup_category_seasonal(self, user_input=None):
        return await self._async_step_setup_category("seasonal", user_input)

    async def async_step_setup_category_systems(self, user_input=None):
        return await self._async_step_setup_category("systems", user_input)

    async def async_step_finish_setup(self, user_input=None):
        """Show a grouped review of selected tasks before completing setup."""
        library = await self.hass.async_add_executor_job(load_library)
        grouped = {}
        for task_id in self._setup_selected_task_ids:
            item = library.get(task_id)
            if item:
                grouped.setdefault(item.get("category", "Other").title(), []).append(
                    item.get("name", task_id)
                )
        summary = "\\n".join(
            f"{category}: " + ", ".join(sorted(names, key=str.casefold))
            for category, names in sorted(grouped.items())
        ) or "No maintenance tasks selected."
        return self.async_show_menu(
            step_id="review_setup",
            menu_options=["back_to_setup_tasks", "confirm_setup"],
            description_placeholders={"selected_tasks_summary": summary},
        )

    async def async_step_review_setup(self, user_input=None):
        """Re-display the initial setup review menu."""
        return await self.async_step_finish_setup()

    async def async_step_back_to_setup_tasks(self, user_input=None):
        """Return to task selection without losing selected tasks."""
        return await self._async_show_setup_task_menu()

    async def async_step_confirm_setup(self, user_input=None):
        """Create the config entry after the task selection review."""
        property_name = self._setup_property_name
        await self.async_set_unique_id(property_name.casefold())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=property_name,
            data={
                CONF_PROPERTY_NAME: property_name,
                CONF_ENABLED_TASK_IDS: self._setup_selected_task_ids,
            },
        )

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
        """Choose which maintenance notifications should be sent."""
        options = self.config_entry.options
        draft = getattr(self, "_notification_draft", options)
        if user_input is not None:
            self._notification_draft = {
                "individual_notifications_enabled": user_input["individual_notifications_enabled"],
                "daily_summary_enabled": user_input["daily_summary_enabled"],
            }
            return self._async_show_notification_wizard_navigation(
                previous=None, next_step="notification_delivery"
            )
        return self.async_show_form(
            step_id="configure_notifications",
            data_schema=vol.Schema({
                vol.Optional(
                    "individual_notifications_enabled",
                    default=draft.get("individual_notifications_enabled", True),
                ): bool,
                vol.Optional(
                    "daily_summary_enabled",
                    default=draft.get("daily_summary_enabled", True),
                ): bool,
            }),
        )

    async def async_step_notification_delivery(self, user_input=None):
        """Configure delivery target and timing for enabled notifications."""
        options = self.config_entry.options
        draft = getattr(self, "_notification_draft", {
            "individual_notifications_enabled": options.get("individual_notifications_enabled", True),
            "daily_summary_enabled": options.get("daily_summary_enabled", True),
        })
        if user_input is not None:
            draft.update(user_input)
            if "notification_target" in draft:
                draft["notification_target"] = draft["notification_target"].strip()
            self._notification_draft = draft
            return self._async_show_notification_wizard_navigation(
                previous="configure_notifications", next_step="save"
            )

        notify_services = self.hass.services.async_services().get("notify", {})
        mobile_app_services = sorted(
            f"notify.{service}" for service in notify_services
            if service.startswith("mobile_app_")
        )
        current_target = draft.get("notification_target", options.get("notification_target", ""))
        if current_target and current_target not in mobile_app_services:
            mobile_app_services.append(current_target)
        if mobile_app_services:
            target_schema = vol.In({
                "": "Home Assistant persistent notifications",
                **{service: service for service in mobile_app_services},
            })
        else:
            target_schema = vol.All(str, vol.Length(max=255))

        fields = {}
        if draft["individual_notifications_enabled"] or draft["daily_summary_enabled"]:
            fields[vol.Optional(
                "notification_target", default=current_target
            )] = target_schema
        if draft["individual_notifications_enabled"]:
            fields[vol.Required(
                "notification_lead_days",
                default=draft.get("notification_lead_days", options.get("notification_lead_days", 7)),
            )] = vol.All(vol.Coerce(int), vol.Range(min=0, max=90))
        if draft["daily_summary_enabled"]:
            fields[vol.Required(
                "daily_summary_time",
                default=draft.get("daily_summary_time", options.get("daily_summary_time", "08:00")),
            )] = vol.Match(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
        if not fields:
            self._notification_draft = draft
            return self._async_show_notification_wizard_navigation(
                previous="configure_notifications", next_step="save"
            )
        return self.async_show_form(
            step_id="notification_delivery", data_schema=vol.Schema(fields)
        )

    def _async_show_notification_wizard_navigation(self, previous, next_step):
        """Offer Back and Continue actions between notification settings."""
        self._notification_wizard_previous = previous
        self._notification_wizard_next = next_step
        menu_options = ["notification_wizard_continue"]
        if previous:
            menu_options.insert(0, "notification_wizard_back")
        return self.async_show_menu(
            step_id="notification_wizard_navigation",
            menu_options=menu_options,
        )

    async def async_step_notification_wizard_navigation(self, user_input=None):
        """Re-display the current notification wizard navigation choices."""
        menu_options = ["notification_wizard_continue"]
        if self._notification_wizard_previous:
            menu_options.insert(0, "notification_wizard_back")
        return self.async_show_menu(
            step_id="notification_wizard_navigation",
            menu_options=menu_options,
        )

    async def async_step_notification_wizard_back(self, user_input=None):
        """Return to notification type selection with choices preserved."""
        return await self.async_step_configure_notifications()

    async def async_step_notification_wizard_continue(self, user_input=None):
        """Continue to delivery settings or save notification preferences."""
        next_step = self._notification_wizard_next
        if next_step != "save":
            return await self.async_step_notification_delivery()
        options = self.config_entry.options
        draft = self._notification_draft
        return self.async_create_entry(
            title="",
            data={
                **options,
                **draft,
                "notification_target": draft.get(
                    "notification_target", options.get("notification_target", "")
                ),
                "notification_lead_days": draft.get(
                    "notification_lead_days", options.get("notification_lead_days", 7)
                ),
                "daily_summary_time": draft.get(
                    "daily_summary_time", options.get("daily_summary_time", "08:00")
                ),
            },
        )

    async def async_step_configure_season_windows(self, user_input=None):
        """Start the seasonal-window wizard with spring dates."""
        self._season_window_draft = dict(
            self.config_entry.options.get("season_windows", {})
        )
        return await self.async_step_season_window_spring(user_input)

    async def _async_step_season_window(self, season, next_season, user_input=None):
        """Collect one season's dates, validating before moving to the next."""
        defaults = {
            "spring": {"start": "03-15", "end": "05-31"},
            "summer": {"start": "06-01", "end": "08-31"},
            "fall": {"start": "09-01", "end": "11-15"},
            "winter": {"start": "11-16", "end": "03-14"},
        }
        configured = getattr(self, "_season_window_draft", {})
        current = configured.get(season, defaults[season])
        if user_input is not None:
            if not all(_is_valid_month_day(user_input[key]) for key in ("start", "end")):
                return self.async_show_form(
                    step_id=f"season_window_{season}",
                    data_schema=vol.Schema({
                        vol.Required("start", default=user_input["start"]): vol.Match(
                            r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
                        ),
                        vol.Required("end", default=user_input["end"]): vol.Match(
                            r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
                        ),
                    }),
                    errors={"base": "invalid_season_date"},
                )
            configured[season] = dict(user_input)
            self._season_window_draft = configured
            previous = {
                "spring": None, "summer": "spring",
                "fall": "summer", "winter": "fall",
            }[season]
            self._season_wizard_previous = previous
            self._season_wizard_next = next_season
            menu_options = ["season_wizard_continue"]
            if previous:
                menu_options.insert(0, "season_wizard_back")
            return self.async_show_menu(
                step_id="season_wizard_navigation",
                menu_options=menu_options,
            )
        return self.async_show_form(
            step_id=f"season_window_{season}",
            data_schema=vol.Schema({
                vol.Required("start", default=current.get("start", defaults[season]["start"])): vol.Match(
                    r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
                ),
                vol.Required("end", default=current.get("end", defaults[season]["end"])): vol.Match(
                    r"^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
                ),
            }),
        )

    async def async_step_season_wizard_navigation(self, user_input=None):
        """Re-display the current seasonal wizard navigation choices."""
        menu_options = ["season_wizard_continue"]
        if self._season_wizard_previous:
            menu_options.insert(0, "season_wizard_back")
        return self.async_show_menu(
            step_id="season_wizard_navigation",
            menu_options=menu_options,
        )

    async def async_step_season_wizard_back(self, user_input=None):
        """Return to the previous season without losing entered dates."""
        return await getattr(
            self, f"async_step_season_window_{self._season_wizard_previous}"
        )()

    async def async_step_season_wizard_continue(self, user_input=None):
        """Continue to the next season or save all seasonal windows."""
        next_season = self._season_wizard_next
        if next_season:
            return await getattr(self, f"async_step_season_window_{next_season}")()
        return self.async_create_entry(
            title="",
            data={
                **self.config_entry.options,
                "season_windows": self._season_window_draft,
            },
        )

    async def async_step_season_window_spring(self, user_input=None):
        return await self._async_step_season_window("spring", "summer", user_input)

    async def async_step_season_window_summer(self, user_input=None):
        return await self._async_step_season_window("summer", "fall", user_input)

    async def async_step_season_window_fall(self, user_input=None):
        return await self._async_step_season_window("fall", "winter", user_input)

    async def async_step_season_window_winter(self, user_input=None):
        return await self._async_step_season_window("winter", None, user_input)



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
            ): _multi_select_checklist(options),
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
        """Start category-by-category interval configuration."""
        self._interval_draft = dict(self.config_entry.options.get("task_intervals", {}))
        return await self._async_show_interval_menu()

    async def _async_interval_tasks(self, category):
        """Return selected built-in recurring tasks for one category."""
        library = await self.hass.async_add_executor_job(load_library)
        return {
            task_id: item for task_id, item in library.items()
            if task_id in self._selected_task_ids
            and item.get("schedule_type") == "interval"
            and not item.get("is_custom")
            and item.get("category", "").casefold() == category
        }

    async def _async_show_interval_menu(self):
        """Show only categories that contain selected recurring tasks."""
        menu_options = []
        for category in TASK_SELECTION_CATEGORIES:
            if await self._async_interval_tasks(category):
                menu_options.append(f"interval_category_{category}")
        if not menu_options:
            return await self.async_step_finish_intervals()
        menu_options.append("finish_intervals")
        return self.async_show_menu(step_id="intervals", menu_options=menu_options)

    async def _async_step_interval_category(self, category, user_input=None):
        """Edit recurring intervals for one selected task category."""
        tasks = await self._async_interval_tasks(category)
        if user_input is not None:
            self._interval_draft.update({
                task_id: user_input[f"interval_{task_id}"]
                for task_id in tasks if f"interval_{task_id}" in user_input
            })
            return await self._async_show_interval_menu()
        fields = {}
        for task_id, item in sorted(tasks.items(), key=lambda pair: pair[1]["name"].casefold()):
            default = self._interval_draft.get(
                task_id, item.get("recommended_interval_days", 30)
            )
            fields[vol.Required(
                f"interval_{task_id}", default=int(default)
            )] = vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))
        return self.async_show_form(
            step_id=f"interval_category_{category}", data_schema=vol.Schema(fields)
        )

    async def async_step_interval_category_hvac(self, user_input=None):
        return await self._async_step_interval_category("hvac", user_input)

    async def async_step_interval_category_safety(self, user_input=None):
        return await self._async_step_interval_category("safety", user_input)

    async def async_step_interval_category_appliances(self, user_input=None):
        return await self._async_step_interval_category("appliances", user_input)

    async def async_step_interval_category_exterior(self, user_input=None):
        return await self._async_step_interval_category("exterior", user_input)

    async def async_step_interval_category_landscape(self, user_input=None):
        return await self._async_step_interval_category("landscape", user_input)

    async def async_step_interval_category_plumbing(self, user_input=None):
        return await self._async_step_interval_category("plumbing", user_input)

    async def async_step_interval_category_electrical(self, user_input=None):
        return await self._async_step_interval_category("electrical", user_input)

    async def async_step_interval_category_interior(self, user_input=None):
        return await self._async_step_interval_category("interior", user_input)

    async def async_step_interval_category_seasonal(self, user_input=None):
        return await self._async_step_interval_category("seasonal", user_input)

    async def async_step_interval_category_systems(self, user_input=None):
        return await self._async_step_interval_category("systems", user_input)

    async def async_step_finish_intervals(self, user_input=None):
        """Persist task selection and all category interval choices."""
        return self.async_create_entry(
            title="",
            data={
                **self.config_entry.options,
                CONF_ENABLED_TASK_IDS: self._selected_task_ids,
                "task_intervals": self._interval_draft,
            },
        )

    async def _async_custom_task_basic_form(self, step_id):
        """Render the basic custom-task page with draft values."""
        library = await self.hass.async_add_executor_job(load_library)
        categories = {
            item.get("category", "").strip().casefold(): item.get("category", "").strip()
            for item in library.values() if item.get("category", "").strip()
        }
        for item in self.config_entry.options.get("custom_tasks", []):
            category = item.get("category", "").strip()
            if category:
                categories[category.casefold()] = category
        options = {key: value for key, value in sorted(categories.items())}
        options["other"] = "Other / Create a new category"
        current = self._custom_task_draft
        category = current.get("category", "hvac")
        options.setdefault(category, category.title())
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema({
                vol.Required("name", default=current.get("name", "")): vol.All(str, vol.Length(min=1, max=80)),
                vol.Required("category", default=category): vol.In(options),
                vol.Optional("description", default=current.get("description", "")): vol.All(str, vol.Length(max=300)),
            }),
        )

    def _async_show_custom_task_wizard_navigation(self, previous, next_step):
        """Show Back and Continue between custom-task wizard pages."""
        self._custom_task_wizard_previous = previous
        self._custom_task_wizard_next = next_step
        return self.async_show_menu(
            step_id="custom_task_wizard_navigation",
            menu_options=["custom_task_wizard_back", "custom_task_wizard_continue"],
        )

    async def async_step_custom_task_wizard_navigation(self, user_input=None):
        return self.async_show_menu(
            step_id="custom_task_wizard_navigation",
            menu_options=["custom_task_wizard_back", "custom_task_wizard_continue"],
        )

    async def async_step_custom_task_wizard_back(self, user_input=None):
        previous = self._custom_task_wizard_previous
        if previous in ("add_custom_task", "edit_custom_task"):
            return await self._async_custom_task_basic_form(previous)
        return await getattr(self, f"async_step_{previous}")()

    async def async_step_custom_task_wizard_continue(self, user_input=None):
        next_step = self._custom_task_wizard_next
        if next_step == "save":
            return await self.async_step_custom_task_save()
        return await getattr(self, f"async_step_{next_step}")()

    async def async_step_add_custom_task(self, user_input=None):
        """Collect basic details and preserve them through Back navigation."""
        if not hasattr(self, "_custom_task_draft") or getattr(self, "_custom_task_editing", False):
            self._custom_task_draft = {}
        self._custom_task_editing = False
        if user_input is not None:
            self._custom_task_draft.update({
                "name": user_input["name"].strip(),
                "category": user_input["category"],
                "description": user_input.get("description", "").strip(),
            })
            self._custom_task_base_step = "add_custom_task"
            self._custom_task_category_is_custom = user_input["category"] == "other"
            next_step = "custom_task_category" if user_input["category"] == "other" else "custom_task_schedule"
            return self._async_show_custom_task_wizard_navigation("add_custom_task", next_step)
        return await self._async_custom_task_basic_form("add_custom_task")

    async def async_step_custom_task_category(self, user_input=None):
        """Collect a reusable category name while retaining the draft."""
        if user_input is not None:
            category = user_input["category_name"].strip()
            if not category:
                return self.async_show_form(
                    step_id="custom_task_category",
                    data_schema=vol.Schema({
                        vol.Required("category_name", default=self._custom_task_draft.get("category_name", "")): vol.All(str, vol.Length(min=1, max=40)),
                    }),
                    errors={"base": "invalid_category"},
                )
            self._custom_task_draft["category_name"] = category
            self._custom_task_draft["category"] = category.casefold()
            return self._async_show_custom_task_wizard_navigation(
                self._custom_task_base_step, "custom_task_schedule"
            )
        return self.async_show_form(
            step_id="custom_task_category",
            data_schema=vol.Schema({
                vol.Required("category_name", default=self._custom_task_draft.get("category_name", "")): vol.All(str, vol.Length(min=1, max=40)),
            }),
        )

    @staticmethod
    def _custom_task_schedule_type_schema(default="interval"):
        return vol.Schema({
            vol.Required("schedule_type", default=default): vol.In({
                "interval": "Repeat by interval",
                "annual": "Repeat annually on a calendar date",
                "monthly": "Repeat monthly on a weekday pattern",
            }),
        })


    @staticmethod
    def _custom_task_schedule_details_schema(schedule_type, current=None):
        current = current or {}
        if schedule_type == "interval":
            return vol.Schema({
                vol.Required("interval_days", default=current.get("interval_days", current.get("recommended_interval_days", 90))): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=3650)
                ),
            })
        if schedule_type == "annual":
            return vol.Schema({
                vol.Required("annual_month", default=current.get("annual_month", 1)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=12)
                ),
                vol.Required("annual_day", default=current.get("annual_day", 1)): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=31)
                ),
            })
        return vol.Schema({
            vol.Required("monthly_week", default=current.get("monthly_week", "first")): vol.In({
                "first": "First", "second": "Second", "third": "Third",
                "fourth": "Fourth", "last": "Last",
            }),
            vol.Required("monthly_weekday", default=current.get("monthly_weekday", 5)): vol.In({
                0: "Monday", 1: "Tuesday", 2: "Wednesday",
                3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday",
            }),
        })

    async def async_step_custom_task_schedule(self, user_input=None):
        """Choose the recurrence pattern before showing its relevant fields."""
        if user_input is not None:
            self._custom_task_draft["schedule_type"] = user_input["schedule_type"]
            return self._async_show_custom_task_wizard_navigation(
                "custom_task_category" if getattr(self, "_custom_task_category_is_custom", False) else self._custom_task_base_step,
                "custom_task_schedule_details",
            )
        return self.async_show_form(
            step_id="custom_task_schedule",
            data_schema=self._custom_task_schedule_type_schema(
                self._custom_task_draft.get("schedule_type", "interval")
            ),
        )

    async def async_step_custom_task_schedule_details(self, user_input=None):
        """Collect schedule fields and preserve them for the previous step."""
        schedule_type = self._custom_task_draft["schedule_type"]
        if user_input is not None:
            self._custom_task_draft.update(user_input)
            if schedule_type == "annual":
                try:
                    date(2000, int(user_input["annual_month"]), int(user_input["annual_day"]))
                except ValueError:
                    return self.async_show_form(
                        step_id="custom_task_schedule_details",
                        data_schema=self._custom_task_schedule_details_schema(schedule_type, self._custom_task_draft),
                        errors={"base": "invalid_annual_date"},
                    )
            return self._async_show_custom_task_wizard_navigation(
                "custom_task_schedule", "custom_task_instructions"
            )
        return self.async_show_form(
            step_id="custom_task_schedule_details",
            data_schema=self._custom_task_schedule_details_schema(schedule_type, self._custom_task_draft),
        )

    @staticmethod
    def _custom_task_instructions_schema(current=None):
        """Build the inspection and safety guidance form with preserved defaults."""
        current = current or {}
        return vol.Schema({
            vol.Optional("how_to_inspect", default=current.get("how_to_inspect", "")): vol.All(str, vol.Length(max=1200)),
            vol.Optional("what_to_look_for", default=current.get("what_to_look_for", "")): vol.All(str, vol.Length(max=1200)),
            vol.Optional("what_to_do_if_issue", default=current.get("what_to_do_if_issue", "")): vol.All(str, vol.Length(max=600)),
            vol.Optional("safety_notes", default=current.get("safety_notes", "")): vol.All(str, vol.Length(max=600)),
        })

    async def async_step_custom_task_instructions(self, user_input=None):
        """Collect inspection guidance and offer a final Back/Save choice."""
        if user_input is not None:
            self._custom_task_draft.update(user_input)
            return self._async_show_custom_task_wizard_navigation(
                "custom_task_schedule_details", "save"
            )
        return self.async_show_form(
            step_id="custom_task_instructions",
            data_schema=self._custom_task_instructions_schema(self._custom_task_draft),
        )

    async def async_step_custom_task_save(self, user_input=None):
        """Validate and save the completed custom task."""
        draft = self._custom_task_draft
        name = draft["name"].strip()
        slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        task_id = f"custom_{slug}"
        existing_tasks = self.config_entry.options.get("custom_tasks", [])
        library = await self.hass.async_add_executor_job(load_library)
        editing = getattr(self, "_custom_task_editing", False)
        original_id = getattr(self, "_custom_task_original_id", None)
        collision = task_id in library or any(
            item["task_id"] == task_id and item["task_id"] != original_id
            for item in existing_tasks
        )
        if not slug or (collision and task_id != original_id):
            return self.async_show_form(
                step_id="edit_custom_task" if editing else "add_custom_task",
                data_schema=vol.Schema({
                    vol.Required("name", default=name): vol.All(str, vol.Length(min=1, max=80)),
                    vol.Required("category", default=draft["category"]): str,
                    vol.Optional("description", default=draft.get("description", "")): vol.All(
                        str, vol.Length(max=300)
                    ),
                }),
                errors={"base": "duplicate_task"},
            )

        schedule_type = draft["schedule_type"]
        interval = int(draft.get("interval_days", draft.get("recommended_interval_days", 90)))
        existing_record = next(
            (item for item in existing_tasks if item["task_id"] == original_id), {}
        ) if editing else {}
        custom_task = {
            **existing_record,
            "task_id": task_id,
            "name": name,
            "category": draft["category"].strip().casefold() or "custom",
            "description": draft.get("description", "").strip(),
            "schedule_type": schedule_type,
            "recommended_interval_days": interval,
            **(
                {"annual_month": int(draft["annual_month"]), "annual_day": int(draft["annual_day"])}
                if schedule_type == "annual" else {}
            ),
            **(
                {"monthly_week": draft["monthly_week"], "monthly_weekday": int(draft["monthly_weekday"])}
                if schedule_type == "monthly" else {}
            ),
            **({
                "priority": "normal",
                "requires_equipment": False,
                "recommendation_note": "Custom task created by the user.",
            } if not editing else {}),
            "how_to_inspect": [
                line.strip() for line in draft.get("how_to_inspect", "").splitlines()
                if line.strip()
            ],
            "what_to_look_for": [
                line.strip() for line in draft.get("what_to_look_for", "").splitlines()
                if line.strip()
            ],
            "what_to_do_if_issue": draft.get("what_to_do_if_issue", "").strip(),
            "safety_notes": draft.get("safety_notes", "").strip(),
            "is_custom": True,
        }
        if getattr(self, "_custom_task_editing", False):
            original_id = self._custom_task_original_id
            if task_id != original_id and (
                task_id in library
                or any(item["task_id"] == task_id and item["task_id"] != original_id
                       for item in existing_tasks)
            ):
                return self.async_show_form(
                    step_id="edit_custom_task",
                    data_schema=vol.Schema({
                        vol.Required("name", default=name): vol.All(str, vol.Length(min=1, max=80)),
                        vol.Required("category", default=draft["category"]): str,
                        vol.Optional("description", default=draft.get("description", "")): vol.All(str, vol.Length(max=300)),
                    }),
                    errors={"base": "duplicate_task"},
                )
            custom_task["task_id"] = original_id
            custom_tasks = [
                custom_task if item["task_id"] == original_id else item
                for item in existing_tasks
            ]
            intervals = dict(self.config_entry.options.get("task_intervals", {}))
            if schedule_type == "interval":
                intervals[original_id] = interval
            else:
                intervals.pop(original_id, None)
            self._custom_task_editing = False
            return self.async_create_entry(
                title="",
                data={
                    **self.config_entry.options,
                    "custom_tasks": custom_tasks,
                    "task_intervals": intervals,
                },
            )
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
                        key: value for key, value in self.config_entry.options.get(
                            "task_intervals", {}
                        ).items() if key != task_id
                    },
                    **({task_id: interval} if schedule_type == "interval" else {}),
                },
            },
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
        """Start or resume editing a custom task with the guided wizard."""
        custom_tasks = list(self.config_entry.options.get("custom_tasks", []))
        current = next(
            (item for item in custom_tasks if item["task_id"] == getattr(self, "_selected_custom_task_id", None)),
            None,
        )
        if current is None:
            return self.async_abort(reason="custom_task_not_found")
        if user_input is not None:
            self._custom_task_draft.update({
                "name": user_input["name"].strip(),
                "category": user_input["category"],
                "description": user_input.get("description", "").strip(),
            })
            self._custom_task_base_step = "edit_custom_task"
            self._custom_task_category_is_custom = user_input["category"] == "other"
            next_step = "custom_task_category" if user_input["category"] == "other" else "custom_task_schedule"
            return self._async_show_custom_task_wizard_navigation("edit_custom_task", next_step)
        if not getattr(self, "_custom_task_editing", False) or not getattr(self, "_custom_task_draft", None):
            self._custom_task_editing = True
            self._custom_task_original_id = current["task_id"]
            self._custom_task_draft = dict(current)
            self._custom_task_draft["how_to_inspect"] = "\n".join(current.get("how_to_inspect", []))
            self._custom_task_draft["what_to_look_for"] = "\n".join(current.get("what_to_look_for", []))
        self._custom_task_base_step = "edit_custom_task"
        return await self._async_custom_task_basic_form("edit_custom_task")

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
        """Start the guided equipment registration flow."""
        if user_input is None:
            if not hasattr(self, "_equipment_draft"):
                self._equipment_draft = {}
            return self.async_show_form(
                step_id="add_equipment",
                data_schema=self._equipment_identity_schema(self._equipment_draft),
            )
        self._equipment_draft.update(user_input)
        return self._async_show_equipment_wizard_navigation(
            previous=None, next_step="add_equipment_details", editing=False
        )

    async def async_step_add_equipment_details(self, user_input=None):
        """Collect installation and lifespan details."""
        if user_input is not None:
            self._equipment_draft.update(user_input)
            try:
                _validate_optional_iso_date(self._equipment_draft.get("installed_date", "").strip())
            except vol.Invalid:
                return self.async_show_form(
                    step_id="add_equipment_details",
                    data_schema=self._equipment_details_schema(self._equipment_draft, await self._async_equipment_task_options()),
                    errors={"base": "invalid_date"},
                )
            return self._async_show_equipment_wizard_navigation(
                previous="add_equipment", next_step="add_equipment_tasks", editing=False
            )
        return self.async_show_form(
            step_id="add_equipment_details",
            data_schema=self._equipment_details_schema(self._equipment_draft, await self._async_equipment_task_options()),
        )

    async def async_step_add_equipment_tasks(self, user_input=None):
        """Choose maintenance tasks associated with this equipment."""
        task_options = await self._async_equipment_task_options()
        if user_input is not None:
            self._equipment_draft.update(user_input)
            return self._async_show_equipment_wizard_navigation(
                previous="add_equipment_details", next_step="save", editing=False
            )
        return self.async_show_form(step_id="add_equipment_tasks", data_schema=self._equipment_tasks_schema(task_options, self._equipment_draft))

    async def async_step_manage_equipment(self, user_input=None):
        equipment = self.config_entry.options.get("equipment_records", [])
        if not equipment:
            return self.async_abort(reason="no_equipment")
        if user_input is not None:
            self._selected_equipment_id = user_input["equipment_id"]
            return self.async_show_menu(step_id="equipment_actions", menu_options=["edit_equipment", "remove_equipment"])
        options = [(item["equipment_id"], item["name"]) for item in equipment]
        return self.async_show_form(step_id="manage_equipment", data_schema=vol.Schema({
            vol.Required("equipment_id"): vol.In(dict(options)),
        }))

    async def async_step_equipment_actions(self, user_input=None):
        return self.async_show_menu(step_id="equipment_actions", menu_options=["edit_equipment", "remove_equipment"])

    async def async_step_edit_equipment(self, user_input=None):
        """Start the guided equipment editing flow."""
        current = self._get_selected_equipment()
        if current is None:
            return self.async_abort(reason="equipment_not_found")
        if user_input is None:
            if not hasattr(self, "_equipment_draft"):
                self._equipment_draft = dict(current)
            return self.async_show_form(step_id="edit_equipment", data_schema=self._equipment_identity_schema(self._equipment_draft))
        self._equipment_draft.update(user_input)
        return self._async_show_equipment_wizard_navigation(
            previous=None, next_step="edit_equipment_details", editing=True
        )

    async def async_step_edit_equipment_details(self, user_input=None):
        """Collect updated installation and lifespan details."""
        if user_input is not None:
            self._equipment_draft.update(user_input)
            try:
                _validate_optional_iso_date(self._equipment_draft.get("installed_date", "").strip())
            except vol.Invalid:
                return self.async_show_form(
                    step_id="edit_equipment_details",
                    data_schema=self._equipment_details_schema(self._equipment_draft, await self._async_equipment_task_options()),
                    errors={"base": "invalid_date"},
                )
            return self._async_show_equipment_wizard_navigation(
                previous="edit_equipment", next_step="edit_equipment_tasks", editing=True
            )
        return self.async_show_form(
            step_id="edit_equipment_details",
            data_schema=self._equipment_details_schema(self._equipment_draft, await self._async_equipment_task_options()),
        )

    async def async_step_edit_equipment_tasks(self, user_input=None):
        """Update the maintenance tasks associated with this equipment."""
        task_options = await self._async_equipment_task_options()
        if user_input is not None:
            self._equipment_draft.update(user_input)
            return self._async_show_equipment_wizard_navigation(
                previous="edit_equipment_details", next_step="save", editing=True
            )
        return self.async_show_form(step_id="edit_equipment_tasks", data_schema=self._equipment_tasks_schema(task_options, self._equipment_draft))

    def _async_show_equipment_wizard_navigation(self, previous, next_step, editing):
        """Offer explicit Back and Continue actions between equipment forms."""
        self._equipment_wizard_previous = previous
        self._equipment_wizard_next = next_step
        self._equipment_wizard_editing = editing
        menu_options = ["equipment_wizard_continue"]
        if previous:
            menu_options.insert(0, "equipment_wizard_back")
        return self.async_show_menu(
            step_id="equipment_wizard_navigation",
            menu_options=menu_options,
        )

    async def async_step_equipment_wizard_navigation(self, user_input=None):
        """Re-display the current equipment wizard navigation choices."""
        menu_options = ["equipment_wizard_continue"]
        if self._equipment_wizard_previous:
            menu_options.insert(0, "equipment_wizard_back")
        return self.async_show_menu(
            step_id="equipment_wizard_navigation",
            menu_options=menu_options,
        )

    async def async_step_equipment_wizard_back(self, user_input=None):
        """Return to the previous equipment step with its draft intact."""
        return await getattr(
            self, f"async_step_{self._equipment_wizard_previous}"
        )()

    async def async_step_equipment_wizard_continue(self, user_input=None):
        """Continue the equipment wizard or save its completed draft."""
        next_step = self._equipment_wizard_next
        if next_step == "save":
            return await self._async_save_equipment(
                editing=self._equipment_wizard_editing
            )
        return await getattr(self, f"async_step_{next_step}")()

    def _get_selected_equipment(self):
        """Return the equipment record selected in the management flow."""
        return next((item for item in self.config_entry.options.get("equipment_records", [])
                     if item.get("equipment_id") == getattr(self, "_selected_equipment_id", None)), None)

    async def _async_equipment_task_options(self):
        """Return enabled built-in and custom maintenance tasks."""
        library = await self.hass.async_add_executor_job(load_library)
        library.update({item["task_id"]: item for item in self.config_entry.options.get("custom_tasks", [])})
        enabled = self.config_entry.options.get(CONF_ENABLED_TASK_IDS, self.config_entry.data.get(CONF_ENABLED_TASK_IDS, []))
        return [(task_id, library[task_id]["name"]) for task_id in enabled if task_id in library]

    async def _async_save_equipment(self, editing):
        """Validate and persist the completed equipment wizard."""
        draft = self._equipment_draft
        equipment = list(self.config_entry.options.get("equipment_records", []))
        current = self._get_selected_equipment() if editing else None
        category, equipment_categories, category_icon = _resolve_equipment_category(self.config_entry.options, draft)
        task_options = await self._async_equipment_task_options()
        identity_step = "edit_equipment" if editing else "add_equipment"
        task_step = "edit_equipment_tasks" if editing else "add_equipment_tasks"
        if category is None:
            return self.async_show_form(step_id=identity_step, data_schema=self._equipment_identity_schema(draft), errors={"base": "invalid_custom_category"})
        name = draft.get("name", "").strip()
        slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
        equipment_id = current["equipment_id"] if current else f"equipment_{slug}"
        if not slug or any(item.get("equipment_id") == equipment_id and (current is None or item.get("equipment_id") != current["equipment_id"]) for item in equipment):
            return self.async_show_form(step_id=identity_step, data_schema=self._equipment_identity_schema(draft), errors={"base": "duplicate_equipment"})
        replacement_task_id = draft.get("replacement_task_id") or ""
        lifespan_months = int(draft.get("lifespan_months", 0) or 0)
        if (lifespan_months or replacement_task_id) and not (lifespan_months and replacement_task_id and draft.get("installed_date", "").strip()):
            return self.async_show_form(step_id="edit_equipment_details" if editing else "add_equipment_details", data_schema=self._equipment_details_schema(draft, task_options), errors={"base": "incomplete_lifespan"})
        if replacement_task_id and any(item.get("equipment_id") != (current or {}).get("equipment_id") and item.get("replacement_task_id") == replacement_task_id for item in equipment):
            return self.async_show_form(step_id=task_step, data_schema=self._equipment_tasks_schema(task_options, draft), errors={"base": "duplicate_replacement_task"})
        task_ids = list(draft.get("task_ids", []))
        if replacement_task_id and replacement_task_id not in task_ids:
            task_ids.append(replacement_task_id)
        updated = {
            **(current or {}), "equipment_id": equipment_id, "name": name, "category": category,
            "category_icon": category_icon, "area_id": draft.get("area_id") or None,
            "manufacturer": draft.get("manufacturer", "").strip(), "model": draft.get("model", "").strip(),
            "installed_date": draft.get("installed_date", "").strip(), "lifespan_months": lifespan_months,
            "replacement_task_id": replacement_task_id or None, "notes": draft.get("notes", "").strip(),
            "task_ids": task_ids,
        }
        if editing:
            equipment = [updated if item.get("equipment_id") == current["equipment_id"] else item for item in equipment]
        else:
            equipment.append(updated)
        equipment = [{**item, "category_icon": category_icon} if item.get("category") == category else item for item in equipment]
        return self.async_create_entry(title="", data={**self.config_entry.options, "equipment_records": equipment, "equipment_categories": equipment_categories})

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

    def _equipment_identity_schema(self, current=None):
        """Build the identity, category, and area step."""
        current = current or {}
        area_options = {"": "No area", **{area.id: area.name for area in ar.async_get(self.hass).async_list_areas()}}
        current_area_id = current.get("area_id") or ""
        if current_area_id and current_area_id not in area_options:
            area_options[current_area_id] = "Previously assigned area (unavailable)"
        custom_categories = self.config_entry.options.get("equipment_categories", [])
        category_options = {name: name for name in EQUIPMENT_CATEGORY_ICONS}
        category_options.update({item["name"]: item["name"] for item in custom_categories if isinstance(item, dict) and item.get("name")})
        current_category = current.get("category", "HVAC")
        if current_category and current_category not in category_options:
            category_options[current_category] = f"Legacy category: {current_category}"
        saved = next((item for item in custom_categories if item.get("name", "").casefold() == current_category.casefold()), None)
        default_icon = current.get("category_icon") or (saved.get("icon") if saved else None) or EQUIPMENT_CATEGORY_ICONS.get(current_category, "mdi:tools")
        return vol.Schema({
            vol.Required("name", default=current.get("name", "")): vol.All(str, vol.Length(min=1, max=80)),
            vol.Required("category", default=current_category): vol.In(category_options),
            vol.Optional("custom_category_name", default=""): vol.All(str, vol.Length(max=40)),
            vol.Optional("custom_category_icon", default=default_icon): selector.IconSelector(selector.IconSelectorConfig()),
            vol.Optional("area_id", default=current_area_id): vol.In(area_options),
        })

    @staticmethod
    def _equipment_details_schema(current=None, task_options=()):
        """Build the installation and lifespan step."""
        current = current or {}
        return vol.Schema({
            vol.Optional("manufacturer", default=current.get("manufacturer", "")): vol.All(str, vol.Length(max=80)),
            vol.Optional("model", default=current.get("model", "")): vol.All(str, vol.Length(max=80)),
            vol.Optional("installed_date", default=current.get("installed_date", "")): vol.All(str, vol.Length(max=10), vol.Match(r"^$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$")),
            vol.Optional("lifespan_months", default=current.get("lifespan_months", 0)): vol.All(vol.Coerce(int), vol.Range(min=0, max=1200)),
            vol.Optional("replacement_task_id", default=current.get("replacement_task_id") or ""): vol.In({"": "None", **dict(task_options)}),
            vol.Optional("notes", default=current.get("notes", "")): vol.All(str, vol.Length(max=500)),
        })

    @staticmethod
    def _equipment_tasks_schema(task_options, current=None):
        """Build the linked maintenance tasks step."""
        current = current or {}
        return vol.Schema({
            vol.Optional("task_ids", default=current.get("task_ids", [])): _multi_select_checklist(task_options),
        })
