"""Read-only REST client for the SensoVibe measurement platform.

Uses stdlib urllib rather than an HTTP client library, matching the platform's
own webhook_service.py: this project pins its dependencies tightly and a new
runtime package is not worth a handful of GETs.

Only GET is implemented, plus the one POST needed to log in. That is not a
convenience - it is the reason this client is safe to hand to an agent. Even if
the model were persuaded to ask for a deletion, there is no method here that
could perform one.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from sql_agent.config import (
    PLATFORM_BASE_URL,
    PLATFORM_EMAIL,
    PLATFORM_PASSWORD,
    PLATFORM_TIMEOUT_S,
)

logger = logging.getLogger(__name__)


class PlatformError(RuntimeError):
    """The platform could not be reached, or refused the request."""


class PlatformAuthError(PlatformError):
    """Credentials were missing, wrong, or the account is inactive."""


def _request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = PLATFORM_TIMEOUT_S,
) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code in (401, 403):
            raise PlatformAuthError(
                f"{method} {url} -> {exc.code}. The platform rejected the credentials "
                f"or the account lacks permission. {detail}"
            ) from exc
        raise PlatformError(f"{method} {url} -> {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise PlatformError(
            f"Cannot reach the platform at {PLATFORM_BASE_URL} ({exc.reason}). "
            "Is the backend running?"
        ) from exc

    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - platform contract break
        raise PlatformError(f"{method} {url} returned non-JSON: {raw[:200]!r}") from exc


class PlatformClient:
    """Authenticated read-only access to the measurement API.

    The access token is short-lived (30 minutes on the platform), so rather than
    tracking expiry we let a 401 drive re-authentication: any call that comes
    back unauthorised is retried once with a fresh token. That handles clock
    skew and a server restart without a scheduler.
    """

    def __init__(
        self,
        base_url: str = PLATFORM_BASE_URL,
        email: str = PLATFORM_EMAIL,
        password: str = PLATFORM_PASSWORD,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self._token: str | None = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- auth --

    def login(self) -> str:
        if not self.password:
            raise PlatformAuthError(
                "PLATFORM_PASSWORD is not set. Add it to .env - the bot needs a "
                "read-only platform login to read sensor data."
            )
        payload = _request(
            "POST",
            f"{self.base_url}/api/v1/auth/login",
            body={"email": self.email, "password": self.password},
        )
        token = (payload or {}).get("access_token")
        if not token:
            raise PlatformAuthError("Login succeeded but returned no access_token.")
        logger.info("Authenticated to platform as %s", self.email)
        return token

    def _ensure_token(self) -> str:
        with self._lock:
            if self._token is None:
                self._token = self.login()
            return self._token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = ""
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                query = "?" + urllib.parse.urlencode(clean)
        url = f"{self.base_url}{path}{query}"

        token = self._ensure_token()
        try:
            return _request("GET", url, token=token)
        except PlatformAuthError:
            # Token expired or revoked - re-authenticate once, then give up.
            with self._lock:
                self._token = None
            token = self._ensure_token()
            return _request("GET", url, token=token)

    # ------------------------------------------------------------ read API --

    def whoami(self) -> dict[str, Any]:
        return self._get("/api/v1/auth/me")

    def list_equipment(self, page_size: int = 100) -> list[dict[str, Any]]:
        """Every machine, following pagination to the end."""
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._get(
                "/api/v1/equipment/", {"page": page, "page_size": page_size}
            )
            batch = (payload or {}).get("items") or []
            items.extend(batch)
            total = (payload or {}).get("total", len(items))
            if len(items) >= total or not batch:
                break
            page += 1
        return items

    def get_equipment(self, equipment_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/equipment/{equipment_id}")

    def list_sensors(self, equipment_id: str) -> list[dict[str, Any]]:
        return self._get(f"/api/v1/equipment/{equipment_id}/sensors") or []

    def list_uploads(
        self,
        sensor_id: str,
        *,
        limit: int,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Captures for one sensor, newest first, capped at ``limit``.

        Returns the rows and the platform's own total, so the caller can say how
        much history was left behind rather than implying the export is complete.
        """
        items: list[dict[str, Any]] = []
        page = 1
        page_size = min(200, max(1, limit))
        total = 0
        while len(items) < limit:
            payload = self._get(
                "/api/v1/measurements/uploads",
                {
                    "sensor_id": sensor_id,
                    "page": page,
                    "page_size": page_size,
                    "from_date": from_date,
                    "to_date": to_date,
                },
            )
            batch = (payload or {}).get("items") or []
            total = (payload or {}).get("total", total)
            if not batch:
                break
            items.extend(batch)
            if len(items) >= total:
                break
            page += 1
        return items[:limit], total

    def get_upload_features(self, upload_id: str) -> list[dict[str, Any]]:
        payload = self._get(f"/api/v1/measurements/uploads/{upload_id}/features")
        return (payload or {}).get("items") or []

    def get_plot_config(self, sensor_id: str) -> dict[str, Any] | None:
        try:
            return self._get(f"/api/v1/measurements/configure/{sensor_id}")
        except PlatformError:
            # 404 is normal - a sensor that has never been configured.
            return None

    def get_baselines(self, sensor_id: str) -> list[dict[str, Any]]:
        try:
            payload = self._get(f"/api/v1/sensors/{sensor_id}/baselines")
        except PlatformError:
            return []
        if isinstance(payload, dict):
            return payload.get("items") or []
        return payload or []


platform_client = PlatformClient()
