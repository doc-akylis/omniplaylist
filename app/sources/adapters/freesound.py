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


class FreesoundAdapter(ProviderAdapter):
    """Freesound API v2 adapter — Creative Commons samples, loops, and field recordings."""

    provider_id = "freesound"
    BASE_URL = "https://freesound.org/apiv2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = api_key if api_key is not None else get_settings().FREESOUND_API_KEY
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.3)
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def capabilities(self) -> ProviderCapabilities:
        configured = self.is_configured()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Freesound (API v2)",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            requires_auth=True,
            auth_configured=configured,
            missing_credentials=[] if configured else ["FREESOUND_API_KEY"],
            supports_search_tracks=True,
            supports_streaming=True,
            supports_download=True,
            formats=["WAV", "FLAC", "MP3", "OGG"],
            rate_limit_info="60 req/min com FREESOUND_API_KEY gratuita.",
            cost_info="Gratuito (CC0, CC BY, CC BY-NC)",
            restrictions="Focado em samples/efeitos/gravações CC; download direto de original requer OAuth2 token enquanto preview HQ MP3 usa API Key.",
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
                f"{self.BASE_URL}/search/text/",
                params={
                    "query": query.strip(),
                    "page_size": limit,
                    "fields": "id,name,username,duration,type,samplerate,bitdepth,license,previews,download",
                    "token": self.api_key.strip(),
                },
            )
            if resp.status_code != 200:
                return []
            items = resp.json().get("results") or []
            for item in items[:limit]:
                fid = str(item.get("id") or "")
                title = str(item.get("name") or "Freesound Audio")
                artist = str(item.get("username") or "Freesound Creator")
                previews = item.get("previews") or {}
                hq_preview = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
                codec = str(item.get("type") or "mp3").lower()
                is_lossless = codec in ("wav", "flac", "aiff")
                lic = str(item.get("license") or "Creative Commons")

                # Without OAuth2 bearer, preview-hq-mp3 is directly fetchable; mark explicitly as preview-hq unless OAuth download endpoint is usable
                perm = DownloadPermission(
                    status=PermissionStatus.ALLOWED_FREE if hq_preview else PermissionStatus.NOT_DOWNLOADABLE,
                    downloadable=bool(hq_preview),
                    requires_payment=False,
                    license_name=lic,
                    license_url=lic if lic.startswith("http") else None,
                    reason="Freesound HQ MP3 CC autorizado via token." if hq_preview else "Sem URL de arquivo disponível.",
                )
                fmts = (
                    [FormatOption(codec="mp3", container="mp3", bitrate_kbps=192, is_lossless=False, download_url=hq_preview)]
                    if hq_preview
                    else []
                )
                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Freesound",
                        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
                        source_item_id=fid,
                        title=title,
                        artist=artist,
                        duration_ms=int(float(item["duration"]) * 1000) if item.get("duration") else None,
                        version_type=TrackMatcher.detect_version_type(title),
                        preview_url=hq_preview,
                        download_url=hq_preview,
                        is_preview_only=False,
                        permission=perm,
                        formats=fmts,
                        declared_codec="mp3" if hq_preview else codec,
                        declared_sample_rate_hz=int(item["samplerate"]) if item.get("samplerate") else None,
                        declared_bit_depth=int(item["bitdepth"]) if item.get("bitdepth") else None,
                        origin_classification="LOSSLESS_SOURCE" if is_lossless else "LOSSY_SOURCE",
                        license_info=lic,
                        raw_metadata={"id": fid, "original_type": codec},
                    )
                )
        return results

    async def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "status": "requires_credentials", "detail": "Configure FREESOUND_API_KEY"}
        try:
            async with self._build_client() as client:
                r = await client.get(f"{self.BASE_URL}/search/text/", params={"query": "piano", "page_size": 1, "token": self.api_key.strip()})
                ok = r.status_code == 200
                return {"ok": ok, "status": "active" if ok else f"http_{r.status_code}", "detail": "Freesound API v2 acessível"}
        except Exception as e:
            return {"ok": False, "status": "unreachable", "detail": str(e)}
