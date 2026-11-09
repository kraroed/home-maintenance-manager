"""Full JSON backup and guarded restore services for Home Maintenance Manager."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN

SERVICE_CREATE_BACKUP = "create_backup"
SERVICE_PREVIEW_RESTORE = "preview_restore"
SERVICE_RESTORE_BACKUP = "restore_backup"
BACKUP_FORMAT = "home_maintenance_manager_backup"
BACKUP_SCHEMA_VERSION = 1
MAX_BACKUP_BYTES = 10 * 1024 * 1024
_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.json$")


def _backup_directory(hass, entry_id):
    return Path(hass.config.path("www", DOMAIN, entry_id))


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _build_payload(entry_data):
    entry = entry_data["config_entry"]
    manager = entry_data["manager"]
    return {
        "format": BACKUP_FORMAT,
        "schema_version": BACKUP_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "property_name": entry_data.get("property_name", entry.title),
        "entry_data": deepcopy(entry.data),
        "options": deepcopy(entry.options),
        "data": deepcopy(manager.data),
    }


def _write_json_file(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
    temporary.replace(path)


def _read_json_file(path):
    if not path.is_file():
        raise HomeAssistantError(f"Backup file was not found: {path.name}")
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise HomeAssistantError("Backup file is larger than the 10 MB limit.")
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        raise HomeAssistantError("The selected backup is not valid JSON.") from err
    return _validate_payload(payload)


def _validate_payload(payload):
    if not isinstance(payload, dict):
        raise HomeAssistantError("Backup must contain a JSON object.")
    if payload.get("format") != BACKUP_FORMAT:
        raise HomeAssistantError("This file is not a Home Maintenance Manager backup.")
    if payload.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise HomeAssistantError("This backup version is not supported by this integration.")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise HomeAssistantError("Backup is missing its maintenance data.")
    if not isinstance(data.get("tasks"), dict) or not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in data["tasks"].items()
    ):
        raise HomeAssistantError("Backup contains an invalid task collection.")
    if not isinstance(data.get("equipment"), dict) or not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in data["equipment"].items()
    ):
        raise HomeAssistantError("Backup contains an invalid equipment collection.")
    if not isinstance(data.get("history"), list) or not all(
        isinstance(item, dict) for item in data["history"]
    ):
        raise HomeAssistantError("Backup contains an invalid completion history.")
    if not isinstance(data.get("settings"), dict):
        raise HomeAssistantError("Backup is missing its settings.")
    notification_state = data.get("notification_state", {})
    if not isinstance(notification_state, dict):
        raise HomeAssistantError("Backup contains invalid notification state.")
    if not isinstance(notification_state.get("individual", {}), dict):
        raise HomeAssistantError("Backup contains invalid reminder delivery state.")
    if not isinstance(payload.get("options", {}), dict):
        raise HomeAssistantError("Backup contains invalid integration options.")
    if not isinstance(payload.get("entry_data", {}), dict):
        raise HomeAssistantError("Backup contains invalid property configuration.")
    return payload


def _safe_filename(filename):
    if not isinstance(filename, str) or not _FILENAME_RE.fullmatch(filename):
        raise HomeAssistantError(
            "Use a JSON filename containing only letters, numbers, dots, underscores, or hyphens."
        )
    return filename


def _merge_history(current, incoming):
    """Restore missing history while retaining every record already on this system."""
    merged = deepcopy(current)
    known_ids = {
        item.get("history_id") for item in merged if item.get("history_id")
    }
    for record in incoming:
        record_id = record.get("history_id")
        if not record_id or record_id not in known_ids:
            merged.append(deepcopy(record))
            if record_id:
                known_ids.add(record_id)
    return merged


def _matching_entries(hass, instance):
    entries = hass.data.get(DOMAIN, {})
    if instance:
        matches = [
            (entry_id, data) for entry_id, data in entries.items()
            if entry_id == instance or data["manager"].storage.store.key == instance
        ]
    else:
        matches = list(entries.items())
    if not matches:
        raise HomeAssistantError("No loaded Home Maintenance Manager property matches this request.")
    if len(matches) != 1:
        raise HomeAssistantError(
            "More than one property is configured. Provide integration_instance to select one."
        )
    return matches[0]


async def async_setup_backup_services(hass):
    """Register JSON backup, preview, and confirmed restore actions."""

    async def create_backup(call: ServiceCall):
        entries = hass.data.get(DOMAIN, {})
        instance = call.data.get("integration_instance")
        selected = (
            [_matching_entries(hass, instance)]
            if instance else list(entries.items())
        )
        links = []
        for entry_id, entry_data in selected:
            filename = f"home_maintenance_backup_{_timestamp()}.json"
            path = _backup_directory(hass, entry_id) / filename
            payload = _build_payload(entry_data)
            await hass.async_add_executor_job(_write_json_file, path, payload)
            links.append(f"[{entry_data.get('property_name', 'Home')}: {filename}]"
                         f"(/local/{DOMAIN}/{entry_id}/{filename})")
        if links:
            persistent_notification.async_create(
                hass,
                "Complete JSON backup created:\n\n" + "\n".join(links),
                "Home Maintenance Manager backup",
                notification_id=f"{DOMAIN}_backup",
            )

    async def preview_restore(call: ServiceCall):
        entry_id, entry_data = _matching_entries(
            hass, call.data.get("integration_instance")
        )
        filename = _safe_filename(call.data["filename"])
        path = _backup_directory(hass, entry_id) / filename
        payload = await hass.async_add_executor_job(_read_json_file, path)
        data = payload["data"]
        current_history = entry_data["manager"].data.get("history", [])
        incoming_history = data["history"]
        new_history = _merge_history(current_history, incoming_history)
        message = (
            f"Backup for **{payload.get('property_name', 'Unknown property')}** is valid.\n\n"
            f"- Tasks in backup: {len(data['tasks'])}\n"
            f"- Equipment records: {len(data['equipment'])}\n"
            f"- Completion records in backup: {len(incoming_history)}\n"
            f"- Existing completion records preserved: {len(current_history)}\n"
            f"- Additional history records to import: {len(new_history) - len(current_history)}\n\n"
            "No data has been changed. To apply it, run **restore_backup** with the same "
            "filename and set **confirm** to true. Restore also creates an automatic "
            "pre-restore JSON backup."
        )
        persistent_notification.async_create(
            hass, message, "Home Maintenance Manager restore preview",
            notification_id=f"{DOMAIN}_restore_preview",
        )

    async def restore_backup(call: ServiceCall):
        if not call.data["confirm"]:
            raise HomeAssistantError(
                "Restore was not applied. Set confirm to true after reviewing the preview."
            )
        entry_id, entry_data = _matching_entries(
            hass, call.data.get("integration_instance")
        )
        filename = _safe_filename(call.data["filename"])
        path = _backup_directory(hass, entry_id) / filename
        payload = await hass.async_add_executor_job(_read_json_file, path)
        manager = entry_data["manager"]
        restored = deepcopy(payload["data"])
        restored.setdefault("notification_state", {"individual": {}, "summary_date": None})
        restored["history"] = _merge_history(
            manager.data.get("history", []), restored["history"]
        )

        # Persist a safety copy of the current state before touching live storage.
        safety_filename = f"home_maintenance_pre_restore_{_timestamp()}.json"
        safety_path = _backup_directory(hass, entry_id) / safety_filename
        safety_payload = _build_payload(entry_data)
        await hass.async_add_executor_job(
            _write_json_file, safety_path, safety_payload
        )

        options = deepcopy(payload.get("options", {}))
        entry_data_value = deepcopy(payload.get("entry_data", {}))
        await manager.storage.async_save(restored)
        manager.data = restored
        manager.enabled_ids = set(options.get(
            "enabled_task_ids",
            entry_data_value.get("enabled_task_ids", manager.enabled_ids),
        ))
        manager.task_intervals = options.get("task_intervals", {})
        manager.equipment_records = options.get("equipment_records", [])
        manager.season_windows = options.get("season_windows", {})
        manager.library.update({
            item["task_id"]: deepcopy(item)
            for item in options.get("custom_tasks", [])
            if isinstance(item, dict) and isinstance(item.get("task_id"), str)
        })

        entry = entry_data["config_entry"]
        hass.config_entries.async_update_entry(
            entry,
            data=entry_data_value,
            options=options,
            title=payload.get("property_name", entry.title),
        )
        entry_data["property_name"] = payload.get("property_name", entry.title)
        await entry_data["coordinator"].async_request_refresh()
        persistent_notification.async_create(
            hass,
            "Restore completed. Existing completion history was retained and missing "
            f"backup records were imported. A pre-restore backup is available as "
            f"{safety_filename}.",
            "Home Maintenance Manager restore complete",
            notification_id=f"{DOMAIN}_restore_complete",
        )

    if not hass.services.has_service(DOMAIN, SERVICE_CREATE_BACKUP):
        hass.services.async_register(
            DOMAIN, SERVICE_CREATE_BACKUP, create_backup,
            schema=vol.Schema({
                vol.Optional("integration_instance"): str,
            }),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_PREVIEW_RESTORE):
        hass.services.async_register(
            DOMAIN, SERVICE_PREVIEW_RESTORE, preview_restore,
            schema=vol.Schema({
                vol.Required("filename"): str,
                vol.Optional("integration_instance"): str,
            }),
        )
    if not hass.services.has_service(DOMAIN, SERVICE_RESTORE_BACKUP):
        hass.services.async_register(
            DOMAIN, SERVICE_RESTORE_BACKUP, restore_backup,
            schema=vol.Schema({
                vol.Required("filename"): str,
                vol.Required("confirm", default=False): bool,
                vol.Optional("integration_instance"): str,
            }),
        )


async def async_unload_backup_services(hass):
    """Remove backup services after the final config entry is unloaded."""
    for service in (
        SERVICE_CREATE_BACKUP,
        SERVICE_PREVIEW_RESTORE,
        SERVICE_RESTORE_BACKUP,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)
