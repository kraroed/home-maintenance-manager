"""Export maintenance completion and schedule-change history to CSV and JSON files."""
import csv
import json
from pathlib import Path

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.core import ServiceCall

from .const import DOMAIN

SERVICE_EXPORT_HISTORY = "export_history"
_REMOVED_HISTORY_FIELDS = {
    "attachments", "labor_cost", "parts_cost", "total_cost", "currency",
}


def _clean_record(record):
    """Return an export-safe copy of a history record."""
    return {
        key: value for key, value in record.items()
        if key not in _REMOVED_HISTORY_FIELDS
    }


def _write_history_files(
    directory, history, property_name, export_format, schedule_history=None
):
    """Write selected completion and schedule history formats."""
    directory.mkdir(parents=True, exist_ok=True)
    schedule_history = schedule_history or []
    filenames = []

    if export_format in ("csv", "both"):
        filename = "maintenance_history.csv"
        fields = [
            "property_name", "history_id", "task_id", "task_name", "completed_at",
            "previous_due", "next_due", "notes", "equipment_ids",
        ]
        with (directory / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for record in history:
                row = _clean_record(record)
                row["property_name"] = property_name
                row["equipment_ids"] = json.dumps(row.get("equipment_ids", []))
                writer.writerow(row)
        filenames.append(filename)

        filename = "maintenance_schedule_history.csv"
        fields = [
            "property_name", "task_id", "task_name", "adjusted_at", "change_type", "reason",
            "previous_due", "next_due", "previous_schedule", "new_schedule",
        ]
        with (directory / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for record in schedule_history:
                row = _clean_record(record)
                row["property_name"] = property_name
                for key in ("previous_schedule", "new_schedule"):
                    row[key] = json.dumps(row.get(key, {}), ensure_ascii=False)
                writer.writerow(row)
        filenames.append(filename)

    if export_format in ("json", "both"):
        filename = "maintenance_history.json"
        payload = {
            "property_name": property_name,
            "history_count": len(history),
            "history": [_clean_record(record) for record in history],
        }
        with (directory / filename).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        filenames.append(filename)

        filename = "maintenance_schedule_history.json"
        payload = {
            "property_name": property_name,
            "schedule_history_count": len(schedule_history),
            "schedule_history": [
                _clean_record(record) for record in schedule_history
            ],
        }
        with (directory / filename).open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        filenames.append(filename)

    return filenames


async def async_setup_history_export(hass):
    """Register the history export service once for the integration domain."""
    async def handle_export(call: ServiceCall):
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            return
        export_format = call.data.get("format", "both")
        links = []
        for entry_id, entry_data in entries.items():
            manager = entry_data["manager"]
            property_name = entry_data.get("property_name", "Home")
            schedule_history = []
            for task_id, task in manager.data.get("tasks", {}).items():
                for record in task.get("schedule_history", []):
                    schedule_history.append({
                        "task_id": task_id,
                        "task_name": task.get("name", task_id),
                        **record,
                    })
            directory = Path(hass.config.path("www", DOMAIN, entry_id))
            filenames = await hass.async_add_executor_job(
                _write_history_files,
                directory,
                list(manager.data.get("history", [])),
                property_name,
                export_format,
                schedule_history,
            )
            links.extend(
                f"[{name}](/local/{DOMAIN}/{entry_id}/{name})" for name in filenames
            )
        if links:
            persistent_notification.async_create(
                hass,
                "Maintenance history export complete:\n\n" + "\n".join(links),
                "Home Maintenance Manager export",
                notification_id=f"{DOMAIN}_history_export",
            )

    if not hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY):
        hass.services.async_register(
            DOMAIN,
            SERVICE_EXPORT_HISTORY,
            handle_export,
            schema=vol.Schema({
                vol.Optional("format", default="both"): vol.In(["csv", "json", "both"]),
            }),
        )


async def async_unload_history_export(hass):
    """Remove the registered export service."""
    if hass.services.has_service(DOMAIN, SERVICE_EXPORT_HISTORY):
        hass.services.async_remove(DOMAIN, SERVICE_EXPORT_HISTORY)
