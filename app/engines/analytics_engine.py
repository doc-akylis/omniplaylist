from collections import Counter
from typing import Any
from app.core.models import UnifiedTrack
from app.engines.genre_engine import GenreEngine


class AnalyticsEngine:
    """Computes comprehensive statistical insights and wrapped-style metrics for the music library."""

    def __init__(self):
        self.genre_engine = GenreEngine()

    def generate_stats(self, tracks: list[UnifiedTrack]) -> dict[str, Any]:
        """Aggregate data to produce library analytics."""
        if not tracks:
            return {
                "total_tracks": 0,
                "total_duration_minutes": 0,
                "top_artists": [],
                "genre_distribution": {},
                "decade_distribution": {},
                "offline_percentage": 0.0,
                "average_bpm": 0.0,
            }

        total_tracks = len(tracks)
        total_duration_ms = sum(t.duration_ms or 0 for t in tracks)
        offline_count = sum(1 for t in tracks if t.local_path)

        # Artists counter
        artist_counts = Counter(t.artist for t in tracks)
        top_artists = artist_counts.most_common(5)

        # Genre distribution
        genre_counter: Counter[str] = Counter()
        for t in tracks:
            for g in t.genres:
                parent = self.genre_engine.get_parent_genre(g)
                genre_counter[parent] += 1

        # Decades distribution
        decade_counter: Counter[str] = Counter()
        for t in tracks:
            if t.release_year:
                decade_floor = (t.release_year // 10) * 10
                decade_counter[f"{decade_floor}s"] += 1
            else:
                decade_counter["Desconhecida"] += 1

        # Average BPM
        tracks_with_bpm = [t.bpm for t in tracks if t.bpm]
        avg_bpm = round(sum(tracks_with_bpm) / len(tracks_with_bpm), 1) if tracks_with_bpm else 0.0

        return {
            "total_tracks": total_tracks,
            "total_duration_minutes": round(total_duration_ms / 60000, 1),
            "top_artists": top_artists,
            "genre_distribution": dict(genre_counter.most_common(8)),
            "decade_distribution": dict(decade_counter),
            "offline_percentage": round((offline_count / total_tracks) * 100, 1) if total_tracks else 0.0,
            "average_bpm": avg_bpm,
        }
