from custom_components.home_maintenance_manager.areas import (
    build_area_groups,
    effective_task_area_ids,
)


def test_unassigned_standalone_task_has_no_effective_area():
    assert effective_task_area_ids({"equipment_ids": []}, {}) == []


def test_standalone_task_uses_its_optional_area():
    assert effective_task_area_ids({"area_id": "kitchen"}, {}) == ["kitchen"]


def test_linked_task_inherits_equipment_area_instead_of_task_area():
    task = {"area_id": "garage", "equipment_ids": ["furnace"]}
    equipment = {"furnace": {"area_id": "basement"}}
    assert effective_task_area_ids(task, equipment) == ["basement"]


def test_task_linked_to_equipment_in_multiple_areas_uses_each_once():
    task = {"equipment_ids": ["furnace", "air_handler", "pump"]}
    equipment = {
        "furnace": {"area_id": "basement"},
        "air_handler": {"area_id": "basement"},
        "pump": {"area_id": "utility"},
    }
    assert effective_task_area_ids(task, equipment) == ["basement", "utility"]


def test_deleted_or_unavailable_areas_are_omitted():
    task = {"equipment_ids": ["furnace"]}
    equipment = {"furnace": {"area_id": "deleted-area"}}
    assert effective_task_area_ids(task, equipment, {"basement"}) == []


def test_area_groups_duplicate_multiarea_tasks_but_not_within_area():
    tasks = [{
        "task_id": "inspect_system",
        "equipment_ids": ["furnace", "pump"],
        "status": "overdue",
    }]
    equipment = [
        {"equipment_id": "furnace", "name": "Furnace", "area_id": "basement"},
        {"equipment_id": "pump", "name": "Pump", "area_id": "utility"},
    ]
    groups = build_area_groups(tasks, equipment, {
        "basement": "Basement",
        "utility": "Utility Room",
    })
    assert len(groups["basement"]["tasks"]) == 1
    assert len(groups["utility"]["tasks"]) == 1
    assert groups["basement"]["counts"]["overdue"] == 1
    assert groups["utility"]["counts"]["overdue"] == 1


def test_unassigned_group_contains_unassigned_tasks_and_equipment():
    tasks = [{"task_id": "custom_task", "status": "due_today"}]
    equipment = [{"equipment_id": "tool", "name": "Tool", "area_id": None}]
    groups = build_area_groups(tasks, equipment, {})
    assert len(groups["unassigned"]["tasks"]) == 1
    assert len(groups["unassigned"]["equipment"]) == 1
    assert groups["unassigned"]["counts"]["due_today"] == 1

def test_equipment_with_deleted_area_is_grouped_as_unassigned():
    equipment = [{
        "equipment_id": "pump",
        "name": "Sump Pump",
        "area_id": "deleted-area",
    }]
    groups = build_area_groups([], equipment, {}, {"basement"})
    assert len(groups["unassigned"]["equipment"]) == 1
    assert groups["unassigned"]["equipment"][0]["name"] == "Sump Pump"

