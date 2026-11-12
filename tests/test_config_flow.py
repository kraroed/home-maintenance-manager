"""Regression tests for Home Maintenance Manager configuration flows."""

import pytest
import voluptuous as vol

from homeassistant.config_entries import SOURCE_USER
from homeassistant.helpers import area_registry as ar
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_maintenance_manager.config_flow import HomeMaintenanceOptionsFlow
from custom_components.home_maintenance_manager.const import (
    CONF_ENABLED_TASK_IDS,
    DOMAIN,
)

async def _open_options_step(hass, flow_id, target):
    """Navigate through the categorized options menu to a selected action."""
    parent = {
        "manage_tasks": "tasks_and_schedules", "add_custom_task": "tasks_and_schedules",
        "manage_custom_tasks": "tasks_and_schedules", "configure_season_windows": "tasks_and_schedules",
        "add_equipment": "equipment_and_areas", "manage_equipment": "equipment_and_areas",
        "create_area": "equipment_and_areas", "manage_task_areas": "equipment_and_areas",
        "configure_notifications": "notifications_menu",
        "configure_automatic_backups": "backups_and_updates", "configure_update_backups": "backups_and_updates",
    }[target]
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": parent}
    )
    assert result["step_id"] == parent
    return await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": target}
    )


async def _submit_equipment_wizard(hass, flow_id, identity, details=None, tasks=None, editing=False):
    """Submit the equipment wizard, following each explicit Continue action."""
    prefix = "edit" if editing else "add"
    result = await hass.config_entries.options.async_configure(flow_id, user_input=identity)
    assert result["step_id"] == "equipment_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_continue"}
    )
    assert result["step_id"] == f"{prefix}_equipment_details"
    result = await hass.config_entries.options.async_configure(flow_id, user_input=details or {})
    assert result["step_id"] == "equipment_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_continue"}
    )
    assert result["step_id"] == f"{prefix}_equipment_tasks"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"task_ids": tasks or []}
    )
    assert result["step_id"] == "equipment_wizard_navigation"
    return await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_continue"}
    )


async def _configure_custom_task(hass, flow_id, user_input=None):
    """Submit a custom-task wizard step and follow its Continue menu."""
    if user_input and user_input.get("next_step_id") in {
        "manage_tasks", "add_custom_task", "manage_custom_tasks",
        "configure_season_windows", "add_equipment", "manage_equipment",
        "create_area", "manage_task_areas", "configure_notifications",
        "configure_automatic_backups", "configure_update_backups",
    }:
        return await _open_options_step(
            hass, flow_id, user_input["next_step_id"]
        )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input=user_input
    )
    if result.get("step_id") == "custom_task_wizard_navigation":
        result = await hass.config_entries.options.async_configure(
            flow_id, user_input={"next_step_id": "custom_task_wizard_continue"}
        )
    return result


