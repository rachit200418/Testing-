"""Adapter interfaces for STT, LLM, and TTS."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class STTResult:
    """Result from speech-to-text transcription."""

    transcript: str
    language: str = "en"
    confidence: float = 1.0
    latency_ms: int = 0


@dataclass
class LLMResult:
    """Result from LLM processing."""

    reply: str
    intent: str
    slots: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    token_count: int = 0
    estimated_cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class TTSResult:
    """Result from text-to-speech synthesis."""

    audio_path: str
    audio_url: str
    latency_ms: int = 0
    duration_ms: int = 0


class STTAdapter(ABC):
    """Interface for Speech-to-Text adapters."""

    @abstractmethod
    async def transcribe(self, audio_path: str) -> STTResult:
        """Transcribe audio file to text."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name for logging."""
        pass


class LLMAdapter(ABC):
    """Interface for LLM adapters."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResult:
        """Generate response from messages with optional tool calling."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name for logging."""
        pass


class TTSAdapter(ABC):
    """Interface for Text-to-Speech adapters."""

    @abstractmethod
    async def synthesize(self, text: str, output_path: str) -> TTSResult:
        """Synthesize text to audio file."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Adapter name for logging."""
        pass