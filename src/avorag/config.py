"""Configuración central de AvoRAG (pydantic-settings, leída de `.env`)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ruta al .env relativa al paquete, no al cwd.
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
    llm_max_tokens: int = 700  # respuestas concisas = generación más rápida (se ven igual con streaming)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o-mini"

    # --- LLM juez (fidelidad/seguridad/corrección) ---
    # Vacío = mismo modelo que genera (autoevaluación); define otro proveedor para juez independiente.
    judge_llm_provider: str = ""
    judge_llm_model: str = ""

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
    # Umbrales de abstención (calibrar con `avorag eval --sweep`). El valor del reranker se
    # calibró sobre el golden n=64: separa trampas (~0) de reales (>=0.02) con ~98% de exactitud.
    min_rerank_score: float = 0.01
    min_rrf_score: float = 0.0

    # --- Multi-tenant ---
    default_tenant: str = "demo"

    # --- Guardarraíles ---
    faithfulness_judge: bool = True
    dose_guardrail: bool = True
    country: str = "CO"  # CO | ES

    # --- Visión (identificación por foto: madurez/patología) ---
    # El módulo de visión SOLO identifica; el RAG aconseja con sus guardarraíles. Ver docs/VISION.md.
    vision_provider: str = "none"  # none | fake | local (TorchScript) | onnx (onnxruntime)
    vision_model_path: str = "models/vision/model.pt"  # .pt (extra 'vision') o .onnx (extra 'vision-onnx')
    vision_labels_path: str = ""  # vacío = labels.json junto al modelo
    vision_device: str = "auto"  # auto | cpu | cuda
    vision_min_confidence: float = 0.55  # bajo esto → requires_review (pedir mejor foto)
    vision_image_max_bytes: int = 8_000_000  # 8 MB

    # --- API ---
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # CORS: vacío = solo mismo origen. Ejemplo: CORS_ALLOW_ORIGINS='["https://tu.app"]'.
    cors_allow_origins: list[str] = []
    # API_KEYS: mapa JSON token->tenant. Vacío = modo abierto (dev).
    api_keys: dict[str, str] = {}
    rate_limit_per_minute: int = 60  # 0 = sin límite; por API key o IP

    # --- Auditoría / privacidad (Habeas Data) ---
    audit_enabled: bool = True
    # False = solo hash + metadatos (minimización de datos personales).
    audit_store_text: bool = True

    # --- Caché de respuestas ---
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600

    # --- Observabilidad ---
    sentry_dsn: str = ""

    @model_validator(mode="after")
    def _check_prod_invariants(self) -> Settings:
        """Valida invariantes de producción (AVORAG_ENV=prod)."""
        if self.avorag_env == "prod":
            if not self.api_keys:
                raise ValueError("AVORAG_ENV=prod requiere API_KEYS no vacío (auth obligatoria).")
            if "*" in self.cors_allow_origins:
                raise ValueError("AVORAG_ENV=prod no admite CORS comodín '*'.")
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada)."""
    return Settings()
