import asyncio
import os
import unittest
from unittest.mock import patch

import centralizada
from agents.mcp import MCPServerStreamableHttp


class CentralizadaMcpTests(unittest.TestCase):
    def test_mcp_supervisor_receives_mcp_server(self):
        mcp_server = MCPServerStreamableHttp(
            name="test",
            params={"url": "http://127.0.0.1:9/mcp", "timeout": 0.1},
        )
        supervisor = centralizada.build_mcp_agents(mcp_server)
        self.assertIs(supervisor._parachute_mcp_server, mcp_server)
        self.assertEqual(
            [worker.mcp_servers[0] for worker in supervisor._parachute_mcp_workers],
            [mcp_server, mcp_server, mcp_server],
        )

    def test_local_mode_keeps_supervisor_and_public_worker_tools(self):
        supervisor = centralizada.build_local_agents()
        self.assertEqual(supervisor.name, "SupervisorCentral")
        self.assertEqual(
            {tool.name for tool in supervisor.tools},
            {"consultar_clima", "consultar_faq", "calendarizar_cita"},
        )

    def test_mcp_unavailable_returns_explicit_error(self):
        with patch.object(centralizada, "MCP_SERVER_URL", "http://127.0.0.1:9/mcp"), patch.object(
            centralizada, "MCP_TIMEOUT", 0.1
        ):
            result = asyncio.run(centralizada.run_agent_mcp_async("hola"))
        self.assertIn("MCP_UNAVAILABLE", result)

    def test_mcp_discovery_retries_transient_failure(self):
        class FakeServer:
            def __init__(self):
                self.attempts = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def list_tools(self):
                self.attempts += 1
                if self.attempts == 1:
                    raise RuntimeError("HTTP 500 durante inicialización")
                return [type("Tool", (), {"name": "faq_tool"})()]

        fake = FakeServer()
        with patch.object(centralizada, "MCPServerStreamableHttp", return_value=fake), patch.object(
            centralizada, "MCP_MAX_RETRIES", 1
        ):
            async def exercise():
                async with centralizada.connected_mcp_server() as server:
                    self.assertIs(server, fake)

            asyncio.run(exercise())
        self.assertEqual(fake.attempts, 2)

    @unittest.skipUnless(os.getenv("RUN_MCP_INTEGRATION") == "1", "requiere servidor MCP levantado")
    def test_query_against_running_mcp(self):
        for query in ("hola", "¿Qué servicios ofrece Parachute S.A.?"):
            result = centralizada.run_agent_mcp(query)
            self.assertNotIn("MCP_UNAVAILABLE", result)


if __name__ == "__main__":
    unittest.main()
