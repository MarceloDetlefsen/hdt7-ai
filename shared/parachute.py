from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import time
import shutil
import subprocess
from copy import deepcopy
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from pathlib import Path
import unicodedata
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


_ACTIVE_TRACE: ContextVar["ToolCallTrace | None"] = ContextVar(
    "parachute_active_tool_trace", default=None
)
_ACTIVE_TRACE_ORIGIN: ContextVar[str | None] = ContextVar(
    "parachute_active_tool_origin", default=None
)
_ACTIVE_EVAL_TODAY: ContextVar[dt.date | None] = ContextVar(
    "parachute_active_eval_today", default=None
)
_ACTIVE_WEATHER_FIXTURE: ContextVar[dict[str, object] | None] = ContextVar(
    "parachute_active_weather_fixture", default=None
)
_ACTIVE_REQUEST_APPOINTMENTS: ContextVar[list[dict[str, object]] | None] = ContextVar(
    "parachute_active_request_appointments", default=None
)


@contextmanager
def evaluation_dependencies(
    *,
    today: dt.date | None = None,
    weather_fixture: dict[str, object] | None = None,
    weather_sequence: list[dict[str, object]] | None = None,
):
    """Activa dependencias simuladas de evaluación para el turno actual.

    Las reglas de validación y evaluación continúan siendo las mismas; solo se
    reemplaza la fuente meteorológica durante el contexto.
    """
    today_token = _ACTIVE_EVAL_TODAY.set(today)
    weather_token = _ACTIVE_WEATHER_FIXTURE.set(
        {
            "fallback": deepcopy(weather_fixture),
            "sequence": deepcopy(weather_sequence or []),
        }
        if weather_fixture is not None or weather_sequence is not None
        else None
    )
    try:
        yield
    finally:
        _ACTIVE_WEATHER_FIXTURE.reset(weather_token)
        _ACTIVE_EVAL_TODAY.reset(today_token)


class ToolCallTrace:
    """Registro por ejecución de llamadas observadas durante un turno."""

    def __init__(self) -> None:
        self.tool_calls: list[dict[str, object]] = []
        self._next_order = 1
        self.current_origin: str | None = None

    def push_origin(self, value: str) -> str | None:
        previous = self.current_origin
        self.current_origin = value
        return previous

    def pop_origin(self, previous: str | None) -> None:
        self.current_origin = previous

    @contextmanager
    def activate(self):
        token = _ACTIVE_TRACE.set(self)
        try:
            yield self
        finally:
            _ACTIVE_TRACE.reset(token)

    @contextmanager
    def origin(self, value: str):
        token = _ACTIVE_TRACE_ORIGIN.set(value)
        try:
            yield
        finally:
            _ACTIVE_TRACE_ORIGIN.reset(token)

    def start(self, name: str, arguments: object, origin: str) -> int:
        order = self._next_order
        self._next_order += 1
        self.tool_calls.append(
            {
                "order": order,
                "name": name,
                "arguments": arguments,
                "result": None,
                "error": None,
                "origin": origin,
            }
        )
        return len(self.tool_calls) - 1

    def finish(
        self,
        index: int,
        *,
        result: object = None,
        error: str | None = None,
    ) -> None:
        call = self.tool_calls[index]
        call["result"] = result
        call["error"] = error

    def fail_open_calls(self, error: str) -> None:
        """Marca como fallidas las llamadas que no alcanzaron su callback final."""
        for call in self.tool_calls:
            if call["result"] is None and call["error"] is None:
                call["error"] = error

    def completed(
        self,
        name: str,
        arguments: object,
        *,
        result: object = None,
        error: str | None = None,
        origin: str | None = None,
    ) -> None:
        index = self.start(
            name,
            arguments,
            origin or _ACTIVE_TRACE_ORIGIN.get() or "hdt4",
        )
        self.finish(index, result=result, error=error)


def active_tool_trace() -> ToolCallTrace | None:
    """Devuelve el registro del turno actual, si existe."""
    return _ACTIVE_TRACE.get()


