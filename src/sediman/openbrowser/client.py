from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class OpenBrowserClient:
    """HTTP client for the open-browser REST API server."""

    def __init__(self, base_url: str = "http://127.0.0.1:7788", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/api/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def navigate(self, url: str) -> dict[str, Any]:
        resp = await self._client.post("/api/pages/navigate", json={"url": url})
        return _parse(resp)

    async def reload(self) -> dict[str, Any]:
        resp = await self._client.post("/api/pages/reload")
        return _parse(resp)

    async def current_page(self) -> dict[str, Any]:
        resp = await self._client.get("/api/pages/current")
        return _parse(resp)

    async def html(self) -> dict[str, Any]:
        resp = await self._client.get("/api/pages/html")
        return _parse(resp)

    async def semantic_tree(self, flat: bool = False) -> dict[str, Any]:
        params = {}
        if flat:
            params["format"] = "flat"
        resp = await self._client.get("/api/semantic/tree", params=params)
        return _parse(resp)

    async def semantic_element(self, element_id: int) -> dict[str, Any]:
        resp = await self._client.get(f"/api/semantic/element/{element_id}")
        return _parse(resp)

    async def semantic_stats(self) -> dict[str, Any]:
        resp = await self._client.get("/api/semantic/stats")
        return _parse(resp)

    async def interactive_elements(self) -> dict[str, Any]:
        resp = await self._client.get("/api/interact/elements")
        return _parse(resp)

    async def click(
        self,
        element_id: int | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if element_id is not None:
            body["element_id"] = element_id
        if selector is not None:
            body["selector"] = selector
        resp = await self._client.post("/api/interact/click", json=body)
        return _parse(resp)

    async def type_text(
        self,
        value: str,
        element_id: int | None = None,
        selector: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"value": value}
        if element_id is not None:
            body["element_id"] = element_id
        if selector is not None:
            body["selector"] = selector
        resp = await self._client.post("/api/interact/type", json=body)
        return _parse(resp)

    async def submit(
        self,
        form_selector: str,
        fields: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "form_selector": form_selector,
            "fields": fields or {},
        }
        resp = await self._client.post("/api/interact/submit", json=body)
        return _parse(resp)

    async def scroll(self, direction: str = "down") -> dict[str, Any]:
        resp = await self._client.post("/api/interact/scroll", json={"direction": direction})
        return _parse(resp)

    async def list_tabs(self) -> dict[str, Any]:
        resp = await self._client.get("/api/tabs")
        return _parse(resp)

    async def create_tab(self, url: str) -> dict[str, Any]:
        resp = await self._client.post("/api/tabs", json={"url": url})
        return _parse(resp)

    async def close_tab(self, tab_id: int) -> dict[str, Any]:
        resp = await self._client.delete(f"/api/tabs/{tab_id}")
        return _parse(resp)

    async def activate_tab(self, tab_id: int) -> dict[str, Any]:
        resp = await self._client.post(f"/api/tabs/{tab_id}/activate")
        return _parse(resp)

    async def get_cookies(self) -> dict[str, Any]:
        resp = await self._client.get("/api/cookies")
        return _parse(resp)

    async def set_cookie(
        self,
        name: str,
        value: str,
        domain: str,
        path: str = "/",
    ) -> dict[str, Any]:
        resp = await self._client.post(
            "/api/cookies",
            json={"name": name, "value": value, "domain": domain, "path": path},
        )
        return _parse(resp)

    async def delete_cookie(self, name: str) -> dict[str, Any]:
        resp = await self._client.delete(f"/api/cookies/{name}")
        return _parse(resp)

    async def clear_cookies(self) -> dict[str, Any]:
        resp = await self._client.delete("/api/cookies")
        return _parse(resp)

    async def network_requests(self) -> dict[str, Any]:
        resp = await self._client.get("/api/network/requests")
        return _parse(resp)

    async def network_har(self) -> dict[str, Any]:
        resp = await self._client.get("/api/network/har")
        return _parse(resp)


def _parse(resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code >= 400:
        try:
            body = resp.json()
            return {"ok": False, "error": body.get("error", f"HTTP {resp.status_code}")}
        except Exception:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    try:
        return resp.json()
    except Exception:
        return {"ok": True, "raw": resp.text}
