"""Regression tests for Home Maintenance Manager configuration flows."""

import pytest

from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