@pytest.mark.asyncio
async def test_user_flow_uses_categorized_task_selection(hass, enable_custom_integrations):
    """Initial setup asks for the property, then selects tasks by category."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"property_name": "Primary Residence"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "setup_tasks"
    assert "setup_category_exterior" in result["menu_options"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "setup_category_exterior"}
    )
    assert result["step_id"] == "setup_category_exterior"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ENABLED_TASK_IDS: ["clean_gutters"]}
    )
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "finish_setup"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "review_setup"
    assert result["description_placeholders"]["selected_tasks_summary"] == "Exterior:\n  • Clean rain gutters"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "back_to_setup_tasks"}
    )
    assert result["step_id"] == "setup_tasks"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "setup_category_safety"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ENABLED_TASK_IDS: ["test_smoke_alarms"]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "finish_setup"}
    )
    summary = result["description_placeholders"]["selected_tasks_summary"]
    assert summary == "Exterior:\n  • Clean rain gutters\nSafety:\n  • Test smoke alarms"
    assert "  • " in summary
    assert result["step_id"] == "review_setup"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "confirm_setup"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Primary Residence"
    assert result["data"]["property_name"] == "Primary Residence"
    assert result["data"][CONF_ENABLED_TASK_IDS] == ["test_smoke_alarms", "clean_gutters"]


@pytest.mark.asyncio
async def test_add_equipment_options_flow_saves_task_associations(hass, enable_custom_integrations):
    """Adding equipment through options stores the selected task associations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU

    result = await _open_options_step(hass, result["flow_id"], "add_equipment")
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_equipment"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"name": "Main HVAC", "category": "HVAC"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "equipment_wizard_continue"}
    )
    invalid_result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"installed_date": "2024-02-30"}
    )
    assert invalid_result["type"] == FlowResultType.FORM
    assert invalid_result["step_id"] == "add_equipment_details"
    assert invalid_result["errors"] == {"base": "invalid_date"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"manufacturer": "Example Manufacturer", "model": "HVAC-100",
                                       "installed_date": "2024-05-01", "notes": "Upstairs and downstairs system"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "equipment_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"task_ids": ["clean_gutters"]}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "equipment_wizard_continue"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    equipment = result["data"]["equipment_records"]
    assert len(equipment) == 1
    assert equipment[0]["equipment_id"] == "equipment_main_hvac"
    assert equipment[0]["name"] == "Main HVAC"
    assert equipment[0]["manufacturer"] == "Example Manufacturer"
    assert equipment[0]["model"] == "HVAC-100"
    assert equipment[0]["task_ids"] == ["clean_gutters"]

def test_equipment_installation_date_requires_real_iso_date(hass):
    """Equipment dates accept blanks and real dates but reject impossible dates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    flow = HomeMaintenanceOptionsFlow(entry)
    flow.hass = hass
    schema = flow._equipment_details_schema(
        task_options=[("clean_gutters", "Clean gutters")]
    )
    valid = {"installed_date": "2024-02-29", "lifespan_months": 0, "replacement_task_id": ""}
    parsed = schema(valid)
    assert parsed["installed_date"] == "2024-02-29"
    assert parsed["lifespan_months"] == 0
    assert parsed["replacement_task_id"] == ""
    assert schema({**valid, "installed_date": ""})["installed_date"] == ""
    for invalid_format in ("20240229", "not-a-date"):
        with pytest.raises(vol.Invalid):
            schema({**valid, "installed_date": invalid_format})


@pytest.mark.asyncio
async def test_custom_equipment_category_is_reusable_with_saved_icon(
    hass, enable_custom_integrations
):
    """Other can create a reusable custom category with its own icon."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "add_equipment")
    result = await _submit_equipment_wizard(
        hass, result["flow_id"],
        {"name": "Standby Generator", "category": "Other",
         "custom_category_name": "Generator", "custom_category_icon": "mdi:air-purifier"},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["equipment_records"][0]["category"] == "Generator"
    assert result["data"]["equipment_records"][0]["category_icon"] == "mdi:air-purifier"
    assert result["data"]["equipment_categories"] == [
        {"name": "Generator", "icon": "mdi:air-purifier"}
    ]

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
        options=result["data"],
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "add_equipment")
    result = await _submit_equipment_wizard(
        hass, result["flow_id"], {"name": "Portable Generator", "category": "Generator"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    records = result["data"]["equipment_records"]
    assert records[-1]["category"] == "Generator"
    assert records[-1]["category_icon"] == "mdi:air-purifier"
    assert result["data"]["equipment_categories"] == [
        {"name": "Generator", "icon": "mdi:air-purifier"}
    ]

@pytest.mark.asyncio
async def test_season_window_options_use_one_step_per_season(
    hass, enable_custom_integrations
):
    """Seasonal settings are collected one season at a time and preserve options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
        options={
            "notification_target": "notify.mobile_app_phone",
            "task_intervals": {"clean_gutters": 120},
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "configure_season_windows")
    assert result["step_id"] == "season_window_spring"
    invalid = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"start": "02-30", "end": "05-25"}
    )
    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {"base": "invalid_season_date"}
    result = await hass.config_entries.options.async_configure(
        invalid["flow_id"], user_input={"start": "03-10", "end": "05-25"}
    )
    assert result["step_id"] == "season_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "season_wizard_continue"}
    )
    assert result["step_id"] == "season_window_summer"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"start": "06-01", "end": "08-31"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "season_wizard_continue"}
    )
    assert result["step_id"] == "season_window_fall"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"start": "09-01", "end": "11-15"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "season_wizard_continue"}
    )
    assert result["step_id"] == "season_window_winter"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"start": "11-16", "end": "03-14"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "season_wizard_continue"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["season_windows"] == {
        "spring": {"start": "03-10", "end": "05-25"},
        "summer": {"start": "06-01", "end": "08-31"},
        "fall": {"start": "09-01", "end": "11-15"},
        "winter": {"start": "11-16", "end": "03-14"},
    }
    assert result["data"]["notification_target"] == "notify.mobile_app_phone"
    assert result["data"]["task_intervals"] == {"clean_gutters": 120}

@pytest.mark.asyncio
async def test_edit_equipment_options_flow_updates_record_and_task_links(
    hass, enable_custom_integrations
):
    """Editing equipment retains its ID while updating details and associations."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters", "replace_disposable_hvac_filter"],
        },
        options={
            "equipment_records": [{
                "equipment_id": "equipment_main_hvac",
                "name": "Main HVAC",
                "category": "HVAC",
                "manufacturer": "Old Manufacturer",
                "model": "OLD-100",
                "installed_date": "2020-01-15",
                "notes": "Original notes",
                "task_ids": ["replace_disposable_hvac_filter"],
            }],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "manage_equipment")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"equipment_id": "equipment_main_hvac"}
    )
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "edit_equipment"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_equipment"

    result = await _submit_equipment_wizard(
        hass, result["flow_id"],
        {"name": "Main and Upstairs HVAC", "category": "HVAC"},
        {"manufacturer": "New Manufacturer", "model": "NEW-200",
         "installed_date": "2024-02-29", "notes": "Updated equipment details"},
        ["clean_gutters", "replace_disposable_hvac_filter"], editing=True,
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    equipment = result["data"]["equipment_records"]
    assert len(equipment) == 1
    assert equipment[0] == {
        "equipment_id": "equipment_main_hvac",
        "name": "Main and Upstairs HVAC",
        "category": "HVAC",
        "category_icon": "mdi:hvac",
        "area_id": None,
        "manufacturer": "New Manufacturer",
        "model": "NEW-200",
        "installed_date": "2024-02-29",
        "lifespan_months": 0,
        "replacement_task_id": None,
        "notes": "Updated equipment details",
        "task_ids": ["clean_gutters", "replace_disposable_hvac_filter"],
    }

@pytest.mark.asyncio
async def test_remove_equipment_options_flow_removes_only_selected_equipment(
    hass, enable_custom_integrations
):
    """Removing equipment leaves other equipment and unrelated options intact."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: ["clean_gutters"]},
        options={
            "equipment_records": [
                {
                    "equipment_id": "equipment_main_hvac",
                    "name": "Main HVAC",
                    "category": "HVAC",
                    "task_ids": ["clean_gutters"],
                },
                {
                    "equipment_id": "equipment_water_heater",
                    "name": "Water Heater",
                    "category": "plumbing",
                    "task_ids": [],
                },
            ],
            "notification_target": "notify.mobile_app_phone",
            "task_intervals": {"clean_gutters": 120},
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "manage_equipment")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"equipment_id": "equipment_main_hvac"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "remove_equipment"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "remove_equipment"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["equipment_records"] == [
        {
            "equipment_id": "equipment_water_heater",
            "name": "Water Heater",
            "category": "plumbing",
            "task_ids": [],
        }
    ]
    assert result["data"]["notification_target"] == "notify.mobile_app_phone"
    assert result["data"]["task_intervals"] == {"clean_gutters": 120}

@pytest.mark.asyncio
async def test_remove_custom_task_clears_active_links_and_preserves_other_options(
    hass, enable_custom_integrations
):
    """Removing a custom task clears active references without dropping other options."""
    custom_task = {
        "task_id": "custom_replace_filter",
        "name": "Replace filter",
        "category": "HVAC",
        "description": "A custom maintenance task.",
        "schedule_type": "interval",
        "recommended_interval_days": 90,
        # Legacy values from a previous recurrence type should be discarded
        # when the task is saved with its current interval schedule.
        "annual_month": 10,
        "annual_day": 15,
        "monthly_week": "last",
        "monthly_weekday": 4,
        "is_custom": True,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["custom_replace_filter", "clean_gutters"],
        },
        options={
            "custom_tasks": [custom_task],
            "task_intervals": {"custom_replace_filter": 90, "clean_gutters": 120},
            "equipment_records": [{
                "equipment_id": "equipment_main_hvac",
                "name": "Main HVAC",
                "category": "HVAC",
                "task_ids": ["custom_replace_filter", "clean_gutters"],
            }],
            "notification_target": "notify.mobile_app_phone",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "manage_custom_tasks")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"task_id": "custom_replace_filter"}
    )
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "remove_custom_task"}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"confirm": True}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["custom_tasks"] == []
    assert result["data"][CONF_ENABLED_TASK_IDS] == ["clean_gutters"]
    assert result["data"]["task_intervals"] == {"clean_gutters": 120}
    assert result["data"]["equipment_records"][0]["task_ids"] == ["clean_gutters"]
    assert result["data"]["notification_target"] == "notify.mobile_app_phone"

@pytest.mark.asyncio
async def test_edit_custom_task_options_flow_keeps_stable_id_and_other_options(
    hass, enable_custom_integrations
):
    """Editing a custom task retains its ID and unrelated configuration."""
    custom_task = {
        "task_id": "custom_replace_filter",
        "name": "Replace filter",
        "category": "HVAC",
        "description": "Original description",
        "area_id": "basement",
        "schedule_type": "interval",
        "recommended_interval_days": 90,
        "is_custom": True,
        "how_to_inspect": [],
        "what_to_look_for": [],
        "what_to_do_if_issue": "",
        "safety_notes": "",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["custom_replace_filter", "clean_gutters"],
        },
        options={
            "custom_tasks": [custom_task],
            "task_intervals": {
                "custom_replace_filter": 90,
                "clean_gutters": 120,
            },
            "notification_target": "notify.mobile_app_phone",
            "equipment_records": [{
                "equipment_id": "equipment_main_hvac",
                "name": "Main HVAC",
                "category": "HVAC",
                "task_ids": ["custom_replace_filter"],
            }],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"next_step_id": "manage_custom_tasks"}
    )
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"task_id": "custom_replace_filter"}
    )
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"next_step_id": "edit_custom_task"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_custom_task"

    result = await _configure_custom_task(hass,
        result["flow_id"],
        user_input={
            "name": "Replace upstairs HVAC filter",
            "category": "other",
            "description": "Updated description",
        },
    )
    assert result["step_id"] == "custom_task_category"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"category_name": "Heating and Cooling"}
    )
    assert result["step_id"] == "custom_task_schedule"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"schedule_type": "interval"}
    )
    assert result["step_id"] == "custom_task_schedule_details"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"interval_days": 120}
    )
    assert result["step_id"] == "custom_task_instructions"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["custom_tasks"] == [{
        **{
            key: value for key, value in custom_task.items()
            if key not in {
                "annual_month", "annual_day", "monthly_week", "monthly_weekday"
            }
        },
        "name": "Replace upstairs HVAC filter",
        "category": "heating and cooling",
        "description": "Updated description",
        "area_id": "basement",
        "recommended_interval_days": 120,
    }]
    # Enabled task selections live in config-entry data; editing options
    # must leave that original selection untouched.
    assert entry.data[CONF_ENABLED_TASK_IDS] == [
        "custom_replace_filter", "clean_gutters"
    ]
    assert CONF_ENABLED_TASK_IDS not in result["data"]
    assert result["data"]["task_intervals"] == {
        "custom_replace_filter": 120,
        "clean_gutters": 120,
    }
    assert result["data"]["notification_target"] == "notify.mobile_app_phone"
    assert result["data"]["equipment_records"][0]["task_ids"] == [
        "custom_replace_filter"
    ]


@pytest.mark.asyncio
async def test_equipment_can_create_and_assign_home_assistant_area(
    hass, enable_custom_integrations
):
    """Users can create an HA area and assign it to household equipment."""
    from homeassistant.helpers import area_registry as ar

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"next_step_id": "create_area"}
    )
    assert result["step_id"] == "create_area"

    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"name": "Basement"}
    )
    assert result["type"] == FlowResultType.MENU
    area = next(
        area for area in ar.async_get(hass).async_list_areas()
        if area.name == "Basement"
    )

    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"next_step_id": "add_equipment"}
    )
    result = await _submit_equipment_wizard(
        hass, result["flow_id"], {"name": "Water Heater", "category": "Plumbing", "area_id": area.id}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["equipment_records"][0]["area_id"] == area.id

@pytest.mark.asyncio
async def test_add_custom_annual_task_saves_calendar_schedule(
    hass, enable_custom_integrations
):
    """Adding an annual custom task stores its month/day without an interval."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _configure_custom_task(hass,
        flow_id, user_input={"next_step_id": "add_custom_task"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"name": "Winterize Sprinklers", "category": "landscape",
                             "description": "Prepare irrigation for winter."}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"schedule_type": "annual"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"annual_month": 10, "annual_day": 15}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    task = result["data"]["custom_tasks"][0]
    assert task["task_id"] == "custom_winterize_sprinklers"
    assert task["schedule_type"] == "annual"
    assert task["annual_month"] == 10
    assert task["annual_day"] == 15
    assert result["data"][CONF_ENABLED_TASK_IDS] == ["custom_winterize_sprinklers"]
    assert "custom_winterize_sprinklers" not in result["data"]["task_intervals"]
