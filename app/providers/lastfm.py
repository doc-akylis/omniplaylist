from typing import Any, Optional
import httpx

from app.config import get_settings


class LastFMProvider:
    """Optional Last.fm API client for genre tags, similar tracks, and similar artists.

    Degrades gracefully (returns empty results without error) when LASTFM_API_KEY is empty.
    """

    BASE_URL = "https://ws.audioscrobbler.com/2.0/"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = api_key if api_key is not None else get_settings().LASTFM_API_KEY
        self.timeout = timeout
        self._transport = transport

    def is_configured(self) -> bool:
        """Return True if LASTFM_API_KEY is set."""
        return bool(self.api_key and self.api_key.strip())

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def get_track_tags(self, artist: str, title: str, limit: int = 8) -> list[str]:
        """Fetch top community genre/mood tags for a track from Last.fm."""
        if not self.is_configured() or not artist or not title:
            return []

        async with self._build_client() as client:
            try:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "method": "track.getTopTags",
                        "artist": artist,
                        "track": title,
                        "api_key": self.api_key,
                        "format": "json",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tags = (data.get("toptags") or {}).get("tag") or []
                    if isinstance(tags, dict):
                        tags = [tags]
                    return [t["name"].strip().lower() for t in tags[:limit] if t.get("name")]
            except Exception as e:
                print(f"[LastFMProvider] Top tags error ({artist} - {title}): {e}")
        return []

    async def get_similar_tracks(
        self, artist: str, title: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Fetch similar tracks from Last.fm."""
        if not self.is_configured() or not artist or not title:
            return []

        async with self._build_client() as client:
            try:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "method": "track.getSimilar",
                        "artist": artist,
                        "track": title,
                        "limit": limit,
                        "api_key": self.api_key,
                        "format": "json",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    tracks = (data.get("similartracks") or {}).get("track") or []
                    if isinstance(tracks, dict):
                        tracks = [tracks]
                    return [
                        {
                            "title": t.get("name", ""),
                            "artist": (t.get("artist") or {}).get("name", ""),
                            "match": float(t.get("match", 0.0)),
                        }
                        for t in tracks[:limit]
                        if t.get("name")
                    ]
            except Exception as e:
                print(f"[LastFMProvider] Similar tracks error ({artist} - {title}): {e}")
        return []

    async def get_similar_artists(self, artist: str, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch similar artists from Last.fm."""
        if not self.is_configured() or not artist:
            return []

        async with self._build_client() as client:
            try:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "method": "artist.getSimilar",
                        "artist": artist,
                        "limit": limit,
                        "api_key": self.api_key,
                        "format": "json",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    artists = (data.get("similarartists") or {}).get("artist") or []
                    if isinstance(artists, dict):
                        artists = [artists]
                    return [
                        {"name": a.get("name", ""), "match": float(a.get("match", 0.0))}
                        for a in artists[:limit]
                        if a.get("name")
                    ]
            except Exception as e:
                print(f"[LastFMProvider] Similar artists error ({artist}): {e}")
        return []
