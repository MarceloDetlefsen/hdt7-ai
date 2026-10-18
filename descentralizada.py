"""Arquitectura descentralizada: agentes pares colaboran mediante handoffs."""
import sys
from agents import Agent, function_tool
from pydantic import BaseModel, Field
from agents import handoff
from shared.parachute import agent_model, agent_model_settings, faq_tool, run_agent, run_chat, schedule_tool, weather_tool

MODEL = agent_model()
SETTINGS = agent_model_settings()
WEATHER_TOOL, FAQ_TOOL, SCHEDULE_TOOL = function_tool(weather_tool), function_tool(faq_tool), function_tool(schedule_tool)

class HandoffPayload(BaseModel):
    reason: str = Field(default="", description="Motivo breve de la delegación")

def acknowledge_handoff(_context, _payload):
    """Callback local para producir un esquema explícito y válido para Groq."""
    return None

weather_agent = Agent(name="WeatherAgent", instructions="Eres especialista independiente en clima. Consulta weather_tool; informa datos, decisión y razones.", tools=[WEATHER_TOOL], model=MODEL, model_settings=SETTINGS)
faq_agent = Agent(name="FAQAgent", instructions="Eres especialista independiente en FAQs. Usa faq_tool y responde en español. Si no hay coincidencia, rechaza temas ajenos a Parachute y nunca uses conocimiento general.", tools=[FAQ_TOOL], model=MODEL, model_settings=SETTINGS)
calendar_agent = Agent(name="CalendarAgent", instructions="Eres especialista independiente en citas. Usa schedule_tool; la herramienta vuelve a consultar Open-Meteo y bloquea condiciones inseguras. Nunca confirmes una cita si devuelve scheduled=false.", tools=[SCHEDULE_TOOL], model=MODEL, model_settings=SETTINGS)
intake_agent = Agent(
    name="IntakeAgent",
    instructions=("Eres un agente par de recepción, no un supervisor. Atiende saludos y decide a qué especialista entregar "
                  "la conversación. Si una consulta mezcla FAQ y clima, haz handoff al especialista que corresponda; los agentes pueden devolverse la conversación."),
    handoffs=[
        handoff(weather_agent, tool_name_override="transfer_to_weatheragent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
        handoff(faq_agent, tool_name_override="transfer_to_faqagent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
        handoff(calendar_agent, tool_name_override="transfer_to_calendaragent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
    ], model=MODEL, model_settings=SETTINGS,
)
weather_agent.handoffs = [
    handoff(faq_agent, tool_name_override="transfer_to_faqagent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
    handoff(calendar_agent, tool_name_override="transfer_to_calendaragent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
]
faq_agent.handoffs = [handoff(weather_agent, tool_name_override="transfer_to_weatheragent", input_type=HandoffPayload, on_handoff=acknowledge_handoff)]
calendar_agent.handoffs = [
    handoff(weather_agent, tool_name_override="transfer_to_weatheragent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
    handoff(faq_agent, tool_name_override="transfer_to_faqagent", input_type=HandoffPayload, on_handoff=acknowledge_handoff),
]

if __name__ == "__main__":
    query = " ".join(sys.argv[1:])
    run_chat(intake_agent) if not query else print(run_agent(intake_agent, query))
