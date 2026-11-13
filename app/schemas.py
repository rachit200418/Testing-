"""Pydantic schemas for request/response validation and API documentation."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class Intent(str, Enum):
    """Supported intents for the clinic appointment assistant."""

    BOOK_APPOINTMENT = "book_appointment"
    CANCEL_APPOINTMENT = "cancel_appointment"
    RESCHEDULE_APPOINTMENT = "reschedule_appointment"
    CHECK_AVAILABILITY = "check_availability"
    FAQ = "faq"
    OUT_OF_SCOPE = "out_of_scope"
    PROMPT_INJECTION = "prompt_injection"
    GREETING = "greeting"
    GOODBYE = "goodbye"


class ToolName(str, Enum):
    """Available tools for the assistant."""

    CHECK_AVAILABILITY = "check_availability"
    BOOK_SLOT = "book_slot"
    CANCEL_BOOKING = "cancel_booking"
    ANSWER_FAQ = "answer_faq"


class SlotKey(str, Enum):
    """Slot keys for appointment booking."""

    PATIENT_NAME = "patient_name"
    DATE = "date"
    TIME = "time"
    BOOKING_ID = "booking_id"
    DOCTOR_NAME = "doctor_name"
    SPECIALTY = "specialty"


# Request/Response Models


class TextChatRequest(BaseModel):
    """Request model for /text/chat endpoint."""

    model_config = ConfigDict(json_schema_extra={"example": {"text": "I want to book an appointment for tomorrow at 3 PM", "session_id": "sess_123"}})

    text: str = Field(..., min_length=1, max_length=5000, description="User's text input")
    session_id: Optional[str] = Field(None, description="Session ID for multi-turn conversation")


class AudioChatRequest(BaseModel):
    """Request model for /audio/chat endpoint (multipart form)."""

    # This is handled via Form/File in the endpoint, but documented here
    session_id: Optional[str] = Field(None, description="Session ID for multi-turn conversation")


class ToolCall(BaseModel):
    """Represents a tool call made by the LLM."""

    name: ToolName
    arguments: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class StageLatency(BaseModel):
    """Latency breakdown per processing stage."""

    stt_ms: Optional[int] = None
    llm_ms: Optional[int] = None
    tts_ms: Optional[int] = None
    total_ms: int


class ChatResponse(BaseModel):
    """Base response model for both text and audio chat."""

    model_config = ConfigDict(json_schema_extra={"example": {"reply": "Sure, I can help with that. What's your name?", "intent": "book_appointment", "slots": {"patient_name": null, "date": "tomorrow", "time": "3 PM"}, "tool_calls": [], "session_id": "sess_123", "latency": {"total_ms": 450}}})

    reply: str = Field(..., description="Assistant's text response")
    intent: Intent
    slots: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    session_id: str
    latency: StageLatency


class TextChatResponse(ChatResponse):
    """Response model for /text/chat endpoint."""

    pass


class AudioChatResponse(ChatResponse):
    """Response model for /audio/chat endpoint."""

    transcript: str = Field(..., description="Transcribed text from audio")
    audio_reply_url: Optional[str] = Field(None, description="URL to generated TTS audio")


class HealthResponse(BaseModel):
    """Response model for /health endpoint."""

    status: str = "healthy"
    version: str
    adapters: dict[str, str]


class SlotInfo(BaseModel):
    """Available slot information."""

    date: str
    time: str
    doctor: str
    specialty: str
    available: bool


class SlotsResponse(BaseModel):
    """Response model for /slots endpoint."""

    slots: list[SlotInfo]


class SessionDeleteResponse(BaseModel):
    """Response model for DELETE /sessions/{id}."""

    deleted: bool
    session_id: str


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: Optional[str] = None
    code: str


# Internal models


class SessionData(BaseModel):
    """Internal session storage model."""

    session_id: str
    created_at: datetime
    updated_at: datetime
    history: list[dict[str, Any]] = Field(default_factory=list)
    pending_confirmation: Optional[dict[str, Any]] = None


class Booking(BaseModel):
    """Booking database model."""

    booking_id: str
    patient_name: str
    date: str
    time: str
    doctor: str
    specialty: str
    created_at: datetime
    status: str = "confirmed"  # confirmed, cancelled


class FAQEntry(BaseModel):
    """FAQ entry model."""

    id: str
    question: str
    answer: str
    category: str


class OutOfFAQEntry(BaseModel):
    """Out-of-FAQ test entry."""

    id: str
    question: str
    expected_behavior: str  # "refuse"
    reason: str


class ManifestEntry(BaseModel):
    """Audio test dataset manifest entry."""

    file: str
    transcript: str
    intent: Intent
    slots_json: str
    accent: str
    noise_level: str
    speed: str
    source: str  # synthetic, real
    tags: str = ""


class LogEntry(BaseModel):
    """Structured log entry for JSON lines logging."""

    timestamp: datetime
    request_id: str
    session_id: Optional[str]
    endpoint: str
    input_text: Optional[str] = None
    transcript: Optional[str] = None
    response_text: str
    intent: Optional[str] = None
    slots: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    latency_ms: dict[str, int] = Field(default_factory=dict)
    token_count: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    pii_masked: bool = False
    error: Optional[str] = None