"""STT Quality Tests - WER and CER with jiwer."""

import csv
import json
from pathlib import Path
from typing import Dict, List

import jiwer
import pytest

from app.adapters.factory import create_stt_adapter
from app.config import get_settings


def load_manifest(manifest_path: Path) -> List[Dict]:
    """Load manifest CSV."""
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def normalize_text(text: str) -> str:
    """Normalize text for WER calculation."""
    # jiwer's default transformation
    transformation = jiwer.Compose([
        jiwer.ToLowerCase(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.RemovePunctuation(),
        jiwer.ExpandCommonEnglishContractions(),
    ])
    return transformation(text)


def compute_wer_cer(reference: str, hypothesis: str) -> tuple[float, float]:
    """Compute WER and CER."""
    ref_norm = normalize_text(reference)
    hyp_norm = normalize_text(hypothesis)

    if not ref_norm:
        return 1.0, 1.0 if hyp_norm else 0.0

    wer = jiwer.wer(ref_norm, hyp_norm)
    cer = jiwer.cer(ref_norm, hyp_norm)

    return wer, cer


class TestSTTQuality:
    """STT quality tests using manifest ground truth."""

    @pytest.fixture(scope="class")
    def stt_adapter(self):
        """Create STT adapter for testing."""
        return create_stt_adapter()

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

    def test_wer_overall(self, stt_adapter, manifest_rows, audio_dir):
        """Test overall WER across all samples."""
        settings = get_settings()
        threshold = settings.wer_threshold_clean  # Default to clean threshold

        results = []
        for row in manifest_rows:
            if row["noise_level"] == "silence":
                continue  # Skip silence

            audio_path = audio_dir / row["file"]
            if not audio_path.exists():
                pytest.skip(f"Audio file not found: {audio_path}")

            reference = row["transcript"]
            if not reference.strip():
                continue  # Skip empty transcripts

            # Transcribe
            import asyncio
            result = asyncio.run(stt_adapter.transcribe(str(audio_path)))
            hypothesis = result.transcript

            wer, cer = compute_wer_cer(reference, hypothesis)
            results.append({
                "file": row["file"],
                "reference": reference,
                "hypothesis": hypothesis,
                "wer": wer,
                "cer": cer,
                "noise_level": row["noise_level"],
                "accent": row["accent"],
                "speed": row["speed"],
            })

        # Overall WER
        overall_wer = sum(r["wer"] for r in results) / len(results) if results else 0
        overall_cer = sum(r["cer"] for r in results) / len(results) if results else 0

        print(f"\nOverall WER: {overall_wer:.2%}")
        print(f"Overall CER: {overall_cer:.2%}")
        print(f"Samples tested: {len(results)}")

        # Save detailed results
        report_dir = Path("reports/stt")
        report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_dir / "wer_detailed.json", "w") as f:
            json.dump(results, f, indent=2)

        # Assert threshold (using clean threshold as baseline)
        assert overall_wer <= threshold, f"Overall WER {overall_wer:.2%} exceeds threshold {threshold:.0%}"

    @pytest.mark.parametrize("noise_level", ["clean", "low_noise", "medium_noise", "high_noise"])
    def test_wer_by_noise_level(self, stt_adapter, manifest_rows, audio_dir, noise_level):
        """Test WER sliced by noise level."""
        settings = get_settings()
        threshold = settings.wer_threshold_clean if noise_level == "clean" else settings.wer_threshold_noisy

        results = []
        for row in manifest_rows:
            if row["noise_level"] != noise_level:
                continue
            if row["noise_level"] == "silence":
                continue

            audio_path = audio_dir / row["file"]
            if not audio_path.exists():
                continue

            reference = row["transcript"]
            if not reference.strip():
                continue

            import asyncio
            result = asyncio.run(stt_adapter.transcribe(str(audio_path)))
            hypothesis = result.transcript

            wer, cer = compute_wer_cer(reference, hypothesis)
            results.append({"wer": wer, "cer": cer})

        if not results:
            pytest.skip(f"No samples for noise level: {noise_level}")

        avg_wer = sum(r["wer"] for r in results) / len(results)
        avg_cer = sum(r["cer"] for r in results) / len(results)

        print(f"\n{noise_level}: WER={avg_wer:.2%}, CER={avg_cer:.2%}, n={len(results)}")

        assert avg_wer <= threshold, f"{noise_level} WER {avg_wer:.2%} exceeds threshold {threshold:.0%}"

    @pytest.mark.parametrize("accent", ["indian", "us", "uk", "au", "hinglish"])
    def test_wer_by_accent(self, stt_adapter, manifest_rows, audio_dir, accent):
        """Test WER sliced by accent."""
        results = []
        for row in manifest_rows:
            if row["accent"] != accent:
                continue
            if row["noise_level"] == "silence":
                continue

            audio_path = audio_dir / row["file"]
            if not audio_path.exists():
                continue

            reference = row["transcript"]
            if not reference.strip():
                continue

            import asyncio
            result = asyncio.run(stt_adapter.transcribe(str(audio_path)))
            hypothesis = result.transcript

            wer, cer = compute_wer_cer(reference, hypothesis)
            results.append({"wer": wer, "cer": cer})

        if not results:
            pytest.skip(f"No samples for accent: {accent}")

        avg_wer = sum(r["wer"] for r in results) / len(results)
        avg_cer = sum(r["cer"] for r in results) / len(results)

        print(f"\n{accent}: WER={avg_wer:.2%}, CER={avg_cer:.2%}, n={len(results)}")

        # Report but don't fail on accent-specific thresholds (informational)
        # Could add accent-specific thresholds in config later

    @pytest.mark.parametrize("speed", ["slow", "normal", "fast"])
    def test_wer_by_speed(self, stt_adapter, manifest_rows, audio_dir, speed):
        """Test WER sliced by speech speed."""
        results = []
        for row in manifest_rows:
            if row["speed"] != speed:
                continue
            if row["noise_level"] == "silence":
                continue

            audio_path = audio_dir / row["file"]
            if not audio_path.exists():
                continue

            reference = row["transcript"]
            if not reference.strip():
                continue

            import asyncio
            result = asyncio.run(stt_adapter.transcribe(str(audio_path)))
            hypothesis = result.transcript

            wer, cer = compute_wer_cer(reference, hypothesis)
            results.append({"wer": wer, "cer": cer})

        if not results:
            pytest.skip(f"No samples for speed: {speed}")

        avg_wer = sum(r["wer"] for r in results) / len(results)
        avg_cer = sum(r["cer"] for r in results) / len(results)

        print(f"\n{speed}: WER={avg_wer:.2%}, CER={avg_cer:.2%}, n={len(results)}")

    def test_wer_by_tags(self, stt_adapter, manifest_rows, audio_dir):
        """Test WER sliced by tags."""
        # Collect all unique tags
        all_tags = set()
        for row in manifest_rows:
            tags = row.get("tags", "").split(",")
            all_tags.update(t.strip() for t in tags if t.strip())

        tag_results = {}
        for tag in sorted(all_tags):
            results = []
            for row in manifest_rows:
                if tag not in row.get("tags", ""):
                    continue
                if row["noise_level"] == "silence":
                    continue

                audio_path = audio_dir / row["file"]
                if not audio_path.exists():
                    continue

                reference = row["transcript"]
                if not reference.strip():
                    continue

                import asyncio
                result = asyncio.run(stt_adapter.transcribe(str(audio_path)))
                hypothesis = result.transcript

                wer, cer = compute_wer_cer(reference, hypothesis)
                results.append({"wer": wer, "cer": cer})

            if results:
                avg_wer = sum(r["wer"] for r in results) / len(results)
                avg_cer = sum(r["cer"] for r in results) / len(results)
                tag_results[tag] = {"wer": avg_wer, "cer": avg_cer, "n": len(results)}
                print(f"\nTag '{tag}': WER={avg_wer:.2%}, CER={avg_cer:.2%}, n={len(results)}")

        # Save tag breakdown
        report_dir = Path("reports/stt")
        report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_dir / "wer_by_tag.json", "w") as f:
            json.dump(tag_results, f, indent=2)


class TestSTTMock:
    """Tests using mock STT for deterministic validation."""

    @pytest.fixture
    def mock_stt(self):
        from app.adapters.mock import MockSTT
        return MockSTT()

    def test_mock_stt_deterministic(self, mock_stt):
        """Mock STT should return consistent transcripts."""
        import asyncio

        # Test known files
        test_cases = [
            ("book_appointment_clean.wav", "I want to book an appointment for tomorrow at 3 PM"),
            ("cancel_booking.wav", "Cancel my appointment for Friday at 2 PM"),
            ("faq_timings.wav", "What are your clinic timings?"),
        ]

        for filename, expected in test_cases:
            result = asyncio.run(mock_stt.transcribe(f"data/audio/{filename}"))
            # Mock returns exact transcript from lookup
            assert result.transcript == expected, f"Mock STT mismatch for {filename}"

    def test_mock_stt_unknown_file(self, mock_stt):
        """Mock STT returns default for unknown files."""
        import asyncio
        result = asyncio.run(mock_stt.transcribe("data/audio/unknown_file.wav"))
        assert "mock transcription" in result.transcript.lower()