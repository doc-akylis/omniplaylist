import pytest
from app.core.models import UnifiedTrack
from app.engines.lyrics_engine import LyricsEngine
from app.providers.deezer import DeezerProvider


def test_deezer_provider_normalization():
    deezer = DeezerProvider()
    raw_item = {
        "id": 123456,
        "title": "One More Time",
        "isrc": "FRZ010000001",
        "bpm": 123.0,
        "duration": 320,
        "release_date": "2001-03-12",
        "preview": "https://cdn.deezer.com/preview.mp3",
        "artist": {"name": "Daft Punk"},
        "album": {"title": "Discovery", "cover_xl": "https://cdn.deezer.com/cover.jpg"},
    }
    track = deezer._to_unified_track(raw_item)
    assert track.title == "One More Time"
    assert track.artist == "Daft Punk"
    assert track.album == "Discovery"
    assert track.isrc == "FRZ010000001"
    assert track.bpm == 123.0
    assert track.release_year == 2001
    assert track.preview_url == "https://cdn.deezer.com/preview.mp3"


def test_lyrics_engine_lrc_save(tmp_path):
    lyrics_eng = LyricsEngine()
    track = UnifiedTrack(
        title="Sample Song",
        artist="Sample Artist",
        lyrics_synced="[00:10.00] Line one\n[00:15.00] Line two",
    )
    lrc_path = lyrics_eng.save_lrc_file(track, output_dir=tmp_path)
    assert lrc_path is not None
    assert lrc_path.exists()
    assert "[00:10.00] Line one" in lrc_path.read_text(encoding="utf-8")
