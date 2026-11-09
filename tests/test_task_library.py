"""Regression tests for the built-in maintenance task catalog."""

from collections import Counter

from custom_components.home_maintenance_manager.task_manager import load_library


def test_builtin_library_contains_120_unique_well_formed_tasks():
    """The full catalog remains available with valid scheduling metadata."""
    library = load_library()

    assert len(library) == 120
    assert len(set(library)) == 120
    assert Counter(task["category"] for task in library.values()) == {
        "hvac": 14,
        "safety": 14,
        "plumbing": 16,
        "appliances": 14,
        "electrical": 8,
        "interior": 10,
        "exterior": 14,
        "landscape": 12,
        "seasonal": 8,
        "systems": 10,
    }

    for task_id, task in library.items():
        assert task["task_id"] == task_id
        assert task["name"].strip()
        assert task["description"].strip()
        assert task["recommendation_note"].strip()
        assert task["schedule_type"] in {"interval", "seasonal"}
        assert isinstance(task["recommended_interval_days"], int)
        assert 1 <= task["recommended_interval_days"] <= 3650
        assert task["priority"] in {"low", "normal", "high"}
        assert isinstance(task["requires_equipment"], bool)

        if task["schedule_type"] == "seasonal":
            assert task["season_keys"]
            assert set(task["season_keys"]) <= {
                "spring", "summer", "fall", "winter"
            }


def test_expanded_library_keeps_existing_task_ids():
    """Expanding the catalog does not rename or remove existing task IDs."""
    library = load_library()

    assert {
        "inspect_hvac_air_filter",
        "replace_disposable_hvac_filter",
        "test_smoke_alarms",
        "clean_gutters",
        "winterize_sprinklers",
        "inspect_sump_pump",
        "service_water_heater",
    } <= set(library)


def test_new_optional_system_tasks_are_individually_selectable_library_entries():
    """Optional systems are catalog entries, not automatically enabled tasks."""
    library = load_library()

    assert {
        "inspect_well_system",
        "test_well_water",
        "inspect_septic_system",
        "service_standby_generator",
        "inspect_pool_equipment",
        "service_spa_hot_tub",
        "inspect_radon_mitigation",
        "inspect_crawlspace",
        "inspect_solar_system",
    } <= set(library)
