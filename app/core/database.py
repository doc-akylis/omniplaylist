from collections.abc import Generator
from sqlmodel import Session, SQLModel, create_engine
from app.config import get_settings

settings = get_settings()

# SQLite engine configuration
connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args=connect_args,
)


def migrate_db() -> None:
    """Safe schema migration adding new columns to existing SQLite tables if needed."""
    if "sqlite" not in settings.DATABASE_URL:
        return

    with engine.connect() as conn:
        try:
            cursor = conn.exec_driver_sql("PRAGMA table_info(unifiedtrack)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            if not existing_cols:
                return

            new_columns = {
                "codec": "TEXT",
                "bitrate_kbps": "INTEGER",
                "sample_rate_hz": "INTEGER",
                "bit_depth": "INTEGER",
                "channels": "INTEGER",
                "file_size_bytes": "INTEGER",
                "integrated_lufs": "REAL",
                "is_corrupted": "BOOLEAN DEFAULT 0",
                "quality_warning": "TEXT",
                "track_number": "INTEGER",
                "play_count": "INTEGER DEFAULT 0",
                "last_played_at": "TIMESTAMP",
                "energy": "REAL",
                "true_peak_dbfs": "REAL",
                "dynamic_range_db": "REAL",
                "crest_factor_db": "REAL",
                "silence_start_ms": "INTEGER",
                "silence_end_ms": "INTEGER",
                "loudness_range_lu": "REAL",
                "momentary_lufs": "REAL",
                "short_term_lufs": "REAL",
                "clipping_count": "INTEGER",
                "analysis_version": "INTEGER DEFAULT 1",
                "analyzed_at": "TIMESTAMP",
                "camelot_code": "TEXT",
                "bpm_stability": "REAL",
                "danceability": "REAL",
                "beatgrid_json": "TEXT",
                "sections_json": "TEXT",
                "musical_analysis_confidence": "REAL",
                "musical_analyzed_at": "TIMESTAMP",
            }
            for col_name, col_type in new_columns.items():
                if col_name not in existing_cols:
                    conn.exec_driver_sql(f"ALTER TABLE unifiedtrack ADD COLUMN {col_name} {col_type}")
            conn.commit()
        except Exception as e:
            print(f"[Database] Migration note: {e}")


def init_db() -> None:
    """Create all database tables on application startup and perform migrations."""
    SQLModel.metadata.create_all(engine)
    migrate_db()


def get_session() -> Generator[Session, None, None]:
    """Dependency helper to yield database sessions."""
    with Session(engine) as session:
        yield session
