"""Tools disponibles para el agente conversacional."""

from __future__ import annotations

import json
from typing import Any

from database import search_knowledge_base

try:
    from shared.parachute import active_tool_origin, active_tool_trace
except ImportError:
    active_tool_origin = lambda: None
    active_tool_trace = lambda: None


SEARCH_KNOWLEDGE_BASE_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_knowledge_base",
        "description": (
            "Busca en la base de conocimientos oficial de Parachute S.A. "
            "las FAQs relacionadas con la consulta del usuario. "
            "Usa esta herramienta antes de responder preguntas sobre el evento. "
            "La consulta debe conservar todas las partes y entidades mencionadas "
            "por el usuario."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pregunta del usuario que debe buscarse en las FAQs.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


TOOLS = [SEARCH_KNOWLEDGE_BASE_TOOL]


def execute_search_knowledge_base(arguments: str | dict[str, Any]) -> str:
    """Ejecuta la tool y devuelve sus FAQs en JSON para el LLM.

    ``arguments`` puede ser el JSON producido por un tool call o un diccionario
    ya decodificado. La validación aquí evita enviar parámetros inesperados a la
    capa de búsqueda.
    """
    if isinstance(arguments, str):
        try:
            parsed_arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("Los argumentos de la herramienta no son JSON válido.") from exc
    else:
        parsed_arguments = arguments

    if not isinstance(parsed_arguments, dict):
        raise ValueError("Los argumentos de la herramienta deben ser un objeto JSON.")
    if set(parsed_arguments) != {"query"}:
        raise ValueError("La herramienta solo acepta el argumento 'query'.")

    query = parsed_arguments["query"]
    if not isinstance(query, str) or not query.strip():
        raise ValueError("El argumento 'query' debe ser un texto no vacío.")

    trace = active_tool_trace()
    origin = active_tool_origin() or "hdt4"
    try:
        results = search_knowledge_base(query=query)
    except Exception as exc:
        if trace is not None:
            trace.completed(
                "search_knowledge_base",
                {"query": query},
                error=str(exc),
                origin=origin,
            )
        raise
    if trace is not None:
        trace.completed(
            "search_knowledge_base",
            {"query": query},
            result=results,
            origin=origin,
        )
    return json.dumps(results, ensure_ascii=False)


TOOL_EXECUTORS = {
    "search_knowledge_base": execute_search_knowledge_base,
}
