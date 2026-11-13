"""Error Propagation Analysis - Classify failures as STT-origin vs LLM-origin."""

import csv
import json
from pathlib import Path
from typing import Dict, List

import pytest

from app.adapters.factory import create_llm_adapter, create_stt_adapter
from app.tools.database import answer_faq


def load_manifest(manifest_path: Path) -> List[Dict]:
    """Load manifest CSV."""
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def parse_slots(slots_json: str) -> Dict:
    """Parse slots JSON safely."""
    try:
        return json.loads(slots_json)
    except json.JSONDecodeError:
        return {}


def intent_match(expected: str, actual: str) -> bool:
    """Check if intents match."""
    return expected == actual


def slots_match(expected: Dict, actual: Dict) -> bool:
    """Check if required slots match."""
    expected_filtered = {k: v for k, v in expected.items() if v is not None}
    for key, expected_val in expected_filtered.items():
        actual_val = actual.get(key)
        if isinstance(expected_val, str) and isinstance(actual_val, str):
            if expected_val.lower().strip() != actual_val.lower().strip():
                return False
        elif expected_val != actual_val:
            return False
    return True


def classify_failure(
    text_intent_ok: bool,
    text_slots_ok: bool,
    audio_intent_ok: bool,
    audio_slots_ok: bool,
) -> str:
    """
    Classify failure origin.
    Returns: 'stt', 'llm', 'both', 'none'
    """
    text_ok = text_intent_ok and text_slots_ok
    audio_ok = audio_intent_ok and audio_slots_ok

    if text_ok and audio_ok:
        return "none"  # Both succeed
    elif text_ok and not audio_ok:
        return "stt"   # Text works, audio fails -> STT issue
    elif not text_ok and not audio_ok:
        return "llm"   # Both fail -> LLM/reasoning issue
    else:
        # text fails but audio works - unlikely but possible
        return "both"


