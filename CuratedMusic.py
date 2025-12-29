#!/usr/bin/env python3

import math
import requests
import random
from collections import Counter
import json
from datetime import datetime, timezone
from collections import Counter
import os
from dotenv import load_dotenv

# === CONFIG (fill these in) ===
load_dotenv()
JELLYFIN_URL = os.getenv("JELLYFIN_URL")
API_KEY = os.getenv("JELLYFIN_API_KEY")

NUMBER_OF_ARTISTS = 20  # Number of top artists to consider
LENGTH_OF_PLAYLIST = 30  # Number of songs in the playlist
LENGTH_OF_HISTORY = 10000  # Number of played items to fetch


# === HEADERS ===
HEADERS = {
    "X-Emby-Token": API_KEY,
    "Content-Type": "application/json"
}


# === STEP 1: Get user ID ===
def get_all_users():
    response = requests.get(f"{JELLYFIN_URL}/Users", headers=HEADERS)
    response.raise_for_status()
    users = response.json()
    return [(user["Id"], user["Name"]) for user in users]

# === STEP 1.1 LOAD VIBE PROFILES ===
def load_vibe_profiles(filename="Vibes.json"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base_dir, filename)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# === STEP 2: Get played songs ===
def get_play_history(user_id):
    url = f"{JELLYFIN_URL}/Users/{user_id}/Items"
    try:
        params = {
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "SortBy": "PlayCount",
            "Fields": "Genres,userdata,ProductionYear,ArtistItems",
            "SortOrder": "Descending",
            "Limit": LENGTH_OF_HISTORY
        }
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])
        # Only include songs the user has played
        for item in items:
            user_data = item.get("UserData", {})
            item["PlayCount"] = user_data.get("PlayCount", 0)
            item["Played"] = user_data.get("Played", False)
            item["IsFavorite"] = user_data.get("IsFavorite", False)
        return items        
    except:
        print("Error fetching play history. Ensure the user has played items.")
        return []


# === STEP 3: Choose top artists (already mostly weighted by play count) ===
def get_top_artists(played_items, max_artists=NUMBER_OF_ARTISTS):
    artist_count = Counter()
    for item in played_items:
        play_count = item.get("PlayCount", 1)
        artists = []
        if item.get("ArtistItems"):
            artists = [a.get("Name") for a in item["ArtistItems"]]
        else:
            artist = item.get("AlbumArtist") or item.get("Artist")
            if artist:
                artists = [artist]

        for artist in artists:
            artist_count[artist] += play_count  # already weighted by play count

    top_artists = [artist for artist, _ in artist_count.most_common(max_artists)]
    return top_artists

