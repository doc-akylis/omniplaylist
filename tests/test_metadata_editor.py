from sqlmodel import Session, SQLModel, create_engine
from app.core.models import UnifiedTrack
from app.engines.metadata_editor import MetadataEditorEngine


def test_metadata_editor_diff_and_apply(tmp_path):
    engine = MetadataEditorEngine()
    db_file = tmp_path / "editor_test.db"
    db_engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(db_engine)

    with Session(db_engine) as session:
        t1 = UnifiedTrack(id=1, title="Track 1", artist="Old Artist", album="Old Album", release_year=2000)
        t2 = UnifiedTrack(id=2, title="Track 2", artist="Old Artist", album="Old Album", release_year=2000)
        session.add_all([t1, t2])
        session.commit()

        # Preview diff
        diffs = engine.preview_batch_changes([t1, t2], artist="New Artist", year=2024)
        assert len(diffs) == 2
        assert diffs[0].artist_new == "New Artist"
        assert diffs[0].year_new == 2024

        # Apply changes
        backup_id = engine.apply_batch_changes([t1, t2], session, artist="New Artist", year=2024, update_files_on_disk=False)
        assert t1.artist == "New Artist"
        assert t1.release_year == 2024

        # Restore from backup snapshot
        success = engine.restore_backup(backup_id, session)
        assert success is True
        assert t1.artist == "Old Artist"
        assert t1.release_year == 2000