@pytest.mark.asyncio
async def test_add_custom_annual_task_rejects_invalid_calendar_date(
    hass, enable_custom_integrations
):
    """Annual schedules reject impossible dates but allow leap day."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _configure_custom_task(hass,
        flow_id, user_input={"next_step_id": "add_custom_task"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"name": "Annual Inspection", "category": "safety"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"schedule_type": "annual"}
    )
    invalid = await _configure_custom_task(hass,
        flow_id, user_input={"annual_month": 2, "annual_day": 30}
    )
    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {"base": "invalid_annual_date"}
    valid = await _configure_custom_task(hass,
        flow_id, user_input={"annual_month": 2, "annual_day": 29}
    )
    valid = await _configure_custom_task(hass,flow_id, user_input={})
    assert valid["type"] == FlowResultType.CREATE_ENTRY
    assert valid["data"]["custom_tasks"][0]["annual_month"] == 2
    assert valid["data"]["custom_tasks"][0]["annual_day"] == 29

@pytest.mark.asyncio
async def test_add_custom_task_can_create_reusable_category(
    hass, enable_custom_integrations
):
    """The Other category path creates a reusable custom category."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _configure_custom_task(hass,
        flow_id, user_input={"next_step_id": "add_custom_task"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"name": "Inspect Pool Cover", "category": "other"}
    )
    assert result["step_id"] == "custom_task_category"
    result = await _configure_custom_task(hass,
        flow_id, user_input={"category_name": "Pool Care"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"schedule_type": "interval"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"interval_days": 60}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={
            "how_to_inspect": "Check for cracks",
            "what_to_look_for": "Tears and worn straps",
            "what_to_do_if_issue": "Repair or replace the cover",
            "safety_notes": "Keep clear of the pool when working alone",
        }
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    task = result["data"]["custom_tasks"][0]
    assert task["category"] == "pool care"
    assert task["recommended_interval_days"] == 60
    assert task["how_to_inspect"] == ["Check for cracks"]
    assert task["what_to_look_for"] == ["Tears and worn straps"]
    assert task["what_to_do_if_issue"] == "Repair or replace the cover"
    assert task["safety_notes"] == "Keep clear of the pool when working alone"
    assert result["data"]["task_intervals"]["custom_inspect_pool_cover"] == 60


@pytest.mark.asyncio
async def test_edit_custom_task_can_switch_to_annual_schedule_and_keep_id_history(
    hass, enable_custom_integrations
):
    """Editing a custom task can switch its schedule while retaining its ID."""
    custom_task = {
        "task_id": "custom_sprinkler_check",
        "name": "Sprinkler check",
        "category": "Outdoor",
        "description": "Check the sprinkler system.",
        "schedule_type": "interval",
        "recommended_interval_days": 90,
        "is_custom": True,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["custom_sprinkler_check"],
        },
        options={
            "custom_tasks": [custom_task],
            "task_intervals": {"custom_sprinkler_check": 90},
            "notification_target": "notify.mobile_app_phone",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"next_step_id": "manage_custom_tasks"}
    )
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"task_id": "custom_sprinkler_check"}
    )
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"next_step_id": "edit_custom_task"}
    )
    result = await _configure_custom_task(hass,
        result["flow_id"],
        user_input={
            "name": "Winterize Sprinklers",
            "category": "outdoor",
            "description": "Prepare irrigation for winter.",
        },
    )
    assert result["step_id"] == "custom_task_schedule"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"schedule_type": "annual"}
    )
    assert result["step_id"] == "custom_task_schedule_details"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={"annual_month": 10, "annual_day": 15}
    )
    assert result["step_id"] == "custom_task_instructions"
    result = await _configure_custom_task(hass,
        result["flow_id"], user_input={}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["custom_tasks"][0]["task_id"] == "custom_sprinkler_check"
    assert result["data"]["custom_tasks"][0]["schedule_type"] == "annual"
    assert result["data"]["custom_tasks"][0]["annual_month"] == 10
    assert result["data"]["custom_tasks"][0]["annual_day"] == 15
    assert "custom_sprinkler_check" not in result["data"]["task_intervals"]
    assert result["data"]["notification_target"] == "notify.mobile_app_phone"

@pytest.mark.asyncio
async def test_add_custom_monthly_task_saves_weekday_pattern(
    hass, enable_custom_integrations
):
    """Adding a monthly custom task stores its ordinal weekday schedule."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _configure_custom_task(hass,
        flow_id, user_input={"next_step_id": "add_custom_task"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"name": "Monthly Alarm Test", "category": "safety",
                             "description": "Test household alarms monthly."}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"schedule_type": "monthly"}
    )
    result = await _configure_custom_task(hass,
        flow_id, user_input={"monthly_week": "second", "monthly_weekday": 1}
    )
    result = await _configure_custom_task(hass,flow_id, user_input={})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    task = result["data"]["custom_tasks"][0]
    assert task["task_id"] == "custom_monthly_alarm_test"
    assert task["schedule_type"] == "monthly"
    assert task["monthly_week"] == "second"
    assert task["monthly_weekday"] == 1
    assert "annual_month" not in task
    assert "custom_monthly_alarm_test" not in result["data"]["task_intervals"]

@pytest.mark.asyncio
async def test_custom_task_wizard_back_preserves_draft_values(
    hass, enable_custom_integrations
):
    """Back navigation returns to prior pages without losing custom task input."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "add_custom_task")
    result = await hass.config_entries.options.async_configure(
        flow_id,
        user_input={
            "name": "Inspect Water Shutoff",
            "category": "plumbing",
            "description": "Locate and test the main shutoff.",
        },
    )
    assert result["step_id"] == "custom_task_wizard_navigation"
    assert result["menu_options"] == ["custom_task_wizard_continue"]
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_continue"}
    )
    assert result["step_id"] == "custom_task_schedule"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"schedule_type": "annual"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_continue"}
    )
    assert result["step_id"] == "custom_task_schedule_details"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"annual_month": 5, "annual_day": 10}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_back"}
    )
    assert result["step_id"] == "custom_task_schedule"
    schedule_defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert schedule_defaults["schedule_type"] == "annual"



