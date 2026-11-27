from pathlib import Path
from typing import Any, Optional
import httpx
from mutagen.id3 import ID3, USLT, ID3NoHeaderError

from app.core.models import UnifiedTrack
from app.providers.rate_limiter import AsyncRateLimiter


class LyricsEngine:
    """Lyrics engine powered by LRCLIB (open source, no API key required).

    Supports synced (.LRC) and plain lyrics, disk export, and ID3 embedding.
    """

    LRCLIB_BASE_URL = "https://lrclib.net/api"

    def __init__(
        self,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.25)
        self._transport = transport

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def fetch_lyrics(self, track: UnifiedTrack) -> tuple[Optional[str], Optional[str]]:
        """Fetch lyrics for a given track from LRCLIB.

        Returns: (synced_lyrics_lrc, plain_lyrics)
        """
        params: dict[str, Any] = {
            "track_name": track.title,
            "artist_name": track.artist,
        }
        if track.album:
            params["album_name"] = track.album
        if track.duration_ms:
            params["duration"] = round(track.duration_ms / 1000)

        async with self._build_client() as client:
            try:
                # 1. Exact match attempt via /api/get
                await self._rate_limiter.acquire()
                resp = await client.get(f"{self.LRCLIB_BASE_URL}/get", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    synced = data.get("syncedLyrics")
                    plain = data.get("plainLyrics")
                    if synced or plain:
                        return synced, plain

                # 2. Fallback search via /api/search
                await self._rate_limiter.acquire()
                search_query = f"{track.artist} {track.title}".strip()
                search_resp = await client.get(
                    f"{self.LRCLIB_BASE_URL}/search", params={"q": search_query}
                )
                if search_resp.status_code == 200:
                    results = search_resp.json()
                    if isinstance(results, list) and results:
                        best = results[0]
                        return best.get("syncedLyrics"), best.get("plainLyrics")
            except Exception as e:
                print(f"[LyricsEngine] Error fetching lyrics for '{track.title}': {e}")

        return None, None

    async def search_lyrics(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        """Search LRCLIB directly for tracks with synced or plain lyrics."""
        clean = query.strip()
        if not clean:
            return []

        async with self._build_client() as client:
            try:
                await self._rate_limiter.acquire()
                resp = await client.get(f"{self.LRCLIB_BASE_URL}/search", params={"q": clean})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data[:limit]
            except Exception as e:
                print(f"[LyricsEngine] Search error for '{clean}': {e}")
        return []

    def save_lrc_file(self, track: UnifiedTrack, output_dir: Optional[Path] = None) -> Optional[Path]:
        """Save synced lyrics as a .lrc file on disk alongside the audio file."""
        if not track.lyrics_synced:
            return None

        if track.local_path:
            lrc_path = Path(track.local_path).with_suffix(".lrc")
        else:
            base_dir = output_dir or Path("./downloads")
            base_dir.mkdir(parents=True, exist_ok=True)
            safe_name = f"{track.artist} - {track.title}".replace("/", "_").replace("\\", "_")
            lrc_path = base_dir / f"{safe_name}.lrc"

        lrc_path.write_text(track.lyrics_synced, encoding="utf-8")
        return lrc_path

    def embed_lyrics_to_audio(
        self, file_path: Path, plain_lyrics: Optional[str]
    ) -> bool:
        """Embed plain text lyrics into MP3 file ID3 tags (USLT frame)."""
        if not plain_lyrics or not file_path.exists():
            return False

        try:
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()

            tags.delall("USLT")
            tags.add(
                USLT(
                    encoding=3,
                    lang="eng",
                    desc="Lyrics",
                    text=plain_lyrics,
                )
            )
            tags.save(file_path)
            return True
        except Exception as e:
            print(f"[LyricsEngine] Failed to embed lyrics into {file_path}: {e}")
            return False
