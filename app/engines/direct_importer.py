import asyncio
import json
import re
from typing import Optional
import httpx
import yt_dlp

from app.core.models import Playlist, UnifiedTrack


class DirectImporter:
    """Imports public playlists from Spotify, YouTube, and Deezer via public URLs without authentication."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    async def import_from_url(self, url: str) -> tuple[Optional[Playlist], list[UnifiedTrack]]:
        """Detect provider and extract playlist metadata and tracks."""
        clean_url = url.strip()

        if "spotify.com" in clean_url:
            return await self._import_spotify(clean_url)
        elif "youtube.com" in clean_url or "youtu.be" in clean_url:
            return await self._import_youtube(clean_url)
        elif "deezer.com" in clean_url:
            return await self._import_deezer(clean_url)
        else:
            raise ValueError("URL não reconhecida. Suportados: Spotify, YouTube e Deezer.")

    async def _import_spotify(self, url: str) -> tuple[Optional[Playlist], list[UnifiedTrack]]:
        """Scrape Spotify public playlist through embed page."""
        match = re.search(r"playlist[/:]([a-zA-Z0-9]+)", url)
        if not match:
            return None, []

        playlist_id = match.group(1)
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(embed_url, headers=headers)
            if resp.status_code != 200:
                return None, []

            html = resp.text

            # Look for NEXT_DATA script block
            next_data_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
            tracks: list[UnifiedTrack] = []
            title = f"Spotify Playlist ({playlist_id})"

            if next_data_match:
                try:
                    payload = json.loads(next_data_match.group(1))
                    entity_state = (
                        payload.get("props", {})
                        .get("pageProps", {})
                        .get("state", {})
                        .get("data", {})
                        .get("entity", {})
                    )
                    title = entity_state.get("name") or title
                    track_list = entity_state.get("trackList", [])

                    for item in track_list:
                        t_title = item.get("title", "Unknown")
                        t_artist = item.get("subtitle", "Unknown")
                        t_duration = item.get("duration", 0)
                        tracks.append(
                            UnifiedTrack(
                                title=t_title,
                                artist=t_artist,
                                duration_ms=t_duration,
                                spotify_id=item.get("id"),
                            )
                        )
                except Exception as e:
                    print(f"[DirectImporter] Spotify json parsing failed: {e}")

            # Fallback regex if __NEXT_DATA__ structure differs
            if not tracks:
                track_matches = re.findall(
                    r'"name":\s*"([^"]+)",\s*"artists":\s*\[\{"name":\s*"([^"]+)"', html
                )
                for t_name, t_art in track_matches:
                    tracks.append(UnifiedTrack(title=t_name, artist=t_art))

            playlist = Playlist(
                name=title,
                source_provider="spotify",
                external_id=playlist_id,
            )
            return playlist, tracks

    async def _import_youtube(self, url: str) -> tuple[Optional[Playlist], list[UnifiedTrack]]:
        """Extract public YouTube playlist via yt-dlp flat playlist extraction."""
        loop = asyncio.get_event_loop()

        def _extract():
            ydl_opts = {
                "extract_flat": True,
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, _extract)
        if not info:
            return None, []

        title = info.get("title", "YouTube Playlist")
        entries = info.get("entries", [])
        tracks: list[UnifiedTrack] = []

        for entry in entries:
            raw_title = entry.get("title", "Unknown Title")
            # Usually format is "Artist - Title" on YouTube
            if " - " in raw_title:
                parts = raw_title.split(" - ", 1)
                artist, track_name = parts[0].strip(), parts[1].strip()
            else:
                artist = entry.get("uploader") or "YouTube Artist"
                track_name = raw_title

            tracks.append(
                UnifiedTrack(
                    title=track_name,
                    artist=artist,
                    ytmusic_id=entry.get("id"),
                    duration_ms=int(entry.get("duration", 0) * 1000) if entry.get("duration") else None,
                )
            )

        playlist = Playlist(
            name=title,
            source_provider="ytmusic",
            external_id=info.get("id"),
        )
        return playlist, tracks

    async def _import_deezer(self, url: str) -> tuple[Optional[Playlist], list[UnifiedTrack]]:
        """Extract public Deezer playlist via public REST API."""
        match = re.search(r"playlist[/:]([0-9]+)", url)
        if not match:
            return None, []

        playlist_id = match.group(1)
        api_url = f"https://api.deezer.com/playlist/{playlist_id}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(api_url)
            if resp.status_code != 200:
                return None, []

            data = resp.json()
            title = data.get("title", "Deezer Playlist")
            tracks_raw = data.get("tracks", {}).get("data", [])
            tracks: list[UnifiedTrack] = []

            for item in tracks_raw:
                artist = item.get("artist", {}).get("name", "Unknown Artist")
                album = item.get("album", {}).get("title")
                cover = item.get("album", {}).get("cover_big")
                duration = item.get("duration", 0) * 1000

                tracks.append(
                    UnifiedTrack(
                        title=item.get("title", "Unknown Title"),
                        artist=artist,
                        album=album,
                        cover_url=cover,
                        duration_ms=duration,
                        deezer_id=str(item.get("id")),
                        preview_url=item.get("preview"),
                        isrc=item.get("isrc"),
                    )
                )

            playlist = Playlist(
                name=title,
                source_provider="deezer",
                external_id=playlist_id,
            )
            return playlist, tracks
