# Jellyfin Curated Playlists

Automatically generates smart playlists for each Jellyfin user based on:
- Play history
- Genres
- Decades
- Favorites
- Replay behavior

## Features
- Per-user playlist generation
- Auto-generated "vibes"
- Safe to run daily via cron
- No plugins or Jellyfin mods required
- Skips already analysed tracks
- Extracts features:
  - RMS & energy
  - BPM & beat confidence
  - Key, scale, strength
  - Bass energy & danceability
- CPU-friendly with configurable throttling


## Requirements
- Python 3.11+
- [Essentia](https://essentia.upf.edu/)
- NumPy
- psutil
- python-dotenv

## Editing Vibe Profiles (Vibes.json)
  
  The Vibes.json file contains all your playlist “vibe” profiles. Each vibe defines rules for selecting songs in Jellyfin. You can add, remove, or tweak vibes to change your playlist generation.
  
  Structure of a vibe
  
  Each vibe is a JSON object like this:

  "EDM Night Drive": {
    "playlist_name": "🌌 EDM Night Drive",
    "require_genre": ["edm", "electronic", "electro", "house", "dance"],
    "genre_boost": ["edm", "electronic", "house", "progressive"],
    "preferred_moods": {
      "electronic": 1,
      "happy": 0.5,
      "party": 0.4,
      "aggressive": -0.5,
      "sad": -0.3
    },
    "bpm_target": 124,
    "bpm_range": 18,
    "bpm_weight": 3,
    "year_weight": 0.4,
    "artist_weight": 0.5,
    "artist_familiarity_weight": 1.0,
    "favorite_weight": 2.0,
    "skip_penalty": 1.0,
    "randomness": [-0.1, 0.6],
    "min_runtime": 180,
    "energy_cap": 0.9,
    "bass_weight": 1.0,
    "dacability_weight": 0.5,
    "key_weight": 0.2,
    "prefer_played": "True"
  },
  
  
  Explanation of fields:
  
  Field	Purpose
  playlist_name	Name of the playlist in Jellyfin. You can add emojis.
  require_genre	List of genres that must be included in the song for this vibe. Leave empty ([]) for no restrictions.
  genre_boost	Genres that get a scoring bonus. Useful for emphasizing certain styles.
  year_weight	Bonus points if a song’s year is in your top played years.
  artist_weight	Bonus points if the song is by one of your top artists.
  skip_penalty	Penalty for songs that are frequently skipped.
  randomness	[min, max] random value added to each song’s score to add variety.
  min_runtime	Minimum song length in seconds. Short songs will be skipped.
  artist_familiarity_weight	Bonus based on how familiar you are with the artist.
  favorite_weight	Bonus if the song is marked as a favorite.
  energy_cap	(Optional) Maximum “energy” of song for this vibe (0–1). Higher energy songs get penalized if above cap.
  prefer_played	"True" to prefer songs you’ve played before.
  prefer_unplayed	"True" to prefer songs you haven’t played yet.
  prefer_recently_played	"True" to give bonus to songs played recently.
  replay_bonus	Bonus applied based on play count.

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
