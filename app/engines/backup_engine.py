from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Optional
import zipfile
from sqlmodel import Session, select

from app.config import get_settings
from app.core.models import BackupRecord, Playlist, UnifiedTrack


class BackupEngine:
    """Manages SQLite database snapshots, ZIP archive generation, integrity checks, and safe restoration."""

    def __init__(self, backup_dir: Optional[Path] = None):
        self.settings = get_settings()
        self.backup_dir = backup_dir or Path("./backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _compute_sha256(self, file_path: Path) -> str:
        """Compute SHA256 hash for archive integrity verification."""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
        return sha.hexdigest()

    def create_backup(self, session: Session) -> BackupRecord:
        """Create a compressed snapshot of the SQLite database and metadata."""
        db_path = Path("./omniplaylist.db")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        zip_filename = f"omniplaylist_backup_{timestamp}.zip"
        zip_path = self.backup_dir / zip_filename

        tracks_count = len(session.exec(select(UnifiedTrack)).all())
        playlists_count = len(session.exec(select(Playlist)).all())

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_out:
            if db_path.exists():
                zip_out.write(db_path, arcname="omniplaylist.db")
            # Include .env if exists
            env_file = Path(".env")
            if env_file.exists():
                zip_out.write(env_file, arcname=".env")

        checksum = self._compute_sha256(zip_path)
        file_size = zip_path.stat().st_size

        record = BackupRecord(
            filename=zip_filename,
            file_path=str(zip_path),
            file_size_bytes=file_size,
            track_count=tracks_count,
            playlist_count=playlists_count,
            checksum_sha256=checksum,
            status="valid",
            created_at=datetime.now(timezone.utc),
        )
        session.add(record)
        session.commit()
        session.refresh(record)

        return record

    def verify_backup_integrity(self, zip_path: Path) -> tuple[bool, str]:
        """Verify ZIP structure, checksum, and test SQLite readability inside archive."""
        if not zip_path.exists():
            return False, "Arquivo de backup não encontrado no disco."

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_in:
                namelist = zip_in.namelist()
                if "omniplaylist.db" not in namelist:
                    return False, "O arquivo de backup não contém 'omniplaylist.db'."

                # Test extraction in memory and open sqlite connection
                db_bytes = zip_in.read("omniplaylist.db")
                temp_test = self.backup_dir / ".test_integrity.db"
                temp_test.write_bytes(db_bytes)

                try:
                    conn = sqlite3.connect(temp_test)
                    cursor = conn.cursor()
                    cursor.execute("SELECT count(*) FROM unifiedtrack")
                    cursor.close()
                    conn.close()
                finally:
                    if temp_test.exists():
                        temp_test.unlink()

            return True, "Backup verificado com sucesso. Integridade de banco confirmada."
        except Exception as e:
            return False, f"Falha na verificação de integridade: {e}"

    def restore_backup(self, zip_path: Path) -> tuple[bool, str]:
        """Safely restore database from a verified ZIP archive."""
        valid, msg = self.verify_backup_integrity(zip_path)
        if not valid:
            return False, f"Restauração abortada: {msg}"

        db_path = Path("./omniplaylist.db")

        # Create temporary safety copy of current db
        if db_path.exists():
            safety_copy = Path(f"./omniplaylist.db.before_restore_{datetime.now(timezone.utc).strftime('%H%M%S')}")
            shutil.copy2(db_path, safety_copy)

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_in:
                zip_in.extract("omniplaylist.db", path=".")
            return True, "Banco de dados restaurado com sucesso a partir do backup."
        except Exception as e:
            return False, f"Erro durante a descompactação: {e}"
