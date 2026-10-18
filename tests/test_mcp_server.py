import asyncio
import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import mcp_server
from shared import parachute


def call_tool(name, arguments):
    return getattr(mcp_server, name)(**arguments)


def text_result(result):
    if isinstance(result, str):
        return json.loads(result)
    return json.loads(result.content[0].text)


class McpContractTests(unittest.TestCase):
    def test_tools_are_registered(self):
        tools = asyncio.run(mcp_server.server.list_tools())
        self.assertEqual(
            {tool.name for tool in tools},
            {"faq_tool", "weather_tool", "schedule_tool"},
        )

    def test_weather_accepts_valid_date_with_fixture(self):
        fixture = {
            "temperature_c": 25,
            "precipitation_mm": 0,
            "cloud_cover_pct": 10,
            "visibility_m": 10000,
            "wind_speed_kmh": 10,
            "wind_gust_kmh": 20,
        }
        with parachute.evaluation_dependencies(
            today=date(2026, 10, 1), weather_fixture=fixture
        ):
            result = text_result(call_tool("weather_tool", {"date": "2026-10-02"}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["decision"], "IDEAL")

    def test_weather_rejects_invalid_date(self):
        result = text_result(call_tool("weather_tool", {"date": "2026-99-99"}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")

    def test_schedule_persists_approved_fixture(self):
        fixture = {
            "temperature_c": 25,
            "precipitation_mm": 0,
            "cloud_cover_pct": 10,
            "visibility_m": 10000,
            "wind_speed_kmh": 10,
            "wind_gust_kmh": 20,
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "citas.json"
            with patch.object(parachute, "APPOINTMENTS_PATH", path):
                with parachute.evaluation_dependencies(
                    today=date(2026, 10, 1), weather_fixture=fixture
                ):
                    result = text_result(
                        call_tool("schedule_tool", {"date": "2026-10-02"})
                    )
            self.assertTrue(result["ok"])
            self.assertTrue(result["data"]["scheduled"])
            self.assertEqual(len(json.loads(path.read_text())), 1)

    def test_schedule_rejects_unsafe_fixture(self):
        fixture = {
            "temperature_c": 25,
            "precipitation_mm": 0,
            "cloud_cover_pct": 10,
            "visibility_m": 10000,
            "wind_speed_kmh": 30,
            "wind_gust_kmh": 40,
        }
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "citas.json"
            with patch.object(parachute, "APPOINTMENTS_PATH", path):
                with parachute.evaluation_dependencies(
                    today=date(2026, 10, 1), weather_fixture=fixture
                ):
                    result = text_result(
                        call_tool("schedule_tool", {"date": "2026-10-02"})
                    )
            self.assertTrue(result["ok"])
            self.assertFalse(result["data"]["scheduled"])
            self.assertEqual(result["data"]["decision"], "NO SEGURO / PROHIBIDO")
            self.assertFalse(path.exists())

    def test_faq_rejects_empty_question(self):
        result = text_result(call_tool("faq_tool", {"question": "  "}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "INVALID_ARGUMENT")


if __name__ == "__main__":
    unittest.main()
