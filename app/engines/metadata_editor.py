from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from mutagen.easyid3 import EasyID3
from sqlmodel import Session

from app.core.models import UnifiedTrack


@dataclass
class MetadataDiff:
    """Preview of field changes before applying to a track."""

    track_id: int
    title_old: str
    title_new: Optional[str]
    artist_old: str
    artist_new: Optional[str]
    album_old: Optional[str]
    album_new: Optional[str]
    genre_old: str
    genre_new: Optional[str]
    year_old: Optional[int]
    year_new: Optional[int]
    track_number_old: Optional[int]
    track_number_new: Optional[int]
    bpm_old: Optional[float]
    bpm_new: Optional[float]
    key_old: Optional[str]
    key_new: Optional[str]


class MetadataEditorEngine:
    """Batch audio and database metadata editing with diff preview and undo backups."""

    def __init__(self):
        self.undo_backups: dict[str, list[dict[str, Any]]] = {}

    def preview_batch_changes(
        self,
        tracks: list[UnifiedTrack],
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[int] = None,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
    ) -> list[MetadataDiff]:
        """Compute diff preview before writing to database and ID3 tags."""
        diffs = []
        for t in tracks:
            diff = MetadataDiff(
                track_id=t.id or 0,
                title_old=t.title,
                title_new=None,
                artist_old=t.artist,
                artist_new=artist if artist is not None else t.artist,
                album_old=t.album,
                album_new=album if album is not None else t.album,
                genre_old=t.genres_raw,
                genre_new=genre if genre is not None else t.genres_raw,
                year_old=t.release_year,
                year_new=year if year is not None else t.release_year,
                track_number_old=t.track_number,
                track_number_new=None,
                bpm_old=t.bpm,
                bpm_new=bpm if bpm is not None else t.bpm,
                key_old=t.key,
                key_new=key if key is not None else t.key,
            )
            diffs.append(diff)
        return diffs

    def apply_batch_changes(
        self,
        tracks: list[UnifiedTrack],
        session: Session,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        genre: Optional[str] = None,
        year: Optional[int] = None,
        bpm: Optional[float] = None,
        key: Optional[str] = None,
        update_files_on_disk: bool = True,
    ) -> str:
        """Apply batch changes to database and physical ID3 tags, storing backup snapshot."""
        backup_id = f"backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        snapshot = []

        for t in tracks:
            # Save original snapshot for undo
            snapshot.append({
                "id": t.id,
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "genres_raw": t.genres_raw,
                "release_year": t.release_year,
                "bpm": t.bpm,
                "key": t.key,
            })

            # Update DB model
            if artist is not None:
                t.artist = artist.strip()
            if album is not None:
                t.album = album.strip()
            if genre is not None:
                t.genres_raw = genre.strip()
            if year is not None:
                t.release_year = year
            if bpm is not None:
                t.bpm = bpm
            if key is not None:
                t.key = key.strip().upper()

            session.add(t)

            # Update physical file ID3 tags if available
            if update_files_on_disk and t.local_path and Path(t.local_path).exists():
                try:
                    audio = EasyID3(t.local_path)
                    if artist is not None:
                        audio["artist"] = t.artist
                    if album is not None:
                        audio["album"] = t.album
                    if genre is not None:
                        audio["genre"] = t.genres_raw
                    if year is not None:
                        audio["date"] = str(year)
                    audio.save(t.local_path)
                except Exception as e:
                    print(f"[MetadataEditor] ID3 write note for {t.local_path}: {e}")

        session.commit()
        self.undo_backups[backup_id] = snapshot
        return backup_id

    def restore_backup(self, backup_id: str, session: Session) -> bool:
        """Restore original metadata from an undo snapshot."""
        snapshot = self.undo_backups.get(backup_id)
        if not snapshot:
            return False

        for original in snapshot:
            track = session.get(UnifiedTrack, original["id"])
            if track:
                track.title = original["title"]
                track.artist = original["artist"]
                track.album = original["album"]
                track.genres_raw = original["genres_raw"]
                track.release_year = original["release_year"]
                track.bpm = original["bpm"]
                track.key = original["key"]
                session.add(track)

        session.commit()
        return True
