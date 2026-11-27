from dataclasses import dataclass
from typing import Any, Optional
import httpx


@dataclass
class ITunesMatch:
    """Metadata and media links returned by iTunes Search API."""

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    hd_cover_url: Optional[str] = None
    preview_url: Optional[str] = None
    release_year: Optional[int] = None
    genre: Optional[str] = None


class ITunesProvider:
    """Async iTunes Public Search API client (no API key required)."""

    BASE_URL = "https://itunes.apple.com/search"

    def __init__(
        self,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def search_tracks(self, query: str, limit: int = 10) -> list[ITunesMatch]:
        """Search iTunes for multiple tracks and return HD covers, previews, and release years."""
        term = query.strip()
        if not term:
            return []

        params = {"term": term, "entity": "song", "limit": limit}
        async with self._build_client() as client:
            try:
                resp = await client.get(self.BASE_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results") or []
                    matches: list[ITunesMatch] = []
                    for item in results:
                        art_100 = item.get("artworkUrl100")
                        hd_cover = art_100.replace("100x100bb", "1400x1400bb") if art_100 else None
                        release_date = item.get("releaseDate")
                        release_year = None
                        if release_date and len(release_date) >= 4:
                            try:
                                release_year = int(release_date[:4])
                            except ValueError:
                                pass
                        matches.append(
                            ITunesMatch(
                                title=item.get("trackName"),
                                artist=item.get("artistName"),
                                album=item.get("collectionName"),
                                hd_cover_url=hd_cover,
                                preview_url=item.get("previewUrl"),
                                release_year=release_year,
                                genre=item.get("primaryGenreName"),
                            )
                        )
                    return matches
            except Exception as e:
                print(f"[ITunesProvider] Search error for '{term}': {e}")
        return []

    async def search_track(self, artist: str, title: str) -> Optional[ITunesMatch]:
        """Search iTunes for a single best-matching track."""
        term = f"{artist} {title}".strip()
        matches = await self.search_tracks(term, limit=3)
        return matches[0] if matches else None
