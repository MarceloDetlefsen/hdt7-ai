"""Smoke test mínimo del cliente MCP Streamable HTTP."""

from __future__ import annotations

import asyncio
import json
import os

from agents.mcp import MCPServerStreamableHttp


URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


async def main() -> None:
    """Lista tools MCP e invoca weather_tool con una fecha de prueba."""
    async with MCPServerStreamableHttp(
        name="Parachute MCP smoke test",
        params={"url": URL, "timeout": float(os.getenv("MCP_TIMEOUT", "10"))},
        cache_tools_list=True,
        max_retry_attempts=1,
    ) as server:
        tools = await server.list_tools()
        print(json.dumps({"url": URL, "tools": [tool.name for tool in tools]}, ensure_ascii=False))
        result = await server.call_tool("weather_tool", {"date": "2026-10-20"})
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
