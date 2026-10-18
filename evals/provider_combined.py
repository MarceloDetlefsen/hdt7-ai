"""Provider combinado para los evals determinísticos de P2 y P3.

FAQ se evalúa end-to-end mediante el agente centralizado real.
Las citas P3 utilizan el provider determinista para evaluar las reglas de
negocio sin depender de que un LLM decida emitir los tool calls.
"""

from __future__ import annotations

import provider
import provider_p3


def call_api(prompt, options, context):
    variables = (context or {}).get("vars", {})

    # Los casos P3 contienen variables específicas de calendarización/clima.
    is_appointment_case = any(
        key in variables
        for key in (
            "fixed_today",
            "weather_fixture",
            "weather_sequence",
            "initial_appointments",
        )
    )

    if is_appointment_case:
        return provider_p3.call_api(prompt, options, context)

    # Los casos FAQ no contienen las variables anteriores y se ejecutan
    # utilizando el agente real.
    return provider.call_api(prompt, options, context)
