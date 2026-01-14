import json
import os
import time
import psutil
from datetime import datetime, timezone
from pathlib import Path
import essentia
import essentia.standard
import essentia.streaming
from essentia.standard import *
import numpy as np
from dotenv import load_dotenv

# =========================
# CONFIG
# =========================
JELLYFIN_FILE = "jellyfin_music_raw.json"
OUTPUT_FILE = "analysed_audio.json"

load_dotenv()
PATH_TO_MUSIC_LIBRARY = os.getenv("PATH_TO_MUSIC_LIBRARY")

try:
    MAX_CPU_PERCENT = float(os.getenv("MAX_CPU_PERCENT", "75.0"))
except ValueError:
    MAX_CPU_PERCENT = 75.0  # fallback

SLEEP_BETWEEN_TRACKS = 0.2  # seconds
SAMPLE_RATE = 44100

# =========================
# RESOURCE LIMITING
# =========================
p = psutil.Process(os.getpid())
p.nice(10)  # lower priority

def resolve_audio_path(jellyfin_path: str, library_root: str) -> Path:
    jellyfin_path = Path(jellyfin_path)

    # Jellyfin absolute path remap
    if jellyfin_path.is_absolute():
        parts = jellyfin_path.parts

        # Find the "Music" folder in Jellyfin path
        if "Music" in parts:
            idx = parts.index("Music")
            relative = Path(*parts[idx+1:])
            return Path(library_root) / relative

        # Fallback: strip leading /
        return Path(library_root) / jellyfin_path.relative_to("/")

    return Path(library_root) / jellyfin_path


def scalar(x):
    """Safely convert Essentia outputs to Python float"""
    if isinstance(x, (list, tuple)):
        return float(np.mean(x))
    if hasattr(x, "shape"):
        return float(np.mean(x))
    return float(x)

# =========================
# LOAD EXISTING ANALYSIS
# =========================
def load_existing():
    file = Path(OUTPUT_FILE)
    if not file.exists():
        print(" No existing analysis found.")
        return {}

    with open(file, "r") as f:
        data = json.load(f)
        print(f" Existing analysis generated at: {data.get('generated_at')}")

    existing = {}

    for item in data.get("tracks", []):
        jellyfin_id = item.get("jellyfin_id")

        if jellyfin_id:
            existing[jellyfin_id] = item
        else:
            # 🔧 legacy fallback (FIXED)
            path = item.get("Path") or item.get("path")
            if path:
                existing[f"PATH::{path}"] = item
    print(f" Loaded {len(existing)} existing analyses.")
    return existing

# =========================
# SAVE PROGRESS
# =========================
def save_progress(tracks):
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "track_count": len(tracks),
        "tracks": list(tracks.values())
    }

    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    os.replace(tmp, OUTPUT_FILE)


