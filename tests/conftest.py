"""Pytest configuration and fixtures for the Voice Assistant QA Platform."""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test environment before importing app
os.environ["STT_ADAPTER"] = "mock"
os.environ["LLM_ADAPTER"] = "mock"
os.environ["TTS_ADAPTER"] = "mock"
os.environ["API_KEY"] = "test-api-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["LOG_LEVEL"] = "WARNING"

from app.main import app
from app.tools.database import init_db, close_db


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await close_db()


@pytest.fixture
def api_headers() -> dict[str, str]:
    """Standard API headers with test API key."""
    return {"X-API-Key": "test-api-key"}


@pytest.fixture
def sample_audio_file() -> Generator[Path, None, None]:
    """Create a temporary WAV file for testing."""
    import wave
    import struct

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_path = Path(f.name)

    with wave.open(str(temp_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        # 1 second of silence
        silence = struct.pack("<" + "h" * 16000, *([0] * 16000))
        wav.writeframes(silence)

    yield temp_path

    temp_path.unlink(missing_ok=True)


@pytest.fixture
def session_id() -> str:
    """Generate a unique session ID for tests."""
    import uuid
    return f"test_sess_{uuid.uuid4().hex[:8]}"


# Test data constants
VALID_TEXT_REQUEST = {
    "text": "I want to book an appointment for tomorrow at 3 PM",
    "session_id": None,
}

BOOKING_FLOW_REQUESTS = [
    "I want to book an appointment",
    "My name is John Doe",
    "Tomorrow at 3 PM",
    "Yes, confirm",
]

CANCEL_FLOW_REQUESTS = [
    "I want to cancel my appointment",
    "Booking ID is BK1234567890",
    "Yes, confirm",
]