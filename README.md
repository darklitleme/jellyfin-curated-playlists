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
