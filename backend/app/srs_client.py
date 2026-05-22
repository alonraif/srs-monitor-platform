import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import get_settings


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class SrsApiSnapshot:
    base_url: str
    reachable: bool
    responses: dict[str, JsonObject] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)


class SrsApiClient:
    # SRS exposes these HTTP API resources in the v1 API. Collection endpoints
    # commonly redirect to trailing-slash URLs, so the HTTP client follows redirects.
    ENDPOINTS = {
        "summaries": "/api/v1/summaries",
        # Explicitly request larger pages to avoid default server-side limits.
        "vhosts": "/api/v1/vhosts/?start=0&count=1000",
        "streams": "/api/v1/streams/?start=0&count=1000",
        "clients": "/api/v1/clients/?start=0&count=1000",
    }

    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.srs_api_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.srs_api_timeout_seconds
        self.username = settings.srs_api_username.strip()
        self.password = settings.srs_api_password

    async def fetch_snapshot(self) -> SrsApiSnapshot:
        auth: tuple[str, str] | None = None
        if self.username:
            auth = (self.username, self.password)
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            auth=auth,
        ) as client:
            tasks = {
                name: self._fetch_json(client, path)
                for name, path in self.ENDPOINTS.items()
            }
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        responses: dict[str, JsonObject] = {}
        errors: dict[str, str] = {}
        for name, result in zip(tasks.keys(), results, strict=True):
            if isinstance(result, Exception):
                errors[name] = str(result)
                continue
            # SRS uses code=0 for successful API responses. Non-zero codes
            # are still useful debug payloads, so preserve them and mark only
            # that endpoint as degraded.
            if result.get("code") not in (None, 0):
                errors[name] = f"SRS API returned code={result.get('code')}"
            responses[name] = result

        return SrsApiSnapshot(
            base_url=self.base_url,
            reachable=bool(responses),
            responses=responses,
            errors=errors,
        )

    async def _fetch_json(self, client: httpx.AsyncClient, path: str) -> JsonObject:
        url = f"{self.base_url}{path}"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"SRS endpoint {path} returned non-object JSON")
        return data


async def fetch_srs_snapshot() -> SrsApiSnapshot:
    return await SrsApiClient().fetch_snapshot()
