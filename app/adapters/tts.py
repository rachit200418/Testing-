"""Real TTS adapters (Edge TTS, Piper)."""

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Any

from app.adapters.base import TTSAdapter, TTSResult
from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


class EdgeTTS(TTSAdapter):
    """Microsoft Edge TTS adapter (free, no API key needed)."""

    name = "edge-tts"

    def __init__(self):
        self.settings = get_settings()
        self.output_dir = Path("data/audio/replies")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, text: str, output_path: str) -> TTSResult:
        """Synthesize text to speech using edge-tts."""
        start = time.perf_counter()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # Use edge-tts command line
        cmd = [
            "edge-tts",
            "--voice",
            self.settings.edge_tts_voice,
            "--text",
            text,
            "--write-media",
            output_path,
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise RuntimeError(f"edge-tts failed: {stderr.decode()}")

        except FileNotFoundError:
            logger.warning("edge-tts not installed, falling back to silent audio")
            return await self._fallback_silent(text, output_path, start)

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Estimate duration (rough: ~150 words per minute)
        word_count = len(text.split())
        duration_ms = int((word_count / 150) * 60 * 1000)

        audio_url = f"/audio/replies/{Path(output_path).name}"

        logger.info(f"Edge TTS synthesized: {text[:30]}... ({latency_ms}ms)")
        return TTSResult(
            audio_path=output_path,
            audio_url=audio_url,
            latency_ms=latency_ms,
            duration_ms=duration_ms,
        )

    async def _fallback_silent(self, text: str, output_path: str, start: float) -> TTSResult:
        """Create silent audio as fallback."""
        import wave
        import struct

        word_count = len(text.split())
        duration_ms = max(1000, int((word_count / 150) * 60 * 1000))
        samples = int(16000 * duration_ms / 1000)

        with wave.open(output_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            silence = struct.pack("<" + "h" * samples, *([0] * samples))
            wav.writeframes(silence)

        latency_ms = int((time.perf_counter() - start) * 1000)
        audio_url = f"/audio/replies/{Path(output_path).name}"

        return TTSResult(
            audio_path=output_path,
            audio_url=audio_url,
            latency_ms=latency_ms,
            duration_ms=duration_ms,
        )


class PiperTTS(TTSAdapter):
    """Piper TTS adapter (local, high quality)."""

    name = "piper"

    def __init__(self):
        self.settings = get_settings()
        self.output_dir = Path("data/audio/replies")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def synthesize(self, text: str, output_path: str) -> TTSResult:
        """Synthesize text to speech using Piper."""
        start = time.perf_counter()

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if not self.settings.piper_model_path:
            logger.warning("Piper model path not configured, falling back to silent audio")
            return await self._fallback_silent(text, output_path, start)

        cmd = [
            "piper",
            "--model",
            self.settings.piper_model_path,
            "--output_file",
            output_path,
        ]

        if self.settings.piper_speaker_id:
            cmd.extend(["--speaker", str(self.settings.piper_speaker_id)])

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(input=text.encode())

            if process.returncode != 0:
                raise RuntimeError(f"Piper failed: {stderr.decode()}")

        except FileNotFoundError:
            logger.warning("Piper not installed, falling back to silent audio")
            return await self._fallback_silent(text, output_path, start)

        latency_ms = int((time.perf_counter() - start) * 1000)

        # Get duration from file
        import wave

        with wave.open(output_path, "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            duration_ms = int(frames / rate * 1000)

        audio_url = f"/audio/replies/{Path(output_path).name}"

        logger.info(f"Piper TTS synthesized: {text[:30]}... ({latency_ms}ms)")
        return TTSResult(
            audio_path=output_path,
            audio_url=audio_url,
            latency_ms=latency_ms,
            duration_ms=duration_ms,
        )

    async def _fallback_silent(self, text: str, output_path: str, start: float) -> TTSResult:
        """Create silent audio as fallback."""
        import wave
        import struct

        word_count = len(text.split())
        duration_ms = max(1000, int((word_count / 150) * 60 * 1000))
        samples = int(16000 * duration_ms / 1000)

        with wave.open(output_path, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            silence = struct.pack("<" + "h" * samples, *([0] * samples))
            wav.writeframes(silence)

        latency_ms = int((time.perf_counter() - start) * 1000)
        audio_url = f"/audio/replies/{Path(output_path).name}"

        return TTSResult(
            audio_path=output_path,
            audio_url=audio_url,
            latency_ms=latency_ms,
            duration_ms=duration_ms,
        )