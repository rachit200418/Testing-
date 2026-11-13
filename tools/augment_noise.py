#!/usr/bin/env python3
"""
Add background noise to audio clips at different SNR levels.
Uses audiomentations for realistic noise augmentation.
"""

import argparse
import asyncio
import csv
import random
import sys
from pathlib import Path
from typing import List, Dict

import numpy as np

try:
    import audiomentations as A
    import soundfile as sf
except ImportError:
    print("audiomentations not installed. Install with: pip install audiomentations soundfile")
    sys.exit(1)


NOISE_TYPES = {
    "tv": "background_tv",
    "traffic": "background_traffic",
    "babble": "background_babble",
    "white": "white_noise",
    "pink": "pink_noise",
}

# SNR levels in dB (lower = more noise)
SNR_LEVELS = {
    "clean": None,      # No noise added
    "low_noise": 20,    # 20 dB SNR
    "medium_noise": 15, # 15 dB SNR
    "high_noise": 10,   # 10 dB SNR
    "very_high_noise": 5, # 5 dB SNR
}


def load_manifest(manifest_path: Path) -> List[Dict]:
    """Load manifest CSV."""
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def create_augmenter(noise_type: str, snr_db: float) -> A.Compose:
    """Create audiomentations augmenter for specific noise type and SNR."""
    # Map noise type to audiomentations
    if noise_type == "tv":
        # TV background - use AddBackgroundNoise with TV-like samples
        return A.Compose([
            A.AddBackgroundNoise(
                sounds_path="tools/noise_samples/tv",
                min_snr_in_db=snr_db,
                max_snr_in_db=snr_db,
                noise_transform=A.PolarityInversion(p=0.5),
                p=1.0,
            )
        ])
    elif noise_type == "traffic":
        return A.Compose([
            A.AddBackgroundNoise(
                sounds_path="tools/noise_samples/traffic",
                min_snr_in_db=snr_db,
                max_snr_in_db=snr_db,
                p=1.0,
            )
        ])
    elif noise_type == "babble":
        return A.Compose([
            A.AddBackgroundNoise(
                sounds_path="tools/noise_samples/babble",
                min_snr_in_db=snr_db,
                max_snr_in_db=snr_db,
                p=1.0,
            )
        ])
    elif noise_type == "white":
        return A.Compose([
            A.AddGaussianNoise(
                min_amplitude=0.001 * (10 ** (-snr_db / 20)),
                max_amplitude=0.01 * (10 ** (-snr_db / 20)),
                p=1.0,
            )
        ])
    elif noise_type == "pink":
        return A.Compose([
            A.AddGaussianNoise(
                min_amplitude=0.001 * (10 ** (-snr_db / 20)),
                max_amplitude=0.01 * (10 ** (-snr_db / 20)),
                p=1.0,
            ),
            # Apply pink noise filter approximation
            A.Equalizer(
                min_gain_db=-12,
                max_gain_db=12,
                p=1.0,
            ),
        ])
    else:
        # Default: Gaussian noise
        return A.Compose([
            A.AddGaussianNoise(
                min_amplitude=0.001 * (10 ** (-snr_db / 20)),
                max_amplitude=0.01 * (10 ** (-snr_db / 20)),
                p=1.0,
            )
        ])


def ensure_noise_samples():
    """Create basic noise samples if they don't exist."""
    noise_dir = Path("tools/noise_samples")
    noise_dir.mkdir(parents=True, exist_ok=True)

    # Generate basic noise samples programmatically
    import soundfile as sf
    import numpy as np

    sample_rate = 16000
    duration = 10  # seconds

    # White noise
    white_path = noise_dir / "white" / "white_noise.wav"
    white_path.parent.mkdir(parents=True, exist_ok=True)
    if not white_path.exists():
        white_noise = np.random.normal(0, 0.1, sample_rate * duration).astype(np.float32)
        sf.write(str(white_path), white_noise, sample_rate)

    # Pink noise (approximate)
    pink_path = noise_dir / "pink" / "pink_noise.wav"
    pink_path.parent.mkdir(parents=True, exist_ok=True)
    if not pink_path.exists():
        # Simple pink noise approximation
        white = np.random.normal(0, 1, sample_rate * duration)
        # Apply 1/f filter approximation
        pink = np.zeros_like(white)
        b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        a = [1, -2.494956002, 2.017265875, -0.522189400]
        for i in range(len(white)):
            pink[i] = white[i] * b[0]
            if i > 0: pink[i] += white[i-1] * b[1] - pink[i-1] * a[1]
            if i > 1: pink[i] += white[i-2] * b[2] - pink[i-2] * a[2]
            if i > 2: pink[i] += white[i-3] * b[3] - pink[i-3] * a[3]
        pink = pink / np.max(np.abs(pink)) * 0.1
        sf.write(str(pink_path), pink.astype(np.float32), sample_rate)

    # TV-like noise (modulated)
    tv_dir = noise_dir / "tv"
    tv_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        tv_path = tv_dir / f"tv_{i}.wav"
        if not tv_path.exists():
            t = np.arange(sample_rate * duration) / sample_rate
            # Modulated noise to simulate TV
            tv = np.random.normal(0, 0.05, sample_rate * duration) * (1 + 0.5 * np.sin(2 * np.pi * 0.1 * t))
            sf.write(str(tv_path), tv.astype(np.float32), sample_rate)

    # Traffic noise
    traffic_dir = noise_dir / "traffic"
    traffic_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        tr_path = traffic_dir / f"traffic_{i}.wav"
        if not tr_path.exists():
            # Low-frequency rumble
            t = np.arange(sample_rate * duration) / sample_rate
            traffic = np.random.normal(0, 0.08, sample_rate * duration)
            traffic = traffic * (0.5 + 0.5 * np.sin(2 * np.pi * 0.05 * t))
            sf.write(str(tr_path), traffic.astype(np.float32), sample_rate)

    # Babble (crowd)
    babble_dir = noise_dir / "babble"
    babble_dir.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        bab_path = babble_dir / f"babble_{i}.wav"
        if not bab_path.exists():
            # Multiple overlapping voices simulation
            babble = np.zeros(sample_rate * duration)
            for _ in range(5):
                voice = np.random.normal(0, 0.03, sample_rate * duration)
                # Add formants
                t = np.arange(sample_rate * duration) / sample_rate
                voice *= (1 + 0.3 * np.sin(2 * np.pi * random.uniform(100, 300) * t))
                babble += voice
            babble = babble / 5 * 0.5
            sf.write(str(bab_path), babble.astype(np.float32), sample_rate)


