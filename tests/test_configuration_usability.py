"""Regression tests for clear and complete configuration translations."""

import json
from pathlib import Path

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.home_maintenance_manager.const import DOMAIN


TRANSLATIONS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "home_maintenance_manager"
    / "translations"
    / "en.json"
)


def _translations():
    return json.loads(TRANSLATIONS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("section", ["config", "options"])
def test_every_configuration_step_has_clear_translations(section):
    """Every translated step and form field has a visible label and explanation."""
    steps = _translations()[section]["step"]
    assert steps
    for step_id, step in steps.items():
        assert step.get("title"), f"{section}.{step_id} is missing a title"
        assert step.get("description"), f"{section}.{step_id} is missing a description"
        fields = step.get("data", {})
        descriptions = step.get("data_description", {})
        for field, label in fields.items():
            assert label, f"{section}.{step_id}.{field} is missing a label"
        assert set(descriptions).issubset(fields), (
            f"{section}.{step_id} has descriptions for fields that are not present"
        )


def test_update_backup_options_explain_selection_and_installation_limits():
    """The update settings explain empty selection and installation tracking limits."""
    step = _translations()["options"]["step"]["configure_update_backups"]
    descriptions = step["data_description"]
    assert "empty" in descriptions["update_backup_entities"].lower()
    assert "does not pause" in descriptions["update_install_tracking_enabled"].lower()
    assert "available" in descriptions["update_backup_on_available"].lower()


def test_automatic_backup_options_explain_frequency_and_retention():
    """Backup controls explain schedule choices and which files retention removes."""
    step = _translations()["options"]["step"]["configure_automatic_backups"]
    descriptions = step["data_description"]
    assert "sunday" in descriptions["automatic_backup_frequency"].lower()
    assert "manual" in descriptions["automatic_backup_retention"].lower()


async def test_create_area_returns_complete_options_menu(hass, enable_custom_integrations):
    """Creating an area returns users to the full options menu."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Primary Residence",
        data={"property_name": "Primary Residence", "enabled_task_ids": []},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options._open_options_step(hass, result["flow_id"], "create_area")
    assert result["step_id"] == "create_area"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"name": "Utility Room"}
    )
    assert result["type"] == FlowResultType.MENU
    assert result["step_id"] == "init"
    assert "manage_custom_tasks" in result["menu_options"]
    assert "configure_automatic_backups" in result["menu_options"]
    assert "configure_update_backups" in result["menu_options"]

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

