from typing import Any, Optional
import httpx

from app.config import get_settings


class ListenBrainzProvider:
    """Optional ListenBrainz API client for similar recordings and listening discovery.

    Degrades gracefully when LISTENBRAINZ_TOKEN is not configured.
    """

    BASE_URL = "https://api.listenbrainz.org/1"
    LABS_URL = "https://labs.api.listenbrainz.org"

    def __init__(
        self,
        token: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.token = token if token is not None else get_settings().LISTENBRAINZ_TOKEN
        self.timeout = timeout
        self._transport = transport

    def is_configured(self) -> bool:
        """Return True if a ListenBrainz token is configured."""
        return bool(self.token and self.token.strip())

    def _build_client(self) -> httpx.AsyncClient:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.is_configured():
            headers["Authorization"] = f"Token {self.token.strip()}"
        kwargs: dict[str, Any] = {"timeout": self.timeout, "headers": headers}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def get_similar_recordings(
        self, recording_mbid: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Fetch similar recordings from ListenBrainz Labs for a MusicBrainz recording ID."""
        if not recording_mbid or not self.is_configured():
            return []

        async with self._build_client() as client:
            try:
                resp = await client.get(
                    f"{self.LABS_URL}/similar-recordings/json",
                    params={
                        "recording_mbids": recording_mbid,
                        "algorithm": "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data[:limit]
            except Exception as e:
                print(f"[ListenBrainzProvider] Similar recordings error ({recording_mbid}): {e}")
        return []
