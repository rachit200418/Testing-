"""Main FastAPI application for the Voice Assistant QA Platform."""

import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import ValidationError

from app.adapters.factory import create_llm_adapter, create_stt_adapter, create_tts_adapter
from app.config import get_settings
from app.guardrails.guardrails import apply_input_guardrails, apply_output_guardrails, check_confirmation_required, validate_tool_call
from app.logging_utils import log_request_response, set_request_context, clear_request_context
from app.schemas import (
    AudioChatResponse,
    ErrorResponse,
    HealthResponse,
    SlotInfo,
    SlotsResponse,
    SessionDeleteResponse,
    TextChatRequest,
    TextChatResponse,
)
from app.tools.database import (
    answer_faq,
    book_slot,
    cancel_booking,
    check_availability,
    close_db,
    create_session,
    delete_session,
    get_booking,
    get_session,
    init_db,
    update_session,
)
from app.logging_utils import get_logger

logger = get_logger(__name__)
settings = get_settings()

# API Key security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Depends(api_key_header)) -> str:
    """Verify API key for protected endpoints."""
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
    return api_key


# Adapter instances (initialized on startup)
stt_adapter = None
llm_adapter = None
tts_adapter = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    global stt_adapter, llm_adapter, tts_adapter

    # Startup
    logger.info("Starting Voice Assistant QA Platform")
    await init_db()

    # Initialize adapters
    stt_adapter = create_stt_adapter()
    llm_adapter = create_llm_adapter()
    tts_adapter = create_tts_adapter()

    logger.info(f"Adapters initialized: STT={stt_adapter.name}, LLM={llm_adapter.name}, TTS={tts_adapter.name}")

    # Ensure audio directories exist
    Path("data/audio/replies").mkdir(parents=True, exist_ok=True)
    Path("data/audio/uploads").mkdir(parents=True, exist_ok=True)

    yield

    # Shutdown
    logger.info("Shutting down Voice Assistant QA Platform")
    await close_db()
    if hasattr(llm_adapter, "close"):
        await llm_adapter.close()


