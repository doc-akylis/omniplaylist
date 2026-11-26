from app.core.models import UnifiedTrack
from app.engines.search_engine import GlobalSearchEngine, SearchQueryCriteria


def test_global_search_multi_criteria():
    engine = GlobalSearchEngine()
    tracks = [
        UnifiedTrack(id=1, title="Rock Track", artist="Bon Jovi", release_year=1986, bpm=130.0, key="8A", local_path="a.mp3"),
        UnifiedTrack(id=2, title="Pop Song", artist="Madonna", release_year=1984, bpm=115.0, key="9A"),
        UnifiedTrack(id=3, title="Modern Electronic", artist="Skrillex", release_year=2023, bpm=140.0, key="8A"),
    ]

    # Test BPM + Year range
    c1 = SearchQueryCriteria(min_bpm=120.0, min_year=1980, max_year=1989)
    res1 = engine.filter_tracks(tracks, c1)
    assert len(res1) == 1
    assert res1[0].artist == "Bon Jovi"

    # Test Offline only
    c2 = SearchQueryCriteria(only_offline=True)
    res2 = engine.filter_tracks(tracks, c2)
    assert len(res2) == 1
    assert res2[0].title == "Rock Track"

    # Test Key search
    c3 = SearchQueryCriteria(key="8A")
    res3 = engine.filter_tracks(tracks, c3)
    assert len(res3) == 2
