#!/usr/bin/env python3
"""
Validate the audio dataset manifest.
Checks: missing files, bad slots JSON, duplicates, schema compliance.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple


REQUIRED_COLUMNS = [
    "file", "transcript", "intent", "slots_json",
    "accent", "noise_level", "speed", "source", "tags"
]

VALID_INTENTS = [
    "book_appointment", "cancel_appointment", "reschedule_appointment",
    "check_availability", "faq", "out_of_scope", "prompt_injection",
    "greeting", "goodbye"
]

VALID_ACCENTS = ["indian", "us", "uk", "au", "hinglish"]
VALID_NOISE_LEVELS = ["clean", "low_noise", "medium_noise", "high_noise", "very_high_noise", "silence", "tv", "traffic", "babble"]
VALID_SPEEDS = ["slow", "normal", "fast"]
VALID_SOURCES = ["synthetic", "real"]


def load_manifest(manifest_path: Path) -> List[Dict]:
    """Load manifest CSV."""
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def validate_schema(rows: List[Dict]) -> Tuple[List[str], List[str]]:
    """Validate manifest schema."""
    errors = []
    warnings = []

    if not rows:
        errors.append("Manifest is empty")
        return errors, warnings

    # Check columns
    for i, row in enumerate(rows):
        for col in REQUIRED_COLUMNS:
            if col not in row:
                errors.append(f"Row {i+1}: Missing column '{col}'")

    return errors, warnings


def validate_intents(rows: List[Dict]) -> Tuple[List[str], List[str]]:
    """Validate intent values."""
    errors = []
    warnings = []

    for i, row in enumerate(rows):
        intent = row.get("intent", "").strip()
        if intent not in VALID_INTENTS:
            errors.append(f"Row {i+1}: Invalid intent '{intent}' (valid: {VALID_INTENTS})")

    return errors, warnings


def validate_slots_json(rows: List[Dict]) -> Tuple[List[str], List[str]]:
    """Validate slots_json is valid JSON."""
    errors = []
    warnings = []

    for i, row in enumerate(rows):
        slots_json = row.get("slots_json", "").strip()
        if not slots_json:
            errors.append(f"Row {i+1}: Empty slots_json")
            continue

        try:
            slots = json.loads(slots_json)
            if not isinstance(slots, dict):
                errors.append(f"Row {i+1}: slots_json must be a JSON object, got {type(slots).__name__}")
        except json.JSONDecodeError as e:
            errors.append(f"Row {i+1}: Invalid JSON in slots_json: {e}")

    return errors, warnings


def validate_categorical(rows: List[Dict]) -> Tuple[List[str], List[str]]:
    """Validate categorical columns."""
    errors = []
    warnings = []

    for i, row in enumerate(rows):
        accent = row.get("accent", "").strip().lower()
        if accent not in VALID_ACCENTS:
            warnings.append(f"Row {i+1}: Unknown accent '{accent}' (known: {VALID_ACCENTS})")

        noise = row.get("noise_level", "").strip().lower()
        if noise not in VALID_NOISE_LEVELS:
            warnings.append(f"Row {i+1}: Unknown noise_level '{noise}' (known: {VALID_NOISE_LEVELS})")

        speed = row.get("speed", "").strip().lower()
        if speed not in VALID_SPEEDS:
            warnings.append(f"Row {i+1}: Unknown speed '{speed}' (known: {VALID_SPEEDS})")

        source = row.get("source", "").strip().lower()
        if source not in VALID_SOURCES:
            errors.append(f"Row {i+1}: Invalid source '{source}' (valid: {VALID_SOURCES})")

    return errors, warnings


def validate_files(rows: List[Dict], audio_dir: Path) -> Tuple[List[str], List[str]]:
    """Check that audio files exist."""
    errors = []
    warnings = []

    for i, row in enumerate(rows):
        filename = row.get("file", "").strip()
        if not filename:
            errors.append(f"Row {i+1}: Empty file name")
            continue

        filepath = audio_dir / filename
        if not filepath.exists():
            errors.append(f"Row {i+1}: Missing audio file: {filepath}")
        elif filepath.stat().st_size == 0:
            warnings.append(f"Row {i+1}: Empty audio file: {filepath}")

    return errors, warnings


def validate_duplicates(rows: List[Dict]) -> Tuple[List[str], List[str]]:
    """Check for duplicate files."""
    errors = []
    warnings = []

    seen = {}
    for i, row in enumerate(rows):
        filename = row.get("file", "").strip()
        if filename in seen:
            errors.append(f"Row {i+1}: Duplicate file '{filename}' (first seen at row {seen[filename]+1})")
        else:
            seen[filename] = i

    return errors, warnings


def validate_coverage(rows: List[Dict]) -> Tuple[List[str], List[str]]:
    """Check dataset coverage across categories."""
    errors = []
    warnings = []

    intents = set(r["intent"] for r in rows)
    accents = set(r["accent"] for r in rows)
    noise_levels = set(r["noise_level"] for r in rows)
    speeds = set(r["speed"] for r in rows)
    sources = set(r["source"] for r in rows)

    # Check each intent has at least some samples
    for intent in VALID_INTENTS:
        if intent not in intents:
            warnings.append(f"Coverage: No samples for intent '{intent}'")

    # Check accent diversity
    if len(accents) < 3:
        warnings.append(f"Coverage: Only {len(accents)} accents ({accents}), consider more")

    # Check noise levels
    if "clean" not in noise_levels:
        warnings.append("Coverage: No clean samples")

    noisy_levels = [n for n in noise_levels if n != "clean" and n != "silence"]
    if len(noisy_levels) < 2:
        warnings.append(f"Coverage: Only {len(noisy_levels)} noise levels ({noisy_levels})")

    # Check speed diversity
    if "fast" not in speeds or "slow" not in speeds:
        warnings.append(f"Coverage: Missing speed variations (have: {speeds})")

    # Check real vs synthetic
    if "real" not in sources:
        warnings.append("Coverage: No real recordings (all synthetic)")

    return errors, warnings


def print_stats(rows: List[Dict]):
    """Print dataset statistics."""
    print("\n=== Dataset Statistics ===")
    print(f"Total samples: {len(rows)}")

    # By intent
    print("\nBy intent:")
    intent_counts = {}
    for r in rows:
        intent_counts[r["intent"]] = intent_counts.get(r["intent"], 0) + 1
    for intent, count in sorted(intent_counts.items()):
        print(f"  {intent}: {count}")

    # By accent
    print("\nBy accent:")
    accent_counts = {}
    for r in rows:
        accent_counts[r["accent"]] = accent_counts.get(r["accent"], 0) + 1
    for accent, count in sorted(accent_counts.items()):
        print(f"  {accent}: {count}")

    # By noise level
    print("\nBy noise level:")
    noise_counts = {}
    for r in rows:
        noise_counts[r["noise_level"]] = noise_counts.get(r["noise_level"], 0) + 1
    for noise, count in sorted(noise_counts.items()):
        print(f"  {noise}: {count}")

    # By speed
    print("\nBy speed:")
    speed_counts = {}
    for r in rows:
        speed_counts[r["speed"]] = speed_counts.get(r["speed"], 0) + 1
    for speed, count in sorted(speed_counts.items()):
        print(f"  {speed}: {count}")

    # By source
    print("\nBy source:")
    source_counts = {}
    for r in rows:
        source_counts[r["source"]] = source_counts.get(r["source"], 0) + 1
    for source, count in sorted(source_counts.items()):
        print(f"  {source}: {count}")

    # Tags
    print("\nTag distribution:")
    tag_counts = {}
    for r in rows:
        tags = r.get("tags", "").split(",")
        for tag in tags:
            tag = tag.strip()
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        print(f"  {tag}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Validate audio dataset manifest")
    parser.add_argument("--manifest", default="data/manifest.csv", help="Manifest CSV path")
    parser.add_argument("--audio-dir", default="data/audio", help="Audio directory")
    parser.add_argument("--stats", action="store_true", help="Print dataset statistics")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    audio_dir = Path(args.audio_dir)

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    print(f"Validating manifest: {manifest_path}")
    rows = load_manifest(manifest_path)
    print(f"Loaded {len(rows)} rows")

    all_errors = []
    all_warnings = []

    # Run all validations
    for validator in [
        validate_schema,
        validate_intents,
        validate_slots_json,
        validate_categorical,
        lambda r: validate_files(r, audio_dir),
        validate_duplicates,
        validate_coverage,
    ]:
        errors, warnings = validator(rows)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    # Print results
    if all_errors:
        print(f"\n❌ ERRORS ({len(all_errors)}):")
        for err in all_errors:
            print(f"  - {err}")
    else:
        print("\n✅ No errors")

    if all_warnings:
        print(f"\n⚠️  WARNINGS ({len(all_warnings)}):")
        for warn in all_warnings:
            print(f"  - {warn}")
    else:
        print("\n✅ No warnings")

    if args.stats:
        print_stats(rows)

    # Exit code
    if all_errors or (args.strict and all_warnings):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()