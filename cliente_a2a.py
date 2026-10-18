"""Cliente de terminal A2A para Parachute S.A.

El modo interactivo conserva ``context_id`` entre mensajes cuando el servidor
lo devuelve. La consulta única y la primera solicitud de una sesión comienzan
un contexto nuevo.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from collections.abc import AsyncIterator

import httpx
from a2a.client import (
    A2ACardResolver,
    AgentCardResolutionError,
    ClientConfig,
    create_client,
)
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageConfiguration,
    SendMessageRequest,
    StreamResponse,
    TaskState,
)


LOGGER = logging.getLogger("parachute.a2a_client")
DEFAULT_SERVER_URL = "http://127.0.0.1:9000"


def server_url() -> str:
    """Obtiene y normaliza la URL base del servidor A2A."""

    return os.getenv("A2A_SERVER_URL", DEFAULT_SERVER_URL).rstrip("/")


def _message_text(message: Message) -> str:
    return "\n".join(part.text for part in message.parts if part.text)


def _state_name(state: int) -> str:
    return TaskState.Name(state)


async def process_response(response: StreamResponse, context: dict[str, str]) -> str | None:
    """Muestra un evento A2A y devuelve texto cuando contiene respuesta final."""

    if response.HasField("status_update"):
        update = response.status_update
        context["context_id"] = update.context_id or context.get("context_id", "")
        state = _state_name(update.status.state)
        print(f"[Estado: {state.removeprefix('TASK_STATE_').lower()}]")
        if state == "TASK_STATE_FAILED":
            detail = update.status.message
            raise RuntimeError(f"La tarea A2A falló{': ' + _message_text(detail) if detail else '.'}")
        return None

    if response.HasField("task"):
        task = response.task
        context["context_id"] = task.context_id
        state = _state_name(task.status.state)
        print(f"[Estado: {state.removeprefix('TASK_STATE_').lower()}]")
        if state == "TASK_STATE_FAILED":
            raise RuntimeError("La tarea A2A falló.")
        if task.artifacts:
            return "\n".join(part.text for artifact in task.artifacts for part in artifact.parts if part.text)
        return None

    if response.HasField("artifact_update"):
        update = response.artifact_update
        context["context_id"] = update.context_id or context.get("context_id", "")
        return "\n".join(part.text for part in update.artifact.parts if part.text)

    if response.HasField("message"):
        message = response.message
        context["context_id"] = message.context_id or context.get("context_id", "")
        return _message_text(message)

    return None


async def send_query(client, text: str, context: dict[str, str]) -> str:
    """Envía una consulta exclusivamente al servidor A2A."""

    message = Message(
        message_id=str(uuid.uuid4()),
        context_id=context.get("context_id", ""),
        role=Role.ROLE_USER,
        parts=[Part(text=text)],
    )
    request = SendMessageRequest(
        message=message,
        configuration=SendMessageConfiguration(
            accepted_output_modes=["text"],
            return_immediately=False,
        ),
    )
    final_text = ""
    responses: AsyncIterator[StreamResponse] = client.send_message(request)
    async for response in responses:
        text_part = await process_response(response, context)
        if text_part:
            final_text = text_part
    if not final_text:
        raise RuntimeError("El servidor A2A no devolvió una respuesta final.")
    return final_text


async def create_a2a_client(http_client: httpx.AsyncClient):
    """Resuelve la Agent Card y crea el cliente con la configuración oficial."""

    base_url = server_url()
    resolver = A2ACardResolver(httpx_client=http_client, base_url=base_url)
    card = await resolver.get_agent_card()
    if not card.name or not card.supported_interfaces:
        raise ValueError("La Agent Card no contiene nombre o interfaces soportadas.")
    config = ClientConfig(
        streaming=False,
        polling=False,
        httpx_client=http_client,
        accepted_output_modes=["text"],
    )
    return create_client(card, client_config=config)


async def run_session(single_query: str | None = None) -> int:
    context: dict[str, str] = {}
    timeout = httpx.Timeout(float(os.getenv("A2A_TIMEOUT", "30")))
    try:
        async with httpx.AsyncClient(timeout=timeout) as http_client:
            client = await create_a2a_client(http_client)
            try:
                if single_query:
                    print(await send_query(client, single_query, context))
                    return 0
                print("Conectado al agente A2A. Escriba 'salir' para terminar.")
                while True:
                    try:
                        text = input("> ").strip()
                    except EOFError:
                        break
                    if text.lower() in {"salir", "exit", "quit"}:
                        break
                    if not text:
                        continue
                    print(await send_query(client, text, context))
                return 0
            finally:
                await client.close()
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        LOGGER.error("No se pudo conectar con el servidor A2A: %s", exc)
        print("Error: el servidor A2A no está disponible o excedió el tiempo de espera.", file=sys.stderr)
        return 1
    except (AgentCardResolutionError, ValueError, RuntimeError) as exc:
        LOGGER.error("Error en la comunicación A2A: %s", exc)
        print(f"Error A2A: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSesión interrumpida.", file=sys.stderr)
        return 130


def main() -> int:
    parser = argparse.ArgumentParser(description="Cliente de terminal A2A de Parachute S.A.")
    parser.add_argument("query", nargs="?", help="Consulta única para el agente remoto")
    args = parser.parse_args()
    return asyncio.run(run_session(args.query))


if __name__ == "__main__":
    raise SystemExit(main())
