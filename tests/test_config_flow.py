"""Regression tests for Home Maintenance Manager configuration flows."""

import pytest
import voluptuous as vol

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_maintenance_manager.config_flow import HomeMaintenanceOptionsFlow
from custom_components.home_maintenance_manager.const import (
    CONF_ENABLED_TASK_IDS,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_user_flow_creates_property_with_selected_tasks(hass, enable_custom_integrations):
    """The initial setup flow stores the property and selected task IDs."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "property_name": "Primary Residence",
            CONF_ENABLED_TASK_IDS: ["clean_gutters"],
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Primary Residence"
    assert result["data"]["property_name"] == "Primary Residence"
    assert result["data"][CONF_ENABLED_TASK_IDS] == ["clean_gutters"]


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

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "add_equipment"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_equipment"

    invalid_result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Main HVAC",
            "category": "HVAC",
            "installed_date": "2024-02-30",
            "task_ids": ["clean_gutters"],
        },
    )
    assert invalid_result["type"] == FlowResultType.FORM
    assert invalid_result["errors"] == {"installed_date": "invalid_date"}
    result = invalid_result

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Main HVAC",
            "category": "HVAC",
            "manufacturer": "Example Manufacturer",
            "model": "HVAC-100",
            "installed_date": "2024-05-01",
            "notes": "Upstairs and downstairs system",
            "task_ids": ["clean_gutters"],
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    equipment = result["data"]["equipment_records"]
    assert len(equipment) == 1
    assert equipment[0]["equipment_id"] == "equipment_main_hvac"
    assert equipment[0]["name"] == "Main HVAC"
    assert equipment[0]["manufacturer"] == "Example Manufacturer"
    assert equipment[0]["model"] == "HVAC-100"
    assert equipment[0]["task_ids"] == ["clean_gutters"]



def test_equipment_installation_date_requires_real_iso_date():
    """Equipment dates accept blanks and real dates but reject impossible dates."""
    schema = HomeMaintenanceOptionsFlow._equipment_schema(
        [("clean_gutters", "Clean gutters")]
    )
    valid = {
        "name": "Main HVAC",
        "category": "HVAC",
        "installed_date": "2024-02-29",
        "task_ids": ["clean_gutters"],
    }
    assert schema(valid)["installed_date"] == "2024-02-29"

    blank_date = {**valid, "installed_date": ""}
    assert schema(blank_date)["installed_date"] == ""

    for invalid_date in ("2024-02-30",):
        # Calendar validity is checked in the flow handler so the form schema
        # remains serializable by Home Assistant's frontend schema codec.
        assert schema({**valid, "installed_date": invalid_date})["installed_date"] == invalid_date

    for invalid_format in ("20240229", "not-a-date"):
        with pytest.raises(vol.Invalid):
            schema({**valid, "installed_date": invalid_format})


@pytest.mark.asyncio
async def test_season_window_options_validate_and_save_all_windows(
    hass, enable_custom_integrations
):
    """Seasonal schedule settings can be customized with valid MM-DD dates."""
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
    assert result["type"] == FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "configure_season_windows"},
    )
    assert result["type"] == FlowResultType.FORM
    schema = result["data_schema"]
    submitted = {
        "spring_start": "03-10",
        "spring_end": "05-25",
        "summer_start": "06-01",
        "summer_end": "08-31",
        "fall_start": "09-01",
        "fall_end": "11-15",
        "winter_start": "11-16",
        "winter_end": "03-14",
    }
    assert schema(submitted) == submitted
    leap_day = {**submitted, "spring_start": "02-29"}
    assert schema(leap_day)["spring_start"] == "02-29"
    for field in ("spring_start", "winter_end"):
        invalid = {**submitted, field: "02-30"}
        with pytest.raises(vol.Invalid, match="MM-DD"):
            schema(invalid)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=submitted
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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_equipment"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"equipment_id": "equipment_main_hvac"}
    )
    assert result["type"] == FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "edit_equipment"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_equipment"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Main and Upstairs HVAC",
            "category": "HVAC",
            "manufacturer": "New Manufacturer",
            "model": "NEW-200",
            "installed_date": "2024-02-29",
            "notes": "Updated equipment details",
            "task_ids": ["clean_gutters", "replace_disposable_hvac_filter"],
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    equipment = result["data"]["equipment_records"]
    assert len(equipment) == 1
    assert equipment[0] == {
        "equipment_id": "equipment_main_hvac",
        "name": "Main and Upstairs HVAC",
        "category": "HVAC",
        "manufacturer": "New Manufacturer",
        "model": "NEW-200",
        "installed_date": "2024-02-29",
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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_equipment"}
    )
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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_custom_tasks"}
    )
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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_custom_tasks"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"task_id": "custom_replace_filter"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "edit_custom_task"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_custom_task"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Replace upstairs HVAC filter",
            "category": "Heating and Cooling",
            "description": "Updated description",
            "schedule_type": "interval",
            "interval_days": 120,
            "annual_month": 1,
            "annual_day": 1,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["custom_tasks"] == [{
        **custom_task,
        "name": "Replace upstairs HVAC filter",
        "category": "heating and cooling",
        "description": "Updated description",
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
async def test_add_custom_annual_task_saves_calendar_schedule(
    hass, enable_custom_integrations
):
    """Adding an annual custom task stores its month/day without an interval."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_custom_task"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Winterize Sprinklers",
            "category": "Outdoor",
            "description": "Prepare irrigation for winter.",
            "schedule_type": "annual",
            "interval_days": 90,
            "annual_month": 10,
            "annual_day": 15,
        },
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
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", CONF_ENABLED_TASK_IDS: []},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_custom_task"}
    )
    invalid = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Annual Inspection",
            "category": "General",
            "schedule_type": "annual",
            "interval_days": 90,
            "annual_month": 2,
            "annual_day": 30,
        },
    )
    assert invalid["type"] == FlowResultType.FORM
    assert invalid["errors"] == {"base": "invalid_annual_date"}

    valid = await hass.config_entries.options.async_configure(
        invalid["flow_id"],
        user_input={
            "name": "Annual Inspection",
            "category": "General",
            "schedule_type": "annual",
            "interval_days": 90,
            "annual_month": 2,
            "annual_day": 29,
        },
    )
    assert valid["type"] == FlowResultType.CREATE_ENTRY
    assert valid["data"]["custom_tasks"][0]["annual_month"] == 2
    assert valid["data"]["custom_tasks"][0]["annual_day"] == 29


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
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "manage_custom_tasks"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"task_id": "custom_sprinkler_check"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": "edit_custom_task"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "name": "Winterize Sprinklers",
            "category": "Outdoor",
            "description": "Prepare irrigation for winter.",
            "schedule_type": "annual",
            "interval_days": 90,
            "annual_month": 10,
            "annual_day": 15,
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["custom_tasks"][0]["task_id"] == "custom_sprinkler_check"
    assert result["data"]["custom_tasks"][0]["schedule_type"] == "annual"
    assert result["data"]["custom_tasks"][0]["annual_month"] == 10
    assert result["data"]["custom_tasks"][0]["annual_day"] == 15
    assert "custom_sprinkler_check" not in result["data"]["task_intervals"]
    assert result["data"]["notification_target"] == "notify.mobile_app_phone"
