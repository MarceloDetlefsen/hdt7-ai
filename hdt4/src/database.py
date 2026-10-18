"""Módulo de base de datos y búsqueda vectorial para las FAQs de Parachute S.A."""

from __future__ import annotations

import os
import json
import re
import sys
import unicodedata
import warnings
from contextlib import contextmanager, redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any, Generator

import psycopg2
from psycopg2.extensions import connection as PgConnection
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# El modelo público puede descargarse sin HF_TOKEN; evita mostrar el aviso
# informativo de autenticación sin ocultar errores reales de Hugging Face.
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
warnings.filterwarnings(
    "ignore",
    message=r"You are sending unauthenticated requests to the HF Hub.*",
)
from sentence_transformers import SentenceTransformer

# Ruta raíz del proyecto y carga de variables de entorno
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_TOP_K = int(os.getenv("DEFAULT_TOP_K", "5"))
DEFAULT_SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.5"))
HYBRID_CANDIDATE_LIMIT = int(os.getenv("HYBRID_CANDIDATE_LIMIT", "120"))

# Variable global para cachear el modelo de embeddings en memoria (Singleton)
_MODEL_INSTANCE: SentenceTransformer | None = None
_STOP_WORDS = {"a", "al", "de", "del", "el", "en", "es", "la", "las", "lo", "los", "para", "por", "que", "se", "un", "una", "y"}


def _search_tokens(text: str) -> set[str]:
    """Obtiene palabras significativas para desempatar resultados vectoriales."""
    normalized = unicodedata.normalize("NFD", text.lower())
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return {
        token
        for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in _STOP_WORDS
    }


def get_db_config() -> dict[str, Any]:
    """Obtiene y valida la configuración de conexión a PostgreSQL."""
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise ValueError(
            "Falta definir la variable de entorno POSTGRES_PASSWORD. "
            "Asegúrate de configurar tu archivo .env basado en .env.example."
        )

    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "parachute_faqs"),
        "user": os.getenv("POSTGRES_USER", "parachute"),
        "password": password,
    }


@contextmanager
def get_connection() -> Generator[PgConnection, None, None]:
    """Context manager para gestionar conexiones a PostgreSQL de forma segura.

    Maneja automáticamente el cierre y rollback en caso de error, y proporciona
    mensajes de diagnóstico claros ante problemas de conexión.
    """
    config = get_db_config()
    conn = None
    try:
        conn = psycopg2.connect(**config)
        yield conn
    except psycopg2.OperationalError as exc:
        raise ConnectionError(
            f"No se pudo conectar a PostgreSQL en {config['host']}:{config['port']}/"
            f"{config['dbname']} con usuario '{config['user']}'. "
            f"Verifica que el contenedor de Docker esté activo ('docker compose up -d').\n"
            f"Detalle técnico: {exc}"
        ) from exc
    finally:
        if conn is not None and not conn.closed:
            conn.close()


def get_embedding_model() -> SentenceTransformer:
    """Carga y reutiliza en memoria el modelo all-MiniLM-L6-v2."""
    global _MODEL_INSTANCE
    if _MODEL_INSTANCE is None:
        # transformers muestra una barra "Loading weights" por stderr al
        # inicializar el modelo. La ocultamos solo durante esa carga; los
        # errores siguen propagándose normalmente.
        with StringIO() as suppressed_stderr:
            with redirect_stderr(suppressed_stderr):
                _MODEL_INSTANCE = SentenceTransformer(MODEL_NAME)
    return _MODEL_INSTANCE


def generate_query_embedding(query: str) -> list[float]:
    """Convierte el texto de la consulta en un vector normalizado de 384 dimensiones."""
    cleaned_query = query.strip()
    if not cleaned_query:
        raise ValueError("La consulta no puede estar vacía.")

    model = get_embedding_model()
    vector = model.encode(cleaned_query, normalize_embeddings=True)
    return [float(v) for v in vector]


