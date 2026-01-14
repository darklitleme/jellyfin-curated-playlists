import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import os

# ==============================
# CONFIG
# ==============================
load_dotenv()

JELLYFIN_URL = os.getenv("JELLYFIN_URL")
API_KEY = os.getenv("JELLYFIN_API_KEY")

OUTPUT_FILE = "jellyfin_music_raw.json"
PAGE_SIZE = 500

HEADERS = {
    "X-Emby-Token": API_KEY
}


# ==============================
# FETCH ALL AUDIO ITEMS (PAGED)
# ==============================
def fetch_all_audio_items():
    items = []
    start = 0
    total = None

    print("📡 Fetching Jellyfin music library (raw)...")

    while True:
        params = {
            "IncludeItemTypes": "Audio",
            "Recursive": "true",
            "StartIndex": start,
            "Limit": PAGE_SIZE,
            "Fields": ",".join([
                "Path",
                "ProviderIds",
                "Genres",
                "Tags",
                "Studios",
                "People",
                "MediaSources",
                "MediaStreams",
                "ImageTags",
                "ImageBlurHashes",
                "AlbumInfo",
                "AudioInfo",
                "DateCreated",
                "Overview"
            ])
        }

        r = requests.get(
            f"{JELLYFIN_URL}/Items",
            headers=HEADERS,
            params=params,
            timeout=60
        )
        r.raise_for_status()

        data = r.json()
        batch = data.get("Items", [])
        if total is None:
            total = data.get("TotalRecordCount", 0)

        items.extend(batch)
        start += len(batch)

        print(f"  → Loaded {len(items)} / {total}")

        if len(batch) == 0 or start >= total:
            break

    return items

def dump_jellyfin_raw():
    items = fetch_all_audio_items()
    print(f"💾 Writing {len(items)} raw tracks to {OUTPUT_FILE}")

    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "track_count": len(items),
        "tracks": items
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("✅ Jellyfin raw dump complete")



