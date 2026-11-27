from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel, Field


class ProviderCategory(str, Enum):
    """Strict 4-tier classification distinguishing discovery/preview from authorized acquisition."""

    DISCOVERY = "DISCOVERY"
    PREVIEW_STREAMING = "PREVIEW_STREAMING"
    AUTHORIZED_DOWNLOAD = "AUTHORIZED_DOWNLOAD"
    COMMERCIAL_DELIVERY = "COMMERCIAL_DELIVERY"


class PermissionStatus(str, Enum):
    """Explicit download authorization state for a specific track or source."""

    ALLOWED_FREE = "ALLOWED_FREE"
    ALLOWED_COMMERCIAL_REQUIRES_APPROVAL = "ALLOWED_COMMERCIAL_REQUIRES_APPROVAL"
    PREVIEW_ONLY = "PREVIEW_ONLY"
    STREAMING_ONLY = "STREAMING_ONLY"
    NOT_DOWNLOADABLE = "NOT_DOWNLOADABLE"
    REQUIRES_CREDENTIALS = "REQUIRES_CREDENTIALS"
    UNAVAILABLE = "UNAVAILABLE"


class FormatOption(BaseModel):
    """Available audio format option declared by a provider."""

    codec: str
    container: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    sample_rate_hz: Optional[int] = None
    bit_depth: Optional[int] = None
    file_size_bytes: Optional[int] = None
    is_lossless: bool = False
    is_derivative: bool = False
    download_url: Optional[str] = None


class DownloadPermission(BaseModel):
    """Explicit permission check result for a track candidate."""

    status: PermissionStatus
    downloadable: bool = False
    requires_payment: bool = False
    requires_credentials: bool = False
    license_name: Optional[str] = None
    license_url: Optional[str] = None
    estimated_cost_label: Optional[str] = None
    reason: str = ""


class ProviderCapabilities(BaseModel):
    """Metadata and operational capabilities exposed by a registered provider."""

    provider_id: str
    name: str
    category: ProviderCategory
    requires_auth: bool = False
    auth_configured: bool = True
    missing_credentials: list[str] = Field(default_factory=list)
    supports_search_tracks: bool = True
    supports_search_artists: bool = False
    supports_search_albums: bool = False
    supports_streaming: bool = False
    supports_download: bool = False
    formats: list[str] = Field(default_factory=list)
    rate_limit_info: str = ""
    cost_info: str = "Gratuito / Público"
    restrictions: str = ""
    docs_verified: bool = True


class NormalizedTrackResult(BaseModel):
    """Unified normalized representation of a track returned by any source adapter."""

    provider_id: str
    provider_name: str
    category: ProviderCategory
    source_item_id: str
    title: str
    artist: str
    album: Optional[str] = None
    track_number: Optional[int] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    mbid: Optional[str] = None
    release_year: Optional[int] = None
    version_type: str = "original"
    genres: list[str] = Field(default_factory=list)
    cover_url: Optional[str] = None
    preview_url: Optional[str] = None
    download_url: Optional[str] = None
    is_preview_only: bool = False
    permission: DownloadPermission
    formats: list[FormatOption] = Field(default_factory=list)
    declared_codec: Optional[str] = None
    declared_bitrate_kbps: Optional[int] = None
    declared_sample_rate_hz: Optional[int] = None
    declared_bit_depth: Optional[int] = None
    origin_classification: str = "UNKNOWN_SOURCE"
    suspected_transcode: bool = False
    license_info: Optional[str] = None
    requires_payment: bool = False
    estimated_cost_label: Optional[str] = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class GroupedRecording(BaseModel):
    """Cluster of NormalizedTrackResult entries representing the same musical recording and version."""

    group_key: str
    title: str
    artist: str
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    mbid: Optional[str] = None
    version_type: str = "original"
    cover_url: Optional[str] = None
    match_confidence: float = 1.0
    match_strategy: str = "exact"
    has_downloadable_source: bool = False
    has_free_download: bool = False
    has_commercial_download: bool = False
    candidates: list[NormalizedTrackResult] = Field(default_factory=list)
    comparison: Optional[dict[str, Any]] = None


class ProviderAdapter(ABC):
    """Common extensible contract implemented by all discovery, preview, authorized, and commercial sources."""

    provider_id: str = "base"

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        """Declare exact provider capabilities, auth status, formats, and restrictions."""
        pass

    @abstractmethod
    async def search_tracks(
        self, query: str, limit: int = 10, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        """Search tracks (or ISRC/album/live/remix queries) and return normalized results."""
        pass

    async def search_artists(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search artists when supported; returns explicit unsupported marker otherwise."""
        return []

    async def search_albums(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search albums when supported; returns empty list otherwise."""
        return []

    async def get_track_details(self, item_id: str) -> Optional[NormalizedTrackResult]:
        """Fetch detailed metadata & format options for a provider-specific item ID."""
        return None

    def get_available_formats(self, item: NormalizedTrackResult) -> list[FormatOption]:
        """Return formats explicitly exposed by this item."""
        return item.formats

    def get_download_permission(self, item: NormalizedTrackResult) -> DownloadPermission:
        """Return explicit download permission without assuming CC or catalog presence implies download."""
        return item.permission

    async def acquire_track(
        self, item: NormalizedTrackResult, dest_dir: Path
    ) -> tuple[Optional[Path], Optional[str]]:
        """Return local/staged path or explicit non-downloadable error if source does not allow file acquisition."""
        perm = self.get_download_permission(item)
        if not perm.downloadable:
            return None, perm.reason or f"{self.provider_id} não disponibiliza download autorizado de arquivo completo."
        return None, "Use DownloadStudioEngine com item.download_url para streaming seguro e validação."

    @abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Check connectivity / configuration readiness of the provider."""
        pass
