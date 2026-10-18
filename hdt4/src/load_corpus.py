"""Parsea el corpus de FAQs, genera embeddings y los guarda en PostgreSQL."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import warnings
from contextlib import redirect_stderr
from io import StringIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg2
from dotenv import load_dotenv

# El modelo público puede descargarse sin HF_TOKEN; evita mostrar el aviso
# informativo de autenticación sin ocultar errores reales de Hugging Face.
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
warnings.filterwarnings(
    "ignore",
    message=r"You are sending unauthenticated requests to the HF Hub.*",
)
from sentence_transformers import SentenceTransformer


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = PROJECT_ROOT / "data" / "Corpus_FAQs_Parachute_SA_2026.txt"
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


@dataclass(frozen=True)
class FAQ:
    id: str
    categoria: str
    pregunta: str
    respuesta: str
    metadata: dict[str, Any]

    @property
    def embedding_text(self) -> str:
        return (
            f"Categoría: {self.categoria}\n"
            f"Pregunta: {self.pregunta}\n"
            f"Respuesta: {self.respuesta}"
        )


def _field(block: str, label: str, faq_id: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+?)\s*$", block, re.MULTILINE)
    if not match:
        raise ValueError(f"{faq_id}: falta el campo {label}")
    return match.group(1)


def parse_corpus(path: Path) -> list[FAQ]:
    """Convierte los bloques del TXT en FAQs validadas."""
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"No existe el corpus: {path}") from exc

    # La cabecera y los registros están separados por líneas de guiones.
    blocks = re.split(r"\n\s*-{5,}\s*\n", content.strip())
    faqs: list[FAQ] = []
    seen_ids: set[str] = set()

    for block in blocks:
        if not re.search(r"^ID:\s*", block, re.MULTILINE):
            continue

        faq_id = _field(block, "ID", "registro desconocido")
        if faq_id in seen_ids:
            raise ValueError(f"ID duplicado en el corpus: {faq_id}")

        category = _field(block, "CATEGORÍA", faq_id)
        question = _field(block, "PREGUNTA", faq_id)
        answer = _field(block, "RESPUESTA", faq_id)
        metadata_text = _field(block, "METADATA", faq_id)
        try:
            metadata = json.loads(metadata_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{faq_id}: METADATA no es JSON válido") from exc
        if not isinstance(metadata, dict):
            raise ValueError(f"{faq_id}: METADATA debe ser un objeto JSON")

        faqs.append(FAQ(faq_id, category, question, answer, metadata))
        seen_ids.add(faq_id)

    if not faqs:
        raise ValueError(f"No se encontraron FAQs en {path}")
    return faqs


def database_connection():
    """Abre la conexión usando las variables POSTGRES_* del archivo .env."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "parachute_faqs"),
        user=os.getenv("POSTGRES_USER", "parachute"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


UPSERT_SQL = """
INSERT INTO faq_embeddings
    (id, categoria, pregunta, respuesta, metadata, embedding)
VALUES (%s, %s, %s, %s, %s::jsonb, %s::vector)
ON CONFLICT (id) DO UPDATE SET
    categoria = EXCLUDED.categoria,
    pregunta = EXCLUDED.pregunta,
    respuesta = EXCLUDED.respuesta,
    metadata = EXCLUDED.metadata,
    embedding = EXCLUDED.embedding,
    updated_at = NOW()
"""


def load_faqs(faqs: list[FAQ], batch_size: int = 32) -> None:
    print(f"Generando embeddings con {MODEL_NAME} para {len(faqs)} FAQs...")
    with StringIO() as suppressed_stderr:
        with redirect_stderr(suppressed_stderr):
            model = SentenceTransformer(MODEL_NAME)
    embeddings = model.encode(
        [faq.embedding_text for faq in faqs],
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    if embeddings.shape != (len(faqs), EMBEDDING_DIMENSION):
        raise ValueError(
            f"Dimensión inesperada: {embeddings.shape}; "
            f"se esperaba ({len(faqs)}, {EMBEDDING_DIMENSION})"
        )

    rows = [
        (
            faq.id,
            faq.categoria,
            faq.pregunta,
            faq.respuesta,
            json.dumps(faq.metadata, ensure_ascii=False),
            "[" + ",".join(str(float(value)) for value in embedding) + "]",
        )
        for faq, embedding in zip(faqs, embeddings)
    ]

    print("Conectando a PostgreSQL...")
    with database_connection() as connection:
        with connection.cursor() as cursor:
            for start in range(0, len(rows), batch_size):
                cursor.executemany(UPSERT_SQL, rows[start : start + batch_size])
            cursor.execute("SELECT COUNT(*) FROM faq_embeddings")
            total = cursor.fetchone()[0]
    print(
        f"Carga completada: {len(faqs)} FAQs insertadas/actualizadas. "
        f"Total actual en la tabla: {total}."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="Ruta al archivo TXT de FAQs (por defecto: %(default)s)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Cantidad de FAQs procesadas por lote (por defecto: %(default)s)",
    )
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size debe ser mayor que cero")

    load_dotenv(PROJECT_ROOT / ".env")
    if not os.getenv("POSTGRES_PASSWORD"):
        print("Falta POSTGRES_PASSWORD en .env o en el entorno.", file=sys.stderr)
        return 1

    try:
        faqs = parse_corpus(args.corpus)
        print(f"FAQs encontradas: {len(faqs)}")
        load_faqs(faqs, args.batch_size)
    except (OSError, ValueError, psycopg2.Error) as exc:
        print(f"Error durante la carga: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
