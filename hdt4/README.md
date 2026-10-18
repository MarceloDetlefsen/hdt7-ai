# Hoja de Trabajo 4 - Function calls & Base de Datos Vectorial

Sistema de preguntas frecuentes (FAQs) con base de datos vectorial PostgreSQL + pgvector y capacidades de Function Calling para un agente conversacional de Parachute S.A.

---

## 1. Infraestructura PostgreSQL + pgvector

La solución utiliza PostgreSQL 16 con la extensión `pgvector`, ejecutado en Docker Compose. Los embeddings son generados con el modelo `all-MiniLM-L6-v2` (384 dimensiones) y se almacenan en la tabla `faq_embeddings` utilizando un índice HNSW para similitud coseno.

### Requisitos

- Docker Engine y Docker Compose v2 (`docker compose`)
- Python 3.10 o superior

### Configuración inicial del entorno

1. Clone el repositorio y sitúese en la raíz del proyecto:
   ```bash
   cd ai-function-calls
   ```

2. Cree su archivo `.env` a partir de la plantilla:
   ```bash
   cp .env.example .env
   ```
   *Nota: Si tiene otro servicio de PostgreSQL corriendo en su máquina en el puerto 5432, puede cambiar `POSTGRES_PORT` en `.env` (por ejemplo a `5434`).*

3. Inicie el contenedor de PostgreSQL con pgvector:
   ```bash
   docker compose up -d
   docker compose ps
   ```

4. Cree y active el entorno virtual de Python:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```

5. Instale las dependencias del proyecto:
   ```bash
   pip install -r requirements.txt
   ```
   *(En Linux con CPU, puede instalar previamente PyTorch CPU para optimizar la descarga: `pip install torch --index-url https://download.pytorch.org/whl/cpu`)*.

6. Configure el cliente OpenAI-compatible de Groq en `.env`:
   - `GROQ_API_KEY`: API key de Groq (no la suba al repositorio).
   - `GROQ_MODEL`: modelo que utilizará el agente.
   - `GROQ_BASE_URL`: endpoint compatible de Groq; el valor del ejemplo ya está configurado.

El contenedor inicializa automáticamente la extensión `vector`, la tabla `faq_embeddings` y el índice HNSW mediante `docker/init.sql`.

Para iniciar el agente con function calling después de cargar el corpus:

```bash
PYTHONPATH=src .venv/bin/python src/agent.py
```

El agente ofrece `search_knowledge_base` al modelo, exige su uso para preguntas de
contenido, ejecuta los tool calls solicitados y devuelve los resultados al modelo antes
de generar la respuesta final. Los saludos y preguntas de cortesía se resuelven localmente.
Si no hay FAQs relevantes, el agente responde de forma segura que no dispone de información.
La sesión termina con `Bye`, `salir`, `exit`, `quit` o
`Ctrl+C`, mostrando `Sesión finalizada.` y devolviendo un cierre normal de la aplicación.

El historial se conserva durante toda la sesión, por lo que se pueden realizar varias
preguntas sin reiniciar el proceso. Si la búsqueda no encuentra FAQs que superen el
umbral de relevancia, el agente devuelve directamente el mensaje de información no
disponible y no permite que el modelo invente una respuesta. Los saludos y preguntas
de cortesía reciben respuestas breves predefinidas para mantener una conversación natural;
las preguntas factuales siguen dependiendo de la base de conocimientos.

En terminales compatibles, `readline` habilita las flechas izquierda/derecha para editar
la pregunta y arriba/abajo para recorrer el historial de consultas.

---

## 2. Flujo de Trabajo y Verificación

Siga este flujo paso a paso para verificar la infraestructura, cargar los datos y realizar consultas vectoriales:

### Paso A: Verificar la conexión a la base de datos
Compruebe que la conexión y la tabla existan antes de comenzar:
```bash
python src/database.py --test-connection
```
**Salida esperada:**
```text
Probando conexión con PostgreSQL...
✓ Conexión exitosa. Total de FAQs en base de datos: 120
```

### Paso B: Cargar el corpus de FAQs (Persona 1)
Si la base de datos está vacía (`Total de FAQs: 0`) o requiere recargar el dump oficial:
```bash
python src/load_corpus.py
```
El cargador parsea los 120 registros de `data/Corpus_FAQs_Parachute_SA_2026.txt`, genera sus embeddings normalizados con `all-MiniLM-L6-v2` e inserta los registros sin duplicados (`upsert` por `id`).

### Paso C: Consultar el motor de búsqueda vectorial (Persona 2)
Puede realizar consultas en lenguaje natural directamente desde la terminal con `src/database.py`:

```bash
python src/database.py "Tienen fotos o videos de lo que es el salto en cuestión?"
```

**Salida de ejemplo:**
```text
Consultando: 'Tienen fotos o videos de lo que es el salto en cuestión?' (top_k=5, threshold=0.5)

--- Resultado #1 (Similitud: 0.6529) ---
ID: FAQ-081 | Categoría: Fotografía y Contenido Multimedia
Pregunta: ¿Puedo saltar con mi propia cámara Go-Pro o teléfono celular?
Respuesta: Por regulaciones de la Dirección General de Aeronáutica Civil (DGAC) y la USPA, no se permite el uso de cámaras...

--- Resultado #2 (Similitud: 0.6029) ---
ID: FAQ-029 | Categoría: Requisitos Físicos y Salud
Pregunta: ¿Cuánto tiempo debo esperar tras hacer buceo antes de saltar?
Respuesta: Se requiere un intervalo mínimo de 24 horas entre su última inmersión de buceo...
```

Parámetros opcionales:
- `--top-k <N>`: Cantidad máxima de resultados a retornar (por defecto: `5`).
- `--threshold <X>`: Umbral mínimo de similitud coseno (por defecto: `0.50`).

---

## 3. Suite de Pruebas de Búsqueda Vectorial (`test_search.py`)

Para consultar la especificación detallada de los casos de prueba (consultas exactas, parafraseadas y fuera de dominio), ejecución automatizada y modo interactivo, revise el archivo:

👉 **[TESTS.md](TESTS.md)**

---

## 4. Guía de Integración para el Agente

Para consultar los detalles técnicos de integración con el LLM (especificación de la función `search_knowledge_base`, formato JSON retornado, manejo de consultas fuera de tema y el schema de la herramienta para Groq / OpenAI), revise el archivo:

👉 **[INTEGRACION.md](INTEGRACION.md)**

---

## 5. Estructura del Proyecto

```text
ai-function-calls/
├── data/
│   └── Corpus_FAQs_Parachute_SA_2026.txt  # Dump oficial de 120 FAQs
├── docker/
│   └── init.sql                          # Esquema de BD, extensión pgvector e índice HNSW
├── src/
│   ├── database.py                       # Conexión a PostgreSQL y motor de búsqueda vectorial
│   ├── agent.py                          # Loop conversacional y ejecución de tool calls
│   ├── groq_client.py                    # Cliente OpenAI-compatible apuntando a Groq
│   ├── load_corpus.py                    # Parser del TXT y cargador con embeddings
│   └── test_search.py                    # Suite de pruebas automatizadas y CLI interactivo
├── docker-compose.yml                    # Definición del contenedor PostgreSQL + pgvector
├── requirements.txt                      # Dependencias del proyecto
├── .env.example                          # Plantilla de variables de entorno
├── INTEGRACION.md                        # Guía de integración para el agente LLM
├── TESTS.md                              # Suite de pruebas de búsqueda vectorial
└── README.md                             # Documentación principal del proyecto
```

---

## 6. Reinicializar la Base de Datos

Para borrar los datos persistidos y recrear el esquema desde cero:

```bash
docker compose down -v
docker compose up -d
python src/load_corpus.py
```
