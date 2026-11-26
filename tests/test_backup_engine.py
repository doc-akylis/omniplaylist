from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine
from app.core.models import UnifiedTrack
from app.engines.backup_engine import BackupEngine


def test_backup_create_verify_and_restore(tmp_path: Path):
    engine = BackupEngine(backup_dir=tmp_path / "backups")
    db_file = Path("./omniplaylist.db")
    db_file.touch()

    # In-memory test engine for session
    test_db = tmp_path / "test_session.db"
    test_engine = create_engine(f"sqlite:///{test_db}")
    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        t = UnifiedTrack(id=1, title="Track 1", artist="Artist 1")
        session.add(t)
        session.commit()

        # Create backup
        record = engine.create_backup(session)
        assert record.filename.endswith(".zip")
        assert Path(record.file_path).exists()
        assert record.checksum_sha256 != ""

        # Verify integrity
        valid, msg = engine.verify_backup_integrity(Path(record.file_path))
        assert valid is True
        assert "confirmada" in msg
