# Architecture

## System Overview

The Voice Assistant QA Platform consists of two main components:

1. **System Under Test (SUT)**: A clinic appointment booking voice assistant
2. **QA Framework**: Comprehensive testing infrastructure

## SUT Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Browser   │────▶│  FastAPI     │────▶│  Adapters   │
│   (Mic)     │     │  Backend     │     │  (STT/LLM/  │
└─────────────┘     └──────────────┘     │   TTS)      │
       ▲                  │              └─────────────┘
       │                  ▼                     ▲
       │         ┌──────────────┐              │
       └─────────│  Web UI      │              │
                 │  (HTML/JS)   │              │
                 └──────────────┘              │
                        │                      │
                        ▼                      │
                 ┌──────────────┐              │
                 │   Tools      │──────────────┘
                 │  (Booking,   │
                 │   FAQ)       │
                 └──────────────┘
```

### Components

**FastAPI Backend** (`app/main.py`):
- `/text/chat` - Text input, JSON output
- `/audio/chat` - Audio file input, JSON + audio output
- `/health` - Health check (no auth)
- `/slots` - Available appointment slots
- `/sessions/{id}` - Session management
- API Key authentication on all except `/health`
- Auto-generated OpenAPI at `/docs`

**Adapters** (pluggable via env vars):
- STT: MockSTT, FasterWhisperSTT
- LLM: MockLLM, OpenAI, Gemini, Ollama
- TTS: MockTTS, EdgeTTS, Piper

**Tools**:
- `check_availability(date, time)` - Returns available slots
- `book_slot(name, date, time)` - Books appointment (requires confirmation)
- `cancel_booking(booking_id)` - Cancels appointment (requires confirmation)
- `answer_faq(question)` - Searches clinic FAQ

**Guardrails**:
- PII masking (phone, email, card, Aadhaar, PAN)
- Prompt injection detection
- Medical advice refusal
- System prompt protection

**Logging**: JSON lines with request/response, latency per stage, tokens, cost, PII masking status

## QA Framework Architecture

```
tests/
├── api/           # Contract tests, schema validation
├── stt/           # WER/CER with jiwer
├── intent/        # Intent/slot accuracy
├── llm_eval/      # DeepEval, Ragas, G-Eval
├── multiturn/     # Conversation context tests
├── safety/        # Injection, PII, refusal tests
├── ui/            # Playwright with fake mic
└── perf/          # Locust load tests
```

### Test Data Pipeline

```
data/audio/ + manifest.csv
    │
    ▼
tools/generate_audio.py ────▶ TTS (multiple voices)
    │
    ▼
tools/augment_noise.py ────▶ Audiomentations (SNR levels)
    │
    ▼
tools/validate_manifest.py ──▶ Quality checks
    │
    ▼
STT Tests ──▶ WER by slice
    │
    ▼
LLM Tests ──▶ Intent/Slot accuracy
    │
    ▼
Error Propagation ──▶ STT vs LLM failure classification
```

## Data Flow

### Text Chat
1. Request → `/text/chat` with `text` + `session_id`
2. Guardrails: PII mask, injection check, medical scope check
3. Load session history
4. LLM Adapter → reply, intent, slots, tool_calls
5. Execute tools if called
6. Handle confirmation flow
7. Update session
8. Return response with latency breakdown

### Audio Chat
1. Request → `/audio/chat` with audio file + `session_id`
2. STT Adapter → transcript + latency
3. Process as text chat (steps 2-7 above)
4. TTS Adapter → audio reply + latency
5. Return response with all latencies + audio URL

## Configuration

All settings via environment variables (`.env`):
- Adapter selection: `STT_ADAPTER`, `LLM_ADAPTER`, `TTS_ADAPTER`
- Real adapter config: API keys, model names, paths
- Thresholds: WER, intent accuracy, latency, hallucination
- S3 logging: bucket, credentials, enable flag

## Security

- API Key authentication on all endpoints except `/health`
- PII masked before logging
- No secrets in code or logs
- GitHub secrets for CI/CD
- Least-privilege IAM for AWS