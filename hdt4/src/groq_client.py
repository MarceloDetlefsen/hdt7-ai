"""Configuración del cliente OpenAI-compatible para Groq."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_GROQ_MODEL = "openai/gpt-oss-20b"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def get_groq_model() -> str:
    """Devuelve el modelo configurado para las solicitudes a Groq."""
    model = os.getenv("GROQ_MODEL", DEFAULT_GROQ_MODEL).strip()
    if not model:
        raise ValueError(
            "Falta definir GROQ_MODEL. Configúralo en .env o en el entorno."
        )
    return model


def get_groq_client() -> OpenAI:
    """Crea un cliente OpenAI apuntando al endpoint compatible de Groq."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your-groq-api-key":
        raise ValueError(
            "Falta definir una API key válida en GROQ_API_KEY. "
            "Configúrala en .env; nunca la incluyas en el repositorio."
        )

    base_url = os.getenv("GROQ_BASE_URL", DEFAULT_GROQ_BASE_URL).strip()
    if not base_url:
        raise ValueError(
            "Falta definir GROQ_BASE_URL. Configúralo en .env o en el entorno."
        )

    return OpenAI(api_key=api_key, base_url=base_url)
