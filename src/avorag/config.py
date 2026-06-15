"""Configuración central de AvoRAG (pydantic-settings, leída de `.env`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Ruta ABSOLUTA al .env (raíz del proyecto). Robusto al directorio de trabajo: funciona
# aunque la app se ejecute desde otro cwd (servidor gestionado, `uv run --project`, etc.).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Todas las variables de entorno del proyecto, con valores por defecto seguros."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General ---
    avorag_env: str = "dev"
    log_level: str = "INFO"
    log_json: bool = False

    # --- Base de datos ---
    database_url: str = "postgresql+psycopg://avorag:avorag@localhost:5432/avorag"
    embedding_dim: int = 1024

    # --- LLM (generación) ---
    llm_provider: str = "ollama"  # ollama | anthropic | openai
    llm_model: str = "qwen2.5:7b-instruct"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 900
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o-mini"

    # --- LLM juez (fidelidad/seguridad/corrección) ---
    # Por defecto vacío = el MISMO modelo que genera se autoevalúa (correlacionado; cifra
    # indicativa, no comercial). Define un proveedor/modelo DISTINTO para una segunda opinión
    # independiente, p.ej. judge_llm_provider=anthropic mientras generas con Ollama.
    judge_llm_provider: str = ""  # vacío = usa el de generación
    judge_llm_model: str = ""  # vacío = modelo por defecto del proveedor del juez

    # --- Embeddings ---
    embedding_provider: str = "ollama"  # ollama | openai | local
    embedding_model: str = "bge-m3"

    # --- Reranker ---
    rerank_provider: str = "none"  # none | cohere | local
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_max_chars: int = 900  # trunca cada candidato antes del cross-encoder (CPU más rápido)
    cohere_api_key: str = ""

    # --- Ollama ---
    ollama_host: str = "http://localhost:11434"

    # --- Recuperación / RAG ---
    retrieval_top_k: int = 12  # candidatos antes del reranking (menos = más rápido)
    final_top_k: int = 6
    rrf_k: int = 60
    # Umbral de evidencia para ABSTENERSE sin llamar al LLM. El score significa cosas distintas
    # según el reranker, así que hay dos umbrales y se aplica el que corresponde:
    #  - min_rerank_score: score del cross-encoder (local: logit; cohere: 0..1). Con bge-reranker
    #    un logit < ~0 indica que el mejor fragmento es más irrelevante que relevante.
    #  - min_rrf_score: score RRF (cuando RERANK_PROVIDER=none). Es una señal débil (los scores
    #    RRF son minúsculos, ~1/61), así que con 'none' la abstención recae sobre todo en el LLM.
    # Calibrar con `avorag eval --sweep` (reporta el umbral que mejor separa trampas de reales).
    min_rerank_score: float = 0.0
    min_rrf_score: float = 0.0

    # --- Multi-tenant ---
    default_tenant: str = "demo"

    # --- Guardarraíles ---
    faithfulness_judge: bool = True
    dose_guardrail: bool = True
    country: str = "CO"  # CO | ES

    # --- API ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # CORS: vacío = solo mismo origen (la UI se sirve desde la misma app). Para exponer
    # a otro frontend, define una lista JSON: CORS_ALLOW_ORIGINS='["https://tu.app"]'.
    cors_allow_origins: list[str] = []
    # Autenticación por API key. Vacío = modo ABIERTO (solo desarrollo / mismo origen). En
    # producción define un mapa JSON token->tenant: API_KEYS='{"clave-secreta":"finca-x"}'.
    # En modo autenticado el tenant se deriva del token (NUNCA del body).
    api_keys: dict[str, str] = {}
    rate_limit_per_minute: int = 60  # 0 = sin límite; por API key o IP

    # --- Auditoría / privacidad (Habeas Data) ---
    audit_enabled: bool = True
    # Si False, NO se guarda el texto en claro de pregunta/respuesta, solo su hash + metadatos
    # (minimización de datos personales). Útil para cumplir Habeas Data en producción.
    audit_store_text: bool = True

    # --- Caché de respuestas (latencia: preguntas repetidas responden al instante) ---
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600

    # --- Observabilidad ---
    sentry_dsn: str = ""


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada). Usar en todo el código."""
    return Settings()