# === STEP 3.1: Get top decades from play history (weighted by play count) ===
def get_top_decades(play_history, top_n=5):
    decade_counter = Counter()

    for item in play_history:
        play_count = item.get("PlayCount", 1)
        year = item.get("ProductionYear")

        if isinstance(year, int):
            decade = (year // 10) * 10
            decade_counter[decade] += play_count

    return decade_counter.most_common(top_n)


# === STEP 4.1: Get top genres from play history (weighted by play count) ===
def get_top_genres(play_history, top_n=10):
    genre_counter = Counter()

    for item in play_history:
        play_count = item.get("PlayCount", 1)  # Use actual play count
        genres = item.get("Genres", [])
        for genre in genres:
            # Split on commas and strip whitespace
            split_genres = [g.strip() for g in genre.split(",")]
            for g in split_genres:
                genre_counter[g] += play_count  # weight by how often song was played

    return genre_counter.most_common(top_n)

# === STEP 4.2: Get top years from play history (weighted by play count) ===
def get_top_years(play_history, top_n=20):
    year_counter = Counter()

    for item in play_history:
        play_count = item.get("PlayCount", 1)
        year = item.get("ProductionYear")
        if isinstance(year, int):
            year_counter[year] += play_count

    return year_counter.most_common(top_n)

# === STEP 4.3: Derive primary vibe from play history ===
def derive_primary_vibes(play_history, max_vibes=3):
    top_genres = get_top_genres(play_history, top_n=10)
    top_decades = get_top_decades(play_history, top_n=5)

    if not top_genres or not top_decades:
        return []

    vibes = []

    for genre, genre_score in top_genres:
        for decade, decade_score in top_decades:
            # Combined strength score
            combined_score = genre_score * 0.6 + decade_score * 0.4

            vibes.append({
                "genre": genre,
                "decade": decade,
                "genre_score": genre_score,
                "decade_score": decade_score,
                "score": combined_score
            })

    # Sort strongest first
    vibes.sort(key=lambda v: v["score"], reverse=True)
    # Keep only top N vibes
    vibes = vibes[:max_vibes * 3]  # Get extra to allow for deduplication

    #mix vibes to avoid similar ones being used everytime
    random.shuffle(vibes)

    # Deduplicate by genre (prevents 80s Rock + 90s Rock spam)
    final_vibes = []
    used_genres = set()

    for vibe in vibes:
        if vibe["genre"] in used_genres:
            continue

        final_vibes.append(vibe)
        used_genres.add(vibe["genre"])

        if len(final_vibes) >= max_vibes:
            break

    return final_vibes


# === STEP 4.3: Get all music data from Jellyfin ===
def get_all_music_data(user_id):
    all_music = []
    url = f"{JELLYFIN_URL}/Users/{user_id}/Items"
    try:
        params = {
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "Fields": "Genres,ProductionYear,ArtistItems,RunTimeTicks,UserData",
            "SortOrder": "Descending"
        }
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])
        for item in items:
            user_data = item.get("UserData", {})

            all_music.append({
                "Id": item.get("Id"),
                "Name": item.get("Name"),
                "Genres": item.get("Genres", []),
                "ProductionYear": item.get("ProductionYear"),
                "Album": item.get("Album"),
                "Artists": [a.get("Name") for a in item.get("ArtistItems", [])]
                    if item.get("ArtistItems")
                    else ([item.get("AlbumArtist") or item.get("Artist")]
                        if (item.get("AlbumArtist") or item.get("Artist")) else []),

                # Timing
                "RuntimeSeconds": item.get("RunTimeTicks", 0) / 10_000_000,
                "PlaybackSeconds": user_data.get("PlaybackPositionTicks", 0) / 10_000_000,

                #User-specific data
                "Played": user_data.get("Played", False),
                "PlayCount": user_data.get("PlayCount", 0),
                "IsFavorite": user_data.get("IsFavorite", False),
                "LastPlayedDate": user_data.get("LastPlayedDate"),
            })
        print(f"Fetched {len(all_music)} total songs from Jellyfin.")
        return all_music

    except:
        print("Error fetching music items from Jellyfin.")
        return []

# === STEP 4.4: Check if song was skipped ===
def get_was_song_skipped(song, threshold_ratio=0.15):
    runtime = song.get("RuntimeSeconds", 0)
    played = song.get("PlaybackSeconds", 0)

    if runtime > 120 and played > 0:
        return (played / runtime) < threshold_ratio

    return False

# === STEP 4.5: Estimate energy level of a song ===
def estimate_energy(song):
    genres = " ".join(song.get("Genres", [])).lower()
    runtime = song.get("RuntimeSeconds", 0)

    if any(x in genres for x in ["death", "metalcore", "hardcore"]):
        return 1.0
    if any(x in genres for x in ["edm", "electronic", "house"]):
        return 0.7
    if runtime > 420:  # long ambient / prog
        return 0.3
    return 0.5

# === STEP 4.6: Calculate days since last played ===
def days_since_played(song):
    last = song.get("LastPlayedDate")
    if not last:
        return None
    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last_dt).days

# === STEP 4.7: Get artist play counts ===
def get_artist_play_counts(play_history):
    artist_counts = Counter()

    for item in play_history:
        artists = []
        if item.get("ArtistItems"):
            artists = [a.get("Name") for a in item["ArtistItems"]]
        else:
            artist = item.get("AlbumArtist") or item.get("Artist")
            if artist:
                artists = [artist]

        for artist in artists:
            artist_counts[artist] += item.get("PlayCount", 1)

    return artist_counts

# === STEP 4.8: Get artist familiarity score ===
def get_artist_familiarity(artist, artist_play_counts, cap=50):
    plays = artist_play_counts.get(artist, 0)
    return min(plays / cap, 1.0)

# === STEP 4.10: Delete old auto-generated playlists ===
def delete_auto_playlists(user_id, prefix="Your"):
    url = f"{JELLYFIN_URL}/Users/{user_id}/Items"

    params = {
        "IncludeItemTypes": "Playlist",
        "Recursive": "true"
    }

    response = requests.get(url, headers=HEADERS, params=params)
    response.raise_for_status()

    playlists = response.json().get("Items", [])

    for p in playlists:
        name = p.get("Name", "")
        if name.startswith(prefix):
            print(f"Deleting old auto playlist: {name}")
            try:
                requests.delete(
                    f"{JELLYFIN_URL}/Items/{p['Id']}",
                    headers=HEADERS
                )
            except requests.exceptions.RequestException as e:
                print(f"Failed to delete {name}: {e}")


