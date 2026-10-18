# Suite de Pruebas de Búsqueda Vectorial

Este documento detalla la suite de pruebas implementada en `src/test_search.py` para verificar el correcto funcionamiento del motor de búsqueda vectorial de Parachute S.A., evaluando la precisión semántica y el filtrado por umbral de similitud.

---

## 1. Escenarios de Prueba Evaluados

La suite valida de forma automatizada los 3 escenarios fundamentales exigidos en la Hoja de Trabajo #4:

1. **Consultas exactas:** Consultas copiadas textualmente del corpus oficial. Deben coincidir con la FAQ esperada con similitud alta ($\ge 0.65$).
   - *FAQ-021:* `"¿Cuál es el peso máximo permitido para saltar?"`
   - *FAQ-029:* `"¿Cuánto tiempo debo esperar tras hacer buceo antes de saltar?"`
   - *FAQ-081:* `"¿Puedo saltar con mi propia cámara Go-Pro o teléfono celular?"`

2. **Consultas parafraseadas:** Preguntas formuladas con redacción coloquial, variaciones de vocabulario o sinónimos. Deben recuperar la FAQ correcta con similitud válida ($\ge 0.55$).
   - *FAQ-081:* `"Tienen fotos o videos de lo que es el salto en cuestión?"`
   - *FAQ-021:* `"¿Hay un límite de peso para lanzarse en paracaídas?"`
   - *FAQ-029:* `"¿Si hice buceo ayer puedo saltar en paracaídas hoy?"`

3. **Consultas fuera de dominio (OOD):** Preguntas ajenas al evento y al paracaidismo. Deben ser descartadas por el umbral de similitud retornando 0 resultados para evitar alucinaciones.
   - Receta culinaria: `"¿Cómo hacer una pizza de pepperoni casera paso a paso?"`
   - Geografía mundial: `"¿Cuál es la capital de Francia y qué monumentos visitar?"`
   - Mecánica automotriz: `"¿Cómo reparar el carburador y motor de una moto?"`

---

## 2. Ejecución Automatizada

Para ejecutar los 9 casos de prueba y obtener el reporte de validación:

```bash
python src/test_search.py
```

### Reporte de salida esperado:

```text
================================================================================
 SUITE DE PRUEBAS DE BÚSQUEDA VECTORIAL - PARACHUTE S.A.
 Configuración: threshold=0.50, top_k=3
================================================================================

[Prueba 1/9] Tipo: EXACTA | Pregunta idéntica a FAQ-021 sobre peso máximo.
Consulta: "¿Cuál es el peso máximo permitido para saltar?"
  ✓ PASÓ: Coincidencia con FAQ-021 (similitud: 0.7491 >= 0.65)
    Pregunta devuelta: "¿Cuál es el peso máximo permitido para saltar?"

[Prueba 2/9] Tipo: EXACTA | Pregunta idéntica a FAQ-029 sobre intervalo tras buceo.
Consulta: "¿Cuánto tiempo debo esperar tras hacer buceo antes de saltar?"
  ✓ PASÓ: Coincidencia con FAQ-029 (similitud: 0.6952 >= 0.65)
    Pregunta devuelta: "¿Cuánto tiempo debo esperar tras hacer buceo antes de saltar?"

[Prueba 3/9] Tipo: EXACTA | Pregunta idéntica a FAQ-081 sobre cámaras personales.
Consulta: "¿Puedo saltar con mi propia cámara Go-Pro o teléfono celular?"
  ✓ PASÓ: Coincidencia con FAQ-081 (similitud: 0.6842 >= 0.65)
    Pregunta devuelta: "¿Puedo saltar con mi propia cámara Go-Pro o teléfono celular?"

[Prueba 4/9] Tipo: PARAFRASEADA | Consulta coloquial sobre paquete de fotos y video.
Consulta: "Tienen fotos o videos de lo que es el salto en cuestión?"
  ✓ PASÓ: Coincidencia con FAQ-081 (similitud: 0.6529 >= 0.55)
    Pregunta devuelta: "¿Puedo saltar con mi propia cámara Go-Pro o teléfono celular?"

[Prueba 5/9] Tipo: PARAFRASEADA | Pregunta sobre peso formulada con términos sinónimos.
Consulta: "¿Hay un límite de peso para lanzarse en paracaídas?"
  ✓ PASÓ: Coincidencia con FAQ-021 (similitud: 0.6537 >= 0.55)
    Pregunta devuelta: "¿Cuál es el peso máximo permitido para saltar?"

[Prueba 6/9] Tipo: PARAFRASEADA | Pregunta médica sobre buceo redactada como caso práctico.
Consulta: "¿Si hice buceo ayer puedo saltar en paracaídas hoy?"
  ✓ PASÓ: Coincidencia con FAQ-029 (similitud: 0.6268 >= 0.55)
    Pregunta devuelta: "¿Cuánto tiempo debo esperar tras hacer buceo antes de saltar?"

[Prueba 7/9] Tipo: FUERA_DE_DOMINIO | Receta gastronómica sin relación con paracaidismo.
Consulta: "¿Cómo hacer una pizza de pepperoni casera paso a paso?"
  ✓ PASÓ: Descartada correctamente. 0 resultados superaron el umbral (0.5).

[Prueba 8/9] Tipo: FUERA_DE_DOMINIO | Pregunta de geografía mundial ajena al evento.
Consulta: "¿Cuál es la capital de Francia y qué monumentos visitar?"
  ✓ PASÓ: Descartada correctamente. 0 resultados superaron el umbral (0.5).

[Prueba 9/9] Tipo: FUERA_DE_DOMINIO | Mecánica automotriz no relacionada con Parachute S.A.
Consulta: "¿Cómo reparar el carburador y motor de una moto?"
  ✓ PASÓ: Descartada correctamente. 0 resultados superaron el umbral (0.5).

================================================================================
 RESULTADO FINAL: 9/9 pruebas superadas.
================================================================================
```

---

## 3. Modo Interactivo en Consola

Permite realizar consultas libres en tiempo real directamente desde la terminal para explorar cómo responde el motor ante cualquier redacción:

```bash
python src/test_search.py --interactive
```

Para salir de la sesión interactiva, escriba `salir`, `exit`, `Bye` o presione `Ctrl+C`.

---

## 4. Parámetros de Calibración Opcionales

Tanto las pruebas automatizadas como el modo interactivo permiten ajustar los hiperparámetros de búsqueda:

- `--threshold <X>`: Umbral mínimo de similitud coseno (por defecto: `0.50`).
- `--top-k <N>`: Cantidad máxima de resultados recuperados (por defecto: `3`).

**Ejemplo:**
```bash
python src/test_search.py --threshold 0.58 --top-k 5
```
