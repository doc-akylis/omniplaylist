from typing import Any, Optional
import httpx

from app.config import get_settings
from app.core.matcher import TrackMatcher
from app.providers.rate_limiter import AsyncRateLimiter
from app.sources.base import (
    DownloadPermission,
    FormatOption,
    NormalizedTrackResult,
    PermissionStatus,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderCategory,
)


class SoundCloudAdapter(ProviderAdapter):
    """SoundCloud API adapter — strictly checks downloadable=true & non-empty download_url."""

    provider_id = "soundcloud"
    BASE_URL = "https://api.soundcloud.com"

    def __init__(
        self,
        client_id: Optional[str] = None,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.client_id = client_id if client_id is not None else get_settings().SOUNDCLOUD_CLIENT_ID
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.3)
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_id.strip())

    def capabilities(self) -> ProviderCapabilities:
        configured = self.is_configured()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="SoundCloud",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            requires_auth=True,
            auth_configured=configured,
            missing_credentials=[] if configured else ["SOUNDCLOUD_CLIENT_ID"],
            supports_search_tracks=True,
            supports_streaming=True,
            supports_download=True,
            formats=["WAV / MP3 / Original (quando downloadable=true)"],
            rate_limit_info="Requer SOUNDCLOUD_CLIENT_ID / OAuth autorizado.",
            cost_info="Gratuito (somente faixas marcadas como downloadable=true pelo criador)",
            restrictions="Nunca faz stream-ripping de HLS; exige downloadable=true e download_url válida.",
        )

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def search_tracks(
        self, query: str, limit: int = 10, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        if not self.is_configured() or not query.strip():
            return []

        await self._rate_limiter.acquire()
        results: list[NormalizedTrackResult] = []
        async with self._build_client() as client:
            resp = await client.get(
                f"{self.BASE_URL}/tracks",
                params={"q": query.strip(), "limit": limit, "client_id": self.client_id.strip()},
            )
            if resp.status_code != 200:
                return []
            items = resp.json()
            if not isinstance(items, list):
                return []
            for item in items[:limit]:
                tid = str(item.get("id") or "")
                title = str(item.get("title") or "Unknown")
                user = item.get("user") or {}
                artist = str(user.get("username") or "SoundCloud Artist")
                is_dl = item.get("downloadable") is True
                dl_url = str(item.get("download_url") or "").strip() if is_dl else ""
                if is_dl and dl_url and "client_id=" not in dl_url:
                    sep = "&" if "?" in dl_url else "?"
                    dl_url = f"{dl_url}{sep}client_id={self.client_id.strip()}"
                orig_fmt = str(item.get("original_format") or "mp3").lower()
                is_lossless = orig_fmt in ("wav", "flac", "aiff")

                if is_dl and dl_url:
                    perm = DownloadPermission(
                        status=PermissionStatus.ALLOWED_FREE,
                        downloadable=True,
                        requires_payment=False,
                        license_name=str(item.get("license") or "SoundCloud Creator Download"),
                        reason="downloadable=true e download_url confirmados.",
                    )
                    fmts = [FormatOption(codec=orig_fmt, container=orig_fmt, is_lossless=is_lossless, download_url=dl_url)]
                else:
                    perm = DownloadPermission(
                        status=PermissionStatus.STREAMING_ONLY,
                        downloadable=False,
                        requires_payment=False,
                        reason="Faixa SoundCloud com downloadable=false (stream-ripping bloqueado).",
                    )
                    fmts = []

                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="SoundCloud",
                        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
                        source_item_id=tid,
                        title=title,
                        artist=artist,
                        duration_ms=int(item["duration"]) if item.get("duration") else None,
                        version_type=TrackMatcher.detect_version_type(title),
                        genres=[str(item["genre"])] if item.get("genre") else [],
                        cover_url=item.get("artwork_url"),
                        preview_url=item.get("stream_url"),
                        download_url=dl_url or None,
                        is_preview_only=False,
                        permission=perm,
                        formats=fmts,
                        declared_codec=orig_fmt if (is_dl and dl_url) else None,
                        origin_classification="LOSSLESS_SOURCE" if (is_dl and is_lossless) else ("LOSSY_SOURCE" if is_dl else "UNKNOWN_SOURCE"),
                        license_info=str(item.get("license") or "SoundCloud"),
                        raw_metadata={"id": tid, "downloadable": is_dl},
                    )
                )
        return results

    async def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "status": "requires_credentials", "detail": "Configure SOUNDCLOUD_CLIENT_ID"}
        try:
            async with self._build_client() as client:
                r = await client.get(f"{self.BASE_URL}/tracks", params={"q": "test", "limit": 1, "client_id": self.client_id.strip()})
                ok = r.status_code == 200
                return {"ok": ok, "status": "active" if ok else f"http_{r.status_code}", "detail": "SoundCloud API acessível"}
        except Exception as e:
            return {"ok": False, "status": "unreachable", "detail": str(e)}
