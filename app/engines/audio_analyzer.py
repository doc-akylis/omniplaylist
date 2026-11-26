from typing import Optional
from app.core.models import UnifiedTrack


class AudioAnalyzer:
    """BPM analysis, Camelot musical key mapping, and harmonic mixing transition engine."""

    # Standard Musical Key to Camelot Wheel mapping
    KEY_TO_CAMELOT = {
        # Minor keys (A)
        "abm": "1A", "g#m": "1A",
        "ebm": "2A", "d#m": "2A",
        "bbm": "3A", "a#m": "3A",
        "fm": "4A",
        "cm": "5A",
        "gm": "6A",
        "dm": "7A",
        "am": "8A",
        "em": "9A",
        "bm": "10A",
        "f#m": "11A", "gbm": "11A",
        "c#m": "12A", "dbm": "12A",
        # Major keys (B)
        "b": "1B",
        "f#": "2B", "gb": "2B",
        "db": "3B", "c#": "3B",
        "ab": "4B", "g#": "4B",
        "eb": "5B", "d#": "5B",
        "bb": "6B", "a#": "6B",
        "f": "7B",
        "c": "8B",
        "g": "9B",
        "d": "10B",
        "a": "11B",
        "e": "12B",
    }

    @classmethod
    def normalize_to_camelot(cls, key_str: Optional[str]) -> Optional[str]:
        """Convert standard key notation (e.g. 'Am', 'C#m', 'F Major') to Camelot code (e.g. '8A')."""
        if not key_str:
            return None

        clean = (
            key_str.lower()
            .replace("major", "")
            .replace("minor", "m")
            .replace(" ", "")
            .strip()
        )
        return cls.KEY_TO_CAMELOT.get(clean, key_str.upper())

    @classmethod
    def are_keys_compatible(cls, key1: Optional[str], key2: Optional[str]) -> bool:
        """Check if two Camelot keys are harmonically compatible for DJ mixing.

        Compatible rules:
        1. Identical key (e.g., 8A -> 8A)
        2. +/- 1 hour on the wheel (e.g., 8A -> 7A or 9A)
        3. Relative major/minor switch (e.g., 8A -> 8B)
        """
        if not key1 or not key2:
            return False

        c1 = cls.normalize_to_camelot(key1)
        c2 = cls.normalize_to_camelot(key2)
        if not c1 or not c2 or len(c1) < 2 or len(c2) < 2:
            return False

        num1, letter1 = int(c1[:-1]), c1[-1].upper()
        num2, letter2 = int(c2[:-1]), c2[-1].upper()

        # Same key
        if num1 == num2 and letter1 == letter2:
            return True

        # Relative switch
        if num1 == num2 and letter1 != letter2:
            return True

        # Adjacent wheel numbers (handling 12 <-> 1 wrap)
        if letter1 == letter2:
            diff = abs(num1 - num2)
            if diff == 1 or diff == 11:
                return True

        return False

    def sort_playlist_for_dj(self, tracks: list[UnifiedTrack]) -> list[UnifiedTrack]:
        """Sort tracks for a smooth DJ set: progressively ascending BPM with harmonic transitions."""
        if len(tracks) <= 1:
            return tracks

        # Partition tracks with BPM from tracks without
        with_bpm = [t for t in tracks if t.bpm]
        without_bpm = [t for t in tracks if not t.bpm]

        # Sort primarily by BPM
        sorted_tracks = sorted(with_bpm, key=lambda t: t.bpm or 0)

        # Reorder adjacent pairs to respect Camelot compatibility where possible
        for i in range(len(sorted_tracks) - 2):
            curr = sorted_tracks[i]
            nxt = sorted_tracks[i + 1]
            third = sorted_tracks[i + 2]

            # If current and next are incompatible, but current and third are, swap them if BPM delta is small
            if not self.are_keys_compatible(curr.key, nxt.key) and self.are_keys_compatible(curr.key, third.key):
                if abs((nxt.bpm or 0) - (third.bpm or 0)) <= 6.0:
                    sorted_tracks[i + 1], sorted_tracks[i + 2] = sorted_tracks[i + 2], sorted_tracks[i + 1]

        return sorted_tracks + without_bpm
