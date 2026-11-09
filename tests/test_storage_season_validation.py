"""Regression tests for malformed stored seasonal window dates."""

import pytest

from custom_components.home_maintenance_manager.storage import MaintenanceStorage


class FakeStore:
    stored = None

    def __init__(self, hass, version, key):
        self.key = key

    async def async_load(self):
        return self.stored

    async def async_save(self, data):
        self.stored = data


@pytest.mark.asyncio
async def test_storage_rejects_invalid_season_window_dates(hass, monkeypatch):
    """Invalid MM-DD values do not replace usable seasonal defaults."""
    FakeStore.stored = {
        "settings": {
            "due_soon_days": True,
            "daily_summary_enabled": False,
            "season_windows": {
                "spring": {"start": "02-30", "end": "05-31"},
                "summer": {"start": "6-01", "end": "08-31"},
                "winter": {"start": "11-16", "end": "02-29"},
            },
        }
    }
    monkeypatch.setattr(
        "custom_components.home_maintenance_manager.storage.Store", FakeStore
    )

    storage = MaintenanceStorage(hass, "invalid-season-dates")
    data = await storage.async_load()

    assert data["settings"]["due_soon_days"] == 7
    assert data["settings"]["daily_summary_enabled"] is False
    assert data["settings"]["season_windows"]["spring"] == {
        "start": "03-15",
        "end": "05-31",
    }
    assert data["settings"]["season_windows"]["summer"] == {
        "start": "06-01",
        "end": "08-31",
    }
    assert data["settings"]["season_windows"]["winter"] == {
        "start": "11-16",
        "end": "02-29",
    }
