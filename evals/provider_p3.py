"""Provider determinista y aislado para los evals P3.

Usa los wrappers de la arquitectura centralizada y el adaptador compartido,
pero no depende de que un LLM decida emitir los tool calls durante un caso
determinista de clima.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date as date_type
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from centralizada import _calendar_worker_tool, _weather_worker_tool  # noqa: E402
from shared import parachute  # noqa: E402
from shared.parachute import (  # noqa: E402
    ToolCallTrace,
    evaluation_dependencies,
    extract_date,
    record_observed_call,
    validate_date,
)


def _json_var(value, default):
    if value is None or value == "":
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    return json.loads(value)


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _created(initial, final):
    remaining = deepcopy(initial)
    result = []
    for appointment in final:
        if appointment in remaining:
            remaining.remove(appointment)
        else:
            result.append(deepcopy(appointment))
    return result


def _appointment(prompt: str) -> str:
    date = extract_date(prompt)
    if not date:
        return "La cita no fue calendarizada: falta una fecha válida."
    try:
        validate_date(date)
    except ValueError as exc:
        return f"La cita no fue calendarizada: {exc}"

    weather_raw = record_observed_call(
        "consultar_clima",
        {"input": date},
        lambda: _weather_worker_tool(date),
        origin="agent:SupervisorCentral",
    )
    weather = json.loads(weather_raw)
    if weather.get("error"):
        return f"La cita no fue calendarizada: no se pudo verificar el clima. Error: {weather['error']}"
    if weather.get("decision") == "NO SEGURO / PROHIBIDO":
        return "Decisión: NO SEGURO / PROHIBIDO. La cita no fue calendarizada."

    result = json.loads(record_observed_call(
        "calendarizar_cita",
        {"input": date},
        lambda: _calendar_worker_tool(date),
        origin="agent:SupervisorCentral",
    ))
    return result.get("message", "La cita no fue calendarizada.") if result.get("scheduled") else f"La cita no fue calendarizada: {result.get('error', 'error de calendarización')}"


def call_api(prompt, options, context):
    variables = (context or {}).get("vars", {})
    today = variables.get("fixed_today")
    weather_fixture = _json_var(variables.get("weather_fixture"), None)
    weather_sequence = _json_var(variables.get("weather_sequence"), None)
    initial = _json_var(variables.get("initial_appointments"), [])
    old_path = parachute.APPOINTMENTS_PATH
    trace = ToolCallTrace()
    with tempfile.TemporaryDirectory(prefix="parachute-p3-") as temp_dir:
        path = Path(temp_dir) / "citas.json"
        path.write_text(json.dumps(initial, ensure_ascii=False), encoding="utf-8")
        parachute.APPOINTMENTS_PATH = path
        try:
            with evaluation_dependencies(
                today=date_type.fromisoformat(today) if today else None,
                weather_fixture=weather_fixture,
                weather_sequence=weather_sequence,
            ), trace.activate():
                output = _appointment(prompt)
            final = _read(path)
        finally:
            parachute.APPOINTMENTS_PATH = old_path
    return {
        "output": output,
        "metadata": {
            "tool_calls": trace.tool_calls,
            "appointments": {"initial": initial, "final": final, "created": _created(initial, final)},
        },
    }
