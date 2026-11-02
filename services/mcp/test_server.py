"""Protocol and HTTP authorization tests run in the optional MCP service environment."""

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx2
from mcp import Client
from server import Settings, create_server, http_app


class MCPTests(unittest.IsolatedAsyncioTestCase):
    """Use the real MCP SDK and ASGI transport with an isolated backend authorization boundary."""

    async def asyncSetUp(self):
        self.tenant = str(uuid4())
        self.token = f"dta_{self.tenant}_fixture-secret"
        self.settings = Settings(
            "https://api.fixture.test",
            resource_url="https://mcp.fixture.test/mcp",
            issuer_url="https://api.fixture.test",
        )
        self.active, self.write = True, False
        self.resource = self.settings.resource_url
        self.calls = []

        def backend(request):
            self.calls.append(request)
            if (
                not self.active
                or request.headers["Authorization"] != "Bearer " + self.token
                or request.headers["X-Tenant-ID"] != self.tenant
            ):
                return httpx2.Response(401)
            path = request.url.path
            if path.endswith("/me"):
                return httpx2.Response(
                    200,
                    json={
                        "tenant_id": self.tenant,
                        "user_id": str(uuid4()),
                        "role": "owner",
                        "can_write_policy": self.write,
                        "resource": self.resource,
                        "expires_at": (
                            datetime.now(timezone.utc) + timedelta(minutes=5)
                        ).isoformat(),
                    },
                )
            if path.endswith("/policy"):
                return httpx2.Response(200 if self.write else 403, json={"revision": 2})
            if path.endswith("/experiments"):
                return httpx2.Response(200, json=[])
            return httpx2.Response(200, json={"counts": {"attempts": 3}})

        self.transport = httpx2.MockTransport(backend)

    async def test_tools_use_backend_permissions_on_every_call(self):
        server = create_server(self.settings, stdio_token=self.token, transport=self.transport)
        async with Client(server, raise_exceptions=True) as client:
            listed = await client.list_tools()
            self.assertEqual(
                {tool.name for tool in listed.tools},
                {"get_usage", "get_session", "list_experiments", "set_policy"},
            )
            result = await client.call_tool("get_usage", {"filters": {"work_item": "TA1"}})
            self.assertFalse(result.is_error)
            self.assertEqual(self.calls[-1].url.params["work_item"], "TA1")
            result = await client.call_tool("get_session", {"session_id": "session-a"})
            self.assertFalse(result.is_error)
            self.assertTrue(
                (await client.call_tool("set_policy", {"config": {}, "revision": 1})).is_error
            )
            self.write = True
            self.assertFalse(
                (await client.call_tool("set_policy", {"config": {}, "revision": 1})).is_error
            )
            self.active = False
            self.assertTrue((await client.call_tool("get_usage", {})).is_error)

    async def test_http_authentication_audience_and_revocation(self):
        app = http_app(self.settings, self.transport)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "fixture", "version": "1"},
            },
        }
        headers = {"Accept": "application/json, text/event-stream"}
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url="https://mcp.fixture.test"
            ) as client:
                self.assertEqual(
                    (await client.post("/mcp", json=payload, headers=headers)).status_code, 401
                )
                headers["Authorization"] = "Bearer " + self.token
                response = await client.post("/mcp", json=payload, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.resource = "https://another.fixture.test/mcp"
                self.assertEqual(
                    (await client.post("/mcp", json=payload, headers=headers)).status_code, 401
                )
                self.resource = self.settings.resource_url
                self.active = False
                self.assertEqual(
                    (await client.post("/mcp", json=payload, headers=headers)).status_code, 401
                )


if __name__ == "__main__":
    unittest.main()
