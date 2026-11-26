import re
from typing import Any
from rapidfuzz import fuzz
from sqlmodel import Session, select

from app.core.models import PlaylistTrackLink, UnifiedTrack


class Deduplicator:
    """Detects and merges duplicate, live, and remastered track versions in the library."""

    NOISE_PATTERN = re.compile(
        r"[\(\[\{].*?(remastered|remaster|live|radio edit|deluxe|version|mono|stereo|re\-recorded).*?[\)\]\}]",
        re.IGNORECASE,
    )

    def __init__(self, fuzzy_threshold: float = 88.0, duration_tolerance_sec: int = 5):
        self.fuzzy_threshold = fuzzy_threshold
        self.duration_tolerance_ms = duration_tolerance_sec * 1000

    def clean_title(self, title: str) -> str:
        """Strip remaster/live annotations for equivalence comparison."""
        cleaned = self.NOISE_PATTERN.sub("", title.lower())
        return " ".join(re.sub(r"[^\w\s]", " ", cleaned).split())

    def find_duplicate_groups(self, tracks: list[UnifiedTrack]) -> list[dict[str, Any]]:
        """Identify clusters of duplicate or near-duplicate songs.

        Returns list of candidate duplicate groups.
        """
        duplicates: list[dict[str, Any]] = []
        visited_ids = set()

        for i, t1 in enumerate(tracks):
            if t1.id in visited_ids:
                continue

            group = [t1]
            c_title1 = self.clean_title(t1.title)
            c_art1 = t1.artist.lower().strip()

            for t2 in tracks[i + 1 :]:
                if t2.id in visited_ids:
                    continue

                # 1. Exact ISRC
                if t1.isrc and t2.isrc and t1.isrc.strip().upper() == t2.isrc.strip().upper():
                    group.append(t2)
                    visited_ids.add(t2.id)
                    continue

                # 2. String similarity
                c_title2 = self.clean_title(t2.title)
                c_art2 = t2.artist.lower().strip()

                artist_sim = fuzz.token_sort_ratio(c_art1, c_art2)
                title_sim = fuzz.token_sort_ratio(c_title1, c_title2)

                if artist_sim >= 85 and title_sim >= self.fuzzy_threshold:
                    # Check duration delta
                    if t1.duration_ms and t2.duration_ms:
                        delta = abs(t1.duration_ms - t2.duration_ms)
                        if delta <= self.duration_tolerance_ms:
                            group.append(t2)
                            visited_ids.add(t2.id)
                    else:
                        group.append(t2)
                        visited_ids.add(t2.id)

            if len(group) > 1:
                visited_ids.add(t1.id)
                duplicates.append({
                    "primary": t1,
                    "candidates": group[1:],
                    "count": len(group),
                })

        return duplicates

    def merge_tracks(
        self, primary_id: int, secondary_id: int, session: Session
    ) -> UnifiedTrack:
        """Merge metadata of secondary track into primary track, reassign playlists, and remove secondary."""
        primary = session.get(UnifiedTrack, primary_id)
        secondary = session.get(UnifiedTrack, secondary_id)

        if not primary or not secondary:
            raise ValueError("Uma ou ambas as faixas não foram encontradas.")

        # Preserve the most complete metadata
        primary.isrc = primary.isrc or secondary.isrc
        primary.spotify_id = primary.spotify_id or secondary.spotify_id
        primary.ytmusic_id = primary.ytmusic_id or secondary.ytmusic_id
        primary.amazon_id = primary.amazon_id or secondary.amazon_id
        primary.deezer_id = primary.deezer_id or secondary.deezer_id
        primary.local_path = primary.local_path or secondary.local_path
        primary.cover_url = primary.cover_url or secondary.cover_url
        primary.bpm = primary.bpm or secondary.bpm
        primary.lyrics_synced = primary.lyrics_synced or secondary.lyrics_synced

        # Reassign playlist associations
        links = session.exec(
            select(PlaylistTrackLink).where(PlaylistTrackLink.track_id == secondary.id)
        ).all()
        for link in links:
            # Check if primary already in that playlist
            already_in = session.exec(
                select(PlaylistTrackLink).where(
                    PlaylistTrackLink.playlist_id == link.playlist_id,
                    PlaylistTrackLink.track_id == primary.id,
                )
            ).first()
            if not already_in:
                link.track_id = primary.id
                session.add(link)
            else:
                session.delete(link)

        # Delete secondary track
        session.delete(secondary)
        session.add(primary)
        session.commit()
        session.refresh(primary)

        return primary