# === STEP 4.10: Build vibe from profile ===
def build_vibe_from_profile(vibe):
        return{
            "playlist_name": f"Your {vibe['decade']}s {vibe['genre']}",
            "require_genre": [vibe["genre"]],
            "genre_boost": [vibe["genre"].lower()],
            "preferred_decade": vibe["decade"],
            "year_weight": 10,
            "artist_weight": 2.5,
            "skip_penalty": 6,
            "randomness": [-0.1, 0.2],
            "min_runtime": 120,
            "prefer_played": "True",
            "Prefer_Recently_Played": "True",
            "artist_familiarity_weight": 3.0,
            "favorite_weight": 10.0,
            "replay_bonus": 5.0
        }

# === STEP 5: Score songs for a specific vibe ===
def score_songs_for_vibe(
    songs,
    top_genres,
    top_years,
    top_artists,
    vibe,
    artist_play_counts,
    playlist_length
):
    genre_set = set(g.lower() for g, _ in top_genres)
    year_set = set(y for y, _ in top_years)
    artist_set = set(top_artists)

    scored = []

    for song in songs:
        score = 0

        genres = [g.lower().strip() for g in song.get("Genres", [])]
        year = song.get("ProductionYear")
        artists = song.get("Artists", [])

        required = [r.lower() for r in vibe.get("require_genre", [])]

        #  Skip songs that don't match required genres
        if required:
            if not any(r in g for g in genres for r in required):
                continue
        if vibe.get("require_favorite") and not song.get("IsFavorite"):
            continue
        # Skip short tracks if vibe wants flow
        if vibe.get("min_runtime", 0) > 0:
            if song.get("RuntimeSeconds", 0) < vibe.get("min_runtime", 0):
                continue
        # Penalty for no genre
        if not genres:
            score -= 1
        # Genre bias
        if vibe.get("genre_boost") is not None:
            for g in genres:
                for boost in vibe.get("genre_boost"):
                    if boost in g:
                        score += 3
        # Familiar genre comfort
        for g in genres:
            if g in genre_set:
                score += 4

        # Prefer unplayed tracks
        if vibe.get("prefer_unplayed") and song.get("Played"):
            score -= 3

        # Prefer already-played tracks
        if vibe.get("prefer_played") == "True" and not song.get("Played")=="True":
            score -= 3

        # Year familiarity
        if vibe.get("year_weight") is not None and year is not None:
            if year in year_set:
                score += vibe["year_weight"]
        # Preferred decade
        if vibe.get("preferred_decade") is not None and year is not None:
            decade = (year // 10) * 10
            if decade == vibe["preferred_decade"]:
                score += 20
        # Artist familiarity
        if vibe.get("artist_weight") is not None and artists is not None:
            if any(a in artist_set for a in artists):
                score += vibe["artist_weight"]

        # Artist familiarity weight
        if(vibe.get("artist_familiarity_weight") is not None):
            artist_fam = 0
            for artist in artists:
                artist_fam = max(
                    artist_fam,
                    get_artist_familiarity(artist, artist_play_counts)
                )
            score += artist_fam * vibe.get("artist_familiarity_weight", 0)

        # Energy bias
        energy = estimate_energy(song)
        if vibe.get("energy_cap") is not None:
            if energy > vibe["energy_cap"]:
                score -= 3
        else:
            score += energy * 2

        # Favorite bonus
        if song.get("IsFavorite") and vibe.get("favorite_weight") is not None:
            score += vibe["favorite_weight"]
        
        # Skip penalty
        if get_was_song_skipped(song):
            score -= vibe["skip_penalty"]
        
        #reward repleyed songs
        if song.get("PlayCount", 0) > 0 and vibe.get("replay_bonus") is not None:
            score += math.log1p(song["PlayCount"]) * vibe["replay_bonus"]

        # Recent play bonus
        days = days_since_played(song)
        if vibe.get("Prefer_Recently_Played") =="True" and days is not None:
            score += max(0, (30 - days) * 0.2)  # More recent plays get higher score
        elif days is not None: # Less recent plays get a small bonus
            score += min(days, 180) * 0.05  # caps at +9

        # Controlled chaos
        rand = vibe.get("randomness", (0, 0))
        if isinstance(rand, (list, tuple)) and len(rand) == 2:
            score += random.uniform(rand[0], rand[1])

        scored.append((score, song["Id"]))

    scored.sort(reverse=True)

    pool = scored[:max(playlist_length * 4, 150)]
    random.shuffle(pool)

    final = []
    seen = set()
    for _, sid in pool:
        if sid not in seen:
            final.append(sid)
            seen.add(sid)
        if len(final) >= playlist_length:
            break

    return final


# === STEP 6: Create or replace playlist ===
def create_or_update_playlist(user_id, playlist_name, song_ids):
    # Check if playlist already exists
    response = requests.get(
        f"{JELLYFIN_URL}/Search/hints",
        headers=HEADERS,
        params={"userId": user_id, "SearchTerm": playlist_name}   
    )

    response.raise_for_status()
    playlists = response.json().get("SearchHints", [])
    # Check if the playlist already exists and delete it if it does
    for p in playlists:
        if p['Name'] == playlist_name:
                print(f"Deleting existing playlist: {playlist_name}")
                try:
                    requests.delete(f"{JELLYFIN_URL}/Items/{p['Id']}", headers=HEADERS)
                except requests.exceptions.RequestException as e:
                    print(f" Failed to delete playlist: {e}")


    # Create new playlist
    print(f"Creating new playlist: {playlist_name} with {len(song_ids)} songs")
    payload = {
        "Name": playlist_name,
        "UserId": user_id,
        "Ids": song_ids,
        "IsPublic": False
    }
    try:
        response = requests.post(
            f"{JELLYFIN_URL}/Playlists",
            headers=HEADERS,
            json=payload
        )
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f" Error creating playlist: {e}")

