from dataclasses import dataclass, field
from typing import Any, Optional
from sqlmodel import Session, select

from app.core.models import UnifiedTrack


@dataclass
class SearchQueryCriteria:
    """Multi-parameter filter criteria for global catalog queries."""

    text_query: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genre: Optional[str] = None
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    min_bpm: Optional[float] = None
    max_bpm: Optional[float] = None
    key: Optional[str] = None
    isrc: Optional[str] = None
    codec: Optional[str] = None
    min_bitrate: Optional[int] = None
    only_offline: bool = False
    provider: Optional[str] = None  # "spotify", "deezer", "ytmusic"


class GlobalSearchEngine:
    """Multi-dimensional search engine querying memory cache or database."""

    def filter_tracks(
        self, tracks: list[UnifiedTrack], criteria: SearchQueryCriteria
    ) -> list[UnifiedTrack]:
        """Apply combined filter query to track list."""
        filtered = []

        for t in tracks:
            # 1. Global text search
            if criteria.text_query:
                q = criteria.text_query.lower()
                full_text = f"{t.title} {t.artist} {t.album or ''} {t.genres_raw} {t.isrc or ''}".lower()
                if q not in full_text:
                    continue

            # 2. Artist
            if criteria.artist and criteria.artist.lower() not in t.artist.lower():
                continue

            # 3. Album
            if criteria.album and (not t.album or criteria.album.lower() not in t.album.lower()):
                continue

            # 4. Genre
            if criteria.genre and (not t.genres_raw or criteria.genre.lower() not in t.genres_raw.lower()):
                continue

            # 5. Year range
            if criteria.min_year and (not t.release_year or t.release_year < criteria.min_year):
                continue
            if criteria.max_year and (not t.release_year or t.release_year > criteria.max_year):
                continue

            # 6. BPM range
            if criteria.min_bpm and (not t.bpm or t.bpm < criteria.min_bpm):
                continue
            if criteria.max_bpm and (not t.bpm or t.bpm > criteria.max_bpm):
                continue

            # 7. Key
            if criteria.key and (not t.key or criteria.key.upper() != t.key.upper()):
                continue

            # 8. ISRC
            if criteria.isrc and (not t.isrc or criteria.isrc.lower() not in t.isrc.lower()):
                continue

            # 9. Offline only
            if criteria.only_offline and not t.local_path:
                continue

            # 10. Codec
            if criteria.codec and (not t.codec or criteria.codec.lower() != t.codec.lower()):
                continue

            # 11. Provider
            if criteria.provider:
                p = criteria.provider.lower()
                if p == "spotify" and not t.spotify_id:
                    continue
                elif p == "deezer" and not t.deezer_id:
                    continue
                elif p == "ytmusic" and not t.ytmusic_id:
                    continue

            filtered.append(t)

        return filtered
