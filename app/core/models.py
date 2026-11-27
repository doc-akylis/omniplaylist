from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
from sqlmodel import Field as SQLField, Relationship, SQLModel


class ExportFormat(str, Enum):
    """Supported playlist export formats."""
    M3U = "m3u"
    M3U8 = "m3u8"
    CSV = "csv"
    JSON = "json"
    XSPF = "xspf"


class PlaylistTrackLink(SQLModel, table=True):
    """Many-to-many link between playlists and unified tracks."""
    playlist_id: Optional[int] = SQLField(default=None, foreign_key="playlist.id", primary_key=True)
    track_id: Optional[int] = SQLField(default=None, foreign_key="unifiedtrack.id", primary_key=True)
    position: int = SQLField(default=0)
    added_at: Optional[datetime] = SQLField(default_factory=lambda: datetime.now(timezone.utc))


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
    musicbrainz_recording_id: Optional[str] = SQLField(default=None, index=True)
    acoustid_id: Optional[str] = SQLField(default=None, index=True)

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
    lastfm_tags: Optional[str] = SQLField(default=None)
    metadata_enriched_at: Optional[datetime] = SQLField(default=None)

    # Local file cache
    local_path: Optional[str] = SQLField(default=None)

    # Audio Quality Intelligence (v2.1)
    is_preview: bool = SQLField(default=False)
    source_classification: Optional[str] = SQLField(default=None)  # LOSSLESS_SOURCE, LOSSY_SOURCE, UNKNOWN_SOURCE
    spectral_cutoff_hz: Optional[float] = SQLField(default=None)
    upscale_status: Optional[str] = SQLField(default=None)  # VERIFIED_LOSSLESS_SOURCE, VERIFIED_LOSSY_SOURCE, LIKELY_UPSCALE, SUSPECTED_UPSCALE, UNKNOWN
    upscale_confidence: Optional[float] = SQLField(default=None)
    is_fake_upscale: bool = SQLField(default=False)
    sub_bass_energy: Optional[float] = SQLField(default=None)
    mid_bass_energy: Optional[float] = SQLField(default=None)
    midrange_energy: Optional[float] = SQLField(default=None)
    high_freq_energy: Optional[float] = SQLField(default=None)
    car_audio_score: Optional[float] = SQLField(default=None)
    car_audio_status: Optional[str] = SQLField(default=None)
    car_audio_ready: bool = SQLField(default=False)
    quality_intelligence_json: Optional[str] = SQLField(default=None)
    quality_analyzed_at: Optional[datetime] = SQLField(default=None)

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
    cover_url: Optional[str] = SQLField(default=None)
    original_order_json: Optional[str] = SQLField(default=None)
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