async def augment_audio(
    input_path: Path,
    output_path: Path,
    noise_type: str,
    snr_db: float,
) -> bool:
    """Augment audio with noise."""
    try:
        # Load audio
        import soundfile as sf
        audio, sr = sf.read(str(input_path))

        # Ensure mono
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)

        # Create augmenter
        augmenter = create_augmenter(noise_type, snr_db)

        # Apply augmentation
        augmented = augmenter(samples=audio, sample_rate=sr)

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(output_path), augmented, sr)
        return True

    except Exception as e:
        print(f"  ✗ Error augmenting {input_path}: {e}")
        return False


def generate_noisy_filename(original: str, noise_type: str, noise_level: str) -> str:
    """Generate filename for noisy version."""
    stem = Path(original).stem
    suffix = Path(original).suffix
    return f"{stem}_{noise_type}_{noise_level}{suffix}"


def main():
    parser = argparse.ArgumentParser(description="Add noise to audio clips")
    parser.add_argument("--manifest", default="data/manifest.csv", help="Manifest CSV path")
    parser.add_argument("--input-dir", default="data/audio", help="Input audio directory")
    parser.add_argument("--output-dir", default="data/audio", help="Output audio directory")
    parser.add_argument("--noise-types", nargs="+", default=["tv", "traffic", "babble"],
                        help="Noise types to add")
    parser.add_argument("--snr-levels", nargs="+", default=["low_noise", "medium_noise", "high_noise"],
                        help="SNR levels to apply")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing files")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}")
        sys.exit(1)

    # Ensure noise samples exist
    ensure_noise_samples()

    rows = load_manifest(manifest_path)
    print(f"Loaded {len(rows)} entries from manifest")

    # Filter rows that have noise_level != clean (those are targets for augmentation)
    target_rows = [r for r in rows if r["noise_level"] != "clean" and r["noise_level"] != "silence"]
    print(f"Target rows for augmentation: {len(target_rows)}")

    # For each target row, we need to find its clean counterpart and augment it
    # The manifest already has entries for noisy versions - we generate those from clean versions
    clean_rows = {r["file"]: r for r in rows if r["noise_level"] == "clean"}

    success = 0
    failed = 0
    skipped = 0

    for row in target_rows:
        noisy_file = row["file"]
        noise_level = row["noise_level"]
        # Infer noise type from tags or filename
        tags = row.get("tags", "")
        noise_type = "white"  # default

        for nt in args.noise_types:
            if nt in tags or nt in noisy_file:
                noise_type = nt
                break

        # Find clean version (same base name without noise suffix)
        clean_file = None
        for cf in clean_rows:
            if cf.replace(".wav", "") in noisy_file:
                clean_file = cf
                break

        if not clean_file:
            print(f"  ⊘ No clean version found for {noisy_file}")
            failed += 1
            continue

        clean_path = input_dir / clean_file
        if not clean_path.exists():
            print(f"  ⊘ Clean file not found: {clean_path}")
            failed += 1
            continue

        output_path = output_dir / noisy_file

        if args.skip_existing and output_path.exists():
            print(f"  ⊘ Skip {noisy_file} (exists)")
            skipped += 1
            continue

        snr_db = SNR_LEVELS.get(noise_level)
        if snr_db is None:
            print(f"  ⊘ Unknown noise level: {noise_level}")
            failed += 1
            continue

        print(f"Augmenting {clean_file} -> {noisy_file} (noise={noise_type}, SNR={snr_db}dB)")

        if asyncio.run(augment_audio(clean_path, output_path, noise_type, snr_db)):
            print(f"  ✓ Success")
            success += 1
        else:
            print(f"  ✗ Failed")
            failed += 1

    print(f"\nDone: {success} success, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    main()