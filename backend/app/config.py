"""Configuration for the local document-to-Markdown service."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./document_parser.db"
    upload_dir: str = "./uploads"
    artifacts_dir: str = "./artifacts"
    langgraph_checkpoint_path: str = "./parser_checkpoints.sqlite"
    max_upload_size_mb: int = Field(default=200, ge=1)
    max_document_pages: int = Field(default=500, ge=1)

    ollama_base_url: str = "http://localhost:11434"
    paddleocr_vl_image: str = (
        "ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/"
        "paddleocr-vl:latest-nvidia-gpu@sha256:"
        "ad0b1f056a76967f9191cd06398e8babb21b49a4673a28c3de5fd31f481884db"
    )
    paddleocr_vl_cache_dir: str = "./.cache/paddleocr-vl"
    paddleocr_vl_timeout_seconds: float = Field(default=600.0, gt=0)
    glm_ocr_timeout_seconds: float = Field(default=600.0, gt=0)
    ollama_review_timeout_seconds: float = Field(default=600.0, gt=0)
    job_shutdown_grace_seconds: float = Field(default=30.0, ge=0)
    job_max_concurrent: int = Field(default=1, ge=1, le=1)
    job_queue_max_depth: int = Field(default=50, ge=1)
    max_batch_files: int = Field(default=20, ge=1, le=50)
    max_batch_size_mb: int = Field(default=1000, ge=1)
    job_timeout_seconds: float = Field(default=21600.0, gt=0)
    parse_batch_pages: int = Field(default=10, ge=1, le=10)
    parse_batch_max_attempts: int = Field(default=2, ge=1, le=3)
    max_page_repairs: int = Field(default=2, ge=0, le=2)

    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    debug: bool = False
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_key: str = ""

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    xai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com"
    openai_timeout_seconds: float = Field(default=180.0, gt=0)
    v2_worker_count: int = Field(default=4, ge=1, le=32)
    openai_pricing_version: str = "operator-configured"
    luna_input_per_million: float = Field(default=0, ge=0)
    luna_cached_input_per_million: float = Field(default=0, ge=0)
    luna_output_per_million: float = Field(default=0, ge=0)
    terra_input_per_million: float = Field(default=0, ge=0)
    terra_cached_input_per_million: float = Field(default=0, ge=0)
    terra_output_per_million: float = Field(default=0, ge=0)
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    xai_base_url: str = "https://api.x.ai"

    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_insecure: bool = True
    otel_service_name: str = "local-document-markdown"
    otel_service_version: str = "1.0.0"
    otel_deployment_environment: str = "local"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def artifacts_path(self) -> Path:
        path = Path(self.artifacts_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
