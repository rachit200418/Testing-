#!/usr/bin/env python3
"""
Baseline Evaluation Runner for Voice Assistant QA Platform.

Runs the golden dataset evaluation with current configuration and saves
results as baseline for regression comparison.

Usage:
    python tools/run_baseline.py --output reports/baseline
    python tools/run_baseline.py --output reports/baseline --stt faster-whisper --llm openai
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def run_baseline(output_dir: Path, stt_adapter: str = "mock", llm_adapter: str = "mock", tts_adapter: str = "mock"):
    """Run baseline evaluation."""

    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.update({
        "STT_ADAPTER": stt_adapter,
        "LLM_ADAPTER": llm_adapter,
        "TTS_ADAPTER": tts_adapter,
        "API_KEY": "test-api-key",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    })

    # Add API keys for real adapters
    if llm_adapter == "openai":
        env["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
    elif llm_adapter == "gemini":
        env["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY", "")

    # Test suites to run for baseline
    test_suites = [
        # LLM Evaluation (smoke)
        ["tests/llm_eval/test_deepeval.py::TestDeepEvalSmoke::test_smoke_relevancy"],
        # Safety
        ["tests/safety/test_safety.py::TestSafetyEndToEnd::test_medical_advice_refused"],
        ["tests/safety/test_safety.py::TestSafetyEndToEnd::test_prompt_injection_refused"],
        ["tests/safety/test_safety.py::TestSafetyEndToEnd::test_pii_masked_in_response"],
        ["tests/safety/test_safety.py::TestSafetyEndToEnd::test_confirmation_before_booking"],
        ["tests/safety/test_safety.py::TestSafetyEndToEnd::test_confirmation_before_cancellation"],
        # Multi-turn
        ["tests/multiturn/test_multiturn.py::TestToolExecution::test_tool_book_slot_args"],
        ["tests/multiturn/test_multiturn.py::TestToolExecution::test_tool_cancel_booking_args"],
        ["tests/multiturn/test_multiturn.py::TestToolExecution::test_confirmation_required"],
        # Intent/Slot
        ["tests/intent/test_intent_slot.py::TestIntentAccuracy::test_intent_accuracy_text"],
        ["tests/intent/test_intent_slot.py::TestSlotAccuracy::test_slot_accuracy_text"],
    ]

    all_results = {
        "timestamp": datetime.utcnow().isoformat(),
        "config": {
            "stt_adapter": stt_adapter,
            "llm_adapter": llm_adapter,
            "tts_adapter": tts_adapter,
        },
        "suites": [],
    }

    overall_passed = True

    for i, suite in enumerate(test_suites):
        suite_name = f"suite_{i}_{suite[0].split('::')[-1]}"
        print(f"\nRunning {suite_name}...")

        cmd = [
            sys.executable, "-m", "pytest",
            *suite,
            "-v", "--tb=short",
            f"--html={output_dir}/{suite_name}_report.html",
            "--self-contained-html",
            "--json-report", f"{output_dir}/{suite_name}_report.json",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        suite_result = {
            "name": suite_name,
            "tests": suite,
            "returncode": result.returncode,
            "passed": result.returncode == 0,
            "duration": 0,  # Could parse from output
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-5000:] if result.stderr else "",
        }

        all_results["suites"].append(suite_result)

        if result.returncode != 0:
            overall_passed = False
            print(f"  ❌ FAILED")
        else:
            print(f"  ✅ PASSED")

    # Save overall results
    all_results["overall_passed"] = overall_passed
    all_results["completed_at"] = datetime.utcnow().isoformat()

    results_file = output_dir / "baseline_results.json"
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)

    # Generate summary
    print(f"\n{'='*60}")
    print(f"BASELINE EVALUATION COMPLETE")
    print(f"{'='*60}")
    print(f"Overall: {'PASSED' if overall_passed else 'FAILED'}")
    print(f"Results saved to: {results_file}")
    print(f"Reports in: {output_dir}")

    for suite in all_results["suites"]:
        status = "✅" if suite["passed"] else "❌"
        print(f"  {status} {suite['name']}")

    return overall_passed


def main():
    parser = argparse.ArgumentParser(description="Run baseline evaluation")
    parser.add_argument("--output", default="reports/baseline", help="Output directory")
    parser.add_argument("--stt", default="mock", choices=["mock", "faster-whisper"], help="STT adapter")
    parser.add_argument("--llm", default="mock", choices=["mock", "openai", "gemini", "ollama"], help="LLM adapter")
    parser.add_argument("--tts", default="mock", choices=["mock", "edge-tts", "piper"], help="TTS adapter")
    args = parser.parse_args()

    output_dir = Path(args.output)
    success = run_baseline(output_dir, args.stt, args.llm, args.tts)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()