# =========================
# ESSENTIA ANALYSIS
# =========================
def analyse_audio(path: Path):
    loader = essentia.standard.MonoLoader(filename=str(path))
    audio = loader()
    print(f" Audio length: {len(audio)/SAMPLE_RATE:.2f} seconds")
    audio_to_analyse = audio[:SAMPLE_RATE*600]  # first 10 minutes


  
    # Low-level
    rms_val = float(np.mean(essentia.standard.RMS()(audio_to_analyse)))
    energy_val = float(np.mean(essentia.standard.Energy()(audio_to_analyse)))
    print(f" RMS: {rms_val:.6f}, Energy: {energy_val:.6f}") 
    # Rhythm
    rhythm_result = essentia.standard.RhythmExtractor2013(method="multifeature")(audio_to_analyse)
    bpm_val = float(rhythm_result[0])
    confidence_val = float(rhythm_result[2])
    print(f" BPM: {bpm_val:.2f}, Confidence: {confidence_val:.4f}") 
    # Tonal
    key, scale, strength = essentia.standard.KeyExtractor()(audio_to_analyse)
    strength_val = float(strength)
    print(f" Key: {key}, Scale: {scale}, Strength: {strength_val:.4f}") 
    # Bass energy via MelBands

    framecutter = essentia.standard.FrameCutter(
        frameSize=2048,
        hopSize=1024,
        startFromZero=True,
        lastFrameToEndOfFile=True
    )

    windowing = essentia.standard.Windowing(type="hann")
    spectrum = essentia.standard.Spectrum()
    melbands = essentia.standard.MelBands(
        numberBands=40,
        sampleRate=SAMPLE_RATE
    )

    bass_vals = []

    # IMPORTANT: feed audio first
    framecutter(audio)

    print(" Calculating bass energy...")
    while True:
        frame = framecutter(audio)
        if frame.size == 0:
            print(" End of audio for bass energy.")
            break

        spec = spectrum(windowing(frame))
        bands = melbands(spec)
        bass_vals.append(float(np.mean(bands[:5])))


    print(f" Calculated {len(bass_vals)} bass frames.")
    bass_energy_val = float(np.mean(bass_vals)) if bass_vals else 0.0
    bass_energy_norm = bass_energy_val / rms_val if rms_val else 0.0
    print(f" Bass Energy: {bass_energy_val:.6f}")
    dance_score = bpm_val * confidence_val * bass_energy_norm
    print(f" Dance Score: {dance_score:.6f}")
    return {
        "low_level": {
            "rms": rms_val,
            "energy": energy_val,
            "bass_energy": bass_energy_norm,
            "danceability_score": dance_score,
        },
        "rhythm": {
            "tempo": bpm_val,
            "beat_confidence": confidence_val,
        },
        "tonal": {
            "key": key,
            "scale": scale,
            "strength": strength_val,
        },
    }

# =========================
# MAIN
# =========================
def createIndex():
    if not os.path.exists(JELLYFIN_FILE):
        raise FileNotFoundError("jellyfin_music_raw.json not found")

    if not os.path.isdir(PATH_TO_MUSIC_LIBRARY):
        raise FileNotFoundError("Music library path invalid")

    with open(JELLYFIN_FILE, "r", encoding="utf-8") as f:
        jellyfin = json.load(f)

    tracks = jellyfin.get("tracks", [])
    existing = load_existing()

    print(f"🎵 Jellyfin tracks: {len(tracks)}")
    print(f"📦 Already analysed: {len(existing)}")
    # ⬇️ Filter out already-analysed tracks
    tracks = [
        t for t in tracks
        if (
            t.get("Id") not in existing
            and f"PATH::{t.get('Path')}" not in existing
            and t.get("Path")
        )
    ]

    print(f"🆕 Tracks to analyse: {len(tracks)}")

    for track in tracks:
        jellyfin_id = track.get("Id")
        rel_path = track.get("Path")

        if not jellyfin_id or not rel_path:
            print(F"Not a real path: {rel_path} or no jellyfin id : {jellyfin_id}")
            continue

        if jellyfin_id in existing:
            print(f"⏭️  Skipping already analysed: {track.get('Name')}")
            continue  # skip already analysed


        full_path = resolve_audio_path(track["Path"], PATH_TO_MUSIC_LIBRARY)
        print(f" \n full_path = {full_path}" )
        if not os.path.exists(full_path):
            print(f"⚠️ Missing file: {full_path}")
            continue
        if not full_path:
            print("❌ full_path is None — skipping")
            continue

        if not isinstance(full_path, (str, Path)):
            print(f"❌ Invalid path type: {type(full_path)} — {full_path}")
            continue

        full_path = Path(full_path)

        if not full_path.exists():
            print(f"⚠️ Missing file: {full_path}")
            continue
        # CPU throttle
        while psutil.cpu_percent(interval=0.5) > MAX_CPU_PERCENT:
            time.sleep(1)

        print(f"🎧 Analysing: {track.get('Name')}")

        try:
            features = analyse_audio(full_path)
        except Exception as e:
            print(f"❌ Failed: {e}")
            continue

        enriched = {
            **track,
            "analysis": features,
            "analysed_at": datetime.now(timezone.utc).isoformat()
        }

        existing[jellyfin_id] = enriched
        save_progress(existing)

        time.sleep(SLEEP_BETWEEN_TRACKS)

    print("✅ Analysis complete")

