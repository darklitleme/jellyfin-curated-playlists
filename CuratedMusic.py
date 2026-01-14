#!/usr/bin/env python3

import math
import requests
import random
from collections import Counter
import json
from datetime import datetime, timezone
import os
from analyse_music import createIndex
from SongManager import dump_jellyfin_raw
from dotenv import load_dotenv


# === CONFIG (fill these in) ===
load_dotenv()
JELLYFIN_URL = os.getenv("JELLYFIN_URL")
API_KEY = os.getenv("JELLYFIN_API_KEY")
PATH_TO_MUSIC_LIBRARY = os.getenv("PATH_TO_MUSIC_LIBRARY")

NUMBER_OF_ARTISTS = 20  # Number of top artists to consider
LENGTH_OF_PLAYLIST = 30  # Number of songs in the playlist
LENGTH_OF_HISTORY = 10000  # Number of played items to fetch
ANALYSED_FILE = "analysed_audio.json"


# === HEADERS ===
HEADERS = {
    "X-Emby-Token": API_KEY,
    "Content-Type": "application/json"
}

KEY_MAP = {
    # Major
    "c": 0, "g": 1, "d": 2, "a": 3, "e": 4, "b": 5,
    "f#": 6, "gb": 6,
    "db": 7, "c#": 7,
    "ab": 8,
    "eb": 9,
    "bb": 10,
    "f": 11,

    # Minor (relative majors)
    "am": 0, "em": 1, "bm": 2, "f#m": 3,
    "c#m": 4, "g#m": 5,
    "d#m": 6, "ebm": 6,
    "bbm": 7,
    "fm": 8,
    "cm": 9,
    "gm": 10,
    "dm": 11
}

MOOD_DIMENSIONS = [
    "aggressive",
    "happy",
    "sad",
    "party",
    "relaxed",
    "electronic",
    "acoustic"
]

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
def get_play_history(user_id, analysis_index):
    url = f"{JELLYFIN_URL}/Users/{user_id}/Items"

    try:
        params = {
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "SortBy": "PlayCount",
            "Fields": "Genres,UserData,ProductionYear,ArtistItems",
            "SortOrder": "Descending",
            "Limit": LENGTH_OF_HISTORY
        }

        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        items = response.json().get("Items", [])

        for item in items:
            user_data = item.get("UserData", {})

            item["PlayCount"] = user_data.get("PlayCount", 0)
            item["Played"] = user_data.get("Played", False)
            item["IsFavorite"] = user_data.get("IsFavorite", False)

            analysis = analysis_index.get(item.get("Id"))
            item["analysis"] = analysis

            low = analysis.get("low_level", {}) if analysis else {}
            rhythm = analysis.get("rhythm", {}) if analysis else {}
            tonal = analysis.get("tonal", {}) if analysis else {}

            item["AB_BPM"] = rhythm.get("tempo")
            item["AB_Energy"] = normalize_energy(low.get("energy"))
            item["AB_Bass"] = low.get("bass_energy")
            item["AB_Dance"] = low.get("danceability_score")
            item["AB_Key"] = tonal.get("key")
            item["AB_Mode"] = tonal.get("scale")

        return items

    except Exception as e:
        print(f"Error fetching play history for user {user_id}: {e}")
        return []

    
# === STEP 2.1: Extract AB:* tags ===
def extract_ab_tags(item):
    """
    Extracts AB:* tags if present.
    Returns a dict with normalized values.
    """
    tags = item.get("Tags", []) or []

    ab = {
        "genre": [],
        "mood": [],
        "bpm": None,
        "key": None
    }

    for tag in tags:
        if not isinstance(tag, str):
            continue

        tag_lower = tag.lower()

        if tag_lower.startswith("ab:genre="):
            ab["genre"].extend(
                g.strip().lower()
                for g in tag.split("=", 1)[1].split(",")
            )

        elif tag_lower.startswith("ab:mood="):
            ab["mood"].extend(
                m.strip().lower()
                for m in tag.split("=", 1)[1].split(",")
            )

        elif tag_lower.startswith("ab:bpm="):
            try:
                ab["bpm"] = int(tag.split("=", 1)[1])
            except ValueError:
                pass

        elif tag_lower.startswith("ab:key="):
            ab["key"] = tag.split("=", 1)[1].strip().lower()

    return ab

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

# === STEP 3.2: Normalize moods ===
def normalize_moods(ab_moods):
    """
    Converts AB:MOOD tags into a normalized mood dict.
    Example:
    ["Not aggressive", "Happy"] →
    {"aggressive": -1, "happy": 1}
    """
    mood_state = {}

    for mood in ab_moods:
        m = mood.strip().lower()

        if m.startswith("not "):
            key = m.replace("not ", "").strip()
            mood_state[key] = -1
        else:
            mood_state[m] = 1

    return mood_state

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

