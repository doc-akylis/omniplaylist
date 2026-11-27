from typing import Any, Optional
import httpx

from app.core.models import UnifiedTrack
from app.providers.base import BaseMusicProvider


class DeezerProvider(BaseMusicProvider):
    """Deezer integration using the open public REST API (no OAuth credentials required).

    Provides reliable ISRC, 30-second high-quality audio previews, release dates, and HD cover art.
    """

    provider_name: str = "deezer"
    BASE_URL = "https://api.deezer.com"

    def __init__(
        self,
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def authenticate(self) -> bool:
        """Deezer search and metadata retrieval does not require authentication."""
        return True

    def _to_unified_track(self, item: dict[str, Any]) -> UnifiedTrack:
        """Convert a Deezer track JSON item to a UnifiedTrack instance."""
        artist_obj = item.get("artist", {})
        artist_name = (
            artist_obj.get("name")
            if isinstance(artist_obj, dict)
            else str(artist_obj or "Unknown Artist")
        )

        album_obj = item.get("album", {})
        album_name = album_obj.get("title") if isinstance(album_obj, dict) else None

        # Prefer XL or Big cover art
        cover_url = None
        if isinstance(album_obj, dict):
            cover_url = (
                album_obj.get("cover_xl")
                or album_obj.get("cover_big")
                or album_obj.get("cover_medium")
            )

        duration_sec = item.get("duration", 0)
        duration_ms = duration_sec * 1000 if duration_sec else None

        # Parse release year if available
        release_date = item.get("release_date")
        release_year = None
        if release_date and len(release_date) >= 4:
            try:
                release_year = int(release_date[:4])
            except ValueError:
                pass

        return UnifiedTrack(
            isrc=item.get("isrc"),
            title=item.get("title") or item.get("title_short") or "Unknown Title",
            artist=artist_name,
            album=album_name,
            duration_ms=duration_ms,
            genres_raw="",
            cover_url=cover_url,
            hd_cover_url=cover_url,
            deezer_id=str(item.get("id")) if item.get("id") else None,
            preview_url=item.get("preview"),
            bpm=float(item["bpm"]) if item.get("bpm") else None,
            release_year=release_year,
        )

    async def search_tracks(self, query: str, limit: int = 20) -> list[UnifiedTrack]:
        """Search Deezer for tracks."""
        async with self._build_client() as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/search",
                    params={"q": query, "limit": limit},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [self._to_unified_track(t) for t in data.get("data", [])]
            except Exception as e:
                print(f"[DeezerProvider] Search error for '{query}': {e}")
        return []

    async def get_track(self, track_id: str) -> Optional[UnifiedTrack]:
        """Retrieve full details for a single track by Deezer ID (including ISRC & BPM)."""
        async with self._build_client() as client:
            try:
                resp = await client.get(f"{self.BASE_URL}/track/{track_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" not in data:
                        return self._to_unified_track(data)
            except Exception as e:
                print(f"[DeezerProvider] Get track error ({track_id}): {e}")
        return None

    async def get_playlist(self, playlist_id: str) -> list[UnifiedTrack]:
        """Fetch all tracks in a Deezer public playlist."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(f"{self.BASE_URL}/playlist/{playlist_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    tracks_data = data.get("tracks", {}).get("data", [])
                    return [self._to_unified_track(t) for t in tracks_data]
            except Exception as e:
                print(f"[DeezerProvider] Get playlist error ({playlist_id}): {e}")
        return []

    async def create_playlist(
        self, name: str, tracks: list[UnifiedTrack], description: str = ""
    ) -> str:
        """Create playlist requires user OAuth on Deezer.

        Returns simulated/placeholder identifier when unauthenticated.
        """
        return f"deezer-playlist-{name.lower().replace(' ', '-')}"