@pytest.mark.asyncio
async def test_add_equipment_lifespan_designates_and_links_replacement_task(
    hass, enable_custom_integrations
):
    """A lifespan configuration automatically associates its replacement task."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "add_equipment")
    result = await _submit_equipment_wizard(
        hass, result["flow_id"],
        {"name": "Smoke Detector Hall", "category": "Safety and security"},
        {"installed_date": "2020-01-15", "lifespan_months": 120,
         "replacement_task_id": "clean_gutters"},
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    record = result["data"]["equipment_records"][0]
    assert record["lifespan_months"] == 120
    assert record["replacement_task_id"] == "clean_gutters"
    assert record["task_ids"] == ["clean_gutters"]


@pytest.mark.asyncio
async def test_add_equipment_rejects_incomplete_lifespan_configuration(
    hass, enable_custom_integrations
):
    """Lifespan scheduling requires an installation date and replacement task."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "add_equipment")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"name": "Smoke Detector Hall", "category": "Safety and security"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "equipment_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"installed_date": "", "lifespan_months": 120, "replacement_task_id": ""}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "equipment_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"task_ids": []}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "equipment_wizard_continue"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_equipment_details"
    assert result["errors"] == {"base": "incomplete_lifespan"}


@pytest.mark.asyncio
async def test_notification_options_use_guided_steps(hass, enable_custom_integrations):
    """Notification type selection leads to a relevant delivery settings step."""
    hass.services.async_register("notify", "mobile_app_test_phone", lambda call: None)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "configure_notifications")
    assert result["step_id"] == "configure_notifications"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": True,
        },
    )
    assert result["step_id"] == "notification_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "notification_wizard_continue"}
    )
    assert result["step_id"] == "notification_delivery"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "notification_target": "notify.mobile_app_test_phone",
            "notification_lead_days": 7,
            "daily_summary_time": "08:00",
        },
    )
    assert result["step_id"] == "notification_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "notification_wizard_continue"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["notification_target"] == "notify.mobile_app_test_phone"
    assert result["data"]["notification_lead_days"] == 7
    assert result["data"]["daily_summary_time"] == "08:00"


