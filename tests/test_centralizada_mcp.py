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

    @unittest.skipUnless(os.getenv("RUN_MCP_INTEGRATION") == "1", "requiere servidor MCP levantado")
    def test_query_against_running_mcp(self):
        result = centralizada.run_agent_mcp("hola")
        self.assertNotIn("MCP_UNAVAILABLE", result)


if __name__ == "__main__":
    unittest.main()