# === STEP 4.4: Derive preferred key from play history ===
def derive_preferred_key(play_history):
    key_counter = Counter()

    for item in play_history:
        tags = item.get("Tags", [])
        for tag in tags:
            if isinstance(tag, str) and tag.lower().startswith("ab:key="):
                key = tag.split("=", 1)[1].strip().lower()
                key_counter[key] += item.get("PlayCount", 1)

    if not key_counter:
        return None

    return key_counter.most_common(1)[0][0]


# === STEP 4.5: Get all music data from Jellyfin ===
def get_all_music_data(user_id, analysis_index):
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
            ab_tags = extract_ab_tags(item)
            jid = item.get("Id")

            all_music.append({

                "Id": item.get("Id"),
                "Name": item.get("Name"),

                # Prefer AB:GENRE if available
                "Genres": ab_tags["genre"] if ab_tags["genre"] else item.get("Genres", []),

                "AB_Mood": ab_tags["mood"],
                "AB_BPM": ab_tags["bpm"],
                "AB_Key": ab_tags["key"],

                "ProductionYear": item.get("ProductionYear"),
                "Album": item.get("Album"),
                "Artists": [a.get("Name") for a in item.get("ArtistItems", [])]
                    if item.get("ArtistItems")
                    else ([item.get("AlbumArtist") or item.get("Artist")]
                        if (item.get("AlbumArtist") or item.get("Artist")) else []),

                "RuntimeSeconds": item.get("RunTimeTicks", 0) / 10_000_000,
                "PlaybackSeconds": user_data.get("PlaybackPositionTicks", 0) / 10_000_000,

                "Played": user_data.get("Played", False),
                "PlayCount": user_data.get("PlayCount", 0),
                "IsFavorite": user_data.get("IsFavorite", False),
                "LastPlayedDate": user_data.get("LastPlayedDate"),

                        })
            item["analysis"] = analysis_index.get(jid)  # None if missing
            
        print(f"Fetched {len(all_music)} total songs from Jellyfin.")
        return all_music

    except:
        print("Error fetching music items from Jellyfin.")
        return []

# === STEP 4.6: Check if song was skipped ===
def get_was_song_skipped(song, threshold_ratio=0.15):
    runtime = song.get("RuntimeSeconds", 0)
    played = song.get("PlaybackSeconds", 0)

    if runtime > 120 and played > 0:
        return (played / runtime) < threshold_ratio

    return False

# === STEP 4.7: Estimate energy level of a song ===
def estimate_energy(song):
    raw_energy  = get_analysis(song, "low_level", "energy")

    if raw_energy is not None:
        NORMALIZATION_MAX = 14.0  # Approximate max energy value
        log_energy = math.log1p(raw_energy)
        return min(log_energy / 14.0, 1.0)


    bpm = song.get("AB_BPM")

    if bpm:
        if bpm >= 150:
            return 1.0
        if bpm >= 120:
            return 0.8
        if bpm >= 90:
            return 0.6
        return 0.4

    # fallback to genre/runtime heuristics
    genres = " ".join(song.get("Genres", [])).lower()
    runtime = song.get("RuntimeSeconds", 0)

    if any(x in genres for x in ["death", "metalcore", "hardcore"]):
        return 1.0
    if any(x in genres for x in ["edm", "electronic", "house"]):
        return 0.7
    if runtime > 420:
        return 0.3
    return 0.5

# === STEP 4.8: Calculate days since last played ===
def days_since_played(song):
    last = song.get("LastPlayedDate")
    if not last:
        return None
    last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - last_dt).days

# === STEP 4.9: Get artist play counts ===
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

# === STEP 4.10: BPM score calculation ===
def bpm_score(song_bpm, target_bpm, bpm_range, weight):
    """
    Returns a BPM-based score.
    Perfect match = full weight.
    Linear falloff inside range.
    Outside range = penalty.
    """
    if not song_bpm or not target_bpm:
        return 0

    diff = abs(song_bpm - target_bpm)

    if diff <= bpm_range:
        # Linear falloff
        return weight * (1 - (diff / bpm_range))
    else:
        # Outside acceptable range → penalty
        return -weight * 0.5
    
# === STEP 4.11: Get artist familiarity score ===
def get_artist_familiarity(artist, artist_play_counts, cap=50):
    plays = artist_play_counts.get(artist, 0)
    return min(plays / cap, 1.0)

# === STEP 4.12: Delete old auto-generated playlists ===
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


# === STEP 4.13: Build vibe from profile ===
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


