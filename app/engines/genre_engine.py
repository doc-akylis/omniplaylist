from collections import defaultdict
from typing import Any
from app.core.models import UnifiedTrack


class GenreEngine:
    """Classifier, normalizer, and hierarchical aggregator for music genres."""

    # Taxonomy mapping: Subgenre -> Parent Genre
    TAXONOMY_MAP = {
        # Electronic / Dance
        "house": "Electronic",
        "techno": "Electronic",
        "deep house": "Electronic",
        "synthwave": "Electronic",
        "darksynth": "Electronic",
        "trance": "Electronic",
        "drum and bass": "Electronic",
        "ambient": "Electronic",
        # Rock & Alternative
        "indie rock": "Rock",
        "alternative rock": "Rock",
        "hard rock": "Rock",
        "punk": "Rock",
        "grunge": "Rock",
        "metal": "Rock",
        "heavy metal": "Rock",
        # Hip Hop & R&B
        "trap": "Hip Hop",
        "boom bap": "Hip Hop",
        "lo-fi hip hop": "Hip Hop",
        "r&b": "Hip Hop & R&B",
        "neo soul": "Hip Hop & R&B",
        # Pop
        "synthpop": "Pop",
        "indie pop": "Pop",
        "dance pop": "Pop",
        "k-pop": "Pop",
        # Latin & World
        "reggaeton": "Latin",
        "bossa nova": "Latin",
        "samba": "Latin",
        "mpb": "Latin",
        # Jazz & Classical
        "bebop": "Jazz",
        "smooth jazz": "Jazz",
        "baroque": "Classical",
        "romantic": "Classical",
    }

    @classmethod
    def normalize_tag(cls, tag: str) -> str:
        """Sanitize and standardize genre tag format."""
        if not tag:
            return ""
        clean = tag.strip().lower().replace("_", " ").replace("-", " ")
        return " ".join(clean.split())

    @classmethod
    def get_parent_genre(cls, subgenre: str) -> str:
        """Resolve a parent high-level category for a subgenre."""
        clean = cls.normalize_tag(subgenre)
        return cls.TAXONOMY_MAP.get(clean, "Other / Miscellaneous")

    def classify_track(self, track: UnifiedTrack) -> list[str]:
        """Normalize all genres assigned to a track."""
        normalized = []
        for g in track.genres:
            norm = self.normalize_tag(g)
            if norm and norm not in normalized:
                normalized.append(norm)
        return normalized

    def build_genre_tree(self, tracks: list[UnifiedTrack]) -> dict[str, Any]:
        """
        Build an aggregated hierarchical tree of genres and tracks.
        Structure:
        {
            "Electronic": {
                "tracks_count": 12,
                "subgenres": {
                    "synthwave": [track1, track2],
                    "techno": [track3]
                }
            }
        }
        """
        tree: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"tracks_count": 0, "subgenres": defaultdict(list)}
        )

        for track in tracks:
            genres = self.classify_track(track)
            if not genres:
                genres = ["unclassified"]

            for genre in genres:
                parent = self.get_parent_genre(genre)
                tree[parent]["tracks_count"] += 1
                tree[parent]["subgenres"][genre].append(track)

        # Convert defaultdicts to standard dicts
        result: dict[str, Any] = {}
        for parent, data in tree.items():
            result[parent] = {
                "tracks_count": data["tracks_count"],
                "subgenres": dict(data["subgenres"]),
            }

        return result
