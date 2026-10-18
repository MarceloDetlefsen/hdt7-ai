import asyncio
import importlib
import inspect
import os
import unittest
from unittest.mock import AsyncMock, patch

from a2a.client import AgentCardResolutionError
from a2a.types import Message, Part, Role, StreamResponse, TaskState, TaskStatus, TaskStatusUpdateEvent

import cliente_a2a


def run(coro):
    return asyncio.run(coro)


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def send_message(self, request):
        self.requests.append(request)

        async def iterator():
            for response in self.responses:
                yield response

        return iterator()

    def close(self):
        return None


class A2AClientTests(unittest.TestCase):
    def test_import_does_not_connect_or_import_local_supervisor(self):
        module = importlib.reload(cliente_a2a)
        source = inspect.getsource(module)
        self.assertNotIn("import centralizada", source)
        self.assertNotIn("shared.parachute", source)

    def test_url_uses_environment(self):
        with patch.dict(os.environ, {"A2A_SERVER_URL": "http://example.test/"}):
            self.assertEqual(cliente_a2a.server_url(), "http://example.test")

    def test_server_unavailable(self):
        with patch.object(cliente_a2a, "create_a2a_client", side_effect=cliente_a2a.httpx.ConnectError("offline")):
            self.assertEqual(run(cliente_a2a.run_session("hola")), 1)

    def test_invalid_agent_card(self):
        error = AgentCardResolutionError("invalid card")
        with patch.object(cliente_a2a, "create_a2a_client", side_effect=error):
            self.assertEqual(run(cliente_a2a.run_session("hola")), 1)

    def test_processes_simulated_message(self):
        response = StreamResponse(message=Message(role=Role.ROLE_AGENT, parts=[Part(text="Respuesta")]))
        context = {}
        self.assertEqual(run(cliente_a2a.process_response(response, context)), "Respuesta")

    def test_processes_failed_task(self):
        status = TaskStatus(state=TaskState.TASK_STATE_FAILED)
        response = StreamResponse(status_update=TaskStatusUpdateEvent(task_id="t", context_id="c", status=status))
        with self.assertRaises(RuntimeError):
            run(cliente_a2a.process_response(response, {}))

    def test_sends_query_with_user_role(self):
        client = FakeClient([StreamResponse(message=Message(role=Role.ROLE_AGENT, parts=[Part(text="OK")]))])
        context = {}
        self.assertEqual(run(cliente_a2a.send_query(client, "Hola", context)), "OK")
        self.assertEqual(client.requests[0].message.role, Role.ROLE_USER)
        self.assertEqual(client.requests[0].message.parts[0].text, "Hola")

    def test_create_client_is_awaited_and_sync_close_is_supported(self):
        card = type("Card", (), {"name": "agent", "supported_interfaces": [object()]})()
        fake_client = FakeClient(
            [StreamResponse(message=Message(role=Role.ROLE_AGENT, parts=[Part(text="OK")]))]
        )

        class FakeResolver:
            def __init__(self, **kwargs):
                pass

            async def get_agent_card(self):
                return card

        async def exercise():
            with patch.object(cliente_a2a, "A2ACardResolver", FakeResolver), patch.object(
                cliente_a2a, "create_client", new=AsyncMock(return_value=fake_client)
            ) as factory:
                async with cliente_a2a.httpx.AsyncClient() as http_client:
                    resolved = await cliente_a2a.create_a2a_client(http_client)
                    self.assertIs(resolved, fake_client)
                    factory.assert_awaited_once()
                    result = await cliente_a2a.send_query(resolved, "Hola", {})
                    self.assertEqual(result, "OK")
                    close_result = resolved.close()
                    self.assertIsNone(close_result)

        run(exercise())

    def test_run_session_accepts_synchronous_close(self):
        client = FakeClient(
            [StreamResponse(message=Message(role=Role.ROLE_AGENT, parts=[Part(text="OK")]))]
        )
        with patch.object(cliente_a2a, "create_a2a_client", new=AsyncMock(return_value=client)):
            self.assertEqual(run(cliente_a2a.run_session("Hola")), 0)


if __name__ == "__main__":
    unittest.main()
