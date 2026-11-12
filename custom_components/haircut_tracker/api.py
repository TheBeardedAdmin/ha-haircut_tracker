"""API Client for Haircut Tracker."""
import asyncio
import base64
import json
import logging
import uuid
from datetime import datetime
import aiohttp

_LOGGER = logging.getLogger(__name__)

class HaircutTrackerAPIError(Exception):
    """Exception to indicate an API error."""

class HaircutTrackerAPI:
    """Haircut Tracker API client."""

    API_BASE = "https://api.sportclipsinc.com/api/v1"
    WEB_BASE = "https://www.sportclipsinc.com"

    def __init__(self, session: aiohttp.ClientSession, store_code: str, email: str = None, password: str = None):
        """Initialize the API client."""
        self._session = session
        self.store_code = store_code
        self.email = email
        self.password = password
        self.bearer_token = None
        self.context_token = None

    async def authenticate(self) -> bool:
        """Authenticate using credentials via NextAuth endpoints."""
        if not self.email or not self.password:
            return False

        try:
            # 1. Fetch CSRF token
            csrf_url = f"{self.WEB_BASE}/api/auth/csrf"
            async with self._session.get(csrf_url) as r:
                if r.status != 200:
                    _LOGGER.error("Failed to fetch CSRF: %s", r.status)
                    return False
                csrf_data = await r.json()
                csrf_token = csrf_data.get("csrfToken")

            if not csrf_token:
                _LOGGER.error("No CSRF token found in response")
                return False

            # 2. POST to callback
            signin_url = f"{self.WEB_BASE}/api/auth/callback/credentials-signin"
            payload = {
                "csrfToken": csrf_token,
                "email": self.email,
                "password": self.password,
                "validToken": str(uuid.uuid4()),
                "baseUrl": "https://api.sportclipsinc.com",
                "redirect": "false",
                "callbackUrl": f"{self.WEB_BASE}/login",
                "json": "true"
            }

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Origin": self.WEB_BASE,
                "Referer": f"{self.WEB_BASE}/login"
            }

            async with self._session.post(signin_url, headers=headers, data=payload) as r:
                if r.status != 200:
                    _LOGGER.error("Signin callback failed: %s", r.status)
                    return False
                # Cookies will be automatically stored in the aiohttp ClientSession cookie jar

            # 3. Fetch session to extract Bearer API token
            session_url = f"{self.WEB_BASE}/api/auth/session"
            async with self._session.get(session_url, headers=headers) as r:
                if r.status != 200:
                    _LOGGER.error("Session request failed: %s", r.status)
                    return False
                session_data = await r.json()
                self.bearer_token = session_data.get("accessToken")

            return self.bearer_token is not None

        except Exception as err:
            _LOGGER.error("Authentication error: %s", err)
            return False

    async def get_context_token(self) -> str:
        """Fetch store context token required for stylist endpoints."""
        url = f"{self.API_BASE}/store/select/{self.store_code}"
        headers = {"Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"

        try:
            async with self._session.post(url, headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    self.context_token = data.get("response", {}).get("token")
                    return self.context_token
        except Exception as err:
            _LOGGER.error("Error getting context token: %s", err)
        return None

    async def get_waitboard(self) -> dict:
        """Fetch waitboard and queue list anonymously."""
        url = f"{self.API_BASE}/user/visits/waitBoard/{self.store_code}"
        try:
            async with self._session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("response", {})
        except Exception as err:
            _LOGGER.error("Error fetching waitboard: %s", err)
        return {}

    async def get_stylist_lineup(self) -> dict:
        """Fetch detailed stylist list and wait times (requires auth)."""
        if not self.bearer_token:
            auth_ok = await self.authenticate()
            if not auth_ok:
                raise HaircutTrackerAPIError("Authentication required for stylist lineup")

        if not self.context_token:
            await self.get_context_token()

        url = f"{self.API_BASE}/store/{self.store_code}/service/stylistsAndWaitTimes"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.bearer_token}"
        }
        if self.context_token:
            headers["store-context-token"] = self.context_token

        payload = {"clients": None}
        try:
            async with self._session.post(url, headers=headers, json=payload) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("response", {})
                elif r.status == 401:
                    # Token expired, re-auth once
                    auth_ok = await self.authenticate()
                    if auth_ok:
                        headers["Authorization"] = f"Bearer {self.bearer_token}"
                        async with self._session.post(url, headers=headers, json=payload) as r2:
                            if r2.status == 200:
                                data = await r2.json()
                                return data.get("response", {})
                _LOGGER.error("Failed to fetch stylists: %s", r.status)
        except Exception as err:
            _LOGGER.error("Error fetching stylists: %s", err)
        return {}

    async def get_visit_history(self) -> list:
        """Fetch user past visit history (requires auth)."""
        if not self.bearer_token:
            auth_ok = await self.authenticate()
            if not auth_ok:
                raise HaircutTrackerAPIError("Authentication required for visit history")

        # Pull history from beginning of 2020
        url = f"{self.API_BASE}/user/visits/history?isLastVisits=false&scheduleFromDate=2020-01-01"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.bearer_token}"
        }

        try:
            async with self._session.get(url, headers=headers) as r:
                if r.status == 200:
                    data = await r.json()
                    return data.get("response", [])
                elif r.status == 401:
                    # Token expired, re-auth once
                    auth_ok = await self.authenticate()
                    if auth_ok:
                        headers["Authorization"] = f"Bearer {self.bearer_token}"
                        async with self._session.get(url, headers=headers) as r2:
                            if r2.status == 200:
                                data = await r2.json()
                                return data.get("response", [])
        except Exception as err:
            _LOGGER.error("Error fetching visit history: %s", err)
        return []

    @classmethod
    async def get_all_stores(cls, session: aiohttp.ClientSession) -> list:
        """Fetch list of all stores globally (public endpoint)."""
        url = f"{cls.API_BASE}/store/list"
        try:
            async with session.get(url) as r:
                if r.status == 200:
                    return await r.json()
        except Exception as err:
            _LOGGER.error("Error fetching store list: %s", err)
        return []
