"""Agente conversacional con function calling para las FAQs de Parachute S.A."""

from __future__ import annotations

import json
import sys
import unicodedata
from collections.abc import Callable
from typing import Any

from openai import BadRequestError

try:
    import readline

    readline.set_history_length(100)
except ImportError:
    # readline no está disponible en algunos entornos, por ejemplo Windows.
    pass

from groq_client import get_groq_client, get_groq_model
from tools import TOOL_EXECUTORS, TOOLS


SYSTEM_PROMPT = """Eres el agente de preguntas frecuentes de Parachute S.A.

Responde exclusivamente con información contenida en los resultados de
search_knowledge_base. No uses conocimiento externo, memoria ni suposiciones.
Debes utilizar la herramienta antes de responder cada pregunta.
Si la herramienta devuelve una lista vacía o los resultados no contienen
información suficiente, responde:
\"Lo siento, no puedo responder esa pregunta con la información disponible en la
base de conocimientos de Parachute S.A.\"
No inventes datos. Responde en español y de forma clara y concisa.

Evalúa cada parte de la pregunta por separado. Responde las partes respaldadas por los
resultados e indica claramente cuáles no pueden responderse. Si ninguna parte tiene
información suficiente, usa exactamente el mensaje de información no disponible. La
información de metadata también forma parte de los resultados y puede utilizarse.

Si la pregunta solicita un solo dato y los resultados únicamente ofrecen una respuesta
general, entrega ese dato con el nivel de precisión disponible y aclara qué detalle no
está especificado. Esto no autoriza a completar ni deducir información ausente.

Los saludos, despedidas y preguntas sobre tus capacidades pueden recibir una respuesta
breve de cortesía. Para cualquier pregunta factual sobre el evento, debes consultar la
herramienta y responder únicamente con sus resultados.
"""

NO_ANSWER = (
    "Lo siento, no puedo responder esa pregunta con la información disponible en la "
    "base de conocimientos de Parachute S.A."
)
EXIT_COMMANDS = {"bye", "salir", "exit", "quit"}
SESSION_END_MESSAGE = "Sesión finalizada."


def _normalize_text(text: str) -> str:
    """Normaliza texto para reconocer expresiones conversacionales comunes."""
    normalized = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(
        char
        for char in normalized
        if unicodedata.category(char) not in {"Mn", "Po", "Pi", "Pf"}
    )


def get_conversational_response(query: str) -> str | None:
    """Devuelve respuestas fijas para cortesía sin inventar datos del evento."""
    normalized_query = _normalize_text(query)
    responses = {
        "hola": "¡Hola! Estoy aquí para ayudarte con información sobre el evento de Parachute S.A.",
        "buenas": "¡Hola! Estoy aquí para ayudarte con información sobre el evento de Parachute S.A.",
        "buenos dias": "¡Buenos días! Estoy aquí para ayudarte con información sobre el evento de Parachute S.A.",
        "buenas tardes": "¡Buenas tardes! Estoy aquí para ayudarte con información sobre el evento de Parachute S.A.",
        "buenas noches": "¡Buenas noches! Estoy aquí para ayudarte con información sobre el evento de Parachute S.A.",
        "como estas": "¡Estoy bien, gracias! Puedo ayudarte con preguntas sobre el evento de Parachute S.A.",
        "que puedes hacer": "Puedo ayudarte a consultar información de las FAQs del evento de Parachute S.A.",
        "en que me puedes ayudar": "Puedo ayudarte a consultar información de las FAQs del evento de Parachute S.A.",
        "que sabes": "Puedo ayudarte a consultar información de las FAQs del evento de Parachute S.A.",
        "que sabes de parachute": "Puedo ayudarte a consultar información de las FAQs del evento de Parachute S.A.",
        "que informacion tienes": "Puedo ayudarte a consultar las FAQs disponibles sobre el evento de Parachute S.A.",
        "que info tienes": "Puedo ayudarte a consultar las FAQs disponibles sobre el evento de Parachute S.A.",
        "que informacion tenes": "Puedo ayudarte a consultar las FAQs disponibles sobre el evento de Parachute S.A.",
        "que info tenes": "Puedo ayudarte a consultar las FAQs disponibles sobre el evento de Parachute S.A.",
        "gracias": "¡Con gusto! Estoy aquí para ayudarte.",
    }
    return responses.get(normalized_query)


