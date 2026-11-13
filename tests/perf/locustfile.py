"""
Locust Performance Tests for Voice Assistant QA Platform.

Tests /text/chat and /audio/chat endpoints with per-stage latency breakdown.
"""

import random
import time
from pathlib import Path

from locust import HttpUser, task, between, events
from locust.env import Environment
from locust.stats import stats_printer, stats_history


# Test audio file for audio chat tests
AUDIO_FILES = [
    "data/audio/book_appointment_clean.wav",
    "data/audio/cancel_booking.wav",
    "data/audio/check_availability.wav",
    "data/audio/faq_timings.wav",
]


class VoiceAssistantUser(HttpUser):
    """Simulated user for voice assistant load testing."""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session_id = None
        self.api_key = "test-api-key"
        self.headers = {"X-API-Key": self.api_key}
    
    def on_start(self):
        """Initialize session on start."""
        self.session_id = f"load_test_{random.randint(10000, 99999)}_{int(time.time())}"
    
    @task(3)
    def text_chat(self):
        """Test /text/chat endpoint."""
        test_messages = [
            "Hello, I need help",
            "Book appointment for John tomorrow at 3 PM",
            "What are the clinic hours?",
            "Cancel my appointment",
            "What slots are available on Monday?",
            "How much is the consultation fee?",
            "Do you accept insurance?",
            "Where is the clinic located?",
        ]
        
        message = random.choice(test_messages)
        
        with self.client.post(
            "/text/chat",
            json={"text": message, "session_id": self.session_id},
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Track per-stage latency
                latency = data.get("latency", {})
                total_ms = latency.get("total_ms", 0)
                llm_ms = latency.get("llm_ms", 0)
                
                # Custom metrics
                response.meta["latency_total"] = total_ms
                response.meta["latency_llm"] = llm_ms
                
                if total_ms > 5000:
                    response.failure(f"High latency: {total_ms}ms")
            else:
                response.failure(f"Status {response.status_code}: {response.text}")
    
    @task(1)
    def audio_chat(self):
        """Test /audio/chat endpoint with audio file."""
        # Pick random audio file
        audio_file = random.choice(AUDIO_FILES)
        audio_path = Path(audio_file)
        
        if not audio_path.exists():
            return  # Skip if file doesn't exist
        
        with open(audio_path, "rb") as f:
            files = {"audio_file": (audio_path.name, f, "audio/wav")}
            data = {"session_id": self.session_id}
            
            with self.client.post(
                "/audio/chat",
                files=files,
                data=data,
                headers=self.headers,
                catch_response=True,
            ) as response:
                if response.status_code == 200:
                    resp_data = response.json()
                    latency = resp_data.get("latency", {})
                    total_ms = latency.get("total_ms", 0)
                    stt_ms = latency.get("stt_ms", 0)
                    llm_ms = latency.get("llm_ms", 0)
                    tts_ms = latency.get("tts_ms", 0)
                    
                    response.meta["latency_total"] = total_ms
                    response.meta["latency_stt"] = stt_ms
                    response.meta["latency_llm"] = llm_ms
                    response.meta["latency_tts"] = tts_ms
                    
                    if total_ms > 10000:
                        response.failure(f"High audio latency: {total_ms}ms")
                else:
                    response.failure(f"Status {response.status_code}: {response.text}")
    
    @task(1)
    def check_slots(self):
        """Test /slots endpoint."""
        dates = ["2024-01-15", "2024-01-16", "2024-01-17", "2024-01-18", "2024-01-19"]
        date = random.choice(dates)
        
        with self.client.get(
            f"/slots?date={date}",
            headers=self.headers,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"Status {response.status_code}")
    
    @task(1)
    def health_check(self):
        """Test /health endpoint (no auth)."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code != 200:
                response.failure(f"Health check failed: {response.status_code}")


class FastVoiceAssistantUser(VoiceAssistantUser):
    """High-frequency user for stress testing."""
    wait_time = between(0.1, 0.5)


# Custom metrics collection
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, **kwargs):
    """Track custom metrics per endpoint."""
    if hasattr(response, "meta"):
        meta = response.meta
        if "latency_total" in meta:
            # Fire custom event for latency tracking
            events.request.fire(
                request_type="CUSTOM",
                name=f"{name}_total_latency",
                response_time=meta["latency_total"],
                response_length=0,
                context=context,
            )
        if "latency_stt" in meta:
            events.request.fire(
                request_type="CUSTOM",
                name=f"{name}_stt_latency",
                response_time=meta["latency_stt"],
                response_length=0,
                context=context,
            )
        if "latency_llm" in meta:
            events.request.fire(
                request_type="CUSTOM",
                name=f"{name}_llm_latency",
                response_time=meta["latency_llm"],
                response_length=0,
                context=context,
            )
        if "latency_tts" in meta:
            events.request.fire(
                request_type="CUSTOM",
                name=f"{name}_tts_latency",
                response_time=meta["latency_tts"],
                response_length=0,
                context=context,
            )


# Thresholds for pass/fail
THRESHOLDS = {
    "text_chat": {
        "p50": 2000,
        "p95": 5000,
        "p99": 10000,
        "error_rate": 0.05,
    },
    "audio_chat": {
        "p50": 5000,
        "p95": 15000,
        "p99": 30000,
        "error_rate": 0.10,
    },
    "health_check": {
        "p50": 100,
        "p95": 500,
        "error_rate": 0.01,
    },
}


@events.test_stop.add_listener
def on_test_stop(environment: Environment, **kwargs):
    """Print summary and check thresholds at test end."""
    print("\n=== PERFORMANCE TEST SUMMARY ===")
    
    for name, entry in environment.stats.entries.items():
        if entry.num_requests == 0:
            continue
        
        method, path = name.split(" ", 1) if " " in name else ("UNKNOWN", name)
        
        print(f"\n{method} {path}:")
        print(f"  Requests: {entry.num_requests}")
        print(f"  Failures: {entry.num_failures} ({entry.error_rate:.2%})")
        print(f"  Avg: {entry.avg_response_time:.0f}ms")
        print(f"  P50: {entry.get_response_time_percentile(0.5):.0f}ms")
        print(f"  P95: {entry.get_response_time_percentile(0.95):.0f}ms")
        print(f"  P99: {entry.get_response_time_percentile(0.99):.0f}ms")
        print(f"  Min: {entry.min_response_time:.0f}ms")
        print(f"  Max: {entry.max_response_time:.0f}ms")
        
        # Check thresholds
        if "text" in path and "chat" in path:
            thresh = THRESHOLDS["text_chat"]
        elif "audio" in path and "chat" in path:
            thresh = THRESHOLDS["audio_chat"]
        elif "health" in path:
            thresh = THRESHOLDS["health_check"]
        else:
            thresh = None
        
        if thresh:
            p95 = entry.get_response_time_percentile(0.95)
            if p95 > thresh["p95"]:
                print(f"  ⚠️  P95 ({p95:.0f}ms) exceeds threshold ({thresh['p95']}ms)")
            if entry.error_rate > thresh["error_rate"]:
                print(f"  ⚠️  Error rate ({entry.error_rate:.2%}) exceeds threshold ({thresh['error_rate']:.2%})")


# Standalone runner for CI
if __name__ == "__main__":
    import sys
    import os
    
    # Run with: locust -f tests/perf/locustfile.py --headless -u 10 -r 2 -t 60s --host http://localhost:8000
    pass