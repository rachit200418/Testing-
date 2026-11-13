"""Configuration management for the Voice Assistant QA Platform."""

import yaml
from pathlib import Path
from typing import Any, Dict, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App settings
    app_name: str = "Voice Assistant QA Platform"
    app_version: str = "0.1.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # API Key authentication
    api_key: str = "test-api-key-change-in-production"

    # Adapter selection (mock | real)
    stt_adapter: Literal["mock", "faster-whisper"] = "mock"
    llm_adapter: Literal["mock", "openai", "gemini", "ollama"] = "mock"
    tts_adapter: Literal["mock", "edge-tts", "piper"] = "mock"

    # Real adapter configuration
    # STT
    whisper_model_size: Literal["tiny", "base", "small", "medium", "large"] = "base"
    whisper_device: Literal["cpu", "cuda"] = "cpu"
    whisper_compute_type: Literal["int8", "float16", "float32"] = "int8"

    # LLM
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-1.5-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # TTS
    edge_tts_voice: str = "en-IN-NeerjaExpressiveNeural"
    piper_model_path: str | None = None
    piper_speaker_id: int = 0

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/app.db"

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_file: str = "logs/app.log"
    log_json: bool = True

    # Thresholds (for QA) - loaded from thresholds.yaml with env override
    wer_threshold_clean: float = 0.10
    wer_threshold_noisy: float = 0.25
    intent_accuracy_threshold: float = 0.90
    slot_accuracy_threshold: float = 0.85
    hallucination_threshold: float = 0.15
    latency_p95_threshold_ms: int = 5000

    # Paths
    data_dir: Path = Path("data")
    audio_dir: Path = Path("data/audio")
    faq_path: Path = Path("data/faq/clinic_faq.json")
    out_of_faq_path: Path = Path("data/faq/out_of_faq.json")
    reports_dir: Path = Path("reports")

    # S3 (optional)
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    enable_s3_logging: bool = False


settings = Settings()


def load_thresholds() -> Dict[str, Any]:
    """Load thresholds from YAML config file."""
    thresholds_path = Path("tests/thresholds.yaml")
    if thresholds_path.exists():
        with open(thresholds_path) as f:
            return yaml.safe_load(f)
    return {}


# Load thresholds at module import
THRESHOLDS = load_thresholds()


def get_threshold(key: str, default: Any = None) -> Any:
    """Get threshold value with priority: env var > yaml > settings default."""
    # Check environment variable first
    import os
    env_key = key.upper()
    if env_key in os.environ:
        val = os.environ[env_key]
        # Try to convert to appropriate type
        if isinstance(default, bool):
            return val.lower() in ("true", "1", "yes")
        elif isinstance(default, int):
            return int(val)
        elif isinstance(default, float):
            return float(val)
        return val

    # Check YAML config
    if key in THRESHOLDS:
        return THRESHOLDS[key]

    # Fall back to settings default
    return getattr(settings, key, default)


def get_settings() -> Settings:
    """Get settings instance (for dependency injection)."""
    return settings