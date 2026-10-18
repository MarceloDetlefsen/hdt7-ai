"""Servidor MCP de Parachute S.A. para HDT7.

Expone únicamente las capacidades de negocio y delega toda la lógica en
``shared.parachute``. El transporte es Streamable HTTP y el endpoint es
``/mcp``.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer

from shared import parachute
from shared.logging_utils import repair_closed_streams


HOST = "127.0.0.1"
DEFAULT_PORT = 8000
MCP_PATH = "/mcp"

logger = logging.getLogger("parachute.mcp")


class ToolExecutionError(RuntimeError):
    """Error técnico serializable producido por una herramienta compartida."""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _json_log(event: str, **fields: Any) -> None:
    """Emite un evento JSON sin incluir secretos ni prompts completos."""
    repair_closed_streams()
    logger.info(json.dumps({"event": event, **fields}, ensure_ascii=False, default=str))


def _correlation_id() -> str:
    return f"mcp-{uuid.uuid4().hex}"


def _envelope(
    *,
    correlation_id: str,
    ok: bool,
    data: Any = None,
    error: dict[str, Any] | None = None,
) -> str:
    return json.dumps(
        {
            "ok": ok,
            "data": data,
            "error": error,
            "correlation_id": correlation_id,
        },
        ensure_ascii=False,
        default=str,
    )


def _technical_error(code: str, message: str, *, retryable: bool) -> dict[str, Any]:
    return {"code": code, "message": message, "retryable": retryable}


def _parse_json_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _run_tool(
    name: str,
    callback: Callable[[], tuple[Any, bool]],
    *,
    safe_log_arguments: dict[str, Any],
) -> str:
    correlation_id = _correlation_id()
    started = time.perf_counter()
    _json_log(
        "mcp_tool_started",
        tool=name,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        correlation_id=correlation_id,
        arguments=safe_log_arguments,
    )
    try:
        data, business_ok = callback()
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        _json_log(
            "mcp_tool_finished",
            tool=name,
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            ok=business_ok,
            result=data,
        )
        return _envelope(
            correlation_id=correlation_id,
            ok=business_ok,
            data=data,
            error=None,
        )
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if isinstance(exc, ToolExecutionError):
            error = _technical_error(exc.code, str(exc), retryable=exc.retryable)
        else:
            error = _technical_error(
                "INVALID_ARGUMENT" if isinstance(exc, ValueError) else "MCP_TOOL_ERROR",
                str(exc),
                retryable=not isinstance(exc, ValueError),
            )
        _json_log(
            "mcp_tool_error",
            tool=name,
            timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            ok=False,
            error=error,
        )
        return _envelope(correlation_id=correlation_id, ok=False, error=error)


def _require_non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} debe ser un string no vacío.")
    return value.strip()


def _require_iso_date(value: object) -> str:
    date_text = _require_non_empty_string(value, "date")
    try:
        dt.date.fromisoformat(date_text)
    except ValueError as exc:
        raise ValueError("date debe ser una fecha ISO válida con formato YYYY-MM-DD.") from exc
    return date_text


def _faq_result(question: str) -> tuple[Any, bool]:
    raw = parachute.faq_tool(question)
    return {"answer": raw, "source": "hdt4", "grounded": True}, True


def _weather_result(date_text: str) -> tuple[Any, bool]:
    raw = _parse_json_text(parachute.weather_tool(date_text))
    if isinstance(raw, dict) and raw.get("error"):
        raise ToolExecutionError(
            "WEATHER_PROVIDER_UNAVAILABLE",
            str(raw["error"]),
            retryable=True,
        )
    return raw, True


def _schedule_result(date_text: str) -> tuple[Any, bool]:
    raw = _parse_json_text(parachute.schedule_tool(date_text))
    if not isinstance(raw, dict):
        raise RuntimeError("schedule_tool devolvió un resultado no JSON.")
    # Una cita insegura es un resultado válido de negocio, no un error técnico.
    if raw.get("scheduled") is False and raw.get("error"):
        message = str(raw["error"])
        if "condiciones" in message.lower() or "prohibido" in message.lower():
            raw["decision"] = "NO SEGURO / PROHIBIDO"
            return raw, True
        raise ToolExecutionError(
            "APPOINTMENT_PERSISTENCE_ERROR",
            message,
            retryable=True,
        )
    return raw, bool(raw.get("scheduled") is True)


server = MCPServer(
    name="parachute-mcp",
    description="Herramientas de FAQs, clima y calendarización segura de Parachute S.A.",
    version="1.0.0",
)


@server.tool(
    name="faq_tool",
    description="Consulta las preguntas frecuentes oficiales de Parachute S.A.",
)
def faq_tool(question: str) -> str:
    """Consulta HDT4 sin publicar search_knowledge_base como tool MCP."""
    return _run_tool(
        "faq_tool",
        lambda: _faq_result(_require_non_empty_string(question, "question")),
        safe_log_arguments={"question_length": len(question) if isinstance(question, str) else None},
    )


@server.tool(
    name="weather_tool",
    description="Consulta Open-Meteo y evalúa la aptitud meteorológica de una fecha.",
)
def weather_tool(date: str) -> str:
    """Consulta clima mediante la integración compartida."""
    return _run_tool(
        "weather_tool",
        lambda: _weather_result(_require_iso_date(date)),
        safe_log_arguments={"date": date if isinstance(date, str) else None},
    )


@server.tool(
    name="schedule_tool",
    description="Calendariza tentativamente una cita solo con clima aprobado.",
)
def schedule_tool(date: str) -> str:
    """Calendariza mediante la barrera de seguridad compartida."""
    return _run_tool(
        "schedule_tool",
        lambda: _schedule_result(_require_iso_date(date)),
        safe_log_arguments={"date": date if isinstance(date, str) else None},
    )


def _port() -> int:
    value = os.getenv("MCP_PORT", str(DEFAULT_PORT))
    try:
        port = int(value)
    except ValueError as exc:
        raise ValueError("MCP_PORT debe ser un entero.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("MCP_PORT debe estar entre 1 y 65535.")
    return port


def main() -> None:
    """Inicia el servidor MCP con Streamable HTTP en /mcp."""
    logging.basicConfig(level=os.getenv("MCP_LOG_LEVEL", "INFO"), format="%(message)s")
    port = _port()
    _json_log(
        "mcp_server_started",
        server="parachute-mcp",
        transport="streamable-http",
        host=HOST,
        port=port,
        path=MCP_PATH,
    )
    server.run(
        transport="streamable-http",
        host=HOST,
        port=port,
        streamable_http_path=MCP_PATH,
        stateless_http=True,
    )


if __name__ == "__main__":
    main()
