from sqlmodel import Session, SQLModel, create_engine, select
from app.core.models import Playlist, PlaylistTrackLink, UnifiedTrack


def test_sqlite_models_and_relationships(tmp_path):
    test_db = tmp_path / "test.db"
    test_engine = create_engine(f"sqlite:///{test_db}")
    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        # Create tracks
        t1 = UnifiedTrack(title="Track 1", artist="Artist 1", isrc="US1234567890", bpm=128.0, key="8A")
        t2 = UnifiedTrack(title="Track 2", artist="Artist 2", bpm=125.0, key="9A")
        session.add(t1)
        session.add(t2)
        session.commit()
        session.refresh(t1)
        session.refresh(t2)

        # Create Playlist
        pl = Playlist(name="Test Playlist", source_provider="local")
        session.add(pl)
        session.commit()
        session.refresh(pl)

        # Associate tracks via link model
        link1 = PlaylistTrackLink(playlist_id=pl.id, track_id=t1.id, position=0)
        link2 = PlaylistTrackLink(playlist_id=pl.id, track_id=t2.id, position=1)
        session.add(link1)
        session.add(link2)
        session.commit()

        # Query back
        queried_pl = session.get(Playlist, pl.id)
        assert queried_pl is not None
        assert len(queried_pl.tracks) == 2
        assert queried_pl.tracks[0].title == "Track 1"
        assert queried_pl.tracks[0].bpm == 128.0
        assert queried_pl.tracks[0].key == "8A"
