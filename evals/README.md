# Hoja de Trabajo 6 - Evals

Evaluación del sistema de asistencia conversacional desarrollado para **Parachute S.A.** utilizando [Promptfoo](https://www.promptfoo.dev/).

---

## 1. Objetivo y Alcance

El sistema de Parachute S.A. posee dos funcionalidades esenciales de negocio:

1. **Resolver preguntas frecuentes (FAQs):** Información sobre peso máximo, edad mínima, políticas de cancelación, alimentos y servicios generales mediante la base de conocimientos oficial.
2. **Agendamiento seguro de citas:** Calendarización sujeta a condiciones meteorológicas en tiempo real (Open-Meteo), ventana máxima de pronóstico de 16 días y reglas estrictas de seguridad aeronáutica (viento, ráfagas, precipitación y nubosidad).

Como etapa previa a su puesta en producción y para soportar futuras iteraciones de producto, se implementaron evaluaciones rigurosas con Promptfoo cubriendo los cuatro criterios clave solicitados:

- **Factuality:** Fidelidad factual evaluada mediante un modelo LLM como juez (`factuality`).
- **Evaluaciones determinísticas:** Validaciones exactas con `icontains` y expresiones regulares (`regex`) con tolerancia a variaciones de formato.
- **Latencia:** Control estricto de tiempo de respuesta mediante aserciones de `latency` con umbral de 60 segundos sin uso de caché.
- **Tool execution:** Verificación de herramientas ejecutadas (obligatorias y prohibidas) a través de la traza observable, validando además la persistencia real de citas en disco.

---

## 2. Estructura de los Evals

Los archivos del módulo de evaluación se organizan de la siguiente manera:

```text
hdt6-ai/
├── README.md                          # Documentación general del repositorio
├── assertions.js                      # Validador JavaScript para tools y persistencia
├── assertions.test.js                 # Pruebas unitarias de las aserciones JS
├── reporte-evals.json                 # Reporte principal de la suite unificada (21 casos)
├── reporte-factuality.json            # Reporte de la suite de factuality (2 casos)
│
└── evals/
    ├── README.md                      # Esta guía técnica detallada
    ├── promptfooconfig.yaml           # Configuración principal unificada (21 casos)
    ├── promptfooconfig-faq.yaml       # Configuración modular: solo FAQs (6 casos)
    ├── promptfooconfig-p3.yaml        # Configuración modular: solo Citas (15 casos)
    ├── promptfooconfig-factuality.yaml# Configuración de factuality con LLM judge (2 casos)
    ├── provider_combined.py           # Router de providers para la suite principal
    ├── provider.py                    # Provider que ejecuta el agente supervisor real
    ├── provider_p3.py                 # Provider determinista para reglas meteorológicas
    ├── reporte-p3.json                # Reporte generado de la ejecución modular P3
    └── cases/
        ├── faq.yaml                   # Definición de los 6 casos de prueba de FAQs
        └── appointments.yaml          # Definición de los 15 casos de calendarización
```

### Organización de las Suites

| Suite | Archivo de Configuración | Casos | Propósito y Criterios Evaluados |
| :--- | :--- | :---: | :--- |
| **Principal Unificada** | `evals/promptfooconfig.yaml` | 21 | FAQ + Citas: determinísticos, latencia, tools obligatorias/prohibidas y persistencia en disco. |
| **Factuality** | `evals/promptfooconfig-factuality.yaml` | 2 | Evaluación con LLM Judge sobre muestra representativa (1 FAQ + 1 Cita). |
| **Modular FAQ** | `evals/promptfooconfig-faq.yaml` | 6 | Ejecución aislada de preguntas frecuentes contra el agente real. |
| **Modular P3 (Citas)**| `evals/promptfooconfig-p3.yaml` | 15 | Ejecución aislada de reglas meteorológicas y límites de seguridad. |

---

## 3. Instalación y Preparación

Desde la raíz del repositorio (`hdt6-ai/`):

1. **Instalar dependencias de Node.js:**
   ```bash
   npm install
   ```

2. **Activar el entorno virtual de Python y cargar variables de entorno:**
   ```bash
   source ../ai-function-calls/.venv/bin/activate
   set -a
   source .env
   set +a
   ```

3. **Verificar variables requeridas en `.env`:**
   ```dotenv
   GROQ_API_KEY=gsk_...
   GROQ_MODEL=openai/gpt-oss-20b
   GROQ_BASE_URL=https://api.groq.com/openai/v1
   ```

---

## 4. Arquitectura de Providers y Enrutamiento

Para garantizar reproducibilidad sin sacrificar la evaluación del agente conversacional real, se diseñó una arquitectura de providers desacoplada coordinada por `evals/provider_combined.py`:

```text
                        evals/provider_combined.py
                                    |
                    +---------------+---------------+
                    |                               |
              (Casos FAQ)                    (Casos Citas)
                    |                               |
                    v                               v
             evals/provider.py             evals/provider_p3.py
                    |                               |
       [SupervisorCentral real]       [Reglas y Wrappers Centralizados]
                    |                               |
          Llama a FAQWorker vía           Ejecución determinista de
         search_knowledge_base          reglas climáticas con fixtures
```

### ¿Por qué desacoplar el provider de citas (`provider_p3.py`)?

1. **Evaluación de reglas deterministas vs. no-determinismo del LLM:** La calendarización de paracaidismo maneja límites críticos de seguridad aeronáutica (viento $>28\text{ km/h}$, ráfagas $>35\text{ km/h}$, lluvia $>0\text{ mm}$, nubes $>75\%$). Si se dependiera de que un LLM decidiera llamar a las herramientas en cada corrida, una variación estocástica del modelo podría ocultar un fallo en las reglas de negocio.
2. **Uso de Fixtures Meteorológicos:** Open-Meteo varía día con día. `provider_p3.py` permite inyectar condiciones climáticas simuladas (`weather_fixture`), fechas controladas (`fixed_today`) y aislar el almacenamiento en archivos temporales para evaluar cada rama lógica de forma 100% reproducible.

---

## 5. Suite Principal Unificada (21 Casos)

La configuración `evals/promptfooconfig.yaml` consolida los 6 casos de FAQ y los 15 casos de citas en una sola corrida end-to-end.

### Comando de Ejecución

```bash
PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo" \
npx --no-install promptfoo eval \
  -c evals/promptfooconfig.yaml \
  --no-cache \
  -o reporte-evals.json
```

### Resultados de la Suite Principal

```text
==================================================
RESULTADOS DE LA EVALUACIÓN
==================================================
Total de Casos: 21
Passed:         20 (95.24%)
Failed:         1 (4.76%)
Errors:         0
Reporte:        reporte-evals.json
==================================================
```

### Análisis de Ingeniería del Único FAIL

El único caso no superado en la suite fue:
> **Pregunta:** *"¿Se permite el ingreso de alimentos y bebidas?"*

- **Comportamiento observable:** La traza registrada en `metadata.tool_calls` comprobó que el agente invocó correctamente la herramienta `consultar_faq` desde `agent:SupervisorCentral`, la cual a su vez ejecutó `search_knowledge_base` en `agent:FAQWorker` y extrajo la respuesta adecuada del corpus oficial.
- **Causa del FAIL:** La llamada completa demoró más de los 60 segundos definidos como umbral de latencia (`threshold: 60000`), alcanzando el límite técnico del provider debido a variabilidad/congestión del servicio de inferencia de Groq.
- **Justificación de Calidad:** Se tomó la decisión de **conservar este resultado como FAIL** en lugar de incrementar arbitrariamente el umbral de latencia a 120 segundos para forzar un 100%. Este resultado demuestra la utilidad práctica de los evals para detectar cuellos de botella reales de infraestructura y latencia antes de producción.

---

## 6. Detalle de Casos: Preguntas Frecuentes (FAQ)

Los casos de FAQ (`evals/cases/faq.yaml`) evalúan tanto preguntas dentro del dominio de la empresa como preguntas que deben ser rechazadas amablemente:

1. **Caso 1: Peso máximo permitido**
   - **Pregunta:** *"¿Cuál es el peso máximo permitido para saltar?"*
   - **Objetivo:** Verificar que el límite operacional es estrictamente de 100 kg.
   - **Aserción:** Expresión regular `100[\s\u00A0\u202F]*kg`, tolerante a espacios no rompibles (NBSP) o delgados generados por el LLM.
   - **Tools requeridas:** `consultar_faq` (Supervisor) $\rightarrow$ `search_knowledge_base` (FAQWorker).

2. **Caso 2: Edad mínima requerida**
   - **Pregunta:** *"¿A partir de qué edad se puede realizar un salto en paracaídas?"*
   - **Objetivo:** Comprobar la restricción legal y de seguro de mayoría de edad.
   - **Aserción:** `icontains: "18 años cumplidos"`.
   - **Tools requeridas:** `consultar_faq` $\rightarrow$ `search_knowledge_base`.

3. **Caso 3: Ingreso de alimentos y bebidas**
   - **Pregunta:** *"¿Se permite el ingreso de alimentos y bebidas al predio?"*
   - **Objetivo:** Informar sobre la política de admisión de alimentos en las instalaciones.
   - **Aserción:** `regex: '(no se permite|prohibido|alimentos|bebidas)'`.
   - **Tools requeridas:** `consultar_faq` $\rightarrow$ `search_knowledge_base`.

4. **Caso 4: Disponibilidad de parqueo**
   - **Pregunta:** *"¿Tienen parqueo disponible y cuál es el costo?"*
   - **Objetivo:** Responder que las instalaciones cuentan con parqueo gratuito para clientes.
   - **Aserción:** `regex: '(parqueo|gratuito|estacionamiento)'`.
   - **Tools requeridas:** `consultar_faq` $\rightarrow$ `search_knowledge_base`.

5. **Caso 5: Pregunta fuera de dominio (Fútbol)**
   - **Pregunta:** *"¿Quién ganó el último mundial de fútbol?"*
   - **Objetivo:** Validar que el agente no alucine respuestas fuera de su catálogo y delimite cortésmente su alcance.
   - **Aserción:** `regex: '(no tengo información|solo puedo responder|Parachute S.A.|paracaidismo)'`.
   - **Comportamiento:** Puede consultar la base de conocimiento y reconocer la falta de datos sin inventar información.

6. **Caso 6: Pregunta fuera de dominio (Música K-Pop)**
   - **Pregunta:** *"¿Cuál es la canción más famosa de BTS?"*
   - **Objetivo:** Comprobar el manejo seguro ante preguntas de cultura popular ajenas a la empresa.
   - **Aserción:** `regex: '(no tengo información|solo puedo responder|Parachute S.A.|paracaidismo)'`.

---

## 7. Detalle de Casos: Calendarización de Citas (15 Casos)

Los 15 casos de calendarización (`evals/cases/appointments.yaml`) cubren exhaustivamente condiciones climáticas favorables, límites críticos de seguridad aeronáutica, validación de fechas y manejo de fallos técnicos.

### Control de Dependencias Aisladas y Fixtures

Para garantizar que las pruebas sean 100% deterministas y reproducibles (sin depender del clima en tiempo real ni de fechas calendario fijas), los casos definen variables controladas:

| Variable | Tipo / Ejemplo | Propósito en la Evaluación |
| :--- | :--- | :--- |
| `fixed_today` | `"2026-09-30"` | Fija la fecha actual del sistema para evaluar ventanas relativas y pasado. |
| `weather_fixture` | JSON con métricas climáticas | Simula velocidad y ráfagas de viento, lluvia, nubes y visibilidad. |
| `weather_sequence` | `["simulated API failure"]` | Inyecta secuencias de fallo en la llamada de red. |
| `initial_appointments` | `[]` | Estado previo de la base de citas en almacenamiento temporal. |
| `required_tools` | `[{"name":"weather_tool"}]` | Lista de herramientas que obligatoriamente deben ejecutarse. |
| `forbidden_tools` | `[{"name":"schedule_tool"}]` | Herramientas cuya ejecución provoca un fallo inmediato (FAIL). |
| `expected_created_appointments` | `0` o `1` | Número exacto de citas que deben quedar persistidas en disco. |

### Desglose Individual de los 15 Casos de Citas

1. **P3 - Clima Ideal (Persiste la cita):**
   - **Parámetros:** Fecha `2026-10-01` (hoy `2026-09-30`). Viento $10\text{ km/h}$, ráfagas $20\text{ km/h}$, nubes $10\%$, lluvia $0\text{ mm}$.
   - **Clasificación:** `IDEAL`.
   - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 1`.

2. **P3 - Clima Marginal por viento (Permite la cita):**
   - **Parámetros:** Fecha `2026-10-02`. Viento $20\text{ km/h}$, ráfagas $30\text{ km/h}$, nubes $10\%$, lluvia $0\text{ mm}$.
   - **Clasificación:** `MARGINAL` (condición para tándem experimentado; requiere confirmación del instructor).
   - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 1`.

3. **P3 - Límite de viento mínimo marginal (Exactamente 20 km/h):**
   - **Parámetros:** Fecha `2026-10-03`. Viento $20\text{ km/h}$ (frontera exacta entre ideal y marginal).
   - **Clasificación:** `MARGINAL`.
   - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 1`.

4. **P3 - Límite de viento máximo marginal (Exactamente 28 km/h):**
   - **Parámetros:** Fecha `2026-10-04`. Viento $28\text{ km/h}$ (límite superior antes de prohibición).
   - **Clasificación:** `MARGINAL`.
   - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 1`.

5. **P3 - Límite de nubes marginal inferior (Exactamente 30%):**
   - **Parámetros:** Fecha `2026-10-05`. Cobertura nubosa $30\%$ (frontera entre cielo claro y nubes dispersas).
   - **Clasificación:** `MARGINAL`.
   - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 1`.

6. **P3 - Límite de nubes marginal superior (Exactamente 75%):**
   - **Parámetros:** Fecha `2026-10-06`. Cobertura nubosa $75\%$ (techo máximo admisible bajo reglas visuales VFR).
   - **Clasificación:** `MARGINAL`.
   - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 1`.

7. **P3 - Viento apenas sobre el límite (28.01 km/h - NO SEGURO / PROHIBIDO):**
   - **Parámetros:** Fecha `2026-10-07`. Viento $28.01\text{ km/h}$ (supera el umbral por $0.01\text{ km/h}$).
   - **Clasificación:** `NO SEGURO / PROHIBIDO`.
   - **Herramientas requeridas:** `weather_tool`.
   - **Herramientas prohibidas:** `calendarizar_cita`, `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 0`.

8. **P3 - Ráfagas apenas sobre el límite (35.1 km/h - NO SEGURO / PROHIBIDO):**
   - **Parámetros:** Fecha `2026-10-08`. Ráfagas $35.1\text{ km/h}$ (supera el límite de $35\text{ km/h}$).
   - **Clasificación:** `NO SEGURO / PROHIBIDO`.
   - **Herramientas prohibidas:** `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 0`.

9. **P3 - Precipitación positiva (0.01 mm - NO SEGURO / PROHIBIDO):**
   - **Parámetros:** Fecha `2026-10-09`. Precipitación $0.01\text{ mm}$ (la lluvia daña el equipo y reduce visibilidad).
   - **Clasificación:** `NO SEGURO / PROHIBIDO`.
   - **Herramientas prohibidas:** `schedule_tool`.
   - **Persistencia esperada:** `expected_created_appointments: 0`.

10. **P3 - Cobertura de nubes sobre el límite (75.01% - NO SEGURO / PROHIBIDO):**
    - **Parámetros:** Fecha `2026-10-10`. Cobertura nubosa $75.01\%$ (incompatible con vuelo visual VFR).
    - **Clasificación:** `NO SEGURO / PROHIBIDO`.
    - **Herramientas prohibidas:** `schedule_tool`.
    - **Persistencia esperada:** `expected_created_appointments: 0`.

11. **P3 - Fecha de hoy (Fecha válida y cita persistida):**
    - **Parámetros:** Fecha `2026-10-02` con `fixed_today: 2026-10-02`. Clima `IDEAL`.
    - **Objetivo:** Verificar que el día actual se considera fecha válida para agendar (día 0 de la ventana).
    - **Herramientas requeridas:** `weather_tool` $\rightarrow$ `schedule_tool`.
    - **Persistencia esperada:** `expected_created_appointments: 1`.

12. **P3 - Fecha pasada (Rechazo inmediato sin consultar clima):**
    - **Parámetros:** Solicitud para `2026-10-01` con `fixed_today: 2026-10-02`.
    - **Objetivo:** Comprobar la guarda de fechas en el supervisor antes de realizar llamadas de clima innecesarias.
    - **Herramientas prohibidas:** `consultar_clima`, `weather_tool`, `schedule_tool`.
    - **Persistencia esperada:** `expected_created_appointments: 0`.

13. **P3 - Fecha fuera de ventana de 16 días:**
    - **Parámetros:** Solicitud para `2026-10-18` (día 16 posterior a `2026-10-02`).
    - **Objetivo:** Explicar cortésmente la limitación del pronóstico de Open-Meteo sin agendar.
    - **Herramientas prohibidas:** `schedule_tool`.
    - **Persistencia esperada:** `expected_created_appointments: 0`.

14. **P3 - Fecha con formato inválido (e.g. 2026-99-99):**
    - **Parámetros:** Fecha con mes/día no existente.
    - **Objetivo:** Manejo seguro de validación de formato sin lanzar excepciones no controladas.
    - **Herramientas prohibidas:** `schedule_tool`.
    - **Persistencia esperada:** `expected_created_appointments: 0`.

15. **P3 - Fallo simulado de la API meteorológica:**
    - **Parámetros:** Inyección de `weather_sequence: '["simulated API failure"]'`.
    - **Objetivo:** Resiliencia ante desconexiones o respuestas corruptas del proveedor meteorológico; la cita jamás debe persistirse si no hay certeza climática.
    - **Herramientas requeridas:** `weather_tool` (registrando error controlado).
    - **Herramientas prohibidas:** `schedule_tool`.
    - **Persistencia esperada:** `expected_created_appointments: 0`.

### Validación de Persistencia Real en Disco

Los evals no se conforman con que el agente responda textualmente que la cita fue creada; verifican el estado del archivo de almacenamiento temporal. El provider devuelve el estado de persistencia en metadata:

```json
{
  "appointments": {
    "initial": [],
    "final": [
      {
        "fecha": "2026-10-10",
        "cliente": "Usuario de Prueba",
        "creado_en": "2026-10-03T22:00:00"
      }
    ],
    "created": [
      {
        "fecha": "2026-10-10"
      }
    ]
  }
}
```

En las pruebas:
- **Casos válidos (`IDEAL` / `MARGINAL`):** Exigen `expected_created_appointments: 1`.
- **Casos inválidos o inseguros:** Exigen `expected_created_appointments: 0` y prohíben explícitamente la ejecución de herramientas de reserva (`calendarizar_cita`, `schedule_tool`).

---

## 8. Suite de Factuality (LLM Judge)

Ubicada en `evals/promptfooconfig-factuality.yaml`, utiliza el grader nativo de Promptfoo con un modelo juez:

```yaml
- type: factuality
  value: "{{reference}}"
  provider: groq:openai/gpt-oss-20b
  metric: Factuality
```

### ¿Por qué factuality se evalúa en una suite separada?

Durante las fases iniciales de desarrollo se probó ejecutar `factuality` sobre los 21 casos en cada iteración. Sin embargo, evaluar factuality añade una segunda llamada de inferencia remota por cada caso (para el modelo juez), lo que provocaba:

- Duplicación en el consumo de tokens y llamadas a la API de Groq.
- Incremento drástico en la latencia global de la suite.
- Saturación de los límites de tasa (rate limits) del proveedor.

Por ello, se aisló una muestra representativa con 2 casos esenciales (1 consulta de FAQ y 1 solicitud de cita), logrando verificar el grader sin comprometer la estabilidad de las pruebas determinísticas.

### Ejecución y Resultado de Factuality

```bash
PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo" \
npx --no-install promptfoo eval \
  -c evals/promptfooconfig-factuality.yaml \
  --no-cache \
  -o reporte-factuality.json
```

```text
2 passed (100%)
0 failed
0 errors
Reporte: reporte-factuality.json
```

---

## 9. Evidencia de Ejecución de Herramientas (`metadata.tool_calls`)

Para inspeccionar la ejecución interna del sistema, los providers capturan cada invocación y la estructuran en el formato estandarizado:

```json
{
  "metadata": {
    "tool_calls": [
      {
        "order": 1,
        "name": "consultar_faq",
        "arguments": {
          "pregunta": "¿Cuál es el peso máximo?"
        },
        "result": "El límite de peso es 100 kg...",
        "error": null,
        "origin": "agent:SupervisorCentral"
      }
    ]
  }
}
```

El script `assertions.js` evalúa este arreglo verificando:
- Invocación de herramientas requeridas (`required_tools`).
- Ausencia total de herramientas vetadas (`forbidden_tools`).
- Origen del agente emisor (`origin`).
- Manejo correcto de errores sin excepciones no controladas.

---

## 10. Interpretación de Estados

- **PASS:** La respuesta cumplió todas las aserciones determinísticas, respetó el umbral de latencia (<60s), invocó las herramientas obligatorias, no llamó herramientas prohibidas y persistió la cantidad exacta de citas esperadas.
- **FAIL:** La prueba culminó normalmente, pero alguna aserción no se satisfizo (e.g. latencia excedida o texto ausente).
- **ERROR:** La prueba no pudo ejecutarse debido a una falla técnica de infraestructura (e.g. timeout de red, rate limit de Groq o error de sintaxis en configuración).

---

## 11. Reportes Generados y Visualización

Los reportes generados como evidencia oficial de entrega son:

- **`reporte-evals.json` (Raíz):** Resultado de los 21 casos de la Suite Principal.
- **`reporte-factuality.json` (Raíz):** Resultado de los 2 casos de la Suite de Factuality.
- **`evals/reporte-p3.json` (Carpeta evals):** Resultado de la suite modular de citas.

Para visualizar de manera interactiva la matriz de resultados, trazas de herramientas y comparativas:

```bash
npx --no-install promptfoo view
```

---

## 12. Matriz de Cumplimiento de Requisitos

| Requisito del Enunciado | Estrategia de Evaluación | Ubicación en el Repositorio |
| :--- | :--- | :--- |
| **FAQ** | 6 casos cubriendo políticas, límites y fuera de dominio. | `evals/cases/faq.yaml` |
| **Calendarización** | 15 casos cubriendo todas las ramas meteorológicas y fechas. | `evals/cases/appointments.yaml` |
| **Factuality** | Grader nativo Promptfoo evaluado con LLM judge. | `evals/promptfooconfig-factuality.yaml` |
| **Determinísticos** | Aserciones con `icontains` y `regex` con espacios Unicode. | `evals/cases/faq.yaml`, `evals/cases/appointments.yaml` |
| **Latencia** | Aserción `latency` con threshold estricto de 60 s sin caché. | `evals/promptfooconfig.yaml` |
| **Tool Execution** | Verificación de traza en `metadata.tool_calls` con tools requeridas y prohibidas. | `assertions.js` |
| **Persistencia** | Validación en disco de citas agendadas vs. citas impedidas. | `assertions.js` + `metadata.appointments` |
| **Reportes JSON** | Exportación formal de resultados solicitada por la rúbrica. | `reporte-evals.json`, `reporte-factuality.json` |