@pytest.mark.asyncio
async def test_manage_tasks_supports_bulk_actions_and_category_selection(
    hass, enable_custom_integrations
):
    """Bulk actions and category edits preserve selections from other categories."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "manage_tasks")
    assert result["type"] == FlowResultType.MENU
    assert result["menu_options"][:2] == ["select_all_tasks", "clear_all_tasks"]
    assert "task_category_hvac" in result["menu_options"]
    assert "finish_task_selection" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "clear_all_tasks"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "task_category_hvac"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "task_category_hvac"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ENABLED_TASK_IDS: ["inspect_hvac_air_filter"]},
    )
    assert result["type"] == FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "task_category_safety"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_ENABLED_TASK_IDS: ["test_smoke_alarms"]},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "finish_task_selection"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "intervals"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "interval_category_hvac"}
    )
    assert result["step_id"] == "interval_category_hvac"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"interval_inspect_hvac_air_filter": 30}
    )
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "interval_category_safety"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"interval_test_smoke_alarms": 30}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "finish_intervals"}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENABLED_TASK_IDS] == [
        "inspect_hvac_air_filter", "test_smoke_alarms"
    ]


@pytest.mark.asyncio
async def test_manage_tasks_clear_all_removes_every_enabled_task(
    hass, enable_custom_integrations
):
    """Clear all removes built-in and custom tasks before saving."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
        options={
            "custom_tasks": [{
                "task_id": "custom_test_task",
                "name": "Custom test task",
                "category": "testing",
                "schedule_type": "annual",
                "recommended_interval_days": 365,
                "is_custom": True,
            }]
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "manage_tasks")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "select_all_tasks"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "clear_all_tasks"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "finish_task_selection"}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENABLED_TASK_IDS] == []



