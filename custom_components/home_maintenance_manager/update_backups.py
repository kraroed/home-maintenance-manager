"""Back up maintenance data when Home Assistant updates become available."""

from datetime import datetime, timezone
import re

from homeassistant.components import persistent_notification
from homeassistant.core import Event
from homeassistant.helpers.event import async_track_state_change_event

from .backup import _backup_directory, _build_payload, _timestamp, _write_json_file
from .const import DOMAIN


def _state_bucket(manager):
    """Return validated per-property update backup tracking state."""
    state = manager.data.setdefault(
        "update_backup_state", {"available": {}, "installations": {}}
    )
    if not isinstance(state, dict):
        state = {"available": {}, "installations": {}}
        manager.data["update_backup_state"] = state
    for key in ("available", "installations"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    return state


def _version(state):
    """Return the update version represented by a Home Assistant update entity."""
    return str(
        state.attributes.get("latest_version")
        or state.attributes.get("installed_version")
        or "unknown"
    )


def async_setup_update_backups(hass, entry, entry_data):
    """Watch selected update entities for availability and installation starts."""
    options = entry.options
    backup_on_available = options.get("update_backup_on_available", False)
    track_installations = options.get("update_install_tracking_enabled", False)
    if not backup_on_available and not track_installations:
        return lambda: None

    selected_entities = set(options.get("update_backup_entities", []))

    async def handle_state_change(event: Event):
        entity_id = event.data.get("entity_id", "")
        if not entity_id.startswith("update."):
            return
        if selected_entities and entity_id not in selected_entities:
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        old_in_progress = (
            old_state.attributes.get("in_progress") is True
            if old_state is not None else False
        )
        in_progress = new_state.attributes.get("in_progress") is True
        manager = entry_data["manager"]
        state = _state_bucket(manager)
        available = state["available"]
        installations = state["installations"]
        version = _version(new_state)

        # Installation has already started. Never create an availability backup
        # here and then incorrectly describe it as a pre-installation backup.
        if in_progress and not old_in_progress:
            if track_installations:
                marker = available.get(entity_id)
                matching_backup = (
                    marker
                    if isinstance(marker, dict)
                    and marker.get("version") == version
                    else None
                )
                started_at = datetime.now(timezone.utc).isoformat()
                installations[entity_id] = {
                    "version": version,
                    "started_at": started_at,
                    "backup_file": (
                        matching_backup.get("filename")
                        if matching_backup else None
                    ),
                }
                await manager.async_save()
                entity_name = new_state.name or entity_id
                if matching_backup:
                    message = (
                        f"{entity_name} ({version}) has started installing. "
                        f"A matching Home Maintenance Manager backup was created "
                        f"when the update became available: {matching_backup['filename']}."
                    )
                else:
                    message = (
                        f"{entity_name} ({version}) has started installing, but no "
                        "matching update-available backup was recorded. The installation "
                        "may already be underway; this notification does not mean a "
                        "backup was completed before it started."
                    )
                slug = re.sub(r"[^A-Za-z0-9_.-]", "_", entity_id)
                persistent_notification.async_create(
                    hass,
                    message,
                    "Home Maintenance Manager update started",
                    notification_id=f"{DOMAIN}_update_started_{slug}",
                )
            return

        if (
            not backup_on_available
            or in_progress
            or new_state.state != "on"
        ):
            return

        # A repeated state refresh for the same version must not create another
        # backup. A newly offered version replaces the previous marker.
        existing = available.get(entity_id)
        if isinstance(existing, dict) and existing.get("version") == version:
            return

        filename = (
            f"home_maintenance_update_{re.sub(r'[^A-Za-z0-9_.-]', '_', entity_id)}_"
            f"{_timestamp()}.json"
        )
        path = _backup_directory(hass, entry.entry_id) / filename
        try:
            payload = _build_payload(entry_data)
            await hass.async_add_executor_job(_write_json_file, path, payload)
        except OSError as err:
            slug = re.sub(r"[^A-Za-z0-9_.-]", "_", entity_id)
            persistent_notification.async_create(
                hass,
                f"Could not create an update-available backup for {entity_id}: {err}",
                "Home Maintenance Manager update backup failed",
                notification_id=f"{DOMAIN}_update_backup_error_{slug}",
            )
            return

        created_at = datetime.now(timezone.utc).isoformat()
        available[entity_id] = {
            "version": version,
            "filename": filename,
            "created_at": created_at,
        }
        await manager.async_save()
        slug = re.sub(r"[^A-Za-z0-9_.-]", "_", entity_id)
        persistent_notification.async_create(
            hass,
            f"Update {version} became available for {entity_id}. "
            f"A Home Maintenance Manager JSON backup was created: {filename}. "
            "This is an early backup; it is not guaranteed to run immediately "
            "before installation.",
            "Home Maintenance Manager update backup",
            notification_id=f"{DOMAIN}_update_backup_{slug}",
        )

    return async_track_state_change_event(
        hass, None, handle_state_change
    )
