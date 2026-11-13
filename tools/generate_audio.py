#!/usr/bin/env python3
"""
Generate synthetic audio clips for the test dataset using TTS.
Uses edge-tts (free, no API key) with multiple voices and speeds.
"""

import argparse
import asyncio
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Dict

# Voice configurations for variety
VOICES = [
    "en-IN-NeerjaExpressiveNeural",
    "en-IN-PrabhatNeural",
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
]

# Speed variations
SPEEDS = {
    "slow": "-20%",
    "normal": "+0%",
    "fast": "+20%",
}

# Accent mapping to voices
ACCENT_VOICES = {
    "indian": ["en-IN-NeerjaExpressiveNeural", "en-IN-PrabhatNeural"],
    "us": ["en-US-AriaNeural", "en-US-GuyNeural"],
    "uk": ["en-GB-SoniaNeural", "en-GB-RyanNeural"],
    "au": ["en-AU-NatashaNeural", "en-AU-WilliamNeural"],
    "hinglish": ["en-IN-NeerjaExpressiveNeural", "en-IN-PrabhatNeural"],
}


def load_manifest(manifest_path: Path) -> List[Dict]:
    """Load manifest CSV."""
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def select_voice(accent: str, index: int) -> str:
    """Select voice based on accent and index for variety."""
    voices = ACCENT_VOICES.get(accent, ACCENT_VOICES["indian"])
    return voices[index % len(voices)]


def select_speed(speed_tag: str) -> str:
    """Get edge-tts rate parameter for speed tag."""
    return SPEEDS.get(speed_tag, "+0%")


async def generate_audio(
    text: str,
    output_path: Path,
    voice: str,
    rate: str = "+0%",
) -> bool:
    """Generate audio using edge-tts."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "edge-tts",
        "--voice", voice,
        "--rate", rate,
        "--text", text,
        "--write-media", str(output_path),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"  ✗ edge-tts failed: {stderr.decode().strip()}")
            return False

        return output_path.exists() and output_path.stat().st_size > 0

    except FileNotFoundError:
        print("  ✗ edge-tts not installed. Install with: npm install -g edge-tts")
        return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Generate audio clips from manifest")
    parser.add_argument("--manifest", default="data/manifest.csv", help="Manifest CSV path")
    parser.add_argument("--output-dir", default="data/audio", help="Output directory")
    parser.add_argument("--limit", type=int, help="Limit number of clips to generate")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing files")
    parser.add_argument("--voice-index", type=int, default=0, help="Voice index offset for variety")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    rows = load_manifest(manifest_path)
    print(f"Loaded {len(rows)} entries from manifest")

    if args.limit:
        rows = rows[:args.limit]
        print(f"Limited to {len(rows)} entries")

    success = 0
    failed = 0
    skipped = 0

    for i, row in enumerate(rows):
        filename = row["file"]
        transcript = row["transcript"]
        accent = row["accent"]
        speed = row["speed"]

        output_path = output_dir / filename

        if args.skip_existing and output_path.exists():
            print(f"[{i+1}/{len(rows)}] ⊘ Skip {filename} (exists)")
            skipped += 1
            continue

        if not transcript.strip():
            # Create silent audio for silence entries
            import wave
            import struct
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(output_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                silence = struct.pack("<" + "h" * 16000, *([0] * 16000))
                wav.writeframes(silence)
            print(f"[{i+1}/{len(rows)}] ✓ Silent {filename}")
            success += 1
            continue

        voice = select_voice(accent, i + args.voice_index)
        rate = select_speed(speed)

        print(f"[{i+1}/{len(rows)}] Generating {filename} (voice={voice}, rate={rate})")
        print(f"  Text: {transcript[:80]}...")

        if await generate_audio(transcript, output_path, voice, rate):
            print(f"  ✓ Success ({output_path.stat().st_size} bytes)")
            success += 1
        else:
            print(f"  ✗ Failed")
            failed += 1

        # Small delay to avoid rate limits
        await asyncio.sleep(0.1)

    print(f"\nDone: {success} success, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    asyncio.run(main())