from abc import ABC, abstractmethod
from typing import Optional
from app.core.models import UnifiedTrack


class BaseMusicProvider(ABC):
    """Abstract base class for all streaming music providers."""

    provider_name: str = "base"

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the provider API / session."""
        pass

    @abstractmethod
    async def search_tracks(self, query: str, limit: int = 20) -> list[UnifiedTrack]:
        """Search for tracks using standard text query."""
        pass

    @abstractmethod
    async def get_playlist(self, playlist_id: str) -> list[UnifiedTrack]:
        """Fetch all tracks belonging to a given playlist identifier."""
        pass

    @abstractmethod
    async def create_playlist(
        self, name: str, tracks: list[UnifiedTrack], description: str = ""
    ) -> str:
        """Create a new playlist and insert tracks. Return new playlist ID."""
        pass

    @abstractmethod
    async def get_track(self, track_id: str) -> Optional[UnifiedTrack]:
        """Retrieve detailed metadata for a single track by provider ID."""
        pass