@pytest.mark.asyncio
async def test_equipment_wizard_back_preserves_identity(hass, enable_custom_integrations):
    """Back from equipment details restores the entered identity and category."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "add_equipment")
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"name": "Hall Smoke Detector", "category": "Safety and security"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"installed_date": "2024-03-12", "manufacturer": "Acme"}
    )
    assert result["step_id"] == "equipment_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_back"}
    )
    assert result["step_id"] == "add_equipment"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["name"] == "Hall Smoke Detector"
    assert defaults["category"] == "Safety and security"


@pytest.mark.asyncio
async def test_season_wizard_back_preserves_dates(hass, enable_custom_integrations):
    """Back from summer returns to spring with the previously entered dates."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "configure_season_windows")
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"start": "03-20", "end": "05-25"}
    )
    assert result["step_id"] == "season_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "season_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"start": "06-05", "end": "08-25"}
    )
    assert result["step_id"] == "season_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "season_wizard_back"}
    )
    assert result["step_id"] == "season_window_spring"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["start"] == "03-20"
    assert defaults["end"] == "05-25"


@pytest.mark.asyncio
async def test_notification_wizard_back_preserves_notification_choices(
    hass, enable_custom_integrations
):
    """Back from delivery settings restores the selected notification types."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
        options={"notification_target": "notify.mobile_app_phone"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "configure_notifications")
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "individual_notifications_enabled": False,
            "daily_summary_enabled": True,
        }
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "notification_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"daily_summary_time": "07:30"}
    )
    assert result["step_id"] == "notification_wizard_navigation"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "notification_wizard_back"}
    )
    assert result["step_id"] == "configure_notifications"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["individual_notifications_enabled"] is False
    assert defaults["daily_summary_enabled"] is True

    # Change the notification choices after returning Back, then verify the
    # delivery values entered on the previous page are still present.
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "individual_notifications_enabled": True,
            "daily_summary_enabled": True,
        }
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "notification_wizard_continue"}
    )
    assert result["step_id"] == "notification_delivery"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["notification_target"] == "notify.mobile_app_phone"
    assert defaults["daily_summary_time"] == "07:30"
    assert defaults["notification_lead_days"] == 7


@pytest.mark.asyncio
async def test_equipment_task_association_back_returns_to_details_with_draft(
    hass, enable_custom_integrations
):
    """Back from equipment task associations restores the equipment details."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: ["clean_gutters"]},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "add_equipment")
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"name": "Hall Smoke Detector", "category": "Safety and security"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"manufacturer": "Acme", "installed_date": "2024-03-12"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_continue"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"task_ids": ["clean_gutters"]}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "equipment_wizard_back"}
    )
    assert result["step_id"] == "add_equipment_details"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["manufacturer"] == "Acme"
    assert defaults["installed_date"] == "2024-03-12"


