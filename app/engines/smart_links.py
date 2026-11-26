from typing import Any, Optional
import httpx
from app.core.models import UnifiedTrack


class SmartLinkEngine:
    """Generates universal smart links (Odesli / Songlink) for multi-platform music sharing."""

    BASE_API = "https://api.song.link/v1-alpha.1/links"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout

    def get_quick_universal_url(self, track: UnifiedTrack) -> str:
        """Construct instant redirect Songlink URL based on available platform IDs."""
        if track.spotify_id:
            return f"https://song.link/s/{track.spotify_id}"
        elif track.deezer_id:
            return f"https://song.link/d/{track.deezer_id}"
        elif track.ytmusic_id:
            return f"https://song.link/y/{track.ytmusic_id}"
        else:
            query = f"{track.artist} {track.title}".replace(" ", "+")
            return f"https://song.link/search?q={query}"

    async def fetch_platform_links(self, track: UnifiedTrack) -> dict[str, Any]:
        """Query Odesli API to resolve concrete links for Spotify, Apple Music, YouTube, Deezer, and Tidal."""
        target_url = None
        if track.spotify_id:
            target_url = f"https://open.spotify.com/track/{track.spotify_id}"
        elif track.deezer_id:
            target_url = f"https://www.deezer.com/track/{track.deezer_id}"
        elif track.ytmusic_id:
            target_url = f"https://www.youtube.com/watch?v={track.ytmusic_id}"

        if not target_url:
            return {"universal_url": self.get_quick_universal_url(track), "links": {}}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(self.BASE_API, params={"url": target_url})
                if resp.status_code == 200:
                    data = resp.json()
                    links = {}
                    for platform, info in data.get("linksByPlatform", {}).items():
                        links[platform] = info.get("url")
                    return {
                        "page_url": data.get("pageUrl"),
                        "links": links,
                    }
            except Exception as e:
                print(f"[SmartLinkEngine] Odesli fetch error: {e}")

        return {"universal_url": self.get_quick_universal_url(track), "links": {}}
