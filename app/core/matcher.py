import re
from typing import Optional
from rapidfuzz import fuzz
from app.core.models import MatchResult, UnifiedTrack


class TrackMatcher:
    """Equivalence engine for matching songs across platforms using ISRC and RapidFuzz."""

    def __init__(self, fuzzy_threshold: float = 0.82, duration_tolerance_sec: int = 8):
        self.fuzzy_threshold = fuzzy_threshold
        self.duration_tolerance_ms = duration_tolerance_sec * 1000

    @staticmethod
    def clean_text(text: str) -> str:
        """Sanitize title or artist string by removing common noise."""
        if not text:
            return ""
        cleaned = text.lower()
        # Remove patterns like (Official Video), [Remastered], (Radio Edit), (feat. X), etc.
        cleaned = re.sub(
            r"[\(\[\{].*?(official|video|audio|remastered|remaster|radio edit|edit|deluxe|version|feat|ft\.).*?[\)\]\}]",
            "",
            cleaned,
        )
        cleaned = re.sub(r"[^\w\s]", " ", cleaned)
        return " ".join(cleaned.split())

    def match(self, source: UnifiedTrack, candidate: UnifiedTrack) -> MatchResult:
        """Compute matching confidence between a source track and a candidate track."""
        # 1. Exact ISRC match (Highest confidence)
        if source.isrc and candidate.isrc:
            if source.isrc.strip().upper() == candidate.isrc.strip().upper():
                return MatchResult(
                    source_track=source,
                    target_track=candidate,
                    confidence_score=1.0,
                    match_strategy="isrc_exact",
                    matched=True,
                )

        # 2. Duration check if both durations are available
        duration_penalty = 1.0
        if source.duration_ms and candidate.duration_ms:
            delta = abs(source.duration_ms - candidate.duration_ms)
            if delta > self.duration_tolerance_ms:
                duration_penalty = max(0.5, 1.0 - (delta / (self.duration_tolerance_ms * 3)))

        # 3. Fuzzy string matching on title and artist
        clean_src_title = self.clean_text(source.title)
        clean_cand_title = self.clean_text(candidate.title)
        clean_src_artist = self.clean_text(source.artist)
        clean_cand_artist = self.clean_text(candidate.artist)

        # Use combination of token_sort_ratio and token_set_ratio for title resilience
        t_sort = fuzz.token_sort_ratio(clean_src_title, clean_cand_title) / 100.0
        t_set = fuzz.token_set_ratio(clean_src_title, clean_cand_title) / 100.0
        title_score = (0.5 * t_sort) + (0.5 * t_set)
        artist_score = fuzz.token_set_ratio(clean_src_artist, clean_cand_artist) / 100.0

        # Weighted composite score: 60% title, 40% artist, scaled by duration alignment
        composite_score = ((0.6 * title_score) + (0.4 * artist_score)) * duration_penalty

        is_match = composite_score >= self.fuzzy_threshold

        return MatchResult(
            source_track=source,
            target_track=candidate,
            confidence_score=round(composite_score, 3),
            match_strategy="fuzzy_rapidfuzz",
            matched=is_match,
        )

    def find_best_match(
        self, source: UnifiedTrack, candidates: list[UnifiedTrack]
    ) -> Optional[MatchResult]:
        """Find candidate with highest confidence above threshold."""
        best_result: Optional[MatchResult] = None
        best_score = -1.0

        for candidate in candidates:
            res = self.match(source, candidate)
            if res.confidence_score > best_score:
                best_score = res.confidence_score
                best_result = res

        if best_result and best_result.matched:
            return best_result
        return None