@pytest.mark.asyncio
async def test_custom_task_category_back_restores_basic_task_draft(
    hass, enable_custom_integrations
):
    """Back from custom category selection restores the basic task form."""
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "add_custom_task")
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "name": "Inspect Main Water Shutoff",
            "category": "other",
            "description": "Locate and test the valve.",
        }
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_continue"}
    )
    assert result["step_id"] == "custom_task_category"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"category_name": "Plumbing"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_back"}
    )
    assert result["step_id"] == "add_custom_task"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["name"] == "Inspect Main Water Shutoff"
    assert defaults["category"] == "other"
    assert defaults["description"] == "Locate and test the valve."


@pytest.mark.asyncio
async def test_edit_custom_task_back_restores_existing_schedule_values(
    hass, enable_custom_integrations
):
    """Back during custom-task editing preserves the existing schedule draft."""
    custom_task = {
        "task_id": "custom_annual_gutter_check",
        "name": "Annual gutter inspection",
        "category": "exterior",
        "description": "Inspect gutters each fall.",
        "schedule_type": "annual",
        "annual_month": 10,
        "annual_day": 15,
        "is_custom": True,
        "how_to_inspect": [],
        "what_to_look_for": [],
        "what_to_do_if_issue": "",
        "safety_notes": "",
    }
    entry = MockConfigEntry(
        domain=DOMAIN, title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: ["custom_annual_gutter_check"]},
        options={"custom_tasks": [custom_task]},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    flow_id = result["flow_id"]
    result = await _open_options_step(hass, flow_id, "manage_custom_tasks")
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"task_id": "custom_annual_gutter_check"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "edit_custom_task"}
    )
    assert result["step_id"] == "edit_custom_task"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={
            "name": "Annual gutter inspection",
            "category": "exterior",
            "description": "Inspect gutters each fall.",
        }
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_continue"}
    )
    assert result["step_id"] == "custom_task_schedule"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"schedule_type": "annual"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_continue"}
    )
    assert result["step_id"] == "custom_task_schedule_details"
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"annual_month": 11, "annual_day": 20}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id, user_input={"next_step_id": "custom_task_wizard_back"}
    )
    assert result["step_id"] == "custom_task_schedule"
    defaults = {
        str(key): (key.default() if callable(key.default) else key.default)
        for key in result["data_schema"].schema
    }
    assert defaults["schedule_type"] == "annual"

@pytest.mark.asyncio
async def test_assign_area_to_standalone_task_options_flow(hass, enable_custom_integrations):
    """A standalone task can be assigned a Home Assistant area."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
        options={},
    )
    entry.add_to_hass(hass)
    area = ar.async_get(hass).async_create("Basement")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await _open_options_step(hass, result["flow_id"], "manage_task_areas")
    assert result["step_id"] == "manage_task_areas"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"task_id": "clean_gutters"}
    )
    assert result["step_id"] == "assign_task_area"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"area_id": area.id}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["task_area_assignments"]["clean_gutters"] == area.id