# === STEP 4.14: Key distance calculation ===
def key_distance(key_a, key_b):
    """
    Returns circular distance between two keys (0–6).
    """
    if key_a not in KEY_MAP or key_b not in KEY_MAP:
        return None

    a = KEY_MAP[key_a]
    b = KEY_MAP[key_b]
    return min(abs(a - b), 12 - abs(a - b))

# === STEP 4.15: Derive user mood profile ===
def derive_user_mood_profile(play_history):
    mood_counter = Counter()

    for item in play_history:
        ab = extract_ab_tags(item)
        moods = normalize_moods(ab.get("mood", []))
        weight = item.get("PlayCount", 1)

        for mood, value in moods.items():
            mood_counter[mood] += value * weight

    if not mood_counter:
        return {}

    # Normalize to -1 → +1 range
    max_val = max(abs(v) for v in mood_counter.values()) or 1

    return {
        mood: round(value / max_val, 2)
        for mood, value in mood_counter.items()
    }


# === STEP 5: Score songs for a specific vibe ===
def score_songs_for_vibe(
        songs,
        top_genres,
        top_years,
        top_artists,
        preferred_key,
        vibe,
        user_moods,
        artist_play_counts,
        playlist_length,
        audio_prefs
):
    genre_set = set(g.lower() for g, _ in top_genres)
    year_set = set(y for y, _ in top_years)
    artist_set = set(top_artists)
    

    scored = []

    for song in songs:
        score = 0
        ab_moods = song.get("AB_Mood", [])
        song_moods = normalize_moods(song.get("AB_Mood", []))
        data = song.get("analysis") or {}

        genres = [g.lower().strip() for g in song.get("Genres", [])]
        year = song.get("ProductionYear")
        artists = song.get("Artists", [])

        required = [r.lower() for r in vibe.get("require_genre", [])]

        if preferred_key is not None and "preferred_key" not in vibe:
            vibe["preferred_key"] = preferred_key
            vibe["key_weight"] = vibe.get("key_weight", 5)
            vibe["key_mode"] = vibe.get("key_mode", "relative")
      
        #  Skip songs that don't match required genres
        if required:
            if not any(r in g for g in genres for r in required):
                continue
        if vibe.get("require_favorite") and not song.get("IsFavorite"):
            continue
        
        # === MOOD SCORING ===
        if user_moods and song_moods:
            mood_score = 0

            for mood, user_pref in user_moods.items():
                song_val = song_moods.get(mood)

                if song_val is None:
                    continue

                # Same direction → reward
                if user_pref * song_val > 0:
                    mood_score += abs(user_pref) * 2
                # Opposite → penalty
                elif user_pref * song_val < 0:
                    mood_score -= abs(user_pref) * 2

            score += mood_score
            
        # === BPM SCORING ===
        song_bpm = (
            get_analysis(song, "rhythm", "tempo")
            or song.get("AB_BPM")
        )

        if vibe.get("bpm_target") and vibe.get("bpm_range") and vibe.get("bpm_weight"):
            score += bpm_score(
                song_bpm,
                vibe["bpm_target"],
                vibe["bpm_range"],
                vibe["bpm_weight"]
            )
            
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

        # Danceability
        dance = get_analysis(song, "low_level", "danceability")

        if dance is not None and vibe.get("dance_weight"):
            target = audio_prefs.get("danceability")

            if target is not None:
                diff = abs(dance - target)
                score += (1 - diff) * vibe["dance_weight"]
            else:
                score += dance * vibe["dance_weight"]

            
        if vibe.get("preferred_moods", []) is not None:
            preferred_moods = vibe.get("preferred_moods", [])
            for mood in preferred_moods:
                if mood.lower() in ab_moods:
                    score += 6

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

        # Key compatibility
        song_key = (
            get_analysis(song, "tonal", "key")
            or song.get("AB_Key")
        )
        if song_key is not None:
            vibe_key = vibe.get("preferred_key")

            if vibe.get("key_mode") != "off" and song_key and vibe_key:
                dist = key_distance(song_key, vibe_key)

                if dist is not None:
                    if dist == 0:
                        score += vibe["key_weight"]          # perfect match
                    elif dist == 1:
                        score += vibe["key_weight"] * 0.6    # very compatible
                    elif dist == 2:
                        score += vibe["key_weight"] * 0.3    # somewhat compatible
                    elif dist >= 5:
                        score -= vibe["key_weight"] * 0.5    # clash

                    
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
        user_energy = audio_prefs.get("energy")

        if vibe.get("energy_cap") is not None:
            if energy > vibe["energy_cap"]:
                score -= 3
        else:
            if user_energy is not None:
                score += (1 - abs(energy - user_energy)) * 2
            else:
                score += energy * 2

        # Bass preference
        bass = get_analysis(song, "low_level", "bass_energy")

        if bass is not None and vibe.get("bass_weight"):
            user_bass = audio_prefs.get("bass")

            if user_bass is not None:
                score += (1 - abs(bass - user_bass)) * vibe["bass_weight"]
            else:
                score += bass * vibe["bass_weight"]

        # Favorite bonus
        if song.get("IsFavorite") and vibe.get("favorite_weight") is not None:
            score += vibe["favorite_weight"]
        
        # Skip penalty
        if get_was_song_skipped(song):
            score -= vibe["skip_penalty"]

        # Bass energy
        bass_energy = get_analysis(song, "low_level", "bass_energy")
        if bass_energy is not None and vibe.get("bass_weight"):
            score += bass_energy * vibe["bass_weight"]
            
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
        "IsPublic": False,
        "MediaType": "Audio",
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
    analised_music = load_analysed_music_index()
    history = get_play_history(user_id , analised_music)
    top_artists = get_top_artists(history)
    artist_play_counts = get_artist_play_counts(history)
    top_genres = get_top_genres(history)
    top_years = get_top_years(history)
    preferred_key = derive_preferred_key(history)
    user_moods = derive_user_mood_profile(history)
    audio_prefs = derive_audio_preferences(history)



    print("🎧 Top genres:")
    for genre, count in top_genres:
        print(f"{genre}: {count} plays")
    
    print("🎧 Top years:")
    for year, count in top_years:
        print(f"{year}: {count} plays")

    if not top_artists:
        print("No artists found in history.")
        return

    all_songs = get_all_music_data(user_id ,analised_music)
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
            preferred_key,
            vibe,
            user_moods,
            artist_play_counts,
            LENGTH_OF_PLAYLIST,
            audio_prefs
        )

        create_or_update_playlist(
            user_id,
            vibe["playlist_name"],
            song_ids
        )


