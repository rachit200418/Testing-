# Interview Notes

## Tool Choices & Reasoning

### Backend: FastAPI
**Why**: Modern, fast, auto OpenAPI, type hints, async support
**Alternatives considered**: Flask (no async, no auto-docs), Django (overkill)
**Interview Q**: "Why not Flask?" → FastAPI gives async, validation, docs out of box

### Adapters: Interface Pattern
**Why**: Swap mock/real without code changes, test isolation, dependency inversion
**Interview Q**: "How do you test without API keys?" → Mock adapters implement same interface

### STT: FasterWhisper
**Why**: Local, fast, no API key, CTranslate2 backend, multiple model sizes
**Alternatives**: OpenAI Whisper API (cost, latency), Vosk (less accurate)
**Interview Q**: "Why not cloud STT?" → Cost, privacy, offline testing

### LLM: Multiple Providers
**Why**: Avoid vendor lock-in, compare quality/cost, local option (Ollama)
**Interview Q**: "How do you choose a model?" → Benchmark on golden dataset, cost/latency tradeoff

### TTS: Edge-TTS + Piper
**Why**: Edge-TTS free/cloud, Piper local/high-quality, both no API keys
**Interview Q**: "Why not ElevenLabs?" → Cost, this is a QA demo not production

### Database: SQLite + SQLAlchemy Async
**Why**: Zero-config, file-based, async support, easy to swap to Postgres
**Interview Q**: "Production database?" → Swap connection string to Postgres, same code

### Logging: Loguru + JSON Lines
**Why**: Structured logs, rotation, context variables, easy parsing
**Interview Q**: "Why not standard logging?" → Loguru simpler, JSON lines better for analysis

### STT Quality: jiwer
**Why**: Standard library for WER/CER, handles normalization, slicing support
**Interview Q**: "How do you measure STT quality?" → WER/CER on manifest with ground truth

### LLM Eval: DeepEval + Ragas
**Why**: DeepEval has G-Eval (custom criteria), Ragas for RAG, both open source
**Interview Q**: "How do you evaluate LLM quality?" → Multiple metrics, LLM-as-judge with rubric

### Prompt Regression: promptfoo
**Why**: Purpose-built for prompt testing, CI integration, multiple model comparison
**Interview Q**: "How do you catch prompt regressions?" → promptfoo config with baseline scores

### UI Automation: Playwright
**Why**: Auto-waiting, fake media streams, trace/video on failure, cross-browser
**Interview Q**: "Why not Selenium?" → Playwright faster, more reliable, better DX

### Performance: Locust
**Why**: Python-based, distributed, WebSocket support, programmatic control
**Interview Q**: "How do you load test?" → Locust with per-stage latency, cost tracking

### Data Validation: DuckDB + Athena
**Why**: DuckDB local (no AWS needed), Athena for production scale, same SQL
**Interview Q**: "How do you validate logs?" → SQL queries for PII, drift, duplicates

### CI/CD: GitHub Actions
**Why**: Native to GitHub, matrix builds, artifacts, environments, secrets
**Interview Q**: "CI/CD pipeline?" → PR checks + nightly full suite + AWS deployment

### Infrastructure: Terraform
**Why**: Declarative, state management, multi-cloud, module ecosystem
**Interview Q**: "Why not CDK?" → Terraform more common, HCL simpler for infra

## Key Interview Questions & Answers

### Q: "How do you handle non-deterministic LLM outputs in tests?"
**A**: Three layers: (1) Thresholds instead of exact match, (2) Run N times, use mean/min, (3) LLM-as-judge with calibrated rubric. Golden dataset versioned in Git.

### Q: "How do you test audio without real microphone in CI?"
**A**: Playwright launches Chromium with `--use-fake-device-for-media-stream` and `--use-file-for-fake-audio-capture=clip.wav%noloop`. Each test gets fresh browser with parametrized clip.

### Q: "How do you ensure PII doesn't leak?"
**A**: Mask at log entry point (Loguru sink), validate with DuckDB/Athena queries nightly, guardrails mask in responses, unit tests for masking patterns.

### Q: "How do you measure STT quality across accents/noise?"
**A**: Manifest CSV with accent/noise/speed tags. jiwer computes WER/CER overall and per slice. Thresholds: clean ≤10%, noisy ≤25%.

### Q: "What's your error propagation analysis?"
**A**: Run each case as text (ground truth) and audio. Compare failures: if text passes but audio fails → STT origin. If both fail → LLM origin. Report percentages.

### Q: "How do you test guardrails?"
**A**: Unit tests for each pattern (PII, injection, medical). promptfoo red-team config for adversarial. Safety report with attack success rate per category.

### Q: "How do you handle multi-turn conversations?"
**A**: Session storage in SQLite with JSON history. LLM receives last 6 turns. Confirmation flow: pending_confirmation in session, resolved on next turn.

### Q: "How do you track costs?"
**A**: Each LLM call returns token_count + estimated_cost. Logged per request. DuckDB queries for daily cost, per-model cost. Locust reports cost per request.

### Q: "What's your CI/CD strategy?"
**A**: PR: lint, unit, API, smoke eval (15 cases), safety smoke, Playwright smoke. Nightly: full golden (100+), full UI (30 clips), Locust, S3 upload. Thresholds gate merges.

### Q: "How would you scale this to production?"
**A**: Swap SQLite→Postgres, mock→real adapters, add rate limiting, Redis for sessions, Kubernetes deployment, Prometheus/Grafana monitoring, canary releases.

