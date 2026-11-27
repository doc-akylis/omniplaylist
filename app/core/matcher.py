from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Optional
from rapidfuzz import fuzz
from app.core.models import MatchResult, UnifiedTrack

if TYPE_CHECKING:
    from app.sources.base import GroupedRecording, NormalizedTrackResult


VERSION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("live", re.compile(r"\b(live|ao vivo|unplugged|in concert|session)\b", re.IGNORECASE)),
    ("remix", re.compile(r"\b(remix|rework|bootleg|vip mix|dub mix|club mix)\b", re.IGNORECASE)),
    ("extended", re.compile(r"\b(extended|ext\.? mix|12[\"\s]?mix|full length)\b", re.IGNORECASE)),
    ("radio_edit", re.compile(r"\b(radio edit|single edit|edit version|short edit)\b", re.IGNORECASE)),
    ("remaster", re.compile(r"\b(remaster(?:ed)?(?:\s*\d{4})?)\b", re.IGNORECASE)),
    ("acoustic", re.compile(r"\b(acoustic|ac[uú]stico|stripped)\b", re.IGNORECASE)),
    ("instrumental", re.compile(r"\b(instrumental|karaoke|backing track)\b", re.IGNORECASE)),
    ("demo", re.compile(r"\b(demo|rough mix|worktape)\b", re.IGNORECASE)),
    ("rerecording", re.compile(r"\b(re-?record(?:ed|ing)|taylor'?s version)\b", re.IGNORECASE)),
    ("clean", re.compile(r"\b(clean version|clean edit|censored)\b", re.IGNORECASE)),
    ("explicit", re.compile(r"\b(explicit)\b", re.IGNORECASE)),
]


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

    @staticmethod
    def detect_version_type(title: str, album: Optional[str] = None) -> str:
        """Classify version label (original, remaster, live, remix, extended, radio_edit, etc.)."""
        title_str = title or ""
        album_str = album or ""
        for label, pattern in VERSION_PATTERNS:
            if pattern.search(title_str):
                return label
        # Check album only for live / remaster / acoustic / instrumental / demo if title didn't specify
        for label, pattern in VERSION_PATTERNS:
            if label in ("live", "remaster", "acoustic", "instrumental", "demo") and pattern.search(album_str):
                return label
        return "original"

    @staticmethod
    def _clean_core_title(title: str) -> str:
        """Clean title while removing version tags only after version_type has already been classified."""
        cleaned = TrackMatcher.clean_text(title)
        for _, pattern in VERSION_PATTERNS:
            cleaned = pattern.sub("", cleaned)
        return " ".join(cleaned.split()) or TrackMatcher.clean_text(title)

    def group_recordings(
        self, results: list[NormalizedTrackResult]
    ) -> list[GroupedRecording]:
        """Group multi-source normalized results by ISRC, MBID, or fuzzy title/artist + duration + exact version_type."""
        from app.sources.base import GroupedRecording, PermissionStatus

        if not results:
            return []

        clusters: list[dict[str, Any]] = []
        for item in results:
            v_type = item.version_type or self.detect_version_type(item.title, item.album)
            norm_isrc = re.sub(r"[^A-Z0-9]", "", (item.isrc or "").upper())
            norm_mbid = (item.mbid or "").strip().lower()
            core_title = self._clean_core_title(item.title)
            clean_artist = self.clean_text(item.artist)

            matched_cluster: Optional[dict[str, Any]] = None
            matched_score = 0.0
            matched_strategy = "exact"

            for cluster in clusters:
                if cluster["version_type"] != v_type:
                    continue

                if norm_isrc and cluster["isrc"] and norm_isrc == cluster["isrc"]:
                    matched_cluster = cluster
                    matched_score = 1.0
                    matched_strategy = "isrc"
                    break

                if norm_mbid and cluster["mbid"] and norm_mbid == cluster["mbid"]:
                    matched_cluster = cluster
                    matched_score = 0.99
                    matched_strategy = "mbid"
                    break

                # Fuzzy matching on cleaned core title & artist + duration check
                title_sim = fuzz.token_sort_ratio(core_title, cluster["core_title"]) / 100.0
                artist_sim = fuzz.token_set_ratio(clean_artist, cluster["clean_artist"]) / 100.0
                combined = (title_sim * 0.6) + (artist_sim * 0.4)

                if combined >= self.fuzzy_threshold and title_sim >= 0.72 and artist_sim >= 0.70:
                    c_dur = cluster["duration_ms"]
                    if item.duration_ms and c_dur:
                        if abs(item.duration_ms - c_dur) > self.duration_tolerance_ms:
                            continue
                    if combined > matched_score:
                        matched_cluster = cluster
                        matched_score = combined
                        matched_strategy = "fuzzy_versioned"

            if matched_cluster is not None:
                matched_cluster["candidates"].append(item)
                if norm_isrc and not matched_cluster["isrc"]:
                    matched_cluster["isrc"] = norm_isrc
                if norm_mbid and not matched_cluster["mbid"]:
                    matched_cluster["mbid"] = norm_mbid
                if not matched_cluster["cover_url"] and item.cover_url:
                    matched_cluster["cover_url"] = item.cover_url
                if not matched_cluster["album"] and item.album:
                    matched_cluster["album"] = item.album
                if not matched_cluster["duration_ms"] and item.duration_ms:
                    matched_cluster["duration_ms"] = item.duration_ms
                matched_cluster["confidence"] = min(matched_cluster["confidence"], round(matched_score, 3))
            else:
                clusters.append(
                    {
                        "isrc": norm_isrc or None,
                        "mbid": norm_mbid or None,
                        "title": item.title,
                        "artist": item.artist,
                        "album": item.album,
                        "duration_ms": item.duration_ms,
                        "cover_url": item.cover_url,
                        "version_type": v_type,
                        "core_title": core_title,
                        "clean_artist": clean_artist,
                        "confidence": 1.0,
                        "strategy": "isrc" if norm_isrc else ("mbid" if norm_mbid else "fuzzy_versioned"),
                        "candidates": [item],
                    }
                )

        grouped: list[GroupedRecording] = []
        for idx, cl in enumerate(clusters):
            cands: list[NormalizedTrackResult] = cl["candidates"]
            has_free = any(
                c.permission.downloadable and c.permission.status == PermissionStatus.ALLOWED_FREE
                for c in cands
            )
            has_comm = any(
                c.permission.downloadable
                and c.permission.status == PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL
                for c in cands
            )
            key_seed = cl["isrc"] or cl["mbid"] or f"{cl['clean_artist']}:{cl['core_title']}:{cl['version_type']}:{idx}"
            grouped.append(
                GroupedRecording(
                    group_key=re.sub(r"[^a-zA-Z0-9:_-]", "_", key_seed)[:120],
                    title=cl["title"],
                    artist=cl["artist"],
                    album=cl["album"],
                    duration_ms=cl["duration_ms"],
                    isrc=cl["isrc"],
                    mbid=cl["mbid"],
                    version_type=cl["version_type"],
                    cover_url=cl["cover_url"],
                    match_confidence=cl["confidence"],
                    match_strategy=cl["strategy"],
                    has_downloadable_source=has_free or has_comm,
                    has_free_download=has_free,
                    has_commercial_download=has_comm,
                    candidates=cands,
                )
            )
        return grouped
