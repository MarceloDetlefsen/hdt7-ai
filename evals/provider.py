"""Proveedor mínimo de Promptfoo para la arquitectura centralizada."""

from __future__ import annotations

import json
import signal
import sys
import tempfile
import threading
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path

from agents import RunHooks

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from centralizada import supervisor  # noqa: E402
from shared import parachute  # noqa: E402
from shared.parachute import (  # noqa: E402
    ToolCallTrace,
    evaluation_dependencies,
    run_agent,
)


_EVAL_LOCK = threading.RLock()
_DEFAULT_DEADLINE_SECONDS = 60

class EvalDeadlineExceeded(TimeoutError):
    """Indica que una llamada del agente excedió el presupuesto del caso."""


@contextmanager
def _evaluation_deadline(seconds: int):
    """Interrumpe una llamada bloqueada sin dejar inutilizable el worker Python.

    El timeout de Promptfoo rechaza la petición desde Node, pero no siempre
    detiene la ejecución síncrona que quedó dentro del proceso Python. Esta
    alarma se dispara antes que ese watchdog externo y permite al wrapper
    persistente responder y continuar con el siguiente caso.
    """
    if (
        not hasattr(signal, "SIGALRM")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return

    def _raise_deadline(_signum, _frame) -> None:
        raise EvalDeadlineExceeded(
            f"El agente excedió el límite de {seconds} segundos para este caso."
        )

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, seconds)
    signal.signal(signal.SIGALRM, _raise_deadline)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer != (0.0, 0.0):
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def _json_var(value, default):
    """Convierte una variable de Promptfoo JSON o devuelve su valor por defecto."""
    if value is None or value == "":
        return deepcopy(default)
    if isinstance(value, (dict, list)):
        return deepcopy(value)
    return json.loads(value)


def _read_appointments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    content = path.read_text(encoding="utf-8").strip()
    return json.loads(content) if content else []


def _created_appointments(initial: list[dict], final: list[dict]) -> list[dict]:
    if final[: len(initial)] == initial:
        return deepcopy(final[len(initial) :])
    remaining = deepcopy(initial)
    created = []
    for appointment in final:
        if appointment in remaining:
            remaining.remove(appointment)
        else:
            created.append(deepcopy(appointment))
    return created


def _json_default(value):
    """Convierte objetos de herramientas a una representación JSON segura."""
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, (date, Path)):
        return str(value)
    return str(value)


def _json_safe(value):
    """El wrapper persistente de Promptfoo solo admite metadatos JSON."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=_json_default))


class EvalRunHooks(RunHooks):
    """Captura las llamadas reales del Agents SDK, incluidos los as_tools."""

    def __init__(self, trace: ToolCallTrace) -> None:
        self.trace = trace
        self._started: list[int] = []
        self._origins: list[str | None] = []

    async def on_tool_start(self, context, agent, tool) -> None:
        name = getattr(tool, "name", tool.__class__.__name__)
        arguments = getattr(context, "tool_arguments", None)
        try:
            import json

            arguments = json.loads(arguments) if arguments else {}
        except (TypeError, ValueError):
            pass
        agent_name = getattr(agent, "name", agent.__class__.__name__)
        origin = f"agent:{agent_name}"
        previous_origin = self.trace.push_origin(origin)
        index = self.trace.start(name, arguments, origin)
        self._started.append(index)
        self._origins.append(previous_origin)

    async def on_tool_end(self, context, agent, tool, result) -> None:
        if not self._started:
            return
        index = self._started.pop()
        self.trace.finish(index, result=result)
        self.trace.pop_origin(self._origins.pop())


def call_api(prompt, options, context):
    """Ejecuta el agente centralizado con el prompt de Promptfoo."""
    provider_config = (options or {}).get("config", {})
    timeout_ms = provider_config.get("timeout", _DEFAULT_DEADLINE_SECONDS * 1000)
    try:
        deadline_seconds = max(1, int(timeout_ms) // 1000 - 5)
    except (TypeError, ValueError):
        deadline_seconds = _DEFAULT_DEADLINE_SECONDS
    variables = (context or {}).get("vars", {})
    fixed_today = variables.get("fixed_today")
    today = date.fromisoformat(fixed_today) if fixed_today else None
    weather_fixture = _json_var(variables.get("weather_fixture"), None)
    weather_sequence = _json_var(variables.get("weather_sequence"), None)
    initial_appointments = _json_var(
        variables.get("initial_appointments"), []
    )
    if not isinstance(initial_appointments, list):
        raise ValueError("initial_appointments debe ser una lista JSON.")
    if weather_fixture is not None and not isinstance(weather_fixture, dict):
        raise ValueError("weather_fixture debe ser un objeto JSON.")
    if weather_sequence is not None and not isinstance(weather_sequence, list):
        raise ValueError("weather_sequence debe ser una lista JSON.")

    trace = ToolCallTrace()
    hooks = EvalRunHooks(trace)
    old_appointments_path = parachute.APPOINTMENTS_PATH
    final_appointments = deepcopy(initial_appointments)

    # Promptfoo puede reutilizar el proceso Python entre casos. El lock evita
    # que dos casos modifiquen simultáneamente la ruta temporal global.
    with _EVAL_LOCK:
        with tempfile.TemporaryDirectory(prefix="parachute-eval-") as temp_dir:
            temporary_appointments_path = Path(temp_dir) / "citas.json"
            temporary_appointments_path.write_text(
                json.dumps(initial_appointments, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            parachute.APPOINTMENTS_PATH = temporary_appointments_path
            try:
                try:
                    with _evaluation_deadline(deadline_seconds), evaluation_dependencies(
                        today=today,
                        weather_fixture=weather_fixture,
                        weather_sequence=weather_sequence,
                    ), trace.activate():
                        respuesta = run_agent(
                            supervisor,
                            prompt,
                            run_hooks=hooks,
                        )
                except EvalDeadlineExceeded as exc:
                    trace.fail_open_calls(str(exc))
                    respuesta = f"No se pudo completar la solicitud: {exc}"
                final_appointments = _read_appointments(temporary_appointments_path)
            finally:
                parachute.APPOINTMENTS_PATH = old_appointments_path

    appointments = {
        "initial": deepcopy(initial_appointments),
        "final": deepcopy(final_appointments),
        "created": _created_appointments(initial_appointments, final_appointments),
    }
    return {
        "output": respuesta,
        "metadata": {
            # `fetch_weather` devuelve un WeatherReport dentro de la traza del
            # guard de calendario. Convierte ese dataclass (y cualquier futuro
            # resultado de tool no primitivo) antes de entregarlo a Promptfoo.
            "tool_calls": _json_safe(trace.tool_calls),
            "appointments": appointments,
        },
    }
