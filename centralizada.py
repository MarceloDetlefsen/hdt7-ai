"""Arquitectura centralizada: un supervisor coordina todos los workers."""
import sys
from agents import Agent, function_tool
from shared.parachute import (
    agent_model,
    agent_model_settings,
    faq_tool,
    record_observed_call,
    run_agent,
    run_chat,
    schedule_tool,
    weather_tool,
)

MODEL = agent_model()
SETTINGS = agent_model_settings()


def _weather_worker_tool(date: str) -> str:
    return record_observed_call(
        "weather_tool",
        {"date": date},
        lambda: weather_tool(date),
        origin="agent:WeatherWorker",
    )


def _faq_worker_tool(question: str) -> str:
    return record_observed_call(
        "faq_tool",
        {"question": question},
        lambda: faq_tool(question),
        origin="agent:FAQWorker",
    )


def _calendar_worker_tool(date: str) -> str:
    return record_observed_call(
        "schedule_tool",
        {"date": date},
        lambda: schedule_tool(date),
        origin="agent:CalendarWorker",
    )


WEATHER_TOOL = function_tool(_weather_worker_tool, name_override="weather_tool")
FAQ_TOOL = function_tool(_faq_worker_tool, name_override="faq_tool")
SCHEDULE_TOOL = function_tool(_calendar_worker_tool, name_override="schedule_tool")
weather_worker = Agent(name="WeatherWorker", instructions="Usa weather_tool para consultar y evaluar una fecha. Nunca inventes datos.", tools=[WEATHER_TOOL], model=MODEL, model_settings=SETTINGS)
faq_worker = Agent(name="FAQWorker", instructions="Responde exclusivamente usando faq_tool. Si no hay coincidencia, di que no existe información en las FAQs. Nunca uses conocimiento general ni respondas temas ajenos a Parachute.", tools=[FAQ_TOOL], model=MODEL, model_settings=SETTINGS)
calendar_worker = Agent(name="CalendarWorker", instructions="Usa schedule_tool para que la propia integración vuelva a consultar el clima. Nunca inventes ni reutilices un reporte.", tools=[SCHEDULE_TOOL], model=MODEL, model_settings=SETTINGS)
supervisor = Agent(
    name="SupervisorCentral",
    instructions=("Eres el único supervisor de Parachute S.A. Decide qué worker usar. "
                  "Para una cita, consulta clima antes de aceptar; nunca autorices si el reporte dice NO SEGURO. "
                  "Si el usuario desea calendarizar, llama primero a WeatherWorker y después a CalendarWorker con el reporte exacto. "
                  "Nunca escribas APTO si la decisión es NO SEGURO / PROHIBIDO. Nunca digas confirmada: la cita solo es tentativa si CalendarWorker devuelve scheduled=true; si devuelve error, informa que no se calendarizó."),
    model=MODEL, model_settings=SETTINGS,
    tools=[weather_worker.as_tool(tool_name="consultar_clima", tool_description="Consulta clima y aptitud para una fecha."),
           faq_worker.as_tool(tool_name="consultar_faq", tool_description="Consulta las preguntas frecuentes."),
           calendar_worker.as_tool(tool_name="calendarizar_cita", tool_description="Calendariza una cita con un reporte meteorológico aprobado.")],
)

if __name__ == "__main__":
    query = " ".join(sys.argv[1:])
    run_chat(supervisor) if not query else print(run_agent(supervisor, query))
