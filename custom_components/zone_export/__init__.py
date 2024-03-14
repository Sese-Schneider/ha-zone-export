"""Zone Export"""

import logging
from datetime import datetime
import os

import voluptuous as vol
from homeassistant.components.recorder import get_instance, history
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import config_validation as cv
from pytz import timezone


_LOGGER = logging.getLogger(__name__)
_hass: HomeAssistant = None

EXPORT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("person"): cv.entity_id,
        vol.Required("zone"): cv.entity_id,
        vol.Required("date_start"): cv.datetime,
        vol.Required("date_end"): cv.datetime,
    }
)


async def async_setup(hass: HomeAssistant, __: ConfigEntry):
    """Set up entry."""

    coordinator = ZoneExport(hass)

    hass.services.async_register(
        "zone_export", "export", coordinator.handle_export, schema=EXPORT_SERVICE_SCHEMA
    )

    _LOGGER.debug("Setup complete")

    return True


class ZoneExport:
    """Zone Export class."""

    def __init__(self, hass: HomeAssistant):
        """Initialize."""
        self.hass = hass

    async def handle_export(self, call):
        """Handle export service call."""

        person = call.data["person"]
        zone = call.data["zone"]
        date_start: datetime = call.data["date_start"]
        date_end: datetime = call.data["date_end"]

        tz = timezone(self.hass.config.time_zone)

        date_start = date_start.replace(tzinfo=tz)
        date_end = date_end.replace(tzinfo=tz)

        zone_name = zone.split(".")[1].lower()

        _LOGGER.info(
            "Exporting data for person %s in zone %s from %s to %s",
            person,
            self.hass.states.get(zone).name,
            date_start,
            date_end,
        )

        instance = get_instance(self.hass)
        states = await instance.async_add_executor_job(
            self._state_changes_during_period,
            date_start,
            date_end,
            person,
        )

        _LOGGER.debug("Found %s state changes", len(states))

        entered = None
        exited = None
        entries = []

        for i, state in enumerate(states):
            _LOGGER.debug("Parsing: %s", state)

            current = state.state.lower()

            if current == zone_name:
                entered = state.last_changed
                exited = None

            if current != zone_name and states[i - 1].state.lower() == zone_name:
                exited = state.last_changed

            if entered and exited:
                entries.append(
                    {
                        "entered": entered.astimezone(tz),
                        "exited": exited.astimezone(tz),
                    }
                )

                entered = None
                exited = None

        _LOGGER.debug("Parsed %s entries", len(entries))

        csv = "entered date,entered time, exited date, exited time\n"
        for entry in entries:
            _LOGGER.debug(
                "Entered zone '%s' from %s to %s",
                zone_name,
                entry["entered"],
                entry["exited"],
            )
            csv += f"{entry['entered'].strftime('%Y-%m-%d')},{entry['entered'].strftime('%H:%M')},{entry['exited'].strftime('%Y-%m-%d')},{entry['exited'].strftime('%H:%M')}\n"

        directory = "/config/www/tmp"
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(f"{directory}/export.csv", "w", encoding="utf-8") as file:
            file.write(csv)
        _LOGGER.info("Exported to /config/www/tmp/export.csv")

    def _state_changes_during_period(
        self, start: datetime, end: datetime, entity_id: str
    ) -> list[State]:
        """Return state changes during a period."""
        return history.state_changes_during_period(
            self.hass,
            start,
            end,
            entity_id,
            include_start_time_state=True,
            no_attributes=True,
        ).get(entity_id, [])
