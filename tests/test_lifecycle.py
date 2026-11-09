"""Regression tests for integration setup and unload lifecycle."""

import pytest

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_maintenance_manager.const import (
    CONF_ENABLED_TASK_IDS,
    DOMAIN,
)
from custom_components.home_maintenance_manager.completion_service import (
    SERVICE_COMPLETE_TASK,
    SERVICE_RESCHEDULE_TASK,
)
from custom_components.home_maintenance_manager.history_export import (
    SERVICE_EXPORT_HISTORY,
)


@pytest.mark.asyncio
async def test_config_entry_setup_registers_platforms_and_services(
    hass, enable_custom_integrations
):
    """A configured property loads its entities and domain services."""
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

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.entry_id in hass.data[DOMAIN]
    assert hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK)
    assert hass.services.has_service(DOMAIN, SERVICE_RESCHEDULE_TASK)
    assert hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY)

    entity_ids = [
        state.entity_id
        for state in hass.states.async_all()
        if state.attributes.get("integration_domain") == DOMAIN
    ]
    assert any(
        state.attributes.get("summary_key") == "total"
        for state in hass.states.async_all()
        if state.attributes.get("integration_domain") == DOMAIN
    )
    assert any("clean_rain_gutters" in entity_id for entity_id in entity_ids)


@pytest.mark.asyncio
async def test_unloading_final_config_entry_cleans_up_services(
    hass, enable_custom_integrations
):
    """Unloading the last property removes its services and runtime data."""
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

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)

    assert entry.entry_id not in hass.data.get(DOMAIN, {})
    assert not hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK)
    assert not hass.services.has_service(DOMAIN, SERVICE_RESCHEDULE_TASK)
    assert not hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY)


@pytest.mark.asyncio
async def test_unloading_one_property_keeps_services_for_remaining_property(
    hass, enable_custom_integrations
):
    """Shared services remain registered until every property is unloaded."""
    entries = [
        MockConfigEntry(
            domain=DOMAIN,
            title=title,
            data={
                "property_name": title,
                CONF_ENABLED_TASK_IDS: ["clean_gutters"],
            },
            options={},
        )
        for title in ("Primary Residence", "Vacation Home")
    ]
    for entry in entries:
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)

    assert len(hass.data[DOMAIN]) == 2

    assert await hass.config_entries.async_unload(entries[0].entry_id)
    assert entries[0].entry_id not in hass.data[DOMAIN]
    assert entries[1].entry_id in hass.data[DOMAIN]
    assert hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK)
    assert hass.services.has_service(DOMAIN, SERVICE_RESCHEDULE_TASK)
    assert hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY)

    assert await hass.config_entries.async_unload(entries[1].entry_id)
    assert not hass.data.get(DOMAIN)
    assert not hass.services.has_service(DOMAIN, SERVICE_COMPLETE_TASK)
    assert not hass.services.has_service(DOMAIN, SERVICE_RESCHEDULE_TASK)
    assert not hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY)