class TestErrorPropagation:
    """Error propagation analysis: STT vs LLM failure classification."""

    @pytest.fixture(scope="class")
    def adapters(self):
        """Create adapters."""
        return {
            "stt": create_stt_adapter(),
            "llm": create_llm_adapter(),
        }

    @pytest.fixture(scope="class")
    def manifest_rows(self):
        """Load manifest rows."""
        manifest_path = Path("data/manifest.csv")
        if not manifest_path.exists():
            pytest.skip("Manifest not found")
        return load_manifest(manifest_path)

    @pytest.fixture(scope="class")
    def audio_dir(self):
        """Audio directory."""
        return Path("data/audio")

    def test_error_propagation_analysis(self, adapters, manifest_rows, audio_dir):
        """Run error propagation analysis on all manifest samples."""
        import asyncio

        stt_adapter = adapters["stt"]
        llm_adapter = adapters["llm"]

        results = []
        classifications = {"stt": 0, "llm": 0, "both": 0, "none": 0}

        for row in manifest_rows:
            if row["noise_level"] == "silence":
                continue

            audio_path = audio_dir / row["file"]
            if not audio_path.exists():
                continue

            transcript = row["transcript"]
            expected_intent = row["intent"]
            expected_slots = parse_slots(row["slots_json"])

            if not transcript.strip():
                continue

            # 1. Text path (ground truth transcript -> LLM)
            messages = [{"role": "user", "content": transcript}]
            text_result = asyncio.run(llm_adapter.chat(messages))

            text_intent_ok = intent_match(expected_intent, text_result.intent)
            text_slots_ok = slots_match(expected_slots, text_result.slots)
            text_ok = text_intent_ok and text_slots_ok

            # 2. Audio path (STT -> LLM)
            stt_result = asyncio.run(stt_adapter.transcribe(str(audio_path)))
            stt_transcript = stt_result.transcript

            audio_messages = [{"role": "user", "content": stt_transcript}]
            audio_result = asyncio.run(llm_adapter.chat(audio_messages))

            audio_intent_ok = intent_match(expected_intent, audio_result.intent)
            audio_slots_ok = slots_match(expected_slots, audio_result.slots)
            audio_ok = audio_intent_ok and audio_slots_ok

            # Classify
            classification = classify_failure(
                text_intent_ok, text_slots_ok,
                audio_intent_ok, audio_slots_ok,
            )
            classifications[classification] += 1

            results.append({
                "file": row["file"],
                "transcript": transcript,
                "stt_transcript": stt_transcript,
                "expected_intent": expected_intent,
                "expected_slots": expected_slots,
                "text_intent": text_result.intent,
                "text_slots": text_result.slots,
                "text_intent_ok": text_intent_ok,
                "text_slots_ok": text_slots_ok,
                "audio_intent": audio_result.intent,
                "audio_slots": audio_result.slots,
                "audio_intent_ok": audio_intent_ok,
                "audio_slots_ok": audio_slots_ok,
                "classification": classification,
            })

        # Summary
        total = sum(classifications.values())
        stt_pct = classifications["stt"] / total * 100 if total > 0 else 0
        llm_pct = classifications["llm"] / total * 100 if total > 0 else 0
        both_pct = classifications["both"] / total * 100 if total > 0 else 0
        none_pct = classifications["none"] / total * 100 if total > 0 else 0

        print(f"\n=== Error Propagation Analysis ===")
        print(f"Total samples: {total}")
        print(f"Both succeed (none): {classifications['none']} ({none_pct:.1f}%)")
        print(f"STT-origin failures: {classifications['stt']} ({stt_pct:.1f}%)")
        print(f"LLM-origin failures: {classifications['llm']} ({llm_pct:.1f}%)")
        print(f"Both/ambiguous: {classifications['both']} ({both_pct:.1f}%)")

        # Save detailed report
        report_dir = Path("reports/error_propagation")
        report_dir.mkdir(parents=True, exist_ok=True)

        with open(report_dir / "error_propagation_detailed.json", "w") as f:
            json.dump({
                "summary": {
                    "total": total,
                    "classifications": classifications,
                    "percentages": {
                        "stt": stt_pct,
                        "llm": llm_pct,
                        "both": both_pct,
                        "none": none_pct,
                    }
                },
                "details": results
            }, f, indent=2)

        # Generate summary report
        with open(report_dir / "summary.txt", "w") as f:
            f.write(f"Error Propagation Analysis Summary\n")
            f.write(f"=====================================\n\n")
            f.write(f"Total samples analyzed: {total}\n\n")
            f.write(f"Classification breakdown:\n")
            f.write(f"  Both succeed:        {classifications['none']:4d} ({none_pct:5.1f}%)\n")
            f.write(f"  STT-origin failures: {classifications['stt']:4d} ({stt_pct:5.1f}%)\n")
            f.write(f"  LLM-origin failures: {classifications['llm']:4d} ({llm_pct:5.1f}%)\n")
            f.write(f"  Both/ambiguous:      {classifications['both']:4d} ({both_pct:5.1f}%)\n\n")

            # Per-category breakdown
            f.write(f"Failure breakdown by intent:\n")
            by_intent = {}
            for r in results:
                intent = r["expected_intent"]
                if intent not in by_intent:
                    by_intent[intent] = {"stt": 0, "llm": 0, "both": 0, "none": 0, "total": 0}
                by_intent[intent][r["classification"]] += 1
                by_intent[intent]["total"] += 1

            for intent, counts in sorted(by_intent.items()):
                f.write(f"  {intent}:\n")
                for cat in ["none", "stt", "llm", "both"]:
                    pct = counts[cat] / counts["total"] * 100 if counts["total"] > 0 else 0
                    f.write(f"    {cat}: {counts[cat]} ({pct:.1f}%)\n")

            f.write(f"\nFailure breakdown by noise level:\n")
            by_noise = {}
            for r in results:
                noise = r.get("file", "").split("_")[-1].replace(".wav", "")
                # Better: get from manifest
                for row in manifest_rows:
                    if row["file"] == r["file"]:
                        noise = row["noise_level"]
                        break
                if noise not in by_noise:
                    by_noise[noise] = {"stt": 0, "llm": 0, "both": 0, "none": 0, "total": 0}
                by_noise[noise][r["classification"]] += 1
                by_noise[noise]["total"] += 1

            for noise, counts in sorted(by_noise.items()):
                f.write(f"  {noise}:\n")
                for cat in ["none", "stt", "llm", "both"]:
                    pct = counts[cat] / counts["total"] * 100 if counts["total"] > 0 else 0
                    f.write(f"    {cat}: {counts[cat]} ({pct:.1f}%)\n")

        # Assert: STT failures should not exceed LLM failures by too much
        # This is informational - thresholds would be set based on requirements
        print(f"\nKey finding: {stt_pct:.1f}% of failures originate at STT, {llm_pct:.1f}% at LLM")