class AudioProvenance(SQLModel, table=True):
    """Structured origin and lifecycle provenance for an audio track."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    track_id: int = SQLField(foreign_key="unifiedtrack.id", index=True)
    acquisition_source: str = SQLField(default="unknown")  # local_scan, download_studio, online_import, unknown
    provider: Optional[str] = SQLField(default=None)
    source_item_id: Optional[str] = SQLField(default=None)
    source_url: Optional[str] = SQLField(default=None)
    file_sha256: Optional[str] = SQLField(default=None, index=True)
    license_info: Optional[str] = SQLField(default=None)
    original_codec: Optional[str] = SQLField(default=None)
    original_bitrate_kbps: Optional[int] = SQLField(default=None)
    original_sample_rate_hz: Optional[int] = SQLField(default=None)
    original_bit_depth: Optional[int] = SQLField(default=None)
    origin_classification: str = SQLField(default="UNKNOWN_SOURCE")  # LOSSLESS_SOURCE, LOSSY_SOURCE, UNKNOWN_SOURCE
    current_container: Optional[str] = SQLField(default=None)
    current_codec: Optional[str] = SQLField(default=None)
    requested_profile: Optional[str] = SQLField(default=None)
    evidence_json: Optional[str] = SQLField(default=None)
    declared_metadata_json: Optional[str] = SQLField(default=None)
    extracted_metadata_json: Optional[str] = SQLField(default=None)
    inferences_json: Optional[str] = SQLField(default=None)
    verification_status: str = SQLField(default="UNVERIFIED")  # VERIFIED, PARTIAL, UNVERIFIED
    engine_name: str = SQLField(default="AudioQualityIntelligenceEngine")
    engine_version: str = SQLField(default="2.2.0")
    acquired_at: Optional[datetime] = SQLField(default=None)
    analyzed_at: Optional[datetime] = SQLField(default=None)
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class AudioProcessingHistory(SQLModel, table=True):
    """Immutable audit trail of conversions, replacements, and quality analyses."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    track_id: int = SQLField(foreign_key="unifiedtrack.id", index=True)
    provenance_id: Optional[int] = SQLField(default=None, foreign_key="audioprovenance.id")
    operation: str = SQLField(index=True)  # acquire, convert, tag, upgrade_replace, quality_analyze
    from_codec: Optional[str] = SQLField(default=None)
    to_codec: Optional[str] = SQLField(default=None)
    from_bitrate_kbps: Optional[int] = SQLField(default=None)
    to_bitrate_kbps: Optional[int] = SQLField(default=None)
    profile: Optional[str] = SQLField(default=None)
    source_path: Optional[str] = SQLField(default=None)
    dest_path: Optional[str] = SQLField(default=None)
    backup_path: Optional[str] = SQLField(default=None)
    was_lossy_to_lossless: bool = SQLField(default=False)
    warnings_json: Optional[str] = SQLField(default=None)
    engine_name: str = SQLField(default="DownloadStudioEngine")
    engine_version: str = SQLField(default="2.1.0")
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class DownloadJob(SQLModel, table=True):
    """Persistent acquisition, conversion, validation, and upgrade job."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    track_id: Optional[int] = SQLField(default=None, foreign_key="unifiedtrack.id", index=True)
    provider: str = SQLField(default="authorized_url")
    source_item_id: Optional[str] = SQLField(default=None)
    source_url: Optional[str] = SQLField(default=None)
    source_label: Optional[str] = SQLField(default=None)
    status: str = SQLField(default="PENDING", index=True)
    profile: str = SQLField(default="ORIGINAL")
    acquisition_mode: str = SQLField(default="AUTO_BEST_SOURCE")
    requires_approval: bool = SQLField(default=False)
    approved_by_user: bool = SQLField(default=False)
    estimated_cost_label: Optional[str] = SQLField(default=None)
    license_info: Optional[str] = SQLField(default=None)
    file_sha256: Optional[str] = SQLField(default=None)
    target_sample_rate_hz: Optional[int] = SQLField(default=None)
    source_path: Optional[str] = SQLField(default=None)
    dest_path: Optional[str] = SQLField(default=None)
    temp_path: Optional[str] = SQLField(default=None)
    backup_path: Optional[str] = SQLField(default=None)
    progress: float = SQLField(default=0.0)
    speed_bps: Optional[float] = SQLField(default=None)
    eta_sec: Optional[float] = SQLField(default=None)
    estimated_bytes: Optional[int] = SQLField(default=None)
    final_bytes: Optional[int] = SQLField(default=None)
    current_stage: str = SQLField(default="PENDING")
    logs_json: str = SQLField(default="[]")
    error_message: Optional[str] = SQLField(default=None)
    attempts: int = SQLField(default=0)
    max_attempts: int = SQLField(default=3)
    upgrade_decision: Optional[str] = SQLField(default=None)
    upgrade_reason: Optional[str] = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = SQLField(default=None)
    finished_at: Optional[datetime] = SQLField(default=None)
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class MusicProviderConfig(SQLModel, table=True):
    """Non-secret configuration and health state for each registered music source adapter."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    provider_id: str = SQLField(unique=True, index=True)
    enabled: bool = SQLField(default=True)
    priority: int = SQLField(default=100)
    last_health_status: Optional[str] = SQLField(default=None)
    last_health_check_at: Optional[datetime] = SQLField(default=None)
    notes: Optional[str] = SQLField(default=None)
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class MusicSearchSession(SQLModel, table=True):
    """Multi-provider search session cache and source telemetry."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    query: str = SQLField(index=True)
    search_type: str = SQLField(default="track")
    providers_queried_json: str = SQLField(default="[]")
    providers_responded_json: str = SQLField(default="[]")
    providers_failed_json: str = SQLField(default="{}")
    downloadable_count: int = SQLField(default=0)
    total_results: int = SQLField(default=0)
    cached_results_json: str = SQLField(default="[]")
    expires_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))


class AcquisitionRecord(SQLModel, table=True):
    """Audit record of automatic or manual source selection, permission approval, and acquisition outcome."""
    id: Optional[int] = SQLField(default=None, primary_key=True)
    search_session_id: Optional[int] = SQLField(default=None, foreign_key="musicsearchsession.id")
    download_job_id: Optional[int] = SQLField(default=None, foreign_key="downloadjob.id", index=True)
    track_id: Optional[int] = SQLField(default=None, foreign_key="unifiedtrack.id", index=True)
    provider_id: str = SQLField(index=True)
    source_item_id: Optional[str] = SQLField(default=None)
    acquisition_mode: str = SQLField(default="AUTO_BEST_SOURCE")
    status: str = SQLField(default="INITIATED")
    license_info: Optional[str] = SQLField(default=None)
    was_paid: bool = SQLField(default=False)
    approved_by_user: bool = SQLField(default=False)
    file_sha256: Optional[str] = SQLField(default=None)
    comparison_summary_json: Optional[str] = SQLField(default=None)
    error_message: Optional[str] = SQLField(default=None)
    created_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = SQLField(default_factory=lambda: datetime.now(timezone.utc))
