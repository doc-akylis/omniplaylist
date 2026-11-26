from sqlmodel import Session, SQLModel, create_engine
from app.core.models import UnifiedTrack
from app.engines.playlist_health import PlaylistHealthEngine


def test_playlist_health_audit():
    engine = PlaylistHealthEngine()
    tracks = [
        UnifiedTrack(id=1, title="Track Normal", artist="Artist", album="Album", duration_ms=210000, isrc="US123", cover_url="cover.jpg"),
        UnifiedTrack(id=2, title="Short Jingle", artist="Artist", duration_ms=15000),  # Suspicious duration (<30s), missing album & cover
        UnifiedTrack(id=3, title="Studio Hit", artist="Band A", album="Hit Album", duration_ms=200000),
        UnifiedTrack(id=4, title="Studio Hit (Live in Rio)", artist="Band A", album="Hit Album", duration_ms=220000),  # Live mixed
        UnifiedTrack(id=5, title="Lost File", artist="Band B", local_path="non_existent_file.mp3"),  # Broken file
    ]

    report = engine.audit_tracks(tracks)
    assert report.total_tracks_checked == 5
    assert len(report.issues) > 0
    categories = [iss.category for iss in report.issues]
    assert "suspicious_duration" in categories
    assert "broken_file" in categories
    assert "missing_cover" in categories


def test_playlist_health_fix_broken_paths(tmp_path):
    engine = PlaylistHealthEngine()
    db_file = tmp_path / "health_test.db"
    db_engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(db_engine)

    with Session(db_engine) as session:
        t = UnifiedTrack(id=1, title="Test", artist="Artist", local_path="missing_file.mp3")
        session.add(t)
        session.commit()
        session.refresh(t)

        fixed = engine.remove_broken_paths_batch([t], session)
        assert fixed == 1
        assert t.local_path is None
