from dataclasses import dataclass
from typing import Any

import httpx

from .config import get_settings


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class PreviewServiceResult:
    ok: bool
    reachable: bool
    status_code: int
    data: JsonObject
    error: str | None = None


class PreviewServiceClient:
    def __init__(self, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.preview_service_url).rstrip("/")
        self.timeout_seconds = timeout_seconds or settings.srs_api_timeout_seconds

    async def start(
        self,
        stream_id: str,
        input_url: str,
        input_protocol: str,
        inactivity_timeout_seconds: int,
    ) -> PreviewServiceResult:
        payload = {
            "stream_id": stream_id,
            "input_url": input_url,
            "input_protocol": input_protocol,
            "preferred_output": "hls",
            "inactivity_timeout_seconds": inactivity_timeout_seconds,
        }
        return await self._request("POST", "/preview/start", json=payload)

    async def stop(self, stream_id: str) -> PreviewServiceResult:
        return await self._request("POST", "/preview/stop", json={"stream_id": stream_id})

    async def status(self) -> PreviewServiceResult:
        return await self._request("GET", "/preview/status")

    async def status_one(self, stream_id: str) -> PreviewServiceResult:
        return await self._request("GET", f"/preview/status/{stream_id}")

    async def _request(self, method: str, path: str, json: JsonObject | None = None) -> PreviewServiceResult:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(method=method, url=url, json=json)
            payload = response.json() if response.content else {}
            if not isinstance(payload, dict):
                payload = {"raw": payload}
            return PreviewServiceResult(
                ok=response.is_success,
                reachable=True,
                status_code=response.status_code,
                data=payload,
                error=None if response.is_success else payload.get("detail", f"http_{response.status_code}"),
            )
        except Exception as exc:
            return PreviewServiceResult(
                ok=False,
                reachable=False,
                status_code=0,
                data={},
                error=str(exc),
            )