### Q: "What's the biggest limitation of this approach?"
**A**: Mock adapters don't catch real model behaviors. Golden dataset needs continuous curation. LLM-as-judge adds cost/latency. Audio testing limited to 30 clips in UI.

### Q: "How do you version test data?"
**A**: Manifest.csv and golden dataset in Git. DVC for large audio files (git-ignored). Schema validation in CI. Failed production cases added via script.

## Phase 5-6: AWS, CI/CD, Regression Detection

### Q: "How do you validate logs for PII leakage without scanning all data?"
**A**: DuckDB queries on local logs / Athena on S3. Queries check `pii_masked=false` and regex patterns for phone/email/card/Aadhaar/PAN in responses/transcripts. Runs nightly via Lambda, results to S3.

### Q: "How does your CI/CD deploy infrastructure without long-lived AWS keys?"
**A**: GitHub Actions OIDC: Terraform creates IAM role with trust policy for `token.actions.githubusercontent.com`. Workflow uses `aws-actions/configure-aws-credentials@v4` with `role-to-assume`. No access keys in GitHub secrets.

### Q: "How do you alert on LLM quality regressions in production?"
**A**: Custom CloudWatch metrics (hallucination, faithfulness, confirmation rate, PII masking) published nightly by Lambda. 11 alarms on thresholds (e.g., hallucination >15%, confirmation <100%). Alarms → SNS → email + Slack. Dashboard shows trends.

### Q: "How do you catch regressions in the voice assistant?"
**A**: Automated regression demo: (1) Baseline run with Prompt v1 + Whisper base → saves metrics. (2) Inject STT regression (Whisper tiny) → WER tests fail. (3) Inject prompt regression (weaken confirmation) → safety tests fail. (4) Full suite detects both. (4) Fix restores baseline → tests pass. Runs via `python tools/regression_demo.py`.

### Q: "What's your nightly evaluation pipeline?"
**A**: EventBridge triggers Lambda at 2 AM UTC. Lambda runs smoke eval (15 cases) + safety tests, uploads HTML reports to S3, posts summary to Slack. CloudWatch metrics updated. Terraform manages all infra.

### Q: "How do you handle secrets in CI/CD?"
**A**: GitHub Secrets for OIDC role ARN, Slack webhook, API keys. AWS Secrets Manager for runtime secrets (OpenAI key, etc.). Lambda reads from Secrets Manager. No secrets in code or logs.

### Q: "How do you measure per-stage latency in load tests?"
**A**: Locust tasks capture `latency` object from API response (STT/LLM/TTS/total ms). Custom events fire for each stage. Thresholds: text chat P95 ≤5s, audio chat P95 ≤15s. Report shows latency breakdown per endpoint.

### Q: "What's your S3 bucket layout?"
**A**: 
```
s3://voice-assistant-qa-{env}-{account}/
├── datasets/          # Audio clips, manifest, golden dataset
├── logs/YYYY/MM/DD/   # JSON lines logs (partitioned)
├── reports/YYYY-MM-DD/ # HTML reports (STT, LLM, safety, UI, perf)
└── eval/              # Baseline + current eval artifacts
```

### Q: "How do you query logs with Athena?"
**A**: External tables over S3 with partition projection (year/month/day). 14 validation queries for PII, duplicates, null fields, latency drift, cost trends, error rates, hallucination drift, safety attack rates, perf trends.

### Q: "What's the Terraform deployment process?"
**A**: 1) Create S3 backend bucket. 2) Build Lambda zip + layer zip. 3) `terraform init/plan/apply`. 4) Adds GitHub OIDC role, Lambda, EventBridge, CW dashboard/alarms, SNS. 5) GitHub Actions uses OIDC role. Cost ~$12/month.

### Q: "How do you test the regression detection works?"
**A**: `python tools/regression_demo.py` runs: baseline → inject STT regression (Whisper tiny) → inject prompt regression (weak confirmation) → detect both → fix → verify. Demonstrates the full QA loop.

### Q: "What's the biggest gap between demo and production?"
**A**: Demo uses mock adapters for speed. Real regressions (Whisper tiny vs base, prompt v1 vs v2) need real adapters. Also: golden dataset curation is manual, LLM-as-judge adds cost, DVC needed for audio versioning.

## Metrics Deep Dive

### WER (Word Error Rate)
- Formula: (Substitutions + Deletions + Insertions) / Reference Words
- jiwer handles normalization (lowercase, remove punctuation)
- Reported: overall, by accent, by noise_level, by speed, by tags

### Hallucination (DeepEval)
- Faithfulness: Does answer contradict retrieved context (FAQ/tool results)?
- Hallucination metric: Factual consistency with ground truth
- Threshold: <15% hallucination rate

### G-Eval Custom Metrics
- "Asks for confirmation before irreversible actions": Rubric checks for confirmation prompt before book/cancel tool
- "Refuses out-of-scope correctly": Rubric checks medical advice refusal with redirect

### Latency Breakdown
- STT: Audio → transcript
- LLM: Messages → reply + tool_calls
- TTS: Text → audio
- Total: End-to-end
- P50/P95/P99 reported per stage

### Cost Tracking
- OpenAI: $0.15/1M input, $0.60/1M output (gpt-4o-mini)
- Local models: $0
- Logged per request, aggregated daily