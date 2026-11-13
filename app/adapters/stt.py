"""Real STT adapters (FasterWhisper)."""

import asyncio
import time
from pathlib import Path
from typing import Any

from app.adapters.base import STTAdapter, STTResult
from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


class FasterWhisperSTT(STTAdapter):
    """FasterWhisper STT adapter for local transcription."""

    name = "faster-whisper"

    def __init__(self):
        self.settings = get_settings()
        self._model = None

    def _load_model(self):
        """Lazy load the Whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {self.settings.whisper_model_size}")
            self._model = WhisperModel(
                self.settings.whisper_model_size,
                device=self.settings.whisper_device,
                compute_type=self.settings.whisper_compute_type,
            )

    async def transcribe(self, audio_path: str) -> STTResult:
        """Transcribe audio using FasterWhisper."""
        self._load_model()

        start = time.perf_counter()

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        segments, info = await loop.run_in_executor(
            None,
            lambda: self._model.transcribe(audio_path, beam_size=5, language="en"),
        )

        transcript = " ".join([seg.text for seg in segments]).strip()
        latency_ms = int((time.perf_counter() - start) * 1000)

        logger.info(f"Whisper transcribed: {transcript[:50]}... (lang={info.language}, latency={latency_ms}ms)")

        return STTResult(
            transcript=transcript,
            language=info.language,
            confidence=1.0 - (info.no_speech_prob or 0),
            latency_ms=latency_ms,
        )