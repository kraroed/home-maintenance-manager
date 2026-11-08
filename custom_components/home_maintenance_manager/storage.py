from homeassistant.helpers.storage import Store

from .const import STORAGE_VERSION


def default_data():
    return {
        "tasks": {},
        "equipment": {},
        "history": [],
        "notification_state": {
            "individual": {},
            "summary_date": None,
        },
        "settings": {
            "due_soon_days": 7,
            "daily_summary_enabled": True,
            "individual_notifications_enabled": True,
            "season_windows": {
                "spring": {"start": "03-15", "end": "05-31"},
                "summer": {"start": "06-01", "end": "08-31"},
                "fall": {"start": "09-01", "end": "11-15"},
                "winter": {"start": "11-16", "end": "03-14"},
            },
        },
    }


class MaintenanceStorage:
    def __init__(self, hass, entry_id):
        self.store = Store(
            hass, STORAGE_VERSION, f"home_maintenance_manager_{entry_id}"
        )

    async def async_load(self):
        stored = await self.store.async_load()
        data = default_data()
        if isinstance(stored, dict):
            for key, value in stored.items():
                if key in data and isinstance(value, type(data[key])):
                    data[key] = value
        return data

    async def async_save(self, data):
        await self.store.async_save(data)
