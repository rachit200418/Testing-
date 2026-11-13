#!/usr/bin/env python3
"""
Add a failed production case as a new dataset entry.
Prompts for details and appends to manifest.csv, copies audio to data/audio/.
"""

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any


MANIFEST_PATH = Path("data/manifest.csv")
AUDIO_DIR = Path("data/audio")

VALID_INTENTS = [
    "book_appointment", "cancel_appointment", "reschedule_appointment",
    "check_availability", "faq", "out_of_scope", "prompt_injection",
    "greeting", "goodbye"
]

VALID_ACCENTS = ["indian", "us", "uk", "au", "hinglish"]
VALID_NOISE_LEVELS = ["clean", "low_noise", "medium_noise", "high_noise", "very_high_noise", "silence", "tv", "traffic", "babble"]
VALID_SPEEDS = ["slow", "normal", "fast"]
VALID_SOURCES = ["synthetic", "real"]


def load_manifest() -> list[Dict[str, Any]]:
    """Load existing manifest."""
    rows = []
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
    return rows


def save_manifest(rows: list[Dict[str, Any]]):
    """Save manifest with all rows."""
    fieldnames = [
        "file", "transcript", "intent", "slots_json",
        "accent", "noise_level", "speed", "source", "tags"
    ]
    with open(MANIFEST_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def prompt_with_default(prompt: str, default: str = "") -> str:
    """Prompt user with default value."""
    if default:
        result = input(f"{prompt} [{default}]: ").strip()
        return result if result else default
    else:
        return input(f"{prompt}: ").strip()


def prompt_choice(prompt: str, choices: list[str], default: str = "") -> str:
    """Prompt user to choose from list."""
    print(f"{prompt}:")
    for i, choice in enumerate(choices, 1):
        marker = " (default)" if choice == default else ""
        print(f"  {i}. {choice}{marker}")

    while True:
        result = input(f"Choose [1-{len(choices)}]: ").strip()
        if not result and default:
            return default
        try:
            idx = int(result) - 1
            if 0 <= idx < len(choices):
                return choices[idx]
        except ValueError:
            pass
        print("Invalid choice, try again.")


def prompt_json(prompt: str, default: str = "{}") -> str:
    """Prompt for JSON input with validation."""
    while True:
        result = input(f"{prompt} [{default}]: ").strip()
        if not result:
            result = default
        try:
            json.loads(result)
            return result
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}. Try again.")


def generate_filename(intent: str, source: str, tags: str) -> str:
    """Generate a unique filename."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    tag_part = tags.split(",")[0] if tags else "case"
    # Sanitize
    tag_part = "".join(c for c in tag_part if c.isalnum() or c in "_-")
    return f"{intent}_{source}_{tag_part}_{timestamp}.wav"


def main():
    parser = argparse.ArgumentParser(description="Add failed production case to dataset")
    parser.add_argument("--audio-file", help="Path to audio file (will be copied)")
    parser.add_argument("--transcript", help="Transcript text")
    parser.add_argument("--intent", help="Intent label")
    parser.add_argument("--slots", help="Slots JSON")
    parser.add_argument("--accent", help="Accent")
    parser.add_argument("--noise-level", help="Noise level")
    parser.add_argument("--speed", help="Speech speed")
    parser.add_argument("--source", help="Source (synthetic/real)")
    parser.add_argument("--tags", help="Comma-separated tags")
    parser.add_argument("--interactive", action="store_true", default=True, help="Interactive mode")
    args = parser.parse_args()

    print("=== Add Failed Production Case ===\n")

    # Load existing manifest to check duplicates
    existing_rows = load_manifest()
    existing_files = {r["file"] for r in existing_rows}

    # Collect data
    if args.audio_file:
        audio_path = Path(args.audio_file)
        if not audio_path.exists():
            print(f"Audio file not found: {audio_path}")
            sys.exit(1)
        filename = audio_path.name
    else:
        # Will generate filename later
        filename = None
        audio_path = None

    if args.transcript:
        transcript = args.transcript
    else:
        transcript = prompt_with_default("Transcript (what was said)")

    if args.intent:
        intent = args.intent
    else:
        intent = prompt_choice("Intent", VALID_INTENTS, "out_of_scope")

    if args.slots:
        slots_json = args.slots
    else:
        slots_json = prompt_json("Slots JSON", "{}")

    if args.accent:
        accent = args.accent
    else:
        accent = prompt_choice("Accent", VALID_ACCENTS, "indian")

    if args.noise_level:
        noise_level = args.noise_level
    else:
        noise_level = prompt_choice("Noise level", VALID_NOISE_LEVELS, "clean")

    if args.speed:
        speed = args.speed
    else:
        speed = prompt_choice("Speed", VALID_SPEEDS, "normal")

    if args.source:
        source = args.source
    else:
        source = prompt_choice("Source", VALID_SOURCES, "real")

    if args.tags:
        tags = args.tags
    else:
        tags = prompt_with_default("Tags (comma-separated)", "production,failure")

    # Generate filename if not provided
    if not filename:
        filename = generate_filename(intent, source, tags)

    # Check duplicate
    if filename in existing_files:
        print(f"File {filename} already exists in manifest!")
        overwrite = input("Overwrite? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Aborted.")
            sys.exit(1)

    # Copy audio file if provided
    if audio_path:
        dest_path = AUDIO_DIR / filename
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(audio_path, dest_path)
        print(f"Copied audio to {dest_path}")
    else:
        print(f"Note: No audio file provided. You'll need to add {filename} manually to {AUDIO_DIR}")

    # Create new row
    new_row = {
        "file": filename,
        "transcript": transcript,
        "intent": intent,
        "slots_json": slots_json,
        "accent": accent,
        "noise_level": noise_level,
        "speed": speed,
        "source": source,
        "tags": tags,
    }

    # Append to manifest
    existing_rows.append(new_row)
    save_manifest(existing_rows)

    print(f"\n✅ Added to manifest: {filename}")
    print(f"   Transcript: {transcript[:80]}...")
    print(f"   Intent: {intent}")
    print(f"   Tags: {tags}")

    # Show the row
    print("\nManifest entry:")
    for k, v in new_row.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()