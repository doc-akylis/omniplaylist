from pathlib import Path
from typing import Any, Optional
from ytmusicapi import YTMusic
from app.config import get_settings
from app.core.models import UnifiedTrack
from app.providers.base import BaseMusicProvider


class YTMusicProvider(BaseMusicProvider):
    """YouTube Music integration via ytmusicapi."""

    provider_name: str = "ytmusic"

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[YTMusic] = None

    async def authenticate(self) -> bool:
        """Initialize YTMusic client using OAuth file if present, else anonymous."""
        auth_file = Path(self.settings.YTMUSIC_AUTH_FILE)
        if auth_file.exists():
            self.client = YTMusic(str(auth_file))
        else:
            self.client = YTMusic()
        return True

    def _to_unified_track(self, item: dict[str, Any]) -> UnifiedTrack:
        """Normalize YTMusic item dictionary to UnifiedTrack."""
        title = item.get("title", "Unknown Title")
        artists_list = item.get("artists", [])
        artist_name = (
            ", ".join([a.get("name", "") for a in artists_list])
            if isinstance(artists_list, list)
            else str(artists_list or "Unknown Artist")
        )
        album_dict = item.get("album") or {}
        album_name = album_dict.get("name") if isinstance(album_dict, dict) else None

        thumbnails = item.get("thumbnails", [])
        cover_url = thumbnails[-1].get("url") if thumbnails else None

        duration_seconds = item.get("duration_seconds")
        duration_ms = int(duration_seconds * 1000) if duration_seconds else None

        return UnifiedTrack(
            isrc=None,  # YTMusic API does not reliably return ISRC directly
            title=title,
            artist=artist_name,
            album=album_name,
            duration_ms=duration_ms,
            genres_raw="",
            cover_url=cover_url,
            ytmusic_id=item.get("videoId"),
        )

    async def search_tracks(self, query: str, limit: int = 20) -> list[UnifiedTrack]:
        """Search YouTube Music for songs."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            return []

        results = self.client.search(query=query, filter="songs", limit=limit)
        return [self._to_unified_track(r) for r in results if r.get("videoId")]

    async def get_playlist(self, playlist_id: str) -> list[UnifiedTrack]:
        """Fetch all tracks from a YouTube Music playlist."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            return []

        playlist_data = self.client.get_playlist(playlistId=playlist_id, limit=None)
        tracks_data = playlist_data.get("tracks", [])
        return [self._to_unified_track(t) for t in tracks_data if t.get("videoId")]

    async def create_playlist(
        self, name: str, tracks: list[UnifiedTrack], description: str = ""
    ) -> str:
        """Create a new playlist in YouTube Music."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            raise RuntimeError("YTMusic client is not initialized")

        video_ids = [t.ytmusic_id for t in tracks if t.ytmusic_id]
        playlist_id = self.client.create_playlist(
            title=name,
            description=description,
            video_ids=video_ids,
        )
        return str(playlist_id)

    async def get_track(self, track_id: str) -> Optional[UnifiedTrack]:
        """Get song details from YouTube Music."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            return None

        data = self.client.get_song(videoId=track_id)
        if not data:
            return None

        video_details = data.get("videoDetails", {})
        return UnifiedTrack(
            title=video_details.get("title", "Unknown"),
            artist=video_details.get("author", "Unknown"),
            duration_ms=int(video_details.get("lengthSeconds", 0)) * 1000,
            ytmusic_id=track_id,
            cover_url=(video_details.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url")),
        )
