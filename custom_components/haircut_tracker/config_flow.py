"""Config flow for Haircut Tracker integration."""
from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from typing import Any
from .const import DOMAIN, CONF_STORE_CODE, CONF_STORE_NAME, CONF_EMAIL, CONF_PASSWORD, CONF_FREQUENCY, DEFAULT_FREQUENCY
from .api import HaircutTrackerAPI

class HaircutTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Haircut Tracker."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> HaircutTrackerOptionsFlowHandler:
        """Get the options flow for this handler."""
        return HaircutTrackerOptionsFlowHandler(config_entry)

    def __init__(self):
        """Initialize config flow."""
        self._stores = []
        self._selected_store = None
        self._email = None
        self._password = None
        self._frequency = DEFAULT_FREQUENCY

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial search step."""
        errors = {}

        if user_input is not None:
            search_query = user_input.get("search_query", "").strip().lower()
            if len(search_query) < 2:
                errors["base"] = "search_too_short"
            else:
                # Fetch stores
                session = async_get_clientsession(self.hass)
                stores_list = await HaircutTrackerAPI.get_all_stores(session)
                
                # Filter stores based on search query
                matches = []
                for store in stores_list:
                    search_vector = store.get("searchVector", "").lower()
                    store_name = store.get("storeName", "").lower()
                    short_code = store.get("shortCode", "").lower()
                    address = store.get("address", "").lower()
                    
                    if search_query in search_vector or search_query in store_name or search_query in short_code or search_query in address:
                        matches.append(store)
                
                if not matches:
                    errors["base"] = "no_stores_found"
                else:
                    self._stores = matches
                    return await self.async_step_select_store()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("search_query"): cv.string,
            }),
            errors=errors,
        )

    async def async_step_select_store(self, user_input: dict | None = None) -> FlowResult:
        """Handle selecting store from the search results."""
        errors = {}

        if user_input is not None:
            selected_code = user_input.get("store_code")
            # Find the selected store details
            store_details = next((s for s in self._stores if s["shortCode"] == selected_code), None)
            if store_details:
                self._selected_store = store_details
                return await self.async_step_options()

        # Build selection options
        store_options = {s["shortCode"]: f"{s['storeName']} ({s['shortCode']}) - {s['address']}" for s in self._stores}

        return self.async_show_form(
            step_id="select_store",
            data_schema=vol.Schema({
                vol.Required("store_code"): vol.In(store_options),
            }),
            errors=errors,
        )

    async def async_step_options(self, user_input: dict | None = None) -> FlowResult:
        """Handle optional credentials and settings step."""
        errors = {}

        if user_input is not None:
            self._email = user_input.get(CONF_EMAIL)
            self._password = user_input.get(CONF_PASSWORD)
            self._frequency = user_input.get(CONF_FREQUENCY, DEFAULT_FREQUENCY)

            if self._email and self._password:
                # Validate credentials
                session = async_get_clientsession(self.hass)
                api = HaircutTrackerAPI(session, self._selected_store["shortCode"], self._email, self._password)
                authenticated = await api.authenticate()
                if not authenticated:
                    errors["base"] = "invalid_auth"
                    
            if not errors:
                title = f"{self._selected_store['storeName']} ({self._selected_store['shortCode']})"
                
                # Check unique
                await self.async_set_unique_id(self._selected_store['shortCode'])
                self._async_abort_entries_match()

                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_STORE_CODE: self._selected_store["shortCode"],
                        CONF_STORE_NAME: self._selected_store["storeName"],
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_FREQUENCY: self._frequency,
                    }
                )

        return self.async_show_form(
            step_id="options",
            data_schema=vol.Schema({
                vol.Optional(CONF_EMAIL): cv.string,
                vol.Optional(CONF_PASSWORD): cv.string,
                vol.Required(CONF_FREQUENCY, default=DEFAULT_FREQUENCY): cv.positive_int,
            }),
            errors=errors,
        )


class HaircutTrackerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Haircut Tracker."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_freq = self.config_entry.options.get(
            CONF_FREQUENCY, self.config_entry.data.get(CONF_FREQUENCY, DEFAULT_FREQUENCY)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_FREQUENCY, default=current_freq): cv.positive_int,
            }),
        )
