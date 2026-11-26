from sqlmodel import Session, SQLModel, create_engine
from app.core.models import UnifiedTrack, UserHistory
from app.engines.music_discovery import MusicDiscoveryEngine


def test_music_discovery_history_and_taste(tmp_path):
    engine = MusicDiscoveryEngine()
    db_file = tmp_path / "disco_test.db"
    db_engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(db_engine)

    with Session(db_engine) as session:
        t1 = UnifiedTrack(id=1, title="Song 1", artist="Artist Alpha", bpm=120.0, key="8A", genres_raw="synthwave")
        t2 = UnifiedTrack(id=2, title="Song 2", artist="Artist Alpha", bpm=122.0, key="9A", genres_raw="synthwave")
        t3 = UnifiedTrack(id=3, title="Song 3", artist="Artist Beta", bpm=140.0, key="2A", genres_raw="rock")
        session.add_all([t1, t2, t3])
        session.commit()

        # Record events
        engine.record_event(session, 1, "played")
        engine.record_event(session, 3, "rejected")

        # Check rejected
        rejected = engine.get_rejected_track_ids(session)
        assert 3 in rejected
        assert 1 not in rejected

        # User taste profile
        profile = engine.get_user_taste_profile([t1, t2], session)
        assert profile["favorite_artists"][0] == "Artist Alpha"
        assert "Electronic" in profile["favorite_genres"]

        # Similar tracks
        similar = engine.find_similar_tracks_in_library(t1, [t1, t2, t3])
        assert len(similar) > 0
        assert similar[0].id == 2  # t2 is harmonically close and same artist
