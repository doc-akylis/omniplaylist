from pathlib import Path
from app.core.models import UnifiedTrack
from app.engines.audio_quality import AudioQualityEngine, QualityProfile


def test_quality_profiles():
    car = QualityProfile.CAR_STEREO
    assert car["format"] == "mp3"
    assert car["bitrate"] == "320k"
    assert car["fat32_safe"] is True

    dj = QualityProfile.DJ_REKORDBOX
    assert dj["format"] == "wav"
    assert dj["bitrate"] == "lossless"

    flac = QualityProfile.ARCHIVE_LOSSLESS
    assert flac["format"] == "flac"


def test_inspect_missing_file():
    engine = AudioQualityEngine()
    missing = Path("non_existent_audio_file.mp3")
    info = engine.inspect_file(missing)
    assert info.is_corrupted is True
    assert "não existe" in info.quality_notes[0]


def test_scan_library_quality():
    engine = AudioQualityEngine()
    tracks = [
        UnifiedTrack(id=1, title="Track 1", artist="Artist 1"),
        UnifiedTrack(id=2, title="Track 2", artist="Artist 2", local_path="invalid_path.mp3"),
    ]
    report = engine.scan_library_quality(tracks)
    assert report["total_analyzed"] == 2
    assert report["corrupted_files"] >= 1
    assert "Baixo (<128k)" in report["bitrate_distribution"]
