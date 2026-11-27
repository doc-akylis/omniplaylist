from collections.abc import Generator
from typing import Any, Optional
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


def _add_missing_columns(conn: Any, table_name: str, columns: dict[str, str]) -> None:
    """Safely inspect PRAGMA table_info and append missing columns to an existing SQLite table."""
    cursor = conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if not existing_cols:
        return
    for col_name, col_type in columns.items():
        if col_name not in existing_cols:
            conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")


def migrate_db(target_engine: Optional[Any] = None) -> None:
    """Safe idempotent schema migration adding new columns to existing SQLite tables if needed."""
    eng = target_engine or engine
    if eng.dialect.name != "sqlite":
        return

    with eng.connect() as conn:
        try:
            unified_columns = {
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
                "musicbrainz_recording_id": "TEXT",
                "acoustid_id": "TEXT",
                "lastfm_tags": "TEXT",
                "metadata_enriched_at": "TIMESTAMP",
                # v2.1 Audio Quality Intelligence
                "is_preview": "BOOLEAN DEFAULT 0",
                "source_classification": "TEXT",
                "spectral_cutoff_hz": "REAL",
                "upscale_status": "TEXT",
                "upscale_confidence": "REAL",
                "is_fake_upscale": "BOOLEAN DEFAULT 0",
                "sub_bass_energy": "REAL",
                "mid_bass_energy": "REAL",
                "midrange_energy": "REAL",
                "high_freq_energy": "REAL",
                "car_audio_score": "REAL",
                "car_audio_status": "TEXT",
                "car_audio_ready": "BOOLEAN DEFAULT 0",
                "quality_intelligence_json": "TEXT",
                "quality_analyzed_at": "TIMESTAMP",
            }
            _add_missing_columns(conn, "unifiedtrack", unified_columns)

            playlist_columns = {
                "cover_url": "TEXT",
                "original_order_json": "TEXT",
            }
            _add_missing_columns(conn, "playlist", playlist_columns)

            link_columns = {
                "added_at": "TIMESTAMP",
            }
            _add_missing_columns(conn, "playlisttracklink", link_columns)

            provenance_columns = {
                "source_item_id": "TEXT",
                "file_sha256": "TEXT",
                "license_info": "TEXT",
                "declared_metadata_json": "TEXT",
                "extracted_metadata_json": "TEXT",
                "inferences_json": "TEXT",
                "verification_status": "TEXT DEFAULT 'UNVERIFIED'",
            }
            _add_missing_columns(conn, "audioprovenance", provenance_columns)

            downloadjob_columns = {
                "source_item_id": "TEXT",
                "acquisition_mode": "TEXT DEFAULT 'AUTO_BEST_SOURCE'",
                "requires_approval": "BOOLEAN DEFAULT 0",
                "approved_by_user": "BOOLEAN DEFAULT 0",
                "estimated_cost_label": "TEXT",
                "license_info": "TEXT",
                "file_sha256": "TEXT",
            }
            _add_missing_columns(conn, "downloadjob", downloadjob_columns)

            conn.commit()
        except Exception as e:
            print(f"[Database] Migration note: {e}")


def init_db(target_engine: Optional[Any] = None) -> None:
    """Create all database tables on application startup and perform idempotent migrations."""
    eng = target_engine or engine
    SQLModel.metadata.create_all(eng)
    migrate_db(eng)


def get_session() -> Generator[Session, None, None]:
    """Dependency helper to yield database sessions."""
    with Session(engine) as session:
        yield session
