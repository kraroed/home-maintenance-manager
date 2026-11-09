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

    for invalid_date in ("2024-02-30", "20240229", "not-a-date"):
        with pytest.raises(vol.Invalid, match="YYYY-MM-DD"):
            schema({**valid, "installed_date": invalid_date})


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

