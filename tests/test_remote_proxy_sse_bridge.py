"""Tests for the local proxy's polling-to-SSE bridge."""

import importlib.util
from pathlib import Path

import httpx
import pytest

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "remote_proxy" / "voicebox_remote_proxy.py"
spec = importlib.util.spec_from_file_location("voicebox_remote_proxy", MODULE_PATH)
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


@pytest.mark.asyncio
async def test_fetch_speak_poll_uses_cursor_and_returns_json():
    assert hasattr(proxy, "fetch_speak_poll")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/events/speak/poll"
        assert request.url.params["after"] == "7"
        return httpx.Response(200, json={"cursor": 8, "events": [{"sequence": 8, "kind": "speak-end"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        payload = await proxy.fetch_speak_poll(client, "https://example.test", 7)
    finally:
        await client.aclose()

    assert payload["cursor"] == 8
    assert payload["events"][0]["kind"] == "speak-end"
