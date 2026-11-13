"""Structured logging utilities for the Voice Assistant QA Platform."""

import json
import re
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import get_settings
from app.schemas import LogEntry


# Context variable for request tracking
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")


# PII patterns for masking
PII_PATTERNS = {
    "phone": re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
}


def mask_pii(text: str) -> tuple[str, bool]:
    """Mask PII in text. Returns (masked_text, was_masked)."""
    masked = text
    was_masked = False
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(masked):
            masked = pattern.sub(f"[REDACTED_{pii_type.upper()}]", masked)
            was_masked = True
    return masked, was_masked


def setup_logging() -> None:
    """Configure loguru for JSON lines logging to file and console."""
    settings = get_settings()

    # Remove default handler
    logger.remove()

    # Ensure log directory exists
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Console handler (human-readable)
    logger.add(
        lambda msg: print(msg, end=""),
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
    )

    # File handler (JSON lines)
    def json_sink(message):
        record = message.record
        log_entry = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "logger": record["name"],
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
            "request_id": request_id_var.get(""),
            "session_id": session_id_var.get(""),
            "extra": record["extra"],
        }
        with open(settings.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    logger.add(
        json_sink,
        level=settings.log_level,
        format="{message}",
        filter=lambda record: record["extra"].get("structured", False),
    )


def log_request_response(
    endpoint: str,
    input_text: str | None,
    transcript: str | None,
    response_text: str,
    intent: str | None,
    slots: dict[str, Any],
    tool_calls: list[dict[str, Any]],
    latency_ms: dict[str, int],
    token_count: int | None = None,
    estimated_cost_usd: float | None = None,
    error: str | None = None,
) -> None:
    """Log a structured request/response entry."""
    # Mask PII in logged fields
    masked_input, input_masked = mask_pii(input_text) if input_text else (None, False)
    masked_transcript, transcript_masked = mask_pii(transcript) if transcript else (None, False)
    masked_response, response_masked = mask_pii(response_text)
    masked_slots = {}
    slots_masked = False
    for k, v in slots.items():
        if isinstance(v, str):
            masked_v, v_masked = mask_pii(v)
            masked_slots[k] = masked_v
            slots_masked = slots_masked or v_masked
        else:
            masked_slots[k] = v

    pii_masked = any([input_masked, transcript_masked, response_masked, slots_masked])

    entry = LogEntry(
        timestamp=datetime.utcnow(),
        request_id=request_id_var.get("") or str(uuid.uuid4()),
        session_id=session_id_var.get("") or None,
        endpoint=endpoint,
        input_text=masked_input,
        transcript=masked_transcript,
        response_text=masked_response,
        intent=intent,
        slots=masked_slots,
        tool_calls=tool_calls,
        latency_ms=latency_ms,
        token_count=token_count,
        estimated_cost_usd=estimated_cost_usd,
        pii_masked=pii_masked,
        error=error,
    )

    logger.bind(structured=True).info(entry.model_dump_json())


def set_request_context(request_id: str, session_id: str = "") -> None:
    """Set context variables for current request."""
    request_id_var.set(request_id)
    if session_id:
        session_id_var.set(session_id)


def clear_request_context() -> None:
    """Clear context variables."""
    request_id_var.set("")
    session_id_var.set("")


def get_logger(name: str):
    """Get a logger instance with the given name."""
    return logger.bind(name=name)