def active_tool_origin() -> str | None:
    """Devuelve el agente/origen que está ejecutando la llamada actual."""
    return _ACTIVE_TRACE_ORIGIN.get() or (
        _ACTIVE_TRACE.get().current_origin if _ACTIVE_TRACE.get() else None
    )


def record_observed_call(
    name: str,
    arguments: object,
    func,
    *,
    origin: str,
):
    """Ejecuta y registra una llamada observada fuera de un SDK hook."""
    trace = active_tool_trace()
    if trace is None:
        return func()
    index = trace.start(name, arguments, origin)
    with trace.origin(origin):
        try:
            result = func()
        except Exception as exc:
            trace.finish(index, error=str(exc))
            raise
    trace.finish(index, result=result)
    return result


def agent_model():
    """Devuelve el modelo configurado: Groq compatible si hay una clave gsk_, o el default de OpenAI."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not groq_key and openai_key.startswith("gsk_"):
        groq_key = openai_key
    if groq_key:
        from agents import OpenAIChatCompletionsModel, set_tracing_disabled
        from openai import AsyncOpenAI
        set_tracing_disabled(True)
        client = AsyncOpenAI(
            api_key=groq_key,
            base_url=os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        )
        model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
        # Este es el modelo Groq disponible en el entorno HDT4; ocultamos su razonamiento
        # para que no se mezcle con los nombres de herramientas del Agents SDK.
        if model_name in {"llama-3.3-70b-versatile", "qwen/qwen3.6-27b", "qwen/qwen3.8-27b"}:
            model_name = "openai/gpt-oss-20b"
        return OpenAIChatCompletionsModel(
            model=model_name,
            openai_client=client,
        )
    return None


def agent_model_settings():
    from agents import ModelSettings
    if os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY", "").startswith("gsk_"):
        return ModelSettings(extra_body={"include_reasoning": False})
    return None

LATITUDE = 14.013722
LONGITUDE = -90.771611
MAX_FORECAST_DAYS = 16


@dataclass
class WeatherReport:
    date: str
    temperature_c: float | None
    precipitation_mm: float | None
    cloud_cover_pct: float | None
    visibility_m: float | None
    wind_speed_kmh: float | None
    wind_gust_kmh: float | None
    decision: str
    reasons: list[str]


def validate_date(date_text: str, today: dt.date | None = None) -> dt.date:
    try:
        requested = dt.date.fromisoformat(date_text)
    except ValueError as exc:
        raise ValueError("La fecha debe tener el formato YYYY-MM-DD.") from exc
    today = today or _ACTIVE_EVAL_TODAY.get() or dt.date.today()
    if requested < today:
        raise ValueError("No se pueden calendarizar citas en una fecha pasada.")
    # Los 16 días de Open-Meteo incluyen el día actual: el último día es hoy + 15.
    if requested >= today + dt.timedelta(days=MAX_FORECAST_DAYS):
        raise ValueError("Open-Meteo solo permite consultar los próximos 16 días, contando hoy.")
    return requested


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def fetch_weather(date_text: str) -> WeatherReport:
    requested = validate_date(date_text)
    fixture_state = _ACTIVE_WEATHER_FIXTURE.get()
    if fixture_state is not None:
        sequence = fixture_state["sequence"]
        if not isinstance(sequence, list):
            raise RuntimeError("El estado de la secuencia meteorológica no es válido.")
        if sequence:
            fixture = sequence.pop(0)
        else:
            fixture = fixture_state["fallback"]
        if fixture is None:
            raise RuntimeError(
                "La secuencia meteorológica de evaluación se agotó y no hay fixture de respaldo."
            )
        if not isinstance(fixture, dict):
            raise ValueError("Cada fixture meteorológico debe ser un objeto JSON.")
        report = WeatherReport(
            date=date_text,
            temperature_c=fixture.get("temperature_c"),
            precipitation_mm=fixture.get("precipitation_mm"),
            cloud_cover_pct=fixture.get("cloud_cover_pct"),
            visibility_m=fixture.get("visibility_m"),
            wind_speed_kmh=fixture.get("wind_speed_kmh"),
            wind_gust_kmh=fixture.get("wind_gust_kmh"),
            decision="",
            reasons=[],
        )
        return evaluate_weather(report)
    params = urllib.parse.urlencode({
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "daily": "temperature_2m_mean,precipitation_sum,cloud_cover_mean,visibility_mean,wind_speed_10m_max,wind_gusts_10m_max",
        "timezone": "America/Guatemala",
        "start_date": requested.isoformat(),
        "end_date": requested.isoformat(),
    })
    url = "https://api.open-meteo.com/v1/forecast?" + params
    request = urllib.request.Request(url, headers={"User-Agent": "HDT5-Parachute/1.0"})
    last_error = None
    payload = None
    # Preferimos curl porque es la misma ruta que el usuario verificó manualmente.
    if shutil.which("curl"):
        for attempt in range(3):
            result = subprocess.run(
                ["curl", "--ipv4", "--fail", "--silent", "--show-error", "--max-time", "15", url],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                payload = json.loads(result.stdout)
                break
            last_error = RuntimeError(result.stderr.strip() or "curl no pudo consultar Open-Meteo")
            if attempt < 2:
                time.sleep(1)
    if payload is None:
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    payload = json.load(response)
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1)
    if payload is None:
        raise last_error or RuntimeError("No se pudo consultar Open-Meteo.")
    daily = payload.get("daily", {})
    temps = [x for x in daily.get("temperature_2m_mean", []) if x is not None]
    precip = [x for x in daily.get("precipitation_sum", []) if x is not None]
    clouds = [x for x in daily.get("cloud_cover_mean", []) if x is not None]
    visibility = [x for x in daily.get("visibility_mean", []) if x is not None]
    winds = [x for x in daily.get("wind_speed_10m_max", []) if x is not None]
    gusts = [x for x in daily.get("wind_gusts_10m_max", []) if x is not None]
    report = WeatherReport(
        date=date_text,
        temperature_c=_mean(temps),
        precipitation_mm=round(sum(precip), 2) if precip else None,
        cloud_cover_pct=round(max(clouds), 2) if clouds else None,
        visibility_m=round(min(visibility), 2) if visibility else None,
        wind_speed_kmh=round(max(winds), 2) if winds else None,
        wind_gust_kmh=round(max(gusts), 2) if gusts else None,
        decision="",
        reasons=[],
    )
    return evaluate_weather(report)


def evaluate_weather(report: WeatherReport) -> WeatherReport:
    reasons: list[str] = []
    unsafe = False
    marginal = False
    if report.wind_speed_kmh is None or report.wind_gust_kmh is None or report.precipitation_mm is None or report.cloud_cover_pct is None:
        unsafe, reasons = True, ["Faltan datos meteorológicos para autorizar el salto."]
    else:
        if report.wind_speed_kmh > 28:
            unsafe, reasons = True, reasons + ["Viento superficial superior a 28 km/h."]
        elif report.wind_speed_kmh >= 20:
            marginal, reasons = True, reasons + ["Viento superficial marginal (20–28 km/h): solo tándem experimentado."]
        if report.wind_gust_kmh > 35:
            unsafe, reasons = True, reasons + ["Ráfagas superiores a 35 km/h."]
        if report.precipitation_mm > 0:
            unsafe, reasons = True, reasons + ["Existe precipitación."]
        if report.cloud_cover_pct > 75:
            unsafe, reasons = True, reasons + ["Cobertura de nubes superior a 75%."]
        elif report.cloud_cover_pct >= 30:
            marginal, reasons = True, reasons + ["Cobertura marginal (30–75%)."]
    report.decision = "NO SEGURO / PROHIBIDO" if unsafe else ("MARGINAL" if marginal else "IDEAL")
    report.reasons = reasons or ["Condiciones dentro del rango ideal definido por Parachute S.A."]
    return report


def weather_tool(date: str) -> str:
    """Consulta Open-Meteo y evalúa si la fecha es apta para saltar. Recibe YYYY-MM-DD."""
    try:
        return json.dumps(asdict(fetch_weather(date)), ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def schedule_tool(date: str) -> str:
    """Consulta nuevamente Open-Meteo y calendariza solo si el clima real es IDEAL o MARGINAL."""
    try:
        validate_date(date)
        # Nunca se confía en un reporte generado por el LLM: la calendarización
        # ejecuta su propia consulta de clima como última barrera de seguridad.
        report = fetch_weather(date)
        decision = report.decision
        if decision not in {"IDEAL", "MARGINAL"}:
            return json.dumps({"scheduled": False, "error": "La cita no puede calendarizarse: condiciones NO SEGURO / PROHIBIDO o reporte inválido."}, ensure_ascii=False)
        APPOINTMENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        appointments = json.loads(APPOINTMENTS_PATH.read_text(encoding="utf-8")) if APPOINTMENTS_PATH.exists() else []
        appointment = {"date": date, "decision": decision, "status": "pending_instructor_confirmation", "weather": asdict(report)}
        appointments.append(appointment)
        APPOINTMENTS_PATH.write_text(json.dumps(appointments, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.dumps({"scheduled": True, **appointment, "message": "Cita calendarizada tentativamente; el instructor debe confirmar la operación."}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"scheduled": False, "error": str(exc)}, ensure_ascii=False)


FAQ_PATH = PROJECT_ROOT / "data" / "Corpus_FAQs_Parachute_SA_2026.txt"
HDT4_FAQ_PATH = Path(__file__).resolve().parents[2] / "ai-function-calls" / "data" / "Corpus_FAQs_Parachute_SA_2026.txt"
HDT4_SRC_PATH = Path(__file__).resolve().parents[1] / "hdt4" / "src"
APPOINTMENTS_PATH = Path(__file__).resolve().parents[1] / "data" / "citas.json"

def _normalize(text: str) -> set[str]:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]{3,}", text))


def _hdt4_faq_answer(question: str) -> str:
    """Invoca literalmente el flujo run_agent_turn de HDT4."""
    if not HDT4_SRC_PATH.exists():
        raise FileNotFoundError("No está disponible la implementación de búsqueda de HDT4.")
    source = str(HDT4_SRC_PATH)
    if source not in sys.path:
        sys.path.insert(0, source)
    from agent import run_agent_turn
    from groq_client import get_groq_client
    client = get_groq_client()
    answer = run_agent_turn(client, [], question)
    no_answer = "Lo siento, no puedo responder esa pregunta con la información disponible"
    # Fallback de orquestación: HDT4 sigue siendo quien busca y redacta cada
    # respuesta; solo repetimos su flujo por cláusula si el separador original
    # no detectó una consulta compuesta.
    if no_answer in answer and re.search(r"\s+y\s+", question, flags=re.IGNORECASE):
        parts = [part.strip(" .,;!?¿¡") for part in re.split(r"\s+y\s+", question, flags=re.IGNORECASE)]
        independent = [run_agent_turn(client, [], part) for part in parts if part]
        if any(no_answer not in item for item in independent):
            return "\n\n".join(independent)
    return answer


def faq_tool(question: str) -> str:
    """Responde usando exactamente el agente conversacional de FAQs de HDT4."""
    try:
        return _hdt4_faq_answer(question)
    except Exception as exc:
        return f"No está disponible la búsqueda FAQ de HDT4: {exc}"


def extract_date(text: str) -> str | None:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return match.group(1) if match else None


def _read_appointments() -> list[dict[str, object]]:
    if not APPOINTMENTS_PATH.exists():
        return []
    try:
        content = APPOINTMENTS_PATH.read_text(encoding="utf-8").strip()
        value = json.loads(content) if content else []
    except (OSError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


def _new_appointment_for_date(
    initial: list[dict[str, object]], date: str,
) -> bool:
    remaining = deepcopy(initial)
    for appointment in _read_appointments():
        if appointment in remaining:
            remaining.remove(appointment)
        elif appointment.get("date") == date:
            return True
    return False


def _successful_schedule_call(date: str, result: object | None = None) -> bool:
    """Comprueba el resultado real de schedule_tool, no el texto del LLM."""
    candidates = []
    trace = active_tool_trace()
    if trace is not None:
        candidates.extend(
            call for call in trace.tool_calls
            if call.get("name") == "schedule_tool"
            and call.get("error") is None
            and isinstance(call.get("arguments"), dict)
            and call["arguments"].get("date") == date
        )
    if result is not None:
        candidates.append({"result": result})
    for call in candidates:
        value = call.get("result")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                continue
        if isinstance(value, dict) and value.get("scheduled") is True:
            return True
    return False


def _calendarization_verified(
    date: str,
    result: object | None = None,
    initial: list[dict[str, object]] | None = None,
) -> bool:
    initial = initial if initial is not None else _ACTIVE_REQUEST_APPOINTMENTS.get()
    if initial is None:
        initial = _read_appointments()
    return _successful_schedule_call(date, result) and _new_appointment_for_date(initial, date)


def _apply_calendar_guard(user_text: str, output: str) -> str:
    date = extract_date(user_text)
    lowered = user_text.lower()
    is_calendar = date and (
        any(word in lowered for word in ("cita", "calendar", "agendar", "reservar"))
        or any(phrase in lowered for phrase in (
            "esa fecha", "esa cita", "quiero la fecha", "la quiero para",
            "lo quiero para", "quiero para", "para esta fecha", "en esta fecha",
        ))
    )
    if not is_calendar:
        return output
    request_initial = _ACTIVE_REQUEST_APPOINTMENTS.get()
    if request_initial is None:
        request_initial = _read_appointments()
    # Postcondición de seguridad: el texto del LLM nunca puede contradecir
    # el clima real consultado por la integración compartida.
    report = record_observed_call(
        "fetch_weather",
        {"date": date},
        lambda: fetch_weather(date),
        origin="guard:calendar",
    )
    metrics = (f"Temperatura: {report.temperature_c} °C; precipitación: {report.precipitation_mm} mm; "
               f"nubes: {report.cloud_cover_pct}%; visibilidad: {report.visibility_m} m; "
               f"viento: {report.wind_speed_kmh} km/h; ráfagas: {report.wind_gust_kmh} km/h.")
    if report.decision == "NO SEGURO / PROHIBIDO":
        return f"Decisión: NO SEGURO / PROHIBIDO.\n{metrics}\nLa cita no fue calendarizada. Razones: {' '.join(report.reasons)}"
    if not output.strip() or "no puedo" in output.lower() or "no dispongo" in output.lower():
        raw_result = record_observed_call(
            "schedule_tool",
            {"date": date},
            lambda: schedule_tool(date),
            origin="guard:calendar",
        )
        result = json.loads(raw_result)
        if result.get("scheduled") and _calendarization_verified(date, result, request_initial):
            return f"{metrics}\n{result.get('message', 'Resultado de calendarización.')}"
        return f"{metrics}\nLa cita no fue calendarizada: no se pudo verificar la herramienta y la persistencia de esta solicitud."
    if _successful_schedule_call(date) and _new_appointment_for_date(request_initial, date):
        return output
    if re.search(r"\b(cita|reserva)\b", output, re.IGNORECASE) and re.search(
        r"\b(agend\w*|calendariz\w*|confirm\w*|program\w*)\b", output, re.IGNORECASE
    ):
        return f"{output}\nLa cita no fue confirmada: no se encontró una llamada exitosa a schedule_tool con una cita nueva persistida en esta solicitud."
    return output


def _apply_domain_guard(user_text: str, output: str) -> str:
    """Impide que el modelo responda conocimiento general fuera de Parachute/FAQs."""
    lowered = user_text.lower().strip()
    if any(word in lowered for word in ("clima", "tiempo", "cita", "calendar", "agendar", "reservar", "salto")):
        return output
    smalltalk_vocabulary = {"hola", "buenas", "buenos", "dias", "tardes", "noches", "como", "estas", "gracias", "adios"}
    if _normalize(lowered) and _normalize(lowered).issubset(smalltalk_vocabulary):
        return output
    # HDT4 divide preguntas, consulta cada parte y genera una respuesta
    # fundamentada. No concatenamos ni reinterpretamos sus resultados.
    return record_observed_call(
        "faq_tool",
        {"question": user_text},
        lambda: faq_tool(user_text),
        origin="guard:domain",
    )


def run_agent(agent, user_text: str, *, run_hooks=None) -> str:
    from agents import Runner
    request_token = _ACTIVE_REQUEST_APPOINTMENTS.set(deepcopy(_read_appointments()))
    owned_trace = active_tool_trace() is None
    trace_context = ToolCallTrace().activate() if owned_trace else nullcontext()
    with trace_context:
        try:
            # HDT4 definía respuestas deterministas para cortesía; se conserva ese
            # comportamiento antes de invocar al modelo de orquestación.
            source = str(HDT4_SRC_PATH)
            if source not in sys.path:
                sys.path.insert(0, source)
            try:
                from agent import get_conversational_response
                conversational = get_conversational_response(user_text)
            except ImportError:
                conversational = None
            if conversational is not None:
                return conversational
            output = Runner.run_sync(agent, user_text, hooks=run_hooks).final_output or ""
            output = _apply_calendar_guard(user_text, output)
            return _apply_domain_guard(user_text, output)
        except Exception as exc:
            trace = active_tool_trace()
            if trace is not None:
                trace.fail_open_calls(str(exc))
            return f"No se pudo completar la solicitud. Verifica el modelo y la conexión del proveedor: {exc}"
        finally:
            _ACTIVE_REQUEST_APPOINTMENTS.reset(request_token)


def run_chat(agent) -> None:
    """Ejecuta una sesión multi-turno conservando el historial del agente."""
    from agents import Runner
    history = []
    print("Chat iniciado. Escribe 'salir' para terminar.")
    try:
        while True:
            user_text = input("Tú: ").strip()
            if user_text.lower() in {"salir", "exit", "quit"}:
                print("Sesión finalizada.")
                return
            if not user_text:
                continue
            try:
                # Conserva las respuestas conversacionales deterministas de HDT4
                # también en el modo interactivo.
                source = str(HDT4_SRC_PATH)
                if source not in sys.path:
                    sys.path.insert(0, source)
                from agent import get_conversational_response
                conversational = get_conversational_response(user_text)
                if conversational is not None:
                    history.extend([
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": conversational},
                    ])
                    print(f"Agente: {conversational}")
                    continue
                # Una fecha acompañada de una continuación de reserva se rutea
                # directamente al flujo climático, sin depender de la decisión
                # probabilística del supervisor.
                if extract_date(user_text) and any(phrase in user_text.lower() for phrase in (
                    "esa fecha", "esa cita", "la quiero para", "lo quiero para",
                    "quiero para", "para esta fecha", "en esta fecha",
                )):
                    print(f"Agente: {_apply_calendar_guard(user_text, '')}")
                    continue
                result = Runner.run_sync(agent, history + [{"role": "user", "content": user_text}])
                history = result.to_input_list()
                output = _apply_calendar_guard(user_text, result.final_output or "")
                print(f"Agente: {_apply_domain_guard(user_text, output)}")
            except Exception as exc:
                print(f"Agente: No se pudo completar la solicitud: {exc}")
    except (EOFError, KeyboardInterrupt):
        print("\nSesión finalizada.")