app = FastAPI(
    title="Voice Assistant QA Platform",
    description="Clinic appointment booking voice assistant with comprehensive QA framework",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for audio replies
from fastapi.staticfiles import StaticFiles

app.mount("/audio/replies", StaticFiles(directory="data/audio/replies"), name="audio_replies")
app.mount("/web", StaticFiles(directory="web"), name="web")


# Tool executor
TOOL_FUNCTIONS = {
    "check_availability": check_availability,
    "book_slot": book_slot,
    "cancel_booking": cancel_booking,
    "answer_faq": answer_faq,
}


async def execute_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Execute tool calls and return results."""
    results = []
    for tc in tool_calls:
        name = tc["name"]
        args = tc.get("arguments", {})

        # Validate
        valid, error = validate_tool_call(name, args)
        if not valid:
            results.append({**tc, "result": None, "error": error})
            continue

        # Execute
        try:
            func = TOOL_FUNCTIONS.get(name)
            if func:
                result = await func(**args)
                results.append({**tc, "result": result, "error": None})
            else:
                results.append({**tc, "result": None, "error": f"Unknown tool: {name}"})
        except Exception as e:
            logger.error(f"Tool {name} failed: {e}")
            results.append({**tc, "result": None, "error": str(e)})

    return results


async def process_chat(
    user_text: str,
    session_id: str,
    is_audio: bool = False,
) -> tuple[str, str, dict[str, Any], list[dict[str, Any]], dict[str, int], int, float]:
    """Process a chat message through the full pipeline."""
    latencies = {}
    total_start = time.perf_counter()

    # Get or create session
    session = await get_session(session_id)
    if not session:
        await create_session(session_id)
        session = await get_session(session_id)

    history = session["history"]
    pending = session.get("pending_confirmation")

    # Build messages for LLM
    messages = []
    for turn in history[-6:]:  # Last 6 turns for context
        messages.append({"role": "user", "content": turn["user"]})
        messages.append({"role": "assistant", "content": turn["assistant"]})

    # Handle pending confirmation
    if pending and user_text.lower() in ["yes", "confirm", "sure", "ok", "please do", "go ahead"]:
        # Execute the pending tool
        tool_name = pending["tool"]
        tool_args = pending["arguments"]
        tool_result = await TOOL_FUNCTIONS[tool_name](**tool_args)

        if tool_result.get("success"):
            if tool_name == "book_slot":
                reply = f"Appointment booked! Your booking ID is {tool_result['booking_id']}. {tool_result['patient_name']} on {tool_result['date']} at {tool_result['time']} with {tool_result['doctor']}."
            elif tool_name == "cancel_booking":
                reply = f"Booking {tool_result['booking_id']} has been cancelled."
            else:
                reply = "Done!"
        else:
            reply = f"Sorry, there was an error: {tool_result.get('error', 'Unknown error')}"

        # Clear pending confirmation
        await update_session(
            session_id,
            user_text,
            reply,
            pending["intent"],
            {},
            [{"name": tool_name, "arguments": tool_args, "result": tool_result}],
            pending_confirmation=False,
        )

        latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)
        return reply, pending["intent"], {}, [{"name": tool_name, "arguments": tool_args, "result": tool_result}], latencies, 0, 0.0

    elif pending and user_text.lower() in ["no", "cancel", "don't", "do not"]:
        reply = "Okay, I've cancelled that request. Let me know if you need anything else."
        await update_session(
            session_id,
            user_text,
            reply,
            "cancel_appointment",
            {},
            [],
            pending_confirmation=False,
        )
        latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)
        return reply, "cancel_appointment", {}, [], latencies, 0, 0.0

    # Apply input guardrails
    guardrail_result = apply_input_guardrails(user_text)
    if not guardrail_result.allowed:
        reply = apply_output_guardrails(guardrail_result.sanitized_text or "I can't help with that.")
        latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)
        await update_session(session_id, user_text, reply, "prompt_injection", {}, [], pending_confirmation=False)
        return reply, "prompt_injection", {}, [], latencies, 0, 0.0

    # Use sanitized text for processing
    processed_text = guardrail_result.sanitized_text or user_text

    # Check for medical advice (out of scope)
    if guardrail_result.out_of_scope:
        reply = apply_output_guardrails(
            "I'm an appointment booking assistant and can't provide medical advice. Please consult a doctor for health concerns. I can help you book an appointment with a specialist."
        )
        latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)
        await update_session(session_id, user_text, reply, "out_of_scope", {}, [], pending_confirmation=False)
        return reply, "out_of_scope", {}, [], latencies, 0, 0.0

    # Add current message
    messages.append({"role": "user", "content": processed_text})

    # Call LLM
    llm_start = time.perf_counter()
    llm_result = await llm_adapter.chat(messages)
    latencies["llm_ms"] = int((time.perf_counter() - llm_start) * 1000)

    reply = llm_result.reply
    intent = llm_result.intent
    slots = llm_result.slots
    tool_calls = llm_result.tool_calls

    # Execute tool calls if any
    if tool_calls:
        tool_start = time.perf_counter()
        executed_calls = await execute_tool_calls(tool_calls)
        latencies["tools_ms"] = int((time.perf_counter() - tool_start) * 1000)

        # Check if any tool requires confirmation
        for tc in executed_calls:
            if check_confirmation_required(tc["name"]) and not tc.get("error"):
                # Set pending confirmation
                await update_session(
                    session_id,
                    user_text,
                    reply,
                    intent,
                    slots,
                    executed_calls,
                    pending_confirmation={"tool": tc["name"], "arguments": tc["arguments"], "intent": intent},
                )
                latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)
                return reply, intent, slots, executed_calls, latencies, llm_result.token_count, llm_result.estimated_cost_usd

        tool_calls = executed_calls

    # Apply output guardrails
    reply = apply_output_guardrails(reply)

    # Update session
    await update_session(session_id, user_text, reply, intent, slots, tool_calls, pending_confirmation=False)

    latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)
    return reply, intent, slots, tool_calls, latencies, llm_result.token_count, llm_result.estimated_cost_usd


# Endpoints


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        adapters={
            "stt": stt_adapter.name if stt_adapter else "not initialized",
            "llm": llm_adapter.name if llm_adapter else "not initialized",
            "tts": tts_adapter.name if tts_adapter else "not initialized",
        },
    )


@app.post("/text/chat", response_model=TextChatResponse, dependencies=[Depends(verify_api_key)])
async def text_chat(request: TextChatRequest):
    """Text chat endpoint."""
    request_id = str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())

    set_request_context(request_id, session_id)

    try:
        start = time.perf_counter()

        reply, intent, slots, tool_calls, latencies, token_count, cost = await process_chat(
            request.text,
            session_id,
            is_audio=False,
        )

        latencies["total_ms"] = int((time.perf_counter() - start) * 1000)

        response = TextChatResponse(
            reply=reply,
            intent=intent,
            slots=slots,
            tool_calls=tool_calls,
            session_id=session_id,
            latency=latencies,
        )

        log_request_response(
            endpoint="/text/chat",
            input_text=request.text,
            transcript=None,
            response_text=reply,
            intent=intent,
            slots=slots,
            tool_calls=tool_calls,
            latency_ms=latencies,
            token_count=token_count,
            estimated_cost_usd=cost,
        )

        return response

    except Exception as e:
        logger.exception(f"Error in text_chat: {e}")
        log_request_response(
            endpoint="/text/chat",
            input_text=request.text,
            transcript=None,
            response_text="",
            intent=None,
            slots={},
            tool_calls=[],
            latency_ms={},
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        clear_request_context()


@app.post("/audio/chat", response_model=AudioChatResponse, dependencies=[Depends(verify_api_key)])
async def audio_chat(
    session_id: str = Form(None),
    audio_file: UploadFile = File(...),
):
    """Audio chat endpoint: audio -> STT -> LLM -> TTS -> audio reply."""
    request_id = str(uuid.uuid4())
    sess_id = session_id or str(uuid.uuid4())

    set_request_context(request_id, sess_id)

    # Validate audio file
    if not audio_file.content_type or not audio_file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="File must be audio")

    # Save uploaded file
    upload_dir = Path("data/audio/uploads")
    upload_dir.mkdir(parents=True, exist_ok=True)
    audio_path = upload_dir / f"{request_id}_{audio_file.filename}"

    content = await audio_file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=413, detail="Audio file too large (max 10MB)")

    with open(audio_path, "wb") as f:
        f.write(content)

    try:
        total_start = time.perf_counter()
        latencies = {}

        # STT
        stt_start = time.perf_counter()
        stt_result = await stt_adapter.transcribe(str(audio_path))
        latencies["stt_ms"] = int((time.perf_counter() - stt_start) * 1000)

        transcript = stt_result.transcript

        # Process through LLM pipeline
        reply, intent, slots, tool_calls, chat_latencies, token_count, cost = await process_chat(
            transcript,
            sess_id,
            is_audio=True,
        )

        latencies.update(chat_latencies)

        # TTS
        tts_start = time.perf_counter()
        reply_audio_path = Path("data/audio/replies") / f"{request_id}_reply.wav"
        tts_result = await tts_adapter.synthesize(reply, str(reply_audio_path))
        latencies["tts_ms"] = tts_result.latency_ms

        latencies["total_ms"] = int((time.perf_counter() - total_start) * 1000)

        response = AudioChatResponse(
            transcript=transcript,
            reply=reply,
            intent=intent,
            slots=slots,
            tool_calls=tool_calls,
            session_id=sess_id,
            latency=latencies,
            audio_reply_url=tts_result.audio_url,
        )

        log_request_response(
            endpoint="/audio/chat",
            input_text=None,
            transcript=transcript,
            response_text=reply,
            intent=intent,
            slots=slots,
            tool_calls=tool_calls,
            latency_ms=latencies,
            token_count=token_count,
            estimated_cost_usd=cost,
        )

        return response

    except Exception as e:
        logger.exception(f"Error in audio_chat: {e}")
        log_request_response(
            endpoint="/audio/chat",
            input_text=None,
            transcript=None,
            response_text="",
            intent=None,
            slots={},
            tool_calls=[],
            latency_ms={},
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        clear_request_context()
        # Cleanup uploaded file
        try:
            audio_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/slots", response_model=SlotsResponse, dependencies=[Depends(verify_api_key)])
async def get_slots(date: str):
    """Get available slots for a date."""
    slots = await check_availability(date)
    return SlotsResponse(slots=[SlotInfo(**s) for s in slots])


@app.delete("/sessions/{session_id}", response_model=SessionDeleteResponse, dependencies=[Depends(verify_api_key)])
async def delete_session_endpoint(session_id: str):
    """Delete a session."""
    deleted = await delete_session(session_id)
    return SessionDeleteResponse(deleted=deleted, session_id=session_id)


# Error handlers
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(error="Validation error", detail=str(exc), code="VALIDATION_ERROR").model_dump(),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.detail, code=f"HTTP_{exc.status_code}").model_dump(),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)