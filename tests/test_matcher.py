from app.core.matcher import TrackMatcher
from app.core.models import UnifiedTrack


def test_isrc_exact_match():
    matcher = TrackMatcher()
    t1 = UnifiedTrack(title="Midnight City", artist="M83", isrc="FR01T1100523")
    t2 = UnifiedTrack(title="Midnight City (Remaster)", artist="M83", isrc="FR01T1100523")

    result = matcher.match(t1, t2)
    assert result.matched is True
    assert result.confidence_score == 1.0
    assert result.match_strategy == "isrc_exact"


def test_fuzzy_match_similarity():
    matcher = TrackMatcher(fuzzy_threshold=0.80)
    t1 = UnifiedTrack(
        title="Starboy (feat. Daft Punk)",
        artist="The Weeknd",
        duration_ms=230000,
    )
    t2 = UnifiedTrack(
        title="Starboy",
        artist="The Weeknd, Daft Punk",
        duration_ms=232000,
    )

    result = matcher.match(t1, t2)
    assert result.matched is True
    assert result.confidence_score >= 0.80
    assert result.match_strategy == "fuzzy_rapidfuzz"


def test_unmatched_different_tracks():
    matcher = TrackMatcher()
    t1 = UnifiedTrack(title="Bohemian Rhapsody", artist="Queen")
    t2 = UnifiedTrack(title="Hotel California", artist="Eagles")

    result = matcher.match(t1, t2)
    assert result.matched is False
    assert result.confidence_score < 0.50


def test_find_best_match_from_candidates():
    matcher = TrackMatcher()
    source = UnifiedTrack(title="Resonance", artist="HOME", duration_ms=212000)
    candidates = [
        UnifiedTrack(title="Resonance (Radio Edit)", artist="HOME", duration_ms=210000),
        UnifiedTrack(title="Decay", artist="HOME", duration_ms=200000),
        UnifiedTrack(title="Something Else", artist="Different Artist"),
    ]

    best = matcher.find_best_match(source, candidates)
    assert best is not None
    assert best.matched is True
    assert best.target_track.title == "Resonance (Radio Edit)"