# === MAIN PLAYLIST GENERATION FUNCTION ===
def Generate_playlist(user_id):
    history = get_play_history(user_id)
    top_artists = get_top_artists(history)
    artist_play_counts = get_artist_play_counts(history)
    top_genres = get_top_genres(history)
    top_years = get_top_years(history)

    print("🎧 Top genres:")
    for genre, count in top_genres:
        print(f"{genre}: {count} plays")
    
    print("🎧 Top years:")
    for year, count in top_years:
        print(f"{year}: {count} plays")

    if not top_artists:
        print("No artists found in history.")
        return

    all_songs = get_all_music_data(user_id)
    VIBE_PROFILES = load_vibe_profiles()

    # Add auto-generated vibes
        # Delete old auto-generated playlists
    delete_auto_playlists(user_id)
        #ADD AUTO VIBES
    print("Generating automatic vibes based on listening history...")
    primary_vibes = derive_primary_vibes(history)
    for i, vibe in enumerate(primary_vibes):
        VIBE_PROFILES[f"Auto Generated Vibe {i+1}"] = build_vibe_from_profile(vibe)
    
    print(f"Total vibes to generate: {len(VIBE_PROFILES)}")

    # Generate playlists for each vibe
    for vibe_name, vibe in VIBE_PROFILES.items():
        print(f"\n Generating: {vibe_name}")

        song_ids = score_songs_for_vibe(
            all_songs,
            top_genres,
            top_years,
            top_artists,
            vibe,
            artist_play_counts,
            LENGTH_OF_PLAYLIST
        )

        create_or_update_playlist(
            user_id,
            vibe["playlist_name"],
            song_ids
        )

# === MAIN ===
def main():
    print("\n=========================================\n")
    print("\n Starting curated playlist generation... \n")
    print(f"Run started at {datetime.now().isoformat()}")
    print("\n=========================================\n")
    
    if not JELLYFIN_URL or not API_KEY:
        print("  Missing Jellyfin configuration in .env file.")
        print(os.getenv("JELLYFIN_URL"), os.getenv("JELLYFIN_API_KEY"))
        raise RuntimeError("Missing Jellyfin configuration (.env)")
    else:
        print("  Jellyfin configuration loaded.")
        for user_id, user_name in get_all_users():
            print(f"\n Processing user: {user_name} (ID: {user_id})\n")
            Generate_playlist(user_id)

    print("\n=========================================\n")
    print("\n  Curated playlist generation complete!  \n") 
    print("\n=========================================\n")

if __name__ == "__main__":
    main()