import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional
import yt_dlp
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3
import httpx

from app.config import get_settings
from app.core.models import UnifiedTrack


class TrackDownloader:
    """Handles audio download via yt-dlp, FFmpeg audio conversion, and Mutagen ID3 tagging."""

    def __init__(self, output_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.output_dir = output_dir or self.settings.DOWNLOAD_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.queue: asyncio.Queue[tuple[UnifiedTrack, Optional[Callable[[float, str], Any]]]] = (
            asyncio.Queue()
        )
        self.is_running = False

    def _apply_id3_tags(self, file_path: Path, track: UnifiedTrack) -> None:
        """Write ID3 metadata and album art using Mutagen."""
        try:
            # Write standard text tags
            try:
                audio = EasyID3(file_path)
            except Exception:
                audio = EasyID3()
                audio.save(file_path)

            audio["title"] = track.title
            audio["artist"] = track.artist
            if track.album:
                audio["album"] = track.album
            if track.genres:
                audio["genre"] = track.genres[0]
            if track.isrc:
                audio["isrc"] = track.isrc
            audio.save(file_path)

            # Write album art if cover URL is available
            if track.cover_url:
                with httpx.Client(timeout=10) as client:
                    resp = client.get(track.cover_url)
                    if resp.status_code == 200:
                        id3 = ID3(file_path)
                        id3.add(
                            APIC(
                                encoding=3,
                                mime="image/jpeg",
                                type=3,
                                desc="Cover",
                                data=resp.content,
                            )
                        )
                        id3.save(file_path)
        except Exception as e:
            print(f"[Downloader] Error writing ID3 tags to {file_path}: {e}")

    async def download_track(
        self,
        track: UnifiedTrack,
        progress_callback: Optional[Callable[[float, str], Any]] = None,
    ) -> Optional[Path]:
        """Download track audio using yt-dlp, convert with FFmpeg, and apply tags."""
        query = (
            f"https://www.youtube.com/watch?v={track.ytmusic_id}"
            if track.ytmusic_id
            else f"ytsearch1:{track.artist} - {track.title} audio"
        )

        safe_filename = f"{track.artist} - {track.title}".replace("/", "_").replace("\\", "_")
        target_template = str(self.output_dir / f"{safe_filename}.%(ext)s")
        final_mp3 = self.output_dir / f"{safe_filename}.mp3"

        if final_mp3.exists():
            if progress_callback:
                progress_callback(1.0, f"Already downloaded: {final_mp3.name}")
            return final_mp3

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": target_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320",
                }
            ],
            "quiet": True,
            "no_warnings": True,
        }

        loop = asyncio.get_event_loop()

        def _run_ytdl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([query])

        if progress_callback:
            progress_callback(0.2, f"Downloading: {track.title}")

        await loop.run_in_executor(None, _run_ytdl)

        if final_mp3.exists():
            if progress_callback:
                progress_callback(0.8, f"Tagging metadata: {track.title}")
            await loop.run_in_executor(None, self._apply_id3_tags, final_mp3, track)

            if progress_callback:
                progress_callback(1.0, f"Completed: {track.title}")

            track.local_path = str(final_mp3)
            return final_mp3

        return None

    async def start_worker(self) -> None:
        """Background queue processor worker."""
        self.is_running = True
        while self.is_running:
            track, cb = await self.queue.get()
            try:
                await self.download_track(track, cb)
            except Exception as e:
                if cb:
                    cb(-1.0, f"Failed {track.title}: {e}")
            finally:
                self.queue.task_done()

    async def enqueue(
        self, track: UnifiedTrack, callback: Optional[Callable[[float, str], Any]] = None
    ) -> None:
        """Add a track to the download queue."""
        await self.queue.put((track, callback))
