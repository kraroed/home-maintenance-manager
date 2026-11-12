"""Helpers for assigning maintenance tasks to Home Assistant areas.

Home Assistant's area registry remains the source of truth. These helpers
only resolve area IDs from the current equipment and task records.
"""


def _clean_area_id(value):
    """Return a non-empty area ID, or None for missing/invalid values."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def effective_task_area_ids(task, equipment_by_id, valid_area_ids=None):
    """Resolve a task's effective areas.

    Tasks linked to equipment inherit the areas of every linked equipment
    record. A standalone task may use its own area_id. If a valid-area
    collection is supplied, deleted or unavailable areas are omitted.
    """
    equipment_ids = task.get("equipment_ids") or []
    if not equipment_ids and task.get("equipment_id"):
        equipment_ids = [task["equipment_id"]]

    candidates = []
    if equipment_ids:
        for equipment_id in equipment_ids:
            equipment = equipment_by_id.get(equipment_id)
            if equipment:
                candidates.append(equipment.get("area_id"))
    else:
        candidates.append(task.get("area_id"))

    valid = set(valid_area_ids) if valid_area_ids is not None else None
    result = []
    for candidate in candidates:
        area_id = _clean_area_id(candidate)
        if area_id and (valid is None or area_id in valid) and area_id not in result:
            result.append(area_id)
    return result


def build_area_groups(tasks, equipment, area_names, valid_area_ids=None):
    """Build per-area task/equipment groups plus an Unassigned group.

    A task linked to equipment in multiple areas appears in each relevant
    area. Counts are per-area; callers should calculate whole-property totals
    from the original task collection, not by summing these groups.
    """
    valid = set(valid_area_ids) if valid_area_ids is not None else None
    equipment_by_id = {
        item.get("equipment_id"): item
        for item in equipment
        if isinstance(item, dict) and _clean_area_id(item.get("equipment_id"))
    }
    groups = {}

    def ensure_group(area_id):
        key = area_id or "unassigned"
        if key not in groups:
            groups[key] = {
                "area_id": area_id,
                "name": area_names.get(area_id, "Unassigned") if area_id else "Unassigned",
                "equipment": [],
                "tasks": [],
                "counts": {
                    "total": 0,
                    "overdue": 0,
                    "due_today": 0,
                    "due_soon": 0,
                    "scheduled": 0,
                    "not_scheduled": 0,
                },
            }
        return groups[key]

    for item in equipment:
        if not isinstance(item, dict):
            continue
        area_id = _clean_area_id(item.get("area_id"))
        if valid is not None and area_id not in valid:
            area_id = None
        ensure_group(area_id)["equipment"].append(item)

    seen_task_ids = set()
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("task_id")
        if task_id in seen_task_ids:
            continue
        seen_task_ids.add(task_id)
        area_ids = effective_task_area_ids(task, equipment_by_id, valid)
        for area_id in area_ids or [None]:
            group = ensure_group(area_id)
            group["tasks"].append(task)
            group["counts"]["total"] += 1
            status = task.get("status")
            count_key = status if status in {
                "overdue", "due_today", "due_soon", "scheduled", "not_scheduled"
            } else "not_scheduled"
            group["counts"][count_key] += 1

    return groups
