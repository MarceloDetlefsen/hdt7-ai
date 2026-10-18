"""Arquitectura centralizada en modo local o mediante MCP remoto."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

from agents import Agent, RunHooks, Runner
from agents.mcp import MCPServerStreamableHttp

from shared.parachute import (
    ToolCallTrace,
    _ACTIVE_REQUEST_APPOINTMENTS,
    _apply_calendar_guard,
    _apply_domain_guard,
    _read_appointments,
    agent_model,
    agent_model_settings,
    faq_tool,
    record_observed_call,
    run_agent,
    run_chat,
    schedule_tool,
    weather_tool,
)
from shared.logging_utils import configure_process_logging, repair_closed_streams

MODEL = agent_model()
SETTINGS = agent_model_settings()
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "10"))
MCP_CACHE_TOOLS = os.getenv("MCP_CACHE_TOOLS", "true").lower() in {"1", "true", "yes"}
MCP_MAX_RETRIES = int(os.getenv("MCP_MAX_RETRIES", "3"))

logger = logging.getLogger("parachute.centralizada")


def _log(event: str, **fields: Any) -> None:
    repair_closed_streams()
    logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _weather_worker_tool(date: str) -> str:
    """Compatibilidad local para providers y evaluaciones existentes."""
    return record_observed_call("weather_tool", {"date": date}, lambda: weather_tool(date), origin="agent:WeatherWorker")


def _faq_worker_tool(question: str) -> str:
    """Compatibilidad local para providers y evaluaciones existentes."""
    return record_observed_call("faq_tool", {"question": question}, lambda: faq_tool(question), origin="agent:FAQWorker")


def _calendar_worker_tool(date: str) -> str:
    """Compatibilidad local para providers y evaluaciones existentes."""
    return record_observed_call("schedule_tool", {"date": date}, lambda: schedule_tool(date), origin="agent:CalendarWorker")


def _local_worker_tools() -> tuple[Any, Any, Any]:
    from agents import function_tool

    return (
        function_tool(_weather_worker_tool, name_override="weather_tool"),
        function_tool(_faq_worker_tool, name_override="faq_tool"),
        function_tool(_calendar_worker_tool, name_override="schedule_tool"),
    )


def _build_supervisor(weather_worker: Agent, faq_worker: Agent, calendar_worker: Agent) -> Agent:
    return Agent(
        name="SupervisorCentral",
        instructions=(
            "Eres el único supervisor de Parachute S.A. Decide qué worker usar. "
            "Para una cita, consulta clima antes de aceptar; nunca autorices si el reporte dice NO SEGURO. "
            "Si el usuario desea calendarizar, llama primero a WeatherWorker y después a CalendarWorker con el reporte exacto. "
            "Nunca escribas APTO si la decisión es NO SEGURO / PROHIBIDO. Nunca digas confirmada: la cita solo es tentativa si CalendarWorker devuelve scheduled=true; si devuelve error, informa que no se calendarizó."
        ),
        model=MODEL,
        model_settings=SETTINGS,
        tools=[
            weather_worker.as_tool(tool_name="consultar_clima", tool_description="Consulta clima y aptitud para una fecha."),
            faq_worker.as_tool(tool_name="consultar_faq", tool_description="Consulta las preguntas frecuentes."),
            calendar_worker.as_tool(tool_name="calendarizar_cita", tool_description="Calendariza una cita con un reporte meteorológico aprobado."),
        ],
    )


def build_local_agents() -> Agent:
    """Construye la arquitectura original con tools locales."""
    weather_tool_local, faq_tool_local, schedule_tool_local = _local_worker_tools()
    weather_worker = Agent(name="WeatherWorker", instructions="Usa weather_tool para consultar y evaluar una fecha. Nunca inventes datos.", tools=[weather_tool_local], model=MODEL, model_settings=SETTINGS)
    faq_worker = Agent(name="FAQWorker", instructions="Responde exclusivamente usando faq_tool. Si no hay coincidencia, di que no existe información en las FAQs. Nunca uses conocimiento general ni respondas temas ajenos a Parachute.", tools=[faq_tool_local], model=MODEL, model_settings=SETTINGS)
    calendar_worker = Agent(name="CalendarWorker", instructions="Usa schedule_tool para que la propia integración vuelva a consultar el clima. Nunca inventes ni reutilices un reporte.", tools=[schedule_tool_local], model=MODEL, model_settings=SETTINGS)
    return _build_supervisor(weather_worker, faq_worker, calendar_worker)


def build_mcp_agents(mcp_server: MCPServerStreamableHttp) -> Agent:
    """Construye workers cuyas tools son descubiertas desde MCP."""
    common = {"mcp_servers": [mcp_server], "model": MODEL, "model_settings": SETTINGS}
    weather_worker = Agent(name="WeatherWorker", instructions="Usa exclusivamente la tool MCP weather_tool para consultar y evaluar una fecha. Nunca inventes datos.", **common)
    faq_worker = Agent(name="FAQWorker", instructions="Usa exclusivamente la tool MCP faq_tool. Si no hay coincidencia, informa que no existe información en las FAQs. Nunca uses conocimiento general.", **common)
    calendar_worker = Agent(name="CalendarWorker", instructions="Usa exclusivamente la tool MCP schedule_tool. La tool vuelve a consultar el clima y bloquea condiciones inseguras. Nunca inventes ni reutilices un reporte.", **common)
    supervisor_mcp = _build_supervisor(weather_worker, faq_worker, calendar_worker)
    # Metadatos de inspección para pruebas y observabilidad; las tools siguen
    # siendo descubiertas y ejecutadas por el SDK MCP remoto.
    supervisor_mcp._parachute_mcp_server = mcp_server
    supervisor_mcp._parachute_mcp_workers = (weather_worker, faq_worker, calendar_worker)
    return supervisor_mcp


class MCPRunHooks(RunHooks):
    """Registra llamadas MCP en la traza compartida de la solicitud."""

    def __init__(self, trace: ToolCallTrace) -> None:
        self.trace = trace
        self._started: list[int] = []

    async def on_tool_start(self, context, agent, tool) -> None:
        name = getattr(tool, "name", tool.__class__.__name__)
        raw_arguments = getattr(context, "tool_arguments", None)
        try:
            arguments = json.loads(raw_arguments) if raw_arguments else {}
        except (TypeError, ValueError):
            arguments = {}
        safe_arguments = dict(arguments) if isinstance(arguments, dict) else {}
        if "question" in safe_arguments:
            safe_arguments["question_length"] = len(str(safe_arguments.pop("question")))
        origin = f"agent:{getattr(agent, 'name', 'unknown')}"
        self._started.append(self.trace.start(name, arguments, origin))
        _log("mcp_tool_started", tool=name, origin=origin, arguments=safe_arguments)

    async def on_tool_end(self, context, agent, tool, result) -> None:
        if not self._started:
            return
        index = self._started.pop()
        self.trace.finish(index, result=result)
        _log("mcp_tool_finished", tool=self.trace.tool_calls[index]["name"], result=result)


@asynccontextmanager
async def connected_mcp_server():
    """Abre MCP, descubre sus tools y garantiza cierre de la sesión."""
    started = time.perf_counter()
    _log("mcp_connection_started", url=MCP_SERVER_URL)
    server = MCPServerStreamableHttp(
        name="Parachute MCP",
        params={"url": MCP_SERVER_URL, "timeout": MCP_TIMEOUT},
        cache_tools_list=MCP_CACHE_TOOLS,
        max_retry_attempts=MCP_MAX_RETRIES,
    )
    try:
        async with server:
            discovered = None
            last_error: Exception | None = None
            for attempt in range(MCP_MAX_RETRIES + 1):
                try:
                    discovered = await server.list_tools()
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt >= MCP_MAX_RETRIES:
                        raise
                    _log(
                        "mcp_tool_discovery_retry",
                        url=MCP_SERVER_URL,
                        attempt=attempt + 1,
                        error=str(exc),
                    )
                    await asyncio.sleep(min(0.25 * (2**attempt), 2.0))
            if discovered is None and last_error is not None:
                raise last_error
            _log("mcp_connection_ready", url=MCP_SERVER_URL, tools=[tool.name for tool in discovered], duration_ms=round((time.perf_counter() - started) * 1000, 2))
            yield server
    except Exception as exc:
        _log("mcp_connection_error", url=MCP_SERVER_URL, error=str(exc))
        raise RuntimeError(f"MCP_UNAVAILABLE: no se pudo conectar a {MCP_SERVER_URL}: {exc}") from exc


async def run_agent_mcp_async(user_text: str) -> str:
    """Ejecuta una solicitud usando exclusivamente tools MCP remotas."""
    from copy import deepcopy

    request_token = _ACTIVE_REQUEST_APPOINTMENTS.set(deepcopy(_read_appointments()))
    trace = ToolCallTrace()
    started = time.perf_counter()
    try:
        with trace.activate():
            async with connected_mcp_server() as mcp_server:
                supervisor_mcp = build_mcp_agents(mcp_server)
                result = await Runner.run(supervisor_mcp, user_text, hooks=MCPRunHooks(trace))
                output = _apply_calendar_guard(user_text, result.final_output or "", mode="mcp")
                output = _apply_domain_guard(user_text, output, mode="mcp")
                _log("mcp_request_finished", duration_ms=round((time.perf_counter() - started) * 1000, 2))
                return output
    except Exception as exc:
        _log("mcp_request_error", duration_ms=round((time.perf_counter() - started) * 1000, 2), error=str(exc))
        return f"MCP_UNAVAILABLE: {exc}"
    finally:
        _ACTIVE_REQUEST_APPOINTMENTS.reset(request_token)


def run_agent_mcp(user_text: str) -> str:
    """Wrapper síncrono para consultas individuales desde la terminal."""
    return asyncio.run(run_agent_mcp_async(user_text))


async def run_chat_mcp_async() -> None:
    """Modo interactivo MCP con una única sesión remota."""
    print("Chat MCP iniciado. Escribe 'salir' para terminar.")
    try:
        async with connected_mcp_server() as mcp_server:
            supervisor_mcp = build_mcp_agents(mcp_server)
            history: list[Any] = []
            while True:
                user_text = (await asyncio.to_thread(input, "Tú: ")).strip()
                if user_text.lower() in {"salir", "exit", "quit"}:
                    print("Sesión finalizada.")
                    return
                if not user_text:
                    continue
                trace = ToolCallTrace()
                with trace.activate():
                    result = await Runner.run(supervisor_mcp, history + [{"role": "user", "content": user_text}], hooks=MCPRunHooks(trace))
                history = result.to_input_list()
                output = _apply_calendar_guard(user_text, result.final_output or "", mode="mcp")
                print(f"Agente: {_apply_domain_guard(user_text, output, mode='mcp')}")
    except Exception as exc:
        print(f"MCP_UNAVAILABLE: {exc}")


def run_chat_mcp() -> None:
    asyncio.run(run_chat_mcp_async())


def main() -> None:
    configure_process_logging(os.getenv("MCP_LOG_LEVEL", "INFO"))
    mode = os.getenv("CENTRALIZADA_MODE", "local").lower()
    query = " ".join(sys.argv[1:])
    if mode == "mcp":
        if query:
            print(run_agent_mcp(query))
        else:
            run_chat_mcp()
        return
    if mode != "local":
        raise SystemExit("CENTRALIZADA_MODE debe ser 'local' o 'mcp'.")
    local_supervisor = build_local_agents()
    if query:
        print(run_agent(local_supervisor, query))
    else:
        run_chat(local_supervisor)


supervisor = build_local_agents()


if __name__ == "__main__":
    main()
