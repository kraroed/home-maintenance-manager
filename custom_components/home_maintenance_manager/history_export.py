"""Export maintenance completion history to CSV and JSON files."""
import csv
import json
from pathlib import Path

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.core import ServiceCall

from .const import DOMAIN

SERVICE_EXPORT_HISTORY = "export_history"

def _write_history_files(directory, history, property_name, export_format):
    """Write selected history formats and return their filenames."""
    directory.mkdir(parents=True, exist_ok=True)
    filenames = []
    if export_format in ("csv", "both"):
        filename = "maintenance_history.csv"
        fields = [
            "history_id", "task_id", "task_name", "completed_at",
            "previous_due", "next_due", "notes", "equipment_ids",
        ]
        with (directory / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for record in history:
                row = {
                    key: value for key, value in record.items()
                    if key not in {"attachments", "labor_cost", "parts_cost", "total_cost", "currency"}
                }
                row["equipment_ids"] = json.dumps(row.get("equipment_ids", []))
                writer.writerow(row)
        filenames.append(filename)
    if export_format in ("json", "both"):
        filename = "maintenance_history.json"
        payload = {
            "property_name": property_name,
            "history_count": len(history),
            "history": [
                {
                    key: value for key, value in record.items()
                    if key not in {"attachments", "labor_cost", "parts_cost", "total_cost", "currency"}
                }
                for record in history
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
            directory = Path(hass.config.path("www", DOMAIN, entry_id))
            filenames = await hass.async_add_executor_job(
                _write_history_files,
                directory,
                list(manager.data.get("history", [])),
                property_name,
                export_format,
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