def _execute_tool_call(tool_call: Any) -> str:
    """Ejecuta un tool call y convierte errores en resultados legibles para el LLM."""
    name = tool_call.function.name
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return json.dumps({"error": f"Herramienta no disponible: {name}"})

    try:
        return executor(tool_call.function.arguments)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return json.dumps({"error": f"No se pudo ejecutar la herramienta: {exc}"})


def _parse_search_results(tool_result: str) -> list[dict[str, Any]]:
    """Valida el contrato JSON de la herramienta de búsqueda."""
    try:
        parsed = json.loads(tool_result)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _split_questions(
    client: Any,
    query: str,
    max_parts: int,
) -> list[str]:
    """Divide una consulta en solicitudes independientes mediante salida estructurada."""
    try:
        response = client.chat.completions.create(
            model=get_groq_model(),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Identifica todas las solicitudes de información que puedan "
                        "responderse de forma independiente. Cada elemento debe pedir "
                        "exactamente un solo dato, nunca dos. Una oración puede contener "
                        "varias cláusulas interrogativas unidas por conjunciones. Conserva "
                        "todas las entidades y detalles. El contexto general es el agente de "
                        "FAQs del evento de Parachute S.A.; úsalo para hacer explícitas "
                        "referencias como 'el evento' o 'la fecha'. Cada pregunta resultante "
                        "debe entenderse por sí sola. No respondas. Verifica que "
                        "ningún elemento contenga más de una solicitud. Devuelve JSON estricto "
                        'con la forma {"questions":["pregunta 1","pregunta 2"]}. '
                        "Si solo existe una solicitud, devuelve una sola pregunta."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
        parsed = json.loads(response.choices[0].message.content or "")
        questions = parsed.get("questions", []) if isinstance(parsed, dict) else []
    except (BadRequestError, json.JSONDecodeError):
        return [query]

    clean_questions = [
        question.strip()
        for question in questions
        if isinstance(question, str) and question.strip()
    ]
    if len(clean_questions) <= 1:
        return [query]
    return clean_questions[:max_parts]


def _generate_grounded_answer(
    client: Any, query: str, evidence: list[dict[str, Any]]
) -> str:
    """Genera una respuesta usando exclusivamente evidencia obtenida por tools."""
    if not any(item["results"] for item in evidence):
        return NO_ANSWER

    prompt = (
        f"Pregunta original:\n{query}\n\n"
        "Evidencia por cada parte de la pregunta:\n"
        f"{json.dumps(evidence, ensure_ascii=False)}\n\n"
        "Responde cada parte exclusivamente con su evidencia correspondiente. "
        "Cuando una parte tenga results vacío, indica que no puedes responder esa parte. "
        "Los campos de metadata son datos oficiales: si el valor solicitado aparece "
        "de forma consistente allí, puedes usarlo aunque la pregunta de la FAQ sea otra. "
        "Para una sola solicitud, da el nivel de precisión disponible y aclara cualquier "
        "detalle que los resultados no especifiquen. Redacta de manera natural y concisa, "
        "sin encabezados, IDs, puntajes, nombres de campos ni explicaciones del proceso de "
        "búsqueda. No presentes una ubicación, fecha u otro dato como más preciso de lo "
        "que muestra la evidencia. "
        f"Si todas las partes tienen results vacío, responde exactamente: {NO_ANSWER}"
    )
    try:
        response = client.chat.completions.create(
            model=get_groq_model(),
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except BadRequestError:
        return NO_ANSWER
    answer = (response.choices[0].message.content or "").strip()
    return answer or NO_ANSWER


def _rewrite_search_query(client: Any, query: str) -> str:
    """Crea una consulta semántica breve sin depender de términos del dominio."""
    try:
        response = client.chat.completions.create(
            model=get_groq_model(),
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Convierte la pregunta en una consulta breve para búsqueda "
                        "semántica. Conserva todas las entidades y todas las partes de "
                        "la pregunta. Devuelve solo la consulta, sin JSON ni explicación."
                    ),
                },
                {"role": "user", "content": query},
            ],
        )
    except BadRequestError:
        return query
    rewritten = (response.choices[0].message.content or "").strip()
    return rewritten or query


def _fallback_after_invalid_tool_call(client: Any, query: str) -> str:
    """Ejecuta la búsqueda si el proveedor genera un tool call inválido."""
    original_result = TOOL_EXECUTORS["search_knowledge_base"]({"query": query})
    if _parse_search_results(original_result):
        return original_result

    search_query = _rewrite_search_query(client, query)
    return TOOL_EXECUTORS["search_knowledge_base"]({"query": search_query})


def _search_question_with_tool(client: Any, question: str) -> str:
    """Solicita y ejecuta un function call para una subpregunta."""
    try:
        response = client.chat.completions.create(
            model=get_groq_model(),
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            tools=TOOLS,
            tool_choice={
                "type": "function",
                "function": {"name": "search_knowledge_base"},
            },
            parallel_tool_calls=False,
        )
    except BadRequestError:
        return _fallback_after_invalid_tool_call(client, question)

    tool_calls = response.choices[0].message.tool_calls or []
    if len(tool_calls) != 1:
        return _fallback_after_invalid_tool_call(client, question)

    tool_result = _execute_tool_call(tool_calls[0])
    if _parse_search_results(tool_result):
        return tool_result
    return _fallback_after_invalid_tool_call(client, question)


def run_agent_turn(
    client: Any,
    messages: list[dict[str, Any]],
    user_query: str,
    *,
    max_tool_rounds: int = 4,
) -> str:
    """Procesa una pregunta, sus tool calls y devuelve la respuesta final.

    ``messages`` se modifica para conservar el historial de la sesión.
    """
    if not user_query.strip():
        return ""
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds debe ser mayor que cero.")

    conversational_response = get_conversational_response(user_query)
    if conversational_response is not None:
        messages.extend(
            [
                {"role": "user", "content": user_query.strip()},
                {"role": "assistant", "content": conversational_response},
            ]
        )
        return conversational_response

    questions = _split_questions(client, user_query, max_tool_rounds)
    evidence: list[dict[str, Any]] = []
    for question in questions:
        tool_result = _search_question_with_tool(client, question)
        evidence.append(
            {
                "question": question,
                "results": _parse_search_results(tool_result),
            }
        )

    answer = _generate_grounded_answer(client, user_query, evidence)
    messages.extend(
        [
            {"role": "user", "content": user_query.strip()},
            {"role": "assistant", "content": answer},
        ]
    )
    return answer


def run_interactive_session(
    client: Any,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Mantiene una sesión activa y conserva el historial entre preguntas."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    output_fn("Agente Parachute S.A. listo. Escribe 'Bye' para salir.")

    while True:
        try:
            user_query = input_fn("\nPregunta > ").strip()
        except (EOFError, KeyboardInterrupt):
            output_fn(f"\n{SESSION_END_MESSAGE}")
            return 0

        if user_query.lower() in EXIT_COMMANDS:
            output_fn(SESSION_END_MESSAGE)
            return 0
        if not user_query:
            continue

        try:
            answer = run_agent_turn(client, messages, user_query)
            output_fn(f"\nRespuesta: {answer}")
        except KeyboardInterrupt:
            output_fn(f"\n{SESSION_END_MESSAGE}")
            return 0
        except Exception as exc:
            output_fn(f"Error al procesar la pregunta: {exc}")


def main() -> int:
    try:
        client = get_groq_client()
    except ValueError as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr)
        return 1

    return run_interactive_session(client)


if __name__ == "__main__":
    raise SystemExit(main())
