from typing import Any, Optional
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from app.config import get_settings
from app.core.models import UnifiedTrack
from app.providers.base import BaseMusicProvider


class SpotifyProvider(BaseMusicProvider):
    """Spotify integration via Spotipy."""

    provider_name: str = "spotify"

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[spotipy.Spotify] = None

    async def authenticate(self) -> bool:
        """Initialize Spotipy client with OAuth credentials."""
        if not self.settings.SPOTIFY_CLIENT_ID or not self.settings.SPOTIFY_CLIENT_SECRET:
            return False

        auth_manager = SpotifyOAuth(
            client_id=self.settings.SPOTIFY_CLIENT_ID,
            client_secret=self.settings.SPOTIFY_CLIENT_SECRET,
            redirect_uri=self.settings.SPOTIFY_REDIRECT_URI,
            scope="playlist-read-private playlist-modify-public playlist-modify-private user-library-read",
        )
        self.client = spotipy.Spotify(auth_manager=auth_manager)
        return True

    def _to_unified_track(self, item: dict[str, Any]) -> UnifiedTrack:
        """Convert Spotify track object into UnifiedTrack."""
        track = item.get("track", item)
        external_ids = track.get("external_ids", {})
        artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])
        album = track.get("album", {})
        images = album.get("images", [])
        cover_url = images[0].get("url") if images else None

        return UnifiedTrack(
            isrc=external_ids.get("isrc"),
            title=track.get("name", "Unknown Title"),
            artist=artists or "Unknown Artist",
            album=album.get("name"),
            duration_ms=track.get("duration_ms"),
            genres_raw="",
            cover_url=cover_url,
            spotify_id=track.get("id"),
        )

    async def search_tracks(self, query: str, limit: int = 20) -> list[UnifiedTrack]:
        """Search Spotify for matching tracks."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            return []

        results = self.client.search(q=query, limit=limit, type="track")
        tracks_data = results.get("tracks", {}).get("items", [])
        return [self._to_unified_track(t) for t in tracks_data]

    async def get_playlist(self, playlist_id: str) -> list[UnifiedTrack]:
        """Fetch all tracks from a Spotify playlist."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            return []

        tracks: list[UnifiedTrack] = []
        results = self.client.playlist_items(playlist_id)
        while results:
            for item in results.get("items", []):
                if item.get("track"):
                    tracks.append(self._to_unified_track(item))
            results = self.client.next(results) if results.get("next") else None

        return tracks

    async def create_playlist(
        self, name: str, tracks: list[UnifiedTrack], description: str = ""
    ) -> str:
        """Create a new playlist in Spotify and add tracks."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            raise RuntimeError("Spotify client is not authenticated")

        user_id = self.client.me()["id"]
        playlist = self.client.user_playlist_create(
            user=user_id, name=name, public=False, description=description
        )
        playlist_id = playlist["id"]

        track_uris = [
            f"spotify:track:{t.spotify_id}" for t in tracks if t.spotify_id
        ]
        # Spotipy accepts at most 100 tracks per batch
        for i in range(0, len(track_uris), 100):
            self.client.playlist_add_items(playlist_id, track_uris[i : i + 100])

        return playlist_id

    async def get_track(self, track_id: str) -> Optional[UnifiedTrack]:
        """Get track by Spotify ID."""
        if not self.client:
            await self.authenticate()
        if not self.client:
            return None

        data = self.client.track(track_id)
        return self._to_unified_track(data) if data else None
