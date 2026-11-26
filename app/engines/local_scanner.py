import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from typing import Any, Optional
import mutagen
from mutagen.easyid3 import EasyID3
from sqlmodel import Session, select

from app.core.models import UnifiedTrack
from app.engines.technical_analysis import TechnicalAnalysisEngine


class LocalScanner:
    """Recursively scans local folders for audio files, extracts tags and indexes them into the database."""

    SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus"}

    def __init__(self, session_factory: Callable[[], Session]):
        self.session_factory = session_factory

    def scan_directory(
        self,
        folder_path: Path,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
        analyze_technical: bool = False,
    ) -> dict[str, int]:
        """Scan a folder recursively and index audio files into SQLite (synchronous wrapper).

        Args:
            folder_path: Path to scan recursively
            progress_callback: Optional callback(idx, total, filename)
            analyze_technical: If True, runs FFmpeg/ffprobe technical analysis on new tracks

        Returns: dict with counts of scanned, added, and skipped tracks.
        """
        stats, new_track_ids = self._scan_and_index(folder_path, progress_callback)

        if analyze_technical and new_track_ids:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                analysis_stats = asyncio.run(
                    self._analyze_new_tracks(new_track_ids, progress_callback)
                )
            else:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    analysis_stats = pool.submit(
                        asyncio.run,
                        self._analyze_new_tracks(new_track_ids, progress_callback),
                    ).result()
            stats.update(analysis_stats)

        return stats

    async def scan_directory_async(
        self,
        folder_path: Path,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
        analyze_technical: bool = False,
    ) -> dict[str, int]:
        """Scan a folder recursively and index audio files into SQLite asynchronously."""
        stats, new_track_ids = self._scan_and_index(folder_path, progress_callback)

        if analyze_technical and new_track_ids:
            analysis_stats = await self._analyze_new_tracks(new_track_ids, progress_callback)
            stats.update(analysis_stats)

        return stats

    def _scan_and_index(
        self,
        folder_path: Path,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
    ) -> tuple[dict[str, int], list[int]]:
        """Walk folder_path, extract tags and persist new tracks, returning stats and new IDs."""
        stats = {"scanned": 0, "added": 0, "skipped": 0}
        if not folder_path.exists() or not folder_path.is_dir():
            return stats, []

        audio_files = [
            f for f in folder_path.rglob("*") if f.suffix.lower() in self.SUPPORTED_EXTENSIONS
        ]
        total = len(audio_files)
        new_track_ids: list[int] = []

        with self.session_factory() as session:
            for idx, file_path in enumerate(audio_files, 1):
                stats["scanned"] += 1
                if progress_callback:
                    progress_callback(idx, total, file_path.name)

                # Check if already indexed by local_path
                existing = session.exec(
                    select(UnifiedTrack).where(UnifiedTrack.local_path == str(file_path))
                ).first()
                if existing:
                    stats["skipped"] += 1
                    continue

                track = self._extract_metadata(file_path)
                if track:
                    session.add(track)
                    stats["added"] += 1

            session.commit()

            # Collect IDs of newly added tracks for technical analysis
            if stats["added"] > 0:
                new_tracks = session.exec(
                    select(UnifiedTrack.id).where(UnifiedTrack.local_path.in_(
                        [str(f) for f in audio_files]
                    ))
                ).all()
                new_track_ids = [tid for tid in new_tracks if tid is not None]

        return stats, new_track_ids

    async def _analyze_new_tracks(
        self,
        track_ids: list[int],
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
    ) -> dict[str, int]:
        """Run technical analysis on specific track IDs."""
        engine = TechnicalAnalysisEngine()
        stats = {"analyzed": 0, "skipped": 0, "errors": 0}
        total = len(track_ids)

        for idx, track_id in enumerate(track_ids, 1):
            if progress_callback:
                progress_callback(idx, total, f"Analisando track {track_id}")

            try:
                with self.session_factory() as session:
                    track = session.get(UnifiedTrack, track_id)
                    if track:
                        result = await engine.analyze_and_persist(track, session)
                        if result:
                            stats["analyzed"] += 1
                        else:
                            stats["skipped"] += 1
            except Exception as e:
                print(f"[LocalScanner] Technical analysis error for track {track_id}: {e}")
                stats["errors"] += 1

        return stats

    def _extract_metadata(self, file_path: Path) -> Optional[UnifiedTrack]:
        """Extract metadata using Mutagen with filename fallback."""
        title = None
        artist = None
        album = None
        genre = ""
        duration_ms = None

        try:
            audio = mutagen.File(str(file_path), easy=True)
            if audio is not None:
                title = audio.get("title", [None])[0]
                artist = audio.get("artist", [None])[0]
                album = audio.get("album", [None])[0]
                genres = audio.get("genre", [])
                genre = ", ".join(genres) if genres else ""
                if audio.info and hasattr(audio.info, "length"):
                    duration_ms = int(audio.info.length * 1000)
        except Exception:
            pass

        # Fallback to filename parsing: "Artist - Title.mp3"
        if not title or not artist:
            stem = file_path.stem
            # Remove leading track numbers like "01 - " or "1. "
            stem = re.sub(r"^\d+[\s\.\-_]+", "", stem)
            if " - " in stem:
                parts = stem.split(" - ", 1)
                artist = artist or parts[0].strip()
                title = title or parts[1].strip()
            else:
                title = title or stem
                artist = artist or "Artista Desconhecido"

        return UnifiedTrack(
            title=title or file_path.stem,
            artist=artist or "Artista Desconhecido",
            album=album,
            genres_raw=genre,
            duration_ms=duration_ms,
            local_path=str(file_path),
        )
