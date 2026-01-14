# Curated Music Analysis

This project analyses your local music library (from a Jellyfin dump) to extract audio features such as rhythm, tonal information, bass energy, and danceability. Results are stored in JSON for later use in playlist generation.

## Features
- Analyses existing Jellyfin music dump (`jellyfin_music_raw.json`)
- Skips already analysed tracks
- Extracts features:
  - RMS & energy
  - BPM & beat confidence
  - Key, scale, strength
  - Bass energy & danceability
- CPU-friendly with configurable throttling
- Saves results incrementally (`analysed_audio.json`)
- Handles errors gracefully

## Requirements
- Python 3.11+
- [Essentia](https://essentia.upf.edu/)
- NumPy
- psutil
- python-dotenv

## Installation
1. Clone the repo:
```bash
git clone https://github.com/yourusername/curated-music-analysis.git
cd curated-music-analysis

    Create a virtual environment:

python -m venv venv
source venv/bin/activate  # Linux / macOS
venv\Scripts\activate     # Windows

    Install dependencies:

pip install -r requirements.txt

    Create a .env file in the root:
JELLYFIN_URL=http://192.168.1.1:8096
JELLYFIN_API_KEY=d12345
PATH_TO_MUSIC_LIBRARY=/full/path/to/your/music/library   - leave this black if you dont want to use Essentia
MAX_CPU_PERCENT=75.0

Usage

python CuratedMusic.py

    The script will load your Jellyfin music dump and analyse unprocessed tracks.

    Progress is saved in analysed_audio.json.

Notes

    Tracks that fail to load or analyse are skipped but logged.

    Large continuous mixes may fail rhythm extraction due to buffer limits.

    Already analysed tracks are skipped automatically.