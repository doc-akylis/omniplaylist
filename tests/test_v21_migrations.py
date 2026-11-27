import shutil
import sqlite3
from pathlib import Path

from sqlmodel import Session, create_engine, select

from app.core.database import init_db, migrate_db
from app.core.models import AudioProvenance, DownloadJob, Playlist, UnifiedTrack


def test_idempotent_migration_on_v20_db_copy(tmp_path: Path):
    """Test idempotent v2.1 migrations on an isolated copy of production omniplaylist.db."""
    prod_db = Path(__file__).resolve().parents[1] / "omniplaylist.db"
    assert prod_db.exists()

    copy_db = tmp_path / "omniplaylist_v20_copy.db"
    shutil.copy2(prod_db, copy_db)

    conn_before = sqlite3.connect(copy_db)
    tracks_before = conn_before.execute("SELECT id, title, artist FROM unifiedtrack ORDER BY id").fetchall()
    playlists_before = conn_before.execute("SELECT id, name FROM playlist ORDER BY id").fetchall()
    links_before = conn_before.execute("SELECT playlist_id, track_id, position FROM playlisttracklink ORDER BY playlist_id, position").fetchall()
    conn_before.close()

    test_engine = create_engine(f"sqlite:///{copy_db}", connect_args={"check_same_thread": False})
    try:
        # Run twice to prove strict idempotency
        init_db(test_engine)
        migrate_db(test_engine)

        with Session(test_engine) as session:
            tracks_after = session.exec(select(UnifiedTrack).order_by(UnifiedTrack.id)).all()
            playlists_after = session.exec(select(Playlist).order_by(Playlist.id)).all()
            assert [(t.id, t.title, t.artist) for t in tracks_after] == tracks_before
            assert [(p.id, p.name) for p in playlists_after] == playlists_before

        conn_after = sqlite3.connect(copy_db)
        tables = {r[0] for r in conn_after.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        links_after = conn_after.execute("SELECT playlist_id, track_id, position FROM playlisttracklink ORDER BY playlist_id, position").fetchall()
        track_cols = {r[1] for r in conn_after.execute("PRAGMA table_info(unifiedtrack)").fetchall()}
        conn_after.close()

        assert {"audioprovenance", "audioprocessinghistory", "downloadjob"}.issubset(tables)
        assert links_after == links_before
        assert {
            "is_preview",
            "source_classification",
            "spectral_cutoff_hz",
            "upscale_status",
            "upscale_confidence",
            "is_fake_upscale",
            "sub_bass_energy",
            "mid_bass_energy",
            "car_audio_score",
            "car_audio_ready",
        }.issubset(track_cols)
    finally:
        test_engine.dispose()
