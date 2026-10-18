"""Arquitectura jerárquica: manager raíz y dos managers especializados."""
import sys
from agents import Agent, function_tool
from shared.parachute import agent_model, agent_model_settings, faq_tool, run_agent, run_chat, schedule_tool, weather_tool

MODEL = agent_model()
SETTINGS = agent_model_settings()
WEATHER_TOOL, FAQ_TOOL, SCHEDULE_TOOL = function_tool(weather_tool), function_tool(faq_tool), function_tool(schedule_tool)
weather_worker = Agent(name="WeatherWorker", instructions="Consulta Open-Meteo y aplica exactamente los umbrales.", tools=[WEATHER_TOOL], model=MODEL, model_settings=SETTINGS)
faq_worker = Agent(name="FAQWorker", instructions="Responde mediante la base de FAQs. Si no hay coincidencia, informa que no existe información. Nunca uses conocimiento general ni respondas temas ajenos a Parachute.", tools=[FAQ_TOOL], model=MODEL, model_settings=SETTINGS)
calendar_worker = Agent(name="CalendarWorker", instructions="Usa schedule_tool; la herramienta vuelve a consultar el clima y bloquea condiciones inseguras.", tools=[SCHEDULE_TOOL], model=MODEL, model_settings=SETTINGS)
weather_manager = Agent(name="WeatherManager", instructions="Coordina al worker meteorológico. Devuelve su resultado sin inventar.", tools=[weather_worker.as_tool(tool_name="ejecutar_revision_climatica", tool_description="Revisa clima para YYYY-MM-DD.")], model=MODEL, model_settings=SETTINGS)
faq_manager = Agent(name="FAQManager", instructions="Coordina al worker de preguntas frecuentes.", tools=[faq_worker.as_tool(tool_name="buscar_faq", tool_description="Busca respuesta en FAQs.")], model=MODEL, model_settings=SETTINGS)
calendar_manager = Agent(name="CalendarManager", instructions="Coordina calendarización. Rechaza reportes inseguros.", tools=[calendar_worker.as_tool(tool_name="ejecutar_calendarizacion", tool_description="Calendariza con reporte JSON aprobado.")], model=MODEL, model_settings=SETTINGS)
root_manager = Agent(
    name="RootManager",
    instructions="Eres manager raíz. Descompón la solicitud y delega a WeatherManager, FAQManager o CalendarManager. Para calendarizar, exige primero revisión meteorológica. Repite exactamente la decisión (IDEAL, MARGINAL o NO SEGURO / PROHIBIDO). Nunca digas confirmada: solo es tentativa si CalendarManager devuelve scheduled=true; si devuelve error, informa que no se calendarizó.",
    model=MODEL, model_settings=SETTINGS,
    tools=[weather_manager.as_tool(tool_name="delegar_clima", tool_description="Delega revisión climática."), faq_manager.as_tool(tool_name="delegar_faq", tool_description="Delega consulta FAQ."), calendar_manager.as_tool(tool_name="delegar_calendarizacion", tool_description="Delega calendarización después de revisar clima.")],
)

if __name__ == "__main__":
    query = " ".join(sys.argv[1:])
    run_chat(root_manager) if not query else print(run_agent(root_manager, query))
