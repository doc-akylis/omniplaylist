from typing import Any, Optional
import httpx

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


class AudiusAdapter(ProviderAdapter):
    """Audius REST API v1 adapter — checks per-track downloadable / is_downloadable flag strictly."""

    provider_id = "audius"
    BASE_URL = "https://api.audius.co/v1"
    APP_NAME = "OmniPlaylist"

    def __init__(
        self,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.25)
        self._transport = transport

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Audius",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            requires_auth=False,
            auth_configured=True,
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_streaming=True,
            supports_download=True,
            formats=["MP3 / Original (quando downloadable=true)"],
            rate_limit_info="API pública v1 sem chave obrigatória (parâmetro app_name).",
            cost_info="Gratuito (Artistas independentes / Eletrônica / Remixes)",
            restrictions="Download permitido SOMENTE quando o artista habilita is_downloadable/downloadable=true; caso contrário apenas streaming.",
        )

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    async def search_tracks(
        self, query: str, limit: int = 10, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        clean = query.strip()
        if not clean:
            return []

        await self._rate_limiter.acquire()
        results: list[NormalizedTrackResult] = []
        async with self._build_client() as client:
            resp = await client.get(
                f"{self.BASE_URL}/tracks/search",
                params={"query": clean, "limit": limit, "app_name": self.APP_NAME},
            )
            if resp.status_code != 200:
                return []
            items = resp.json().get("data") or []
            for item in items[:limit]:
                tid = str(item.get("id") or "")
                title = str(item.get("title") or "Unknown Title")
                user = item.get("user") or {}
                artist = str(user.get("name") or user.get("handle") or "Unknown Artist")
                is_dl = bool(item.get("is_downloadable") or item.get("downloadable"))
                stream_url = f"{self.BASE_URL}/tracks/{tid}/stream?app_name={self.APP_NAME}" if tid else None
                dl_url = item.get("download_url") or (
                    f"{self.BASE_URL}/tracks/{tid}/stream?app_name={self.APP_NAME}&download=true" if (is_dl and tid) else None
                )
                artwork = item.get("artwork") or {}
                cover_url = artwork.get("1000x1000") or artwork.get("480x480") or artwork.get("150x150")
                dur_sec = item.get("duration")

                if is_dl and dl_url:
                    perm = DownloadPermission(
                        status=PermissionStatus.ALLOWED_FREE,
                        downloadable=True,
                        requires_payment=False,
                        license_name="Audius Creator Free Download",
                        reason="Artista habilitou download gratuito na faixa Audius (downloadable=true).",
                    )
                    fmts = [FormatOption(codec="mp3", container="mp3", bitrate_kbps=320, is_lossless=False, download_url=dl_url)]
                else:
                    perm = DownloadPermission(
                        status=PermissionStatus.STREAMING_ONLY,
                        downloadable=False,
                        requires_payment=False,
                        reason="Faixa Audius com downloadable=false (apenas streaming permitido).",
                    )
                    fmts = []

                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Audius",
                        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
                        source_item_id=tid,
                        title=title,
                        artist=artist,
                        duration_ms=int(float(dur_sec) * 1000) if dur_sec else None,
                        version_type=TrackMatcher.detect_version_type(title),
                        genres=[str(item["genre"])] if item.get("genre") else [],
                        cover_url=cover_url,
                        preview_url=stream_url,
                        download_url=dl_url if is_dl else None,
                        is_preview_only=False,
                        permission=perm,
                        formats=fmts,
                        declared_codec="mp3" if is_dl else None,
                        declared_bitrate_kbps=320 if is_dl else None,
                        origin_classification="LOSSY_SOURCE" if is_dl else "UNKNOWN_SOURCE",
                        license_info="Audius Download Enabled" if is_dl else "Audius Stream Only",
                        raw_metadata={"id": tid, "downloadable": is_dl},
                    )
                )
        return results

    async def health_check(self) -> dict[str, Any]:
        try:
            async with self._build_client() as client:
                r = await client.get(f"{self.BASE_URL}/tracks/trending", params={"limit": 1, "app_name": self.APP_NAME})
                ok = r.status_code == 200
                return {"ok": ok, "status": "active" if ok else f"http_{r.status_code}", "detail": "Audius v1 Discovery API acessível"}
        except Exception as e:
            return {"ok": False, "status": "unreachable", "detail": str(e)}
