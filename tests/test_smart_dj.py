from app.core.models import UnifiedTrack
from app.engines.ai_curator import AICurator, SmartDJFilter


def test_smart_dj_unique_artists():
    curator = AICurator()
    catalog = [
        UnifiedTrack(id=1, title="Song A1", artist="Queen", release_year=1980, bpm=120.0),
        UnifiedTrack(id=2, title="Song A2", artist="Queen", release_year=1982, bpm=122.0),
        UnifiedTrack(id=3, title="Song B1", artist="Survivor", release_year=1982, bpm=120.0),
    ]

    filt = SmartDJFilter(unique_artists_only=True, track_count=10)
    result = curator.generate_smart_dj_set("rock anos 80", catalog, custom_filter=filt)

    artists = [t.artist for t in result.tracks]
    assert len(artists) == len(set(artists))
    assert len(result.tracks) == 2


def test_smart_dj_excluded_artists():
    curator = AICurator()
    catalog = [
        UnifiedTrack(id=1, title="Good Song", artist="Artist OK", bpm=125.0),
        UnifiedTrack(id=2, title="Bad Song", artist="Artist Ban", bpm=125.0),
    ]

    filt = SmartDJFilter(excluded_artists=["artist ban"])
    result = curator.generate_smart_dj_set("animada sem Artist Ban", catalog, custom_filter=filt)

    artists = [t.artist for t in result.tracks]
    assert "Artist Ban" not in artists
    assert len(result.tracks) == 1
    assert result.tracks[0].artist == "Artist OK"


def test_smart_dj_justifications():
    curator = AICurator()
    catalog = [
        UnifiedTrack(id=1, title="Midnight City", artist="M83", bpm=105.0, release_year=2011, genres_raw="synthwave"),
    ]

    result = curator.generate_smart_dj_set("synthwave 2010s", catalog)
    assert 1 in result.justifications
    reason = result.justifications[1]
    assert "Synthwave" in reason or "2011" in reason