#============= here be new code =============#

def load_analysed_music_index(path="analysed_audio.json"):
    if not os.path.exists(path):
        print("⚠️ analysed_audio.json not found")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    index = {}

    for t in data.get("tracks", []):
        jid = t.get("Id") or t.get("jellyfin_id")
        if jid:
            index[jid] = t.get("analysis")

    print(f"🔬 Loaded analysis for {len(index)} tracks")
    return index

def get_analysis(song, *keys, default=None):
    """
    Safe nested getter for song['analysis'].
    Example:
        get_analysis(song, "rhythm", "bpm")
    """
    data = song.get("analysis")
    if not isinstance(data, dict):
        return default

    for k in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(k)

    return data if data is not None else default

def normalize_energy(energy):
    if energy is None:
        return None

    # log-scale compression + clamp
    return min(1.0, max(0.0, math.log10(energy + 1) / 6))


def derive_audio_preferences(play_history):
    acc = {
        "danceability": [],
        "energy": [],
        "bass": [],
        "bpm": []
    }

    for song in play_history:
        weight = song.get("PlayCount", 1)

        d = get_analysis(song, "low_level", "danceability")
        e = get_analysis(song, "low_level", "energy")
        b = get_analysis(song, "low_level", "bass_energy")
        bpm = get_analysis(song, "rhythm", "tempo")

        if d is not None:
            acc["danceability"].extend([d] * weight)
        if e is not None:
            acc["energy"].extend([e] * weight)
        if b is not None:
            acc["bass"].extend([b] * weight)
        if bpm is not None:
            acc["bpm"].extend([bpm] * weight)

    def avg(x):
        return sum(x) / len(x) if x else None

    return {
        "danceability": avg(acc["danceability"]),
        "energy": avg(acc["energy"]),
        "bass": avg(acc["bass"]),
        "bpm": avg(acc["bpm"])
    }

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
        if not os.path.exists(PATH_TO_MUSIC_LIBRARY) or PATH_TO_MUSIC_LIBRARY=="":
            print("  Missing or invalid PATH_TO_MUSIC_LIBRARY in .env file.")
            print(" no AI analysis will be possible.")

            for user_id, user_name in get_all_users():
                print(f"\n Processing user: {user_name} (ID: {user_id})\n")
                Generate_playlist(user_id)
        else:
            print("  PATH_TO_MUSIC_LIBRARY loaded.")
            print("  Starting music analysis...")
            dump_jellyfin_raw()
            createIndex()
            print("  Music analysis complete.\n")

            for user_id, user_name in get_all_users():
                print(f"\n Processing user: {user_name} (ID: {user_id})\n")
                Generate_playlist(user_id)

    print("\n=========================================\n")
    print("\n  Curated playlist generation complete!  \n") 
    print("\n=========================================\n")

if __name__ == "__main__":
    main()