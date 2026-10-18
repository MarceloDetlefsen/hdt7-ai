"""Suite de pruebas y validación para el motor de búsqueda vectorial de Parachute S.A.

Comprueba los 3 escenarios obligatorios:
1. Consultas exactas (copiadas textualmente del corpus).
2. Consultas parafraseadas (distinta redacción, misma intención semántica).
3. Consultas fuera de dominio / out-of-domain (temas ajenos que deben ser descartados).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Any

from database import DEFAULT_SIMILARITY_THRESHOLD, search_knowledge_base


@dataclass(frozen=True)
class TestCase:
    categoria: str
    query: str
    tipo: str  # 'exacta', 'parafraseada', 'fuera_de_dominio'
    expected_id: str | None = None
    min_similarity: float = 0.50
    should_match: bool = True
    descripcion: str = ""


TEST_SUITE: list[TestCase] = [
    # ---------------------------------------------------------
    # 1. Consultas EXACTAS (copiadas textualmente del corpus)
    # ---------------------------------------------------------
    TestCase(
        categoria="Requisitos Físicos y Salud",
        query="¿Cuál es el peso máximo permitido para saltar?",
        tipo="exacta",
        expected_id="FAQ-021",
        min_similarity=0.65,
        should_match=True,
        descripcion="Pregunta idéntica a FAQ-021 sobre peso máximo.",
    ),
    TestCase(
        categoria="Requisitos Físicos y Salud",
        query="¿Cuánto tiempo debo esperar tras hacer buceo antes de saltar?",
        tipo="exacta",
        expected_id="FAQ-029",
        min_similarity=0.65,
        should_match=True,
        descripcion="Pregunta idéntica a FAQ-029 sobre intervalo tras buceo.",
    ),
    TestCase(
        categoria="Fotografía y Contenido Multimedia",
        query="¿Puedo saltar con mi propia cámara Go-Pro o teléfono celular?",
        tipo="exacta",
        expected_id="FAQ-081",
        min_similarity=0.65,
        should_match=True,
        descripcion="Pregunta idéntica a FAQ-081 sobre cámaras personales.",
    ),
    # ---------------------------------------------------------
    # 2. Consultas PARAFRASEADAS (variación de vocabulario / coloquial)
    # ---------------------------------------------------------
    TestCase(
        categoria="Fotografía y Contenido Multimedia",
        query="Tienen fotos o videos de lo que es el salto en cuestión?",
        tipo="parafraseada",
        expected_id="FAQ-081",
        min_similarity=0.55,
        should_match=True,
        descripcion="Consulta coloquial sobre paquete de fotos y video.",
    ),
    TestCase(
        categoria="Requisitos Físicos y Salud",
        query="¿Hay un límite de peso para lanzarse en paracaídas?",
        tipo="parafraseada",
        expected_id="FAQ-021",
        min_similarity=0.55,
        should_match=True,
        descripcion="Pregunta sobre peso formulada con términos sinónimos.",
    ),
    TestCase(
        categoria="Requisitos Físicos y Salud",
        query="¿Si hice buceo ayer puedo saltar en paracaídas hoy?",
        tipo="parafraseada",
        expected_id="FAQ-029",
        min_similarity=0.55,
        should_match=True,
        descripcion="Pregunta médica sobre buceo redactada como caso práctico.",
    ),
    # ---------------------------------------------------------
    # 3. Consultas FUERA DE DOMINIO (Out-Of-Domain / OOD)
    # ---------------------------------------------------------
    TestCase(
        categoria="Fuera de Dominio",
        query="¿Cómo hacer una pizza de pepperoni casera paso a paso?",
        tipo="fuera_de_dominio",
        expected_id=None,
        min_similarity=0.0,
        should_match=False,
        descripcion="Receta gastronómica sin relación con paracaidismo.",
    ),
    TestCase(
        categoria="Fuera de Dominio",
        query="¿Cuál es la capital de Francia y qué monumentos visitar?",
        tipo="fuera_de_dominio",
        expected_id=None,
        min_similarity=0.0,
        should_match=False,
        descripcion="Pregunta de geografía mundial ajena al evento.",
    ),
    TestCase(
        categoria="Fuera de Dominio",
        query="¿Cómo reparar el carburador y motor de una moto?",
        tipo="fuera_de_dominio",
        expected_id=None,
        min_similarity=0.0,
        should_match=False,
        descripcion="Mecánica automotriz no relacionada con Parachute S.A.",
    ),
]


def run_tests(threshold: float = 0.50, top_k: int = 3) -> bool:
    """Ejecuta todos los casos de prueba y presenta un informe estructurado."""
    print("=" * 80)
    print(" SUITE DE PRUEBAS DE BÚSQUEDA VECTORIAL - PARACHUTE S.A.")
    print(f" Configuración: threshold={threshold:.2f}, top_k={top_k}")
    print("=" * 80)

    passed_count = 0
    total_count = len(TEST_SUITE)

    for i, test in enumerate(TEST_SUITE, start=1):
        print(f"\n[Prueba {i}/{total_count}] Tipo: {test.tipo.upper()} | {test.descripcion}")
        print(f"Consulta: \"{test.query}\"")

        results = search_knowledge_base(test.query, top_k=top_k, threshold=threshold)

        if test.should_match:
            if not results:
                print(f"  ✗ FALLÓ: Se esperaban resultados pero no se obtuvo ninguno (threshold={threshold}).")
                continue

            top_result = results[0]
            sim = top_result["similarity"]
            result_ids = [r["id"] for r in results]

            id_match = (test.expected_id in result_ids) if test.expected_id else True
            sim_ok = sim >= test.min_similarity

            if id_match and sim_ok:
                print(f"  ✓ PASÓ: Coincidencia con {top_result['id']} (similitud: {sim:.4f} >= {test.min_similarity})")
                print(f"    Pregunta devuelta: \"{top_result['pregunta']}\"")
                passed_count += 1
            else:
                reasons: list[str] = []
                if not id_match:
                    reasons.append(f"ID esperado {test.expected_id} no está entre los resultados {result_ids}")
                if not sim_ok:
                    reasons.append(f"Similitud {sim:.4f} es menor a la mínima requerida {test.min_similarity}")
                print(f"  ✗ FALLÓ: {', '.join(reasons)}")
        else:
            if not results:
                print(f"  ✓ PASÓ: Descartada correctamente. 0 resultados superaron el umbral ({threshold}).")
                passed_count += 1
            else:
                print(
                    f"  ✗ FALLÓ: La consulta fuera de dominio no fue descartada. "
                    f"Devolvió {len(results)} resultado(s). "
                    f"Top resultado: {results[0]['id']} con similitud {results[0]['similarity']:.4f}."
                )

    print("\n" + "=" * 80)
    print(f" RESULTADO FINAL: {passed_count}/{total_count} pruebas superadas.")
    print("=" * 80)
    return passed_count == total_count


def interactive_mode(threshold: float = 0.50, top_k: int = 3) -> None:
    """Modo interactivo en consola para evaluar preguntas libres."""
    print("=" * 80)
    print(" MODO INTERACTIVO DE BÚSQUEDA VECTORIAL")
    print(f" (threshold={threshold}, top_k={top_k})")
    print(" Escribe tu consulta o 'salir' / 'Bye' para terminar.")
    print("=" * 80)

    while True:
        try:
            query = input("\nPregunta > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nSaliendo del modo interactivo...")
            break

        if not query:
            continue
        if query.lower() in {"salir", "exit", "bye", "quit"}:
            print("Sesión finalizada.")
            break

        results = search_knowledge_base(query, top_k=top_k, threshold=threshold)
        if not results:
            print("⚠ Sin resultados: ninguna FAQ superó el umbral de similitud.")
        else:
            for idx, res in enumerate(results, 1):
                print(f"  [{idx}] {res['id']} (similitud: {res['similarity']:.4f}) - {res['categoria']}")
                print(f"      P: {res['pregunta']}")
                print(f"      R: {res['respuesta'][:140]}...")


def main() -> int:
    parser = argparse.ArgumentParser(description="Suite de pruebas de búsqueda vectorial.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_SIMILARITY_THRESHOLD,
        help=f"Umbral mínimo de similitud coseno (por defecto: {DEFAULT_SIMILARITY_THRESHOLD})",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="Cantidad de resultados a recuperar (por defecto: 3)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Ejecutar la terminal interactiva para probar consultas libres",
    )
    args = parser.parse_args()

    if args.interactive:
        interactive_mode(threshold=args.threshold, top_k=args.top_k)
        return 0

    success = run_tests(threshold=args.threshold, top_k=args.top_k)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
