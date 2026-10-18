"""Servidor A2A para la arquitectura centralizada de Parachute S.A.

La primera versión usa tareas independientes: no conserva historial conversacional
entre solicitudes A2A. Cada ejecución delega en ``centralizada.run_agent_mcp_async``
y, por tanto, conserva la conexión y las herramientas remotas de MCP sin exponer
los workers como agentes A2A separados.
"""

from __future__ import annotations

import logging
import os
import time
import uuid

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers.default_request_handler_v2 import (
    DefaultRequestHandlerV2,
)
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
    Role,
)
from starlette.applications import Starlette

import centralizada
from shared.logging_utils import repair_closed_streams


LOGGER = logging.getLogger("parachute.a2a")
A2A_HOST = os.getenv("A2A_HOST", "127.0.0.1")
A2A_PORT = int(os.getenv("A2A_PORT", "9000"))
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
A2A_URL = os.getenv("A2A_URL", f"http://{A2A_HOST}:{A2A_PORT}")


def _configure_logging() -> None:
    repair_closed_streams()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def build_agent_card() -> AgentCard:
    """Construye la Agent Card pública del único agente remoto."""

    return AgentCard(
        name="Parachute S.A. Central Supervisor",
        description="Supervisor centralizado para FAQ, clima y citas seguras.",
        supported_interfaces=[
            AgentInterface(
                url=A2A_URL,
                protocol_binding="JSONRPC",
                protocol_version="1.0",
            )
        ],
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="faq",
                name="Preguntas frecuentes",
                description="Responde preguntas frecuentes de Parachute S.A.",
                tags=["faq", "información"],
                examples=["¿Cuál es el horario de atención?"],
            ),
            AgentSkill(
                id="weather",
                name="Consulta de clima",
                description="Consulta el clima y aplica las reglas meteorológicas.",
                tags=["clima", "weather"],
                examples=["¿Cómo estará el clima el 2026-09-20?"],
            ),
            AgentSkill(
                id="scheduling",
                name="Calendarización segura",
                description="Calendariza citas únicamente cuando el clima es seguro.",
                tags=["citas", "calendarización", "seguridad"],
                examples=["Quiero calendarizar una cita el 2026-09-20"],
            ),
        ],
    )


class CentralizedA2AExecutor(AgentExecutor):
    """Adaptador A2A del supervisor centralizado."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        correlation_id = str(uuid.uuid4())
        started = time.perf_counter()
        repair_closed_streams()
        task_id = context.task_id or "unknown"
        context_id = context.context_id or "unknown"
        user_text = context.get_user_input()
        LOGGER.info(
            "a2a_request_start correlation_id=%s task_id=%s context_id=%s text_length=%d mcp_url=%s",
            correlation_id,
            task_id,
            context_id,
            len(user_text),
            MCP_SERVER_URL,
        )
        try:
            if not user_text.strip():
                result = "ERROR_INVALID_INPUT: El mensaje debe contener texto."
            else:
                result = await centralizada.run_agent_mcp_async(user_text)
            await event_queue.enqueue_event(
                Message(
                    message_id=correlation_id,
                    context_id=context_id,
                    task_id=task_id,
                    role=Role.ROLE_AGENT,
                    parts=[Part(text=str(result))],
                )
            )
            LOGGER.info(
                "a2a_request_end correlation_id=%s task_id=%s context_id=%s duration_ms=%.2f result_length=%d",
                correlation_id,
                task_id,
                context_id,
                (time.perf_counter() - started) * 1000,
                len(str(result)),
            )
        except Exception as exc:
            LOGGER.exception(
                "a2a_request_error correlation_id=%s task_id=%s context_id=%s duration_ms=%.2f error=%s",
                correlation_id,
                task_id,
                context_id,
                (time.perf_counter() - started) * 1000,
                type(exc).__name__,
            )
            await event_queue.enqueue_event(
                Message(
                    message_id=correlation_id,
                    context_id=context_id,
                    task_id=task_id,
                    role=Role.ROLE_AGENT,
                    parts=[Part(text=f"MCP_UNAVAILABLE: {exc}")],
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("La cancelación no está implementada en HDT7.")


def create_app() -> Starlette:
    """Crea la aplicación ASGI sin iniciar un servidor al importar el módulo."""

    card = build_agent_card()
    handler = DefaultRequestHandlerV2(
        agent_executor=CentralizedA2AExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = create_agent_card_routes(card)
    routes.extend(create_jsonrpc_routes(handler, "/"))
    return Starlette(routes=routes)


app = create_app()


if __name__ == "__main__":
    import uvicorn

    _configure_logging()
    LOGGER.info(
        "a2a_server_start host=%s port=%d card=/.well-known/agent-card.json mcp_url=%s",
        A2A_HOST,
        A2A_PORT,
        MCP_SERVER_URL,
    )
    uvicorn.run(app, host=A2A_HOST, port=A2A_PORT)
