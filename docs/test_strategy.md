# Test Strategy

## Handling Non-Deterministic Output

### Problem
LLM outputs are non-deterministic. Traditional assert-equals tests don't work.

### Solution: Multi-Layer Approach

1. **Thresholds, Not Exact Match**
   - Define minimum acceptable scores (e.g., hallucination < 15%)
   - Tests fail only when thresholds breached

2. **Multiple Runs (Configurable N)**
   - Run each test case N times (default: 3)
   - Use mean/min scores for pass/fail
   - Reduces flakiness from single bad run

3. **LLM-as-Judge with Rubric**
   - Use a calibrated judge model (GPT-4o or similar)
   - Structured rubric for each metric
   - Calibrate against 20 human-labelled cases
   - Report judge-human agreement (Cohen's kappa)

4. **Golden Dataset Versioning**
   - 100+ cases in `data/golden/` (JSON/CSV)
   - Versioned in Git with expected behaviors
   - Source references for each case
   - Separate from training data

### Metrics & Thresholds

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| Clean WER | ≤ 10% | Usable transcription quality |
| Noisy WER | ≤ 25% | Realistic for noisy environments |
| Intent Accuracy | ≥ 90% | Core routing must work |
| Slot Accuracy | ≥ 85% | Critical for booking |
| Hallucination | ≤ 15% | Safety critical |
| Faithfulness | ≥ 80% | Must ground in FAQ/tools |
| Answer Relevancy | ≥ 80% | Must address user query |
| Confirmation Rate | 100% | Must ask before irreversible actions |
| Refusal Rate (OOS) | 100% | Must refuse medical advice |
| P95 Latency | ≤ 5000ms | User experience |

## Test Pyramid

```
                    ┌─────────────┐
                    │  E2E/UI     │  ← 10% (Playwright, 20-30 clips)
                    ├─────────────┤
                    │  Integration│  ← 20% (API, multiturn, tools)
                    ├─────────────┤
                    │  Component  │  ← 30% (STT, intent, LLM eval)
                    ├─────────────┤
                    │  Unit       │  ← 40% (guardrails, tools, adapters)
                    └─────────────┘
```

### Layer Responsibilities

**Unit (40%)**: Pure functions, guardrails, adapter interfaces, tool logic
- Deterministic, fast, no external dependencies
- Mock adapters only

**Component (30%)**: Individual quality metrics
- STT: WER/CER on manifest slices
- Intent/Slot: Accuracy on golden dataset
- LLM: DeepEval metrics per case
- Safety: Injection/PII/Refusal per attack

**Integration (20%)**: Cross-component flows
- API contract tests (schemathesis)
- Multi-turn conversations
- Tool execution + confirmation
- Error propagation (STT→LLM)

**E2E/UI (10%)**: Real user journeys
- Playwright with fake microphone
- 20-30 representative clips only
- Full audio→STT→LLM→TTS pipeline
- Visual regression (1 screenshot check)

## What Is Tested At Which Layer

| Capability | Unit | Component | Integration | E2E |
|------------|------|-----------|-------------|-----|
| PII masking | ✓ | | | |
| Injection detection | ✓ | ✓ | | |
| Medical refusal | | ✓ | ✓ | ✓ |
| Confirmation flow | | | ✓ | ✓ |
| Tool arguments | ✓ | | ✓ | |
| STT accuracy | | ✓ | | ✓ |
| LLM metrics | | ✓ | | |
| API schema | | | ✓ | |
| Latency breakdown | | | ✓ | ✓ |
| Cost tracking | | | ✓ | ✓ |
| Audio pipeline | | | | ✓ |

## Risk List

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| LLM hallucinates medical advice | Medium | High | Guardrails + refusal tests + monitoring |
| STT fails on accents | High | Medium | Diverse dataset, per-slice thresholds |
| Prompt injection bypasses | Low | High | Red-team tests, monitoring |
| PII leaks in logs | Medium | High | Masking at log entry, validation queries |
| Latency regression | Medium | Medium | Per-stage tracking, alerts |
| Cost overrun | Low | Medium | Per-request tracking, daily limits |
| Flaky UI tests | High | Low | Fake mic, auto-waiting, limited scope |

## CI/CD Gates

### Pull Request (every PR)
- Lint (ruff) + Format (black) + Typecheck (mypy)
- Unit tests (100% pass)
- API tests (100% pass)
- Smoke eval (10-15 golden cases, mock adapters)
- Safety smoke (injection, PII, refusal)
- Playwright smoke (3 critical paths)

### Nightly (scheduled)
- Full golden dataset eval (all 100+ cases)
- Full Playwright suite (20-30 clips)
- Locust load test (10 users, 30s)
- Reports uploaded to S3
- CloudWatch metrics updated

### Threshold Enforcement
- Any threshold breach → PR fails
- Reports uploaded as artifacts
- Slack notification on nightly failure

## Regression Detection (Phase 6)

### Automated Regression Demo
The framework includes a complete regression detection demonstration (`tools/regression_demo.py`):

1. **Baseline**: Run with Prompt v1 + Whisper base (mock) → saves metrics to `reports/baseline`
2. **Inject STT Regression**: Switch to Whisper tiny → WER increases → STT tests fail
3. **Inject Prompt Regression**: Weaken confirmation requirement → safety tests fail
4. **Detect**: Full test suite catches both regressions
5. **Fix**: Restore Prompt v1 + Whisper base → tests pass again

### Baseline Evaluation
`tools/run_baseline.py` runs the golden dataset evaluation with current configuration and saves results as baseline for comparison.

### Regression Test Categories

| Regression Type | Detection Method | Threshold |
|----------------|------------------|-----------|
| STT Quality Drop | WER/CER increase on manifest slices | Clean WER >10%, Noisy WER >25% |
| Prompt Weakening | Safety tests (confirmation, refusal, PII) | Any safety test fails |
| LLM Quality Drop | DeepEval metrics (hallucination, faithfulness) | Hallucination >15%, Faithfulness <80% |
| Latency Regression | Locust P95/P99 per endpoint | P95 >5s (text), >15s (audio) |
| Cost Increase | Per-request cost tracking | Cost >$0.01/request |

### Running Regression Detection
```bash
# Full demo (baseline → inject → detect → fix)
python tools/regression_demo.py

# Baseline only
python tools/run_baseline.py --output reports/baseline

# With real adapters
python tools/run_baseline.py --stt faster-whisper --llm openai
```