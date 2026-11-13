"""Adapter factory for creating STT, LLM, and TTS adapters based on configuration."""

from app.adapters.base import LLMAdapter, STTAdapter, TTSAdapter
from app.adapters.llm import GeminiLLM, OllamaLLM, OpenAILLM
from app.adapters.mock import MockLLM, MockSTT, MockTTS
from app.adapters.stt import FasterWhisperSTT
from app.adapters.tts import EdgeTTS, PiperTTS
from app.config import get_settings


def create_stt_adapter() -> STTAdapter:
    """Create STT adapter based on settings."""
    settings = get_settings()
    if settings.stt_adapter == "faster-whisper":
        return FasterWhisperSTT()
    return MockSTT()


def create_llm_adapter() -> LLMAdapter:
    """Create LLM adapter based on settings."""
    settings = get_settings()
    if settings.llm_adapter == "openai":
        return OpenAILLM()
    elif settings.llm_adapter == "gemini":
        return GeminiLLM()
    elif settings.llm_adapter == "ollama":
        return OllamaLLM()
    return MockLLM()


def create_tts_adapter() -> TTSAdapter:
    """Create TTS adapter based on settings."""
    settings = get_settings()
    if settings.tts_adapter == "edge-tts":
        return EdgeTTS()
    elif settings.tts_adapter == "piper":
        return PiperTTS()
    return MockTTS()