-- Esquema inicial para los embeddings de las FAQs de Parachute S.A.
-- La imagen pgvector ya incluye la extensión; aquí se habilita en esta base.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS faq_embeddings (
    id TEXT PRIMARY KEY,
    categoria TEXT NOT NULL,
    pregunta TEXT NOT NULL,
    respuesta TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS faq_embeddings_categoria_idx
    ON faq_embeddings (categoria);

-- Índice para búsquedas por similitud coseno con all-MiniLM-L6-v2.
CREATE INDEX IF NOT EXISTS faq_embeddings_embedding_hnsw_idx
    ON faq_embeddings USING hnsw (embedding vector_cosine_ops);
