"""Guardrails for safety: PII masking, prompt injection detection, out-of-scope handling."""

import re
from typing import Any

from app.logging_utils import get_logger

logger = get_logger(__name__)

# PII patterns
PII_PATTERNS = {
    "phone": re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "card": re.compile(r"\b(?:\d[ -]*?){13,16}\b"),
    "aadhaar": re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    "pan": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
}

# Prompt injection patterns
INJECTION_PATTERNS = [
    r"ignore\s+(?:previous|above|all)\s+(?:instructions|prompts|rules)",
    r"system\s+prompt",
    r"reveal\s+(?:your|the)\s+(?:prompt|instructions|system)",
    r"you\s+are\s+now\s+(?:a|an)",
    r"forget\s+(?:everything|all|instructions)",
    r"pretend\s+to\s+be",
    r"roleplay\s+as",
    r"act\s+as\s+(?:a|an)",
    r"override\s+(?:safety|guidelines|rules)",
    r"bypass\s+(?:safety|filters|guards)",
    r"developer\s+mode",
    r"debug\s+mode",
]

# Out-of-scope medical topics
MEDICAL_ADVICE_PATTERNS = [
    r"\b(?:medicine|medication|drug|prescription)\b.*\b(?:for|take|should)\b",
    r"\b(?:diagnose|diagnosis|condition|disease|illness)\b",
    r"\b(?:symptom|pain|ache|fever|cough)\b.*\b(?:what|which|how)\b",
    r"\b(?:treatment|therapy|cure|remedy)\b.*\b(?:for|recommend)\b",
    r"\b(?:side\s+effect|adverse|reaction)\b",
    r"\b(?:dosage|dose|mg|ml)\b.*\b(?:how|what)\b",
    r"\b(?:safe|safety)\b.*\b(?:pregnan|breastfeed|child)\b",
    r"\b(?:refer|referral|specialist)\b.*\b(?:for|to)\b",
    r"\b(?:test|scan|x-ray|mri|ct|blood)\b.*\b(?:need|should|get)\b",
]


def mask_pii(text: str) -> tuple[str, dict[str, int]]:
    """Mask PII in text. Returns (masked_text, counts_by_type)."""
    if not text:
        return text, {}

    masked = text
    counts = {}

    for pii_type, pattern in PII_PATTERNS.items():
        matches = pattern.findall(masked)
        if matches:
            counts[pii_type] = len(matches)
            masked = pattern.sub(f"[REDACTED_{pii_type.upper()}]", masked)

    return masked, counts


def detect_prompt_injection(text: str) -> tuple[bool, list[str]]:
    """Detect prompt injection attempts. Returns (is_injection, matched_patterns)."""
    if not text:
        return False, []

    matched = []
    text_lower = text.lower()

    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matched.append(pattern)

    return len(matched) > 0, matched


def is_out_of_scope_medical(text: str) -> tuple[bool, list[str]]:
    """Check if text is asking for medical advice. Returns (is_medical, matched_patterns)."""
    if not text:
        return False, []

    matched = []
    text_lower = text.lower()

    for pattern in MEDICAL_ADVICE_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            matched.append(pattern)

    return len(matched) > 0, matched


def sanitize_response(text: str) -> str:
    """Sanitize assistant response (mask PII, remove system info)."""
    masked, _ = mask_pii(text)

    # Remove any accidental system prompt leakage
    system_indicators = [
        "system prompt",
        "my instructions are",
        "as an ai",
        "i am programmed",
        "my guidelines",
        "i cannot reveal",
    ]
    for indicator in system_indicators:
        if indicator in masked.lower():
            logger.warning(f"Potential system prompt leakage detected: {indicator}")
            masked = "[Response filtered for safety]"

    return masked


def validate_tool_call(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str | None]:
    """Validate tool call arguments. Returns (is_valid, error_message)."""
    if tool_name == "book_slot":
        required = ["name", "date", "time"]
        for field in required:
            if not arguments.get(field):
                return False, f"Missing required field: {field}"
        # Basic validation
        if len(arguments["name"]) < 2:
            return False, "Name too short"
    elif tool_name == "cancel_booking":
        if not arguments.get("booking_id"):
            return False, "Missing booking_id"
        if not re.match(r"^BK\d{10,}$", arguments["booking_id"]):
            return False, "Invalid booking ID format"
    elif tool_name == "check_availability":
        if not arguments.get("date"):
            return False, "Missing date"
    elif tool_name == "answer_faq":
        if not arguments.get("question"):
            return False, "Missing question"

    return True, None


def check_confirmation_required(tool_name: str) -> bool:
    """Check if tool requires user confirmation."""
    return tool_name in ["book_slot", "cancel_booking"]


class GuardrailResult:
    """Result of guardrail checks."""

    def __init__(
        self,
        allowed: bool,
        reason: str | None = None,
        pii_masked: bool = False,
        injection_detected: bool = False,
        out_of_scope: bool = False,
        sanitized_text: str | None = None,
    ):
        self.allowed = allowed
        self.reason = reason
        self.pii_masked = pii_masked
        self.injection_detected = injection_detected
        self.out_of_scope = out_of_scope
        self.sanitized_text = sanitized_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "pii_masked": self.pii_masked,
            "injection_detected": self.injection_detected,
            "out_of_scope": self.out_of_scope,
        }


def apply_input_guardrails(text: str) -> GuardrailResult:
    """Apply all input guardrails."""
    # Check prompt injection
    is_injection, injection_patterns = detect_prompt_injection(text)
    if is_injection:
        logger.warning(f"Prompt injection detected: {injection_patterns}")
        return GuardrailResult(
            allowed=False,
            reason="Prompt injection attempt detected",
            injection_detected=True,
            sanitized_text="I can't help with that request. Let me know if you'd like to book an appointment or have questions about the clinic.",
        )

    # Check out-of-scope medical
    is_medical, medical_patterns = is_out_of_scope_medical(text)
    if is_medical:
        logger.info(f"Out-of-scope medical request detected: {medical_patterns}")
        return GuardrailResult(
            allowed=True,  # Allow but will be handled with refusal
            reason="Medical advice request - will refuse",
            out_of_scope=True,
        )

    # Mask PII
    masked_text, pii_counts = mask_pii(text)
    pii_masked = len(pii_counts) > 0

    return GuardrailResult(
        allowed=True,
        pii_masked=pii_masked,
        sanitized_text=masked_text,
    )


def apply_output_guardrails(text: str) -> str:
    """Apply output guardrails (sanitize response)."""
    return sanitize_response(text)