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

## Requirements
- Jellyfin 10.8+
- Python 3.9+
- Jellyfin API key

## Editing Vibe Profiles (Vibes.json)
  
  The Vibes.json file contains all your playlist “vibe” profiles. Each vibe defines rules for selecting songs in Jellyfin. You can add, remove, or tweak vibes to change your playlist generation.
  
  Structure of a vibe
  
  Each vibe is a JSON object like this:
  
  "Metal Gym": {
      "playlist_name": "💪 Metal Gym",
      "require_genre": ["metal", "metalcore", "death", "hardcore"],
      "genre_boost": ["metal", "metalcore", "death", "hardcore"],
      "year_weight": 0.5,
      "artist_weight": 2.0,
      "skip_penalty": 4,
      "randomness": [-0.3, 0.5],
      "min_runtime": 120,
      "artist_familiarity_weight": 2.0,
      "favorite_weight": 4.0
  }
  
  
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
```bash
git clone https://github.com/darklitleme/jellyfin-curated-playlists.git
cd jellyfin-curated-playlists
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

nano .env


Your .env should look like the below:
JELLYFIN_URL=jellyfin ip address here eg : 192.168.1.1:8096
JELLYFIN_API_KEY=Jelly fin API Key here eg : jgh3jhgy43jy4gj3h4g