def search_faqs(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """Busca en faq_embeddings las FAQs más cercanas utilizando distancia coseno.

    Args:
        query: Consulta o pregunta formulada por el usuario.
        top_k: Cantidad máxima de resultados a retornar.
        threshold: Similitud mínima (entre 0.0 y 1.0) para considerar un resultado válido.
                   Los resultados con similitud menor al umbral serán descartados.

    Returns:
        Lista de diccionarios con las FAQs relevantes y su puntaje de similitud.
        Si ningún resultado supera el umbral, retorna una lista vacía.
    """
    if not query or not query.strip():
        return []

    # 1. Vectorizar la consulta con el mismo modelo y normalización
    query_vector = generate_query_embedding(query)
    vector_str = "[" + ",".join(str(v) for v in query_vector) + "]"

    # 2. Consultar PostgreSQL usando el operador <=> de distancia coseno y el índice HNSW
    # El corpus oficial contiene 120 registros. Se recupera un conjunto amplio
    # por pgvector y luego se reordena por coincidencia léxica para tolerar
    # preguntas cortas o ambiguas sin crear reglas por FAQ.
    candidate_limit = max(top_k, HYBRID_CANDIDATE_LIMIT)
    sql = """
    SELECT
        id,
        categoria,
        pregunta,
        respuesta,
        metadata,
        1 - (embedding <=> %s::vector) AS similarity
    FROM faq_embeddings
    ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """

    results: list[dict[str, Any]] = []
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (vector_str, vector_str, candidate_limit))
            rows = cur.fetchall()

            query_tokens = _search_tokens(query)
            ranked_rows: list[tuple[float, Any, float, float]] = []
            for row in rows:
                similarity = float(row["similarity"])
                searchable_text = " ".join(
                    [
                        row["categoria"],
                        row["pregunta"],
                        json.dumps(row["metadata"], ensure_ascii=False),
                    ]
                )
                result_tokens = _search_tokens(searchable_text)
                overlap = (
                    len(query_tokens & result_tokens) / len(query_tokens)
                    if query_tokens
                    else 0.0
                )
                ranking_score = similarity + (0.50 * overlap)
                ranked_rows.append((ranking_score, row, similarity, overlap))

            for _, row, similarity, overlap in sorted(
                ranked_rows, key=lambda item: item[0], reverse=True
            )[:top_k]:
                # Filtrar resultados que no alcancen el umbral de similitud
                strong_lexical_match = overlap >= 0.80
                if similarity >= threshold or strong_lexical_match:
                    results.append(
                        {
                            "id": row["id"],
                            "categoria": row["categoria"],
                            "pregunta": row["pregunta"],
                            "respuesta": row["respuesta"],
                            "metadata": row["metadata"],
                            "similarity": round(similarity, 4),
                        }
                    )

            # Los metadata contienen hechos globales del corpus (empresa,
            # evento, fecha, unidades, etc.). Se convierten automáticamente en
            # candidatos semánticos para poder responder sobre esos campos sin
            # asociar frases concretas a valores concretos en el agente.
            seen_metadata: set[str] = set()
            for row in rows:
                metadata = row["metadata"]
                metadata_key = json.dumps(
                    metadata, ensure_ascii=False, sort_keys=True
                )
                if metadata_key in seen_metadata:
                    continue
                seen_metadata.add(metadata_key)

                metadata_text = " ".join(
                    f"{key}: {value}" for key, value in metadata.items()
                )
                metadata_vector = generate_query_embedding(metadata_text)
                metadata_similarity = sum(
                    query_value * metadata_value
                    for query_value, metadata_value in zip(
                        query_vector, metadata_vector
                    )
                )
                if metadata_similarity >= max(0.0, threshold - 0.03):
                    results.append(
                        {
                            "id": "METADATA",
                            "categoria": "Datos generales del corpus",
                            "pregunta": "Contexto general del evento",
                            "respuesta": metadata_text,
                            "metadata": metadata,
                            "similarity": round(metadata_similarity, 4),
                        }
                    )

    results.sort(key=lambda item: item["similarity"], reverse=True)
    return results[:top_k]


def search_knowledge_base(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Función de interfaz para la herramienta (Tool/Function Calling) del agente.

    Permite a la Persona 3 invocar directamente la búsqueda sobre la base de
    conocimientos sin preocuparse por la conexión ni la vectorización.
    """
    applied_threshold = (
        threshold if threshold is not None else DEFAULT_SIMILARITY_THRESHOLD
    )
    return search_faqs(query=query, top_k=top_k, threshold=applied_threshold)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Búsqueda vectorial en FAQs de Parachute S.A."
    )
    parser.add_argument("query", nargs="?", help="Pregunta a consultar")
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Número máximo de resultados (por defecto: {DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_SIMILARITY_THRESHOLD,
        help=f"Umbral mínimo de similitud (por defecto: {DEFAULT_SIMILARITY_THRESHOLD})",
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Verificar la conexión a PostgreSQL y estado de la tabla",
    )
    args = parser.parse_args()

    if args.test_connection or not args.query:
        print("Probando conexión con PostgreSQL...")
        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT COUNT(*) FROM faq_embeddings;")
                    total = cursor.fetchone()[0]
                    print(f"✓ Conexión exitosa. Total de FAQs en base de datos: {total}")
        except Exception as err:
            print(f"✗ Error al conectar: {err}", file=sys.stderr)
            sys.exit(1)

        if not args.query:
            sys.exit(0)

    print(f"\nConsultando: '{args.query}' (top_k={args.top_k}, threshold={args.threshold})")
    matches = search_knowledge_base(
        args.query, top_k=args.top_k, threshold=args.threshold
    )
    if not matches:
        print("No se encontraron FAQs que superen el umbral de similitud.")
    else:
        for idx, match in enumerate(matches, 1):
            print(f"\n--- Resultado #{idx} (Similitud: {match['similarity']:.4f}) ---")
            print(f"ID: {match['id']} | Categoría: {match['categoria']}")
            print(f"Pregunta: {match['pregunta']}")
            print(f"Respuesta: {match['respuesta']}")
