from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Relationship, SQLModel


class ExportFormat(str, Enum):
    """Supported playlist export formats."""
    M3U8 = "m3u8"
    CSV = "csv"
    JSON = "json"
    XSPF = "xspf"


class PlaylistTrackLink(SQLModel, table=True):
    """Many-to-many link between playlists and unified tracks."""
    playlist_id: Optional[int] = SQLField(default=None, foreign_key="playlist.id", primary_key=True)
    track_id: Optional[int] = SQLField(default=None, foreign_key="unifiedtrack.id", primary_key=True)
    position: int = SQLField(default=0)


class UnifiedTrack(SQLModel, table=True):
    """Normalized multi-platform track model."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    isrc: Optional[str] = SQLField(default=None, index=True)
    title: str = SQLField(index=True)
    artist: str = SQLField(index=True)
    album: Optional[str] = SQLField(default=None)
    duration_ms: Optional[int] = SQLField(default=None)
    genres_raw: str = SQLField(default="")  # Comma-separated or JSON list
    cover_url: Optional[str] = SQLField(default=None)

    # Provider specific IDs
    spotify_id: Optional[str] = SQLField(default=None, index=True)
    ytmusic_id: Optional[str] = SQLField(default=None, index=True)
    amazon_id: Optional[str] = SQLField(default=None, index=True)
    deezer_id: Optional[str] = SQLField(default=None, index=True)

    # Audio analysis & characteristics
    bpm: Optional[float] = SQLField(default=None)
    key: Optional[str] = SQLField(default=None)  # e.g., '8A', 'Am'
    camelot_code: Optional[str] = SQLField(default=None)  # e.g., '8A', '11B'
    bpm_stability: Optional[float] = SQLField(default=None)
    danceability: Optional[float] = SQLField(default=None)  # 0.0 to 1.0
    beatgrid_json: Optional[str] = SQLField(default=None)
    sections_json: Optional[str] = SQLField(default=None)
    musical_analysis_confidence: Optional[float] = SQLField(default=None)  # 0.0 to 1.0
    musical_analyzed_at: Optional[datetime] = SQLField(default=None)
    replay_gain: Optional[float] = SQLField(default=None)
    integrated_lufs: Optional[float] = SQLField(default=None)
    energy: Optional[float] = SQLField(default=None)  # 0.0 to 1.0

    # Technical audio inspection & quality
    codec: Optional[str] = SQLField(default=None)
    bitrate_kbps: Optional[int] = SQLField(default=None)
    sample_rate_hz: Optional[int] = SQLField(default=None)
    bit_depth: Optional[int] = SQLField(default=None)
    channels: Optional[int] = SQLField(default=None)
    file_size_bytes: Optional[int] = SQLField(default=None)
    is_corrupted: bool = SQLField(default=False)
    quality_warning: Optional[str] = SQLField(default=None)

    # Advanced technical analysis (FFmpeg/ffprobe)
    true_peak_dbfs: Optional[float] = SQLField(default=None)
    dynamic_range_db: Optional[float] = SQLField(default=None)
    crest_factor_db: Optional[float] = SQLField(default=None)
    silence_start_ms: Optional[int] = SQLField(default=None)
    silence_end_ms: Optional[int] = SQLField(default=None)
    loudness_range_lu: Optional[float] = SQLField(default=None)
    momentary_lufs: Optional[float] = SQLField(default=None)
    short_term_lufs: Optional[float] = SQLField(default=None)
    clipping_count: Optional[int] = SQLField(default=None)
    analysis_version: int = SQLField(default=1)
    analyzed_at: Optional[datetime] = SQLField(default=None)

    # Playback stats & metadata details
    track_number: Optional[int] = SQLField(default=None)
    play_count: int = SQLField(default=0)
    last_played_at: Optional[datetime] = SQLField(default=None)

    # Lyrics & Enhanced Metadata
    lyrics_synced: Optional[str] = SQLField(default=None)  # LRC format
    lyrics_plain: Optional[str] = SQLField(default=None)
    preview_url: Optional[str] = SQLField(default=None)
    hd_cover_url: Optional[str] = SQLField(default=None)
    release_year: Optional[int] = SQLField(default=None)

    # Local file cache
    local_path: Optional[str] = SQLField(default=None)

    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))

    playlists: list["Playlist"] = Relationship(
        back_populates="tracks", link_model=PlaylistTrackLink
    )

    @property
    def genres(self) -> list[str]:
        """Return genres as a clean list of strings."""
        if not self.genres_raw:
            return []
        return [g.strip() for g in self.genres_raw.split(",") if g.strip()]


class Playlist(SQLModel, table=True):
    """Playlist representation."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    name: str = SQLField(index=True)
    description: Optional[str] = SQLField(default=None)
    source_provider: str = SQLField(default="local")  # spotify, ytmusic, amazon, local
    external_id: Optional[str] = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))

    tracks: list[UnifiedTrack] = Relationship(
        back_populates="playlists", link_model=PlaylistTrackLink
    )


