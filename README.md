# Hoja de Trabajo 6 - Evaluaciones con Promptfoo

### Miembros del Equipo

- Marcelo Detlefsen - 24554
- Julían Divas - 24687
- Luis Angel Girón - 24753

---

## Resumen del Proyecto

Este repositorio contiene el sistema de asistencia conversacional para **Parachute S.A.**, enfocado en dos capacidades esenciales de negocio:

1. **Resolución de Preguntas Frecuentes (FAQs):** Respuestas precisas sobre requisitos, peso, edad, políticas y equipo utilizando el corpus oficial de la empresa.
2. **Calendarización Segura de Citas de Paracaidismo:** Agendamiento condicionado a pronósticos en tiempo real de Open-Meteo (evaluando viento, ráfagas, precipitación y nubosidad) dentro de una ventana máxima de 16 días y aplicando reglas estrictas de seguridad aeronáutica.

Tras haber explorado patrones de orquestación en la entrega anterior (Centralizada, Jerárquica y Descentralizada), para esta Hoja de Trabajo 6 se seleccionó la **Arquitectura Centralizada** (`centralizada.py`) para someterla a evaluación sistemática y automatizada mediante [Promptfoo](https://www.promptfoo.dev/).

---

## Estructura del Repositorio

```text
hdt6-ai/
├── centralizada.py            # Agente supervisor central y workers como tools
├── jerarquica.py              # Arquitectura jerárquica (HDT5)
├── descentralizada.py         # Arquitectura descentralizada con handoffs (HDT5)
├── shared/
│   └── parachute.py           # Lógica compartida: Open-Meteo, reglas de vuelo, FAQs y citas
├── data/                      # Corpus de FAQs y persistencia de citas
├── tests/                     # Pruebas unitarias deterministas con unittest
├── evals/                     # Configuración, datasets, providers y docs de evaluación
│   ├── README.md              # Documentación detallada y exhaustiva de los evals
│   ├── promptfooconfig.yaml   # Configuración de la suite principal (21 casos)
│   ├── promptfooconfig-factuality.yaml # Suite de factuality con LLM judge
│   ├── cases/                 # Casos de prueba (faq.yaml y appointments.yaml)
│   ├── provider_combined.py   # Router de providers para la suite principal
│   ├── provider.py            # Provider para interacción con el agente real
│   └── provider_p3.py         # Provider determinista para reglas meteorológicas
├── assertions.js              # Validación de tool execution y persistencia de citas
├── reporte-evals.json         # Resultados exportados de la suite principal
└── reporte-factuality.json    # Resultados exportados de la suite de factuality
```

---

## Requisitos y Preparación

### Requisitos

- **Python:** 3.10 o superior.
- **Node.js:** v18+ y `npm`.
- **API Key:** Groq (o compatible con OpenAI).

### Instalación

1. **Instalar dependencias de Python y Node.js:**
   ```bash
   pip install -r requirements.txt
   npm install
   ```

2. **Configuración de Variables de Entorno:**
   Copiar la plantilla y configurar las credenciales:
   ```bash
   cp .env.example .env
   ```
   Asegurar las credenciales mínimas en `.env`:
   ```dotenv
   GROQ_API_KEY=gsk_...
   GROQ_MODEL=openai/gpt-oss-20b
   GROQ_BASE_URL=https://api.groq.com/openai/v1
   ```

3. **Cargar variables en la sesión:**
   ```bash
   set -a
   source .env
   set +a
   ```

---

## Guía de Uso

### 1. Ejecución del Agente Conversacional

El agente centralizado puede ejecutarse en modo consulta directa o en modo interactivo:

```bash
# Modo consulta única
python centralizada.py "¿Cuál es el peso máximo permitido para saltar?"
python centralizada.py "Quiero calendarizar una cita el 2026-10-10"

# Modo chat interactivo
python centralizada.py
```

### 2. Ejecución de Pruebas Unitarias

Para validar las reglas deterministas de clima, umbrales y citas sin llamadas de red:

```bash
python -m unittest discover -s tests -v
```

### 3. Ejecución de Evaluaciones con Promptfoo

Las evaluaciones están divididas en dos suites principales:

#### A. Suite Principal (21 casos: 6 FAQ + 15 Citas)
Evalúa aserciones determinísticas (`icontains`, `regex`), umbrales de latencia, llamadas a herramientas obligatorias/prohibidas (`tool execution`) y persistencia en disco de citas:

```bash
PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo" npx --no-install promptfoo eval \
  -c evals/promptfooconfig.yaml \
  --no-cache \
  -o reporte-evals.json
```

#### B. Suite de Factuality (Muestra representativa con LLM Judge)
Evalúa fidelidad factual contra respuestas de referencia utilizando un modelo evaluador:

```bash
PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo" npx --no-install promptfoo eval \
  -c evals/promptfooconfig-factuality.yaml \
  --no-cache \
  -o reporte-factuality.json
```

#### C. Interfaz Web de Resultados
Para inspeccionar visualmente las métricas, latencias y trazas de las corridas:

```bash
npx --no-install promptfoo view
```

---

## Resultados de las Evaluaciones

| Suite de Evaluación | Total Casos | PASS | FAIL | ERROR | Efectividad |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Suite Principal** (FAQ + Citas) | 21 | 20 | 1 | 0 | **95.24%** |
| **Factuality** (LLM Judge) | 2 | 2 | 0 | 0 | **100.00%** |

### Criterios Clave Validados

- **Factuality:** Cumplimiento total contra las referencias oficiales tanto en consultas de FAQs como en agendamiento.
- **Determinísticos:** Validación estricta con `icontains` y `regex` con tolerancia de formato en unidades (e.g. `100 kg`).
- **Latencia:** Límite establecido en 60 segundos por caso (`latency <= 60000 ms`).
- **Tool Execution:** Inspección de trazas reales (`metadata.tool_calls`) verificando que se invoquen las herramientas requeridas y no se ejecuten herramientas prohibidas ante condiciones inseguras.
- **Persistencia de Citas:** Comprobación directa sobre el archivo de citas para asegurar que solo se persistan reservas en condiciones `IDEAL` o `MARGINAL`.

> [!NOTE]
> **Detalle del único FAIL registrado:** El caso *¿Se permite el ingreso de alimentos y bebidas?* ejecutó correctamente la herramienta `consultar_faq` y recuperó la respuesta, pero superó el umbral estricto de latencia de 60 segundos debido a variabilidad del proveedor Groq. Se conservó como FAIL para reflejar con honestidad los hallazgos de latencia.

---

## Cobertura de Requerimientos

| Requerimiento del Enunciado | Implementación en el Proyecto | Archivos de Referencia |
| :--- | :--- | :--- |
| **Arquitectura seleccionada** | Centralizada: supervisor con workers coordinados mediante `as_tool()`. | [centralizada.py](centralizada.py) |
| **Funcionalidad 1: FAQs** | 6 casos evaluando límites físicos, políticas y preguntas fuera de dominio. | [evals/cases/faq.yaml](evals/cases/faq.yaml) |
| **Funcionalidad 2: Citas** | 15 casos con fixtures de clima, límites de viento/lluvia/nubes y fechas. | [evals/cases/appointments.yaml](evals/cases/appointments.yaml) |
| **Evals: Factuality** | Grader nativo `factuality` de Promptfoo con modelo LLM judge. | [evals/promptfooconfig-factuality.yaml](evals/promptfooconfig-factuality.yaml) |
| **Evals: Determinísticos** | Validaciones exactas con `icontains` y `regex` con tolerancia de formato. | [evals/cases/faq.yaml](evals/cases/faq.yaml) |
| **Evals: Latencia** | Aserción `latency` con umbral máximo de 60 s (`threshold: 60000`). | [evals/promptfooconfig.yaml](evals/promptfooconfig.yaml) |
| **Evals: Tool Execution** | Inspección de herramientas obligatorias y prohibidas en la traza. | [assertions.js](assertions.js) |
| **Persistencia Real de Citas** | Comprobación de estado final en disco (`expected_created_appointments`). | [assertions.js](assertions.js) |
| **Archivos de Reporte** | Reportes JSON exportados por Promptfoo requeridos para la entrega. | [reporte-evals.json](reporte-evals.json), [reporte-factuality.json](reporte-factuality.json) |

---

## Documentación Detallada y Enlaces

Para una profundización técnica sobre los criterios de diseño, providers, fixtures y la arquitectura del sistema, consultar los siguientes documentos:

- **Detalle Técnico de Evaluaciones y Promptfoo:** [evals/README.md](evals/README.md)
- **Análisis de Arquitecturas Multiagente (HDT5):** [respuestas_hdt5.md](respuestas_hdt5.md) y [respuestas_hdt5.pdf](respuestas_hdt5.pdf)
- **Reportes de Resultados (Promptfoo):** [reporte-evals.json](reporte-evals.json) y [reporte-factuality.json](reporte-factuality.json)

