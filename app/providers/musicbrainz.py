from dataclasses import dataclass
from typing import Any, Optional
import httpx

from app.providers.rate_limiter import AsyncRateLimiter


@dataclass
class MusicBrainzMatch:
    """Structured metadata returned by MusicBrainz + Cover Art Archive."""

    recording_id: Optional[str] = None
    isrc: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    release_id: Optional[str] = None
    release_year: Optional[int] = None
    hd_cover_url: Optional[str] = None


class MusicBrainzProvider:
    """Async MusicBrainz + Cover Art Archive client with strict 1 req/s rate limit.

    Requires no API key, but strictly enforces:
    - Mandatory User-Agent identifying OmniPlaylist 2.0
    - Minimum 1.0 second interval between consecutive MusicBrainz API requests
    """

    BASE_URL = "https://musicbrainz.org/ws/2"
    CAA_URL = "https://coverartarchive.org"
    USER_AGENT = "OmniPlaylist/2.0 (https://github.com/doc-akylis/omniplaylist)"

    def __init__(
        self,
        timeout: float = 10.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=1.0)
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "headers": {
                "User-Agent": self.USER_AGENT,
                "Accept": "application/json",
            },
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _parse_year(date_str: Optional[str]) -> Optional[int]:
        if date_str and len(date_str) >= 4:
            try:
                return int(date_str[:4])
            except ValueError:
                return None
        return None

    def _extract_from_recording(self, rec: dict[str, Any]) -> MusicBrainzMatch:
        recording_id = rec.get("id")
        isrcs = rec.get("isrcs") or []
        isrc = isrcs[0] if isinstance(isrcs, list) and isrcs else None

        artist_name = None
        credits = rec.get("artist-credit") or []
        if credits and isinstance(credits[0], dict):
            artist_name = credits[0].get("name") or (credits[0].get("artist") or {}).get("name")

        release_id = None
        album_title = None
        release_year = self._parse_year(rec.get("first-release-date"))
        releases = rec.get("releases") or []
        if releases and isinstance(releases[0], dict):
            release_id = releases[0].get("id")
            album_title = releases[0].get("title")
            if release_year is None:
                release_year = self._parse_year(releases[0].get("date"))

        return MusicBrainzMatch(
            recording_id=recording_id,
            isrc=isrc,
            title=rec.get("title"),
            artist=artist_name,
            album=album_title,
            release_id=release_id,
            release_year=release_year,
        )

    async def lookup_by_isrc(self, isrc: str) -> Optional[MusicBrainzMatch]:
        """Lookup a recording by ISRC via MusicBrainz WS2."""
        if not isrc or not isrc.strip():
            return None

        clean_isrc = isrc.strip().upper()
        await self._rate_limiter.acquire()
        async with self._build_client() as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/recording",
                    params={"query": f"isrc:{clean_isrc}", "fmt": "json", "limit": 1},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    recordings = data.get("recordings") or []
                    if recordings:
                        match = self._extract_from_recording(recordings[0])
                        if not match.isrc:
                            match.isrc = clean_isrc
                        if match.release_id:
                            match.hd_cover_url = await self.fetch_cover_art(match.release_id)
                        return match
            except Exception as e:
                print(f"[MusicBrainzProvider] ISRC lookup error ({clean_isrc}): {e}")
        return None

    async def search_recording(self, artist: str, title: str) -> Optional[MusicBrainzMatch]:
        """Search recording by artist and title via MusicBrainz WS2."""
        if not artist and not title:
            return None

        parts = []
        if artist:
            parts.append(f'artist:"{artist.strip()}"')
        if title:
            parts.append(f'recording:"{title.strip()}"')
        query = " AND ".join(parts)

        await self._rate_limiter.acquire()
        async with self._build_client() as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/recording",
                    params={"query": query, "fmt": "json", "limit": 3},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    recordings = data.get("recordings") or []
                    if recordings:
                        match = self._extract_from_recording(recordings[0])
                        if match.release_id:
                            match.hd_cover_url = await self.fetch_cover_art(match.release_id)
                        return match
            except Exception as e:
                print(f"[MusicBrainzProvider] Search error ({artist} - {title}): {e}")
        return None

    async def search_recordings(self, query_text: str, limit: int = 8) -> list[MusicBrainzMatch]:
        """Search recordings by free-text query or ISRC via MusicBrainz WS2."""
        clean = query_text.strip()
        if not clean:
            return []

        await self._rate_limiter.acquire()
        async with self._build_client() as client:
            try:
                resp = await client.get(
                    f"{self.BASE_URL}/recording",
                    params={"query": clean, "fmt": "json", "limit": limit},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    recordings = data.get("recordings") or []
                    matches: list[MusicBrainzMatch] = []
                    for rec in recordings[:limit]:
                        m = self._extract_from_recording(rec)
                        if m.release_id:
                            # Direct Cover Art Archive front-500 image URL pattern (avoids N extra requests)
                            m.hd_cover_url = f"{self.CAA_URL}/release/{m.release_id}/front-500"
                        matches.append(m)
                    return matches
            except Exception as e:
                print(f"[MusicBrainzProvider] Free-text search error ({clean}): {e}")
        return []

    async def fetch_cover_art(self, release_id: str) -> Optional[str]:
        """Fetch HD cover art URL from Cover Art Archive for a MusicBrainz release ID."""
        if not release_id:
            return None

        async with self._build_client() as client:
            try:
                resp = await client.get(f"{self.CAA_URL}/release/{release_id}", follow_redirects=True)
                if resp.status_code == 200:
                    data = resp.json()
                    images = data.get("images") or []
                    for img in images:
                        if img.get("front"):
                            thumbs = img.get("thumbnails") or {}
                            return thumbs.get("1200") or thumbs.get("large") or img.get("image")
                    if images:
                        thumbs = images[0].get("thumbnails") or {}
                        return thumbs.get("1200") or thumbs.get("large") or images[0].get("image")
            except Exception as e:
                print(f"[MusicBrainzProvider] Cover Art Archive error ({release_id}): {e}")
        return None