class ExportConfig(BaseModel):
    """Configuration schema for exporting playlists."""
    playlist_id: int
    format: ExportFormat = ExportFormat.M3U8
    output_directory: Optional[str] = None
    include_extended_info: bool = True
    sync_to_provider: Optional[str] = None  # e.g., 'ytmusic', 'spotify'


class MatchResult(BaseModel):
    """Result of track equivalence matching."""
    source_track: UnifiedTrack
    target_track: Optional[UnifiedTrack] = None
    confidence_score: float = Field(ge=0.0, le=1.0)
    match_strategy: str  # 'isrc', 'fuzzy_token', 'exact_meta', etc.
    matched: bool = False


class DeviceSyncProfile(SQLModel, table=True):
    """Sync target profile configuration (e.g. Car USB, DJ drive, Portable player)."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    name: str = SQLField(index=True)
    target_dir: str
    profile_type: str = SQLField(default="car")  # car, dj, archive, custom
    output_format: str = SQLField(default="mp3")
    bitrate_kbps: int = SQLField(default=320)
    naming_pattern: str = SQLField(default="{artist}/{album}/{track_number} - {title}.{ext}")
    auto_generate_m3u: bool = SQLField(default=True)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class UserHistory(SQLModel, table=True):
    """Audit log of user events (listens, recommendations, additions, rejections)."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    track_id: Optional[int] = SQLField(default=None, foreign_key="unifiedtrack.id")
    event_type: str = SQLField(index=True)  # "played", "recommended", "added", "rejected"
    notes: Optional[str] = SQLField(default=None)
    timestamp: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class BackupRecord(SQLModel, table=True):
    """Catalog of database snapshots and library backups."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    filename: str = SQLField(index=True)
    file_path: str
    file_size_bytes: int = SQLField(default=0)
    track_count: int = SQLField(default=0)
    playlist_count: int = SQLField(default=0)
    checksum_sha256: str = SQLField(default="")
    status: str = SQLField(default="valid")
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class UserSettings(SQLModel, table=True):
    """Global user appearance, audio playback, and dashboard preferences."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    theme_name: str = SQLField(default="Omni Green")
    accent_color: str = SQLField(default="#1DB954")
    bg_color: str = SQLField(default="#121212")
    card_bg: str = SQLField(default="#181818")
    text_color: str = SQLField(default="#E5E7EB")
    card_rounding: str = SQLField(default="rounded-xl")
    density: str = SQLField(default="comfortable")
    enable_history_tracking: bool = SQLField(default=True)
    crossfade_sec: float = SQLField(default=0.0)
    eq_gains_json: str = SQLField(default="[0,0,0,0,0,0,0,0,0,0]")
    dashboard_layout_json: str = SQLField(
        default='["stats","recent_added","favorite_playlists","quick_actions","download_queue"]'
    )
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