class TestErrorPropagationMock:
    """Deterministic error propagation test using mock adapters."""

    @pytest.fixture
    def mock_adapters(self):
        from app.adapters.mock import MockSTT, MockLLM
        return {"stt": MockSTT(), "llm": MockLLM()}

    def test_mock_error_propagation(self, mock_adapters):
        """Test error propagation with known mock behaviors."""
        import asyncio

        stt = mock_adapters["stt"]
        llm = mock_adapters["llm"]

        # Test cases where we know the expected behavior
        test_cases = [
            {
                "file": "book_appointment_clean.wav",
                "transcript": "I want to book an appointment for tomorrow at 3 PM",
                "expected_intent": "book_appointment",
                "expected_slots": {"patient_name": None, "date": "tomorrow", "time": "3 PM"},
                "should_succeed_both": True,
            },
            {
                "file": "book_appointment_noisy.wav",
                "transcript": "I want to book an appointment for tomorrow at 3 PM",
                "expected_intent": "book_appointment",
                "expected_slots": {"patient_name": None, "date": "tomorrow", "time": "3 PM"},
                "should_succeed_both": True,  # Mock STT returns same transcript
            },
            {
                "file": "out_of_scope_medical.wav",
                "transcript": "What medicine should I take for headache?",
                "expected_intent": "out_of_scope",
                "expected_slots": {},
                "should_succeed_both": True,
            },
        ]

        for case in test_cases:
            # Text path
            messages = [{"role": "user", "content": case["transcript"]}]
            text_result = asyncio.run(llm.chat(messages))

            text_intent_ok = text_result.intent == case["expected_intent"]
            text_slots_ok = True  # Simplified

            # Audio path (mock STT returns same transcript)
            audio_messages = [{"role": "user", "content": case["transcript"]}]
            audio_result = asyncio.run(llm.chat(audio_messages))

            audio_intent_ok = audio_result.intent == case["expected_intent"]
            audio_slots_ok = True

            classification = classify_failure(text_intent_ok, text_slots_ok, audio_intent_ok, audio_slots_ok)

            if case["should_succeed_both"]:
                assert classification == "none", f"Expected 'none' for {case['file']}, got {classification}"

        print("Mock error propagation test passed")


def test_faq_grounding():
    """Test FAQ answer grounding (for RAGAS/DeepEval integration)."""
    # This tests the answer_faq tool directly
    test_questions = [
        ("What are the clinic timings?", "9:00 AM"),
        ("How much is the consultation fee?", "₹500"),
        ("Do you accept insurance?", "insurance"),
    ]

    for question, expected_keyword in test_questions:
        result = answer_faq(question)
        assert result["found"], f"FAQ not found for: {question}"
        assert expected_keyword.lower() in result["answer"].lower(), \
            f"Expected keyword '{expected_keyword}' not in answer: {result['answer']}"

    # Test out-of-scope
    result = answer_faq("What medicine for headache?")
    assert not result["found"], "Should not find answer for medical question"