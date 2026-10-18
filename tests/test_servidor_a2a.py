import asyncio
import unittest
from unittest.mock import patch

import httpx

import servidor_a2a


class FakeContext:
    task_id = "task-test"
    context_id = "context-test"

    def __init__(self, text):
        self.text = text

    def get_user_input(self):
        return self.text


class FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


def run(coro):
    return asyncio.run(coro)


class A2AServerTests(unittest.TestCase):
    def test_import_and_card_without_starting_server(self):
        card = servidor_a2a.build_agent_card()
        self.assertEqual(card.name, "Parachute S.A. Central Supervisor")
        self.assertEqual(len(card.skills), 3)
        self.assertEqual([skill.id for skill in card.skills], ["faq", "weather", "scheduling"])

    def test_agent_card_endpoint(self):
        async def request():
            transport = httpx.ASGITransport(app=servidor_a2a.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get("/.well-known/agent-card.json")

        response = run(request())
        self.assertEqual(response.status_code, 200)
        card = response.json()
        self.assertEqual(card["name"], "Parachute S.A. Central Supervisor")
        self.assertEqual(len(card["skills"]), 3)

    def _query(self, text, result):
        queue = FakeQueue()
        executor = servidor_a2a.CentralizedA2AExecutor()
        with patch.object(servidor_a2a.centralizada, "run_agent_mcp_async", return_value=result):
            run(executor.execute(FakeContext(text), queue))
        self.assertEqual(len(queue.events), 1)
        return queue.events[0].parts[0].text

    def _send_http(self, text, result):
        async def request():
            transport = httpx.ASGITransport(app=servidor_a2a.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": "request-1",
                    "method": "SendMessage",
                    "params": {
                        "message": {
                            "messageId": "message-1",
                            "role": "ROLE_USER",
                            "parts": [{"text": text}],
                        }
                    },
                }
                with patch.object(
                    servidor_a2a.centralizada,
                    "run_agent_mcp_async",
                    return_value=result,
                ):
                    return await client.post(
                        "/",
                        json=payload,
                        headers={"A2A-Version": "1.0"},
                    )

        response = run(request())
        self.assertEqual(response.status_code, 200)
        return response.json()["result"]["message"]["parts"][0]["text"]

    def test_faq_query_over_a2a_endpoint(self):
        self.assertEqual(self._send_http("¿Cuál es el horario?", "FAQ OK"), "FAQ OK")

    def test_faq_query(self):
        self.assertEqual(self._query("¿Cuál es el horario?", "FAQ OK"), "FAQ OK")

    def test_weather_query(self):
        self.assertEqual(self._query("¿Cómo estará el clima el 2026-09-20?", "WEATHER OK"), "WEATHER OK")

    def test_schedule_query(self):
        self.assertEqual(self._query("Calendarizar el 2026-09-20", "CITA OK"), "CITA OK")

    def test_mcp_unavailable_is_propagated(self):
        self.assertEqual(
            self._query("¿Cuál es el horario?", "MCP_UNAVAILABLE: servidor no disponible"),
            "MCP_UNAVAILABLE: servidor no disponible",
        )


if __name__ == "__main__":
    unittest.main()
