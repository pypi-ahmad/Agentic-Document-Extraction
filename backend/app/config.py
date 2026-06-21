"""Application configuration via pydantic-settings."""

from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models.enums import LLMProviderID


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM API keys (optional — only needed for the provider in use) ──
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    default_llm_provider: LLMProviderID = LLMProviderID.AUTO

    # ── Database ──
    database_url: str = "sqlite+aiosqlite:///./extraction.db"

    # ── File / artifact storage ──
    upload_dir: Annotated[str, Field(description="Directory for uploaded files")] = "./uploads"
    artifacts_dir: Annotated[str, Field(description="Directory for extraction artifacts")] = (
        "./artifacts"
    )
    max_upload_size_mb: int = 50

    # ── OCR engine feature flags ──
    # Each flag enables/disables the corresponding parser in the UI.
    enable_paddleocr: bool = False
    enable_glm_ocr: bool = False
    # Local Ollama endpoint used by the GLM-OCR provider.
    ollama_base_url: str = "http://localhost:11434"
    ollama_glm_ocr_model: str = "glm-ocr:latest"
    glm_ocr_timeout_seconds: float = 120.0
    # Grace period (seconds) given to in-flight jobs to finish on shutdown.
    job_shutdown_grace_seconds: float = 30.0
    # Maximum number of concurrent in-process jobs.
    job_max_concurrent: int = 8
    # Optional Redis URL. When set, the Arq-backed job queue is used
    # instead of the in-process queue.
    redis_url: str = ""

    # ── Agentic pipeline tuning ──
    confidence_threshold: float = 0.6
    """Fields below this confidence score are flagged for review (0.0-1.0)."""
    confidence_calibration_path: str = "./calibration.json"
    """Path to a per-field isotonic calibration artifact. Set to '' to disable."""
    llm_max_retries: int = 2
    """Maximum retry attempts for transient LLM errors (rate limits, 5xx)."""
    llm_retry_base_delay: float = 1.0
    """Base delay in seconds for exponential backoff between retries."""
    max_reflection_attempts: int = 2
    """Maximum times the pipeline re-extracts after a validation failure.
    Set to 0 to disable the reflection loop entirely."""

    # ── Server ──
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # ── CORS ──
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── Helpers ──

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def artifacts_path(self) -> Path:
        p = Path(self.artifacts_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
