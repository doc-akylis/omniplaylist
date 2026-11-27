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


class JamendoAdapter(ProviderAdapter):
    """Jamendo API v3.0 adapter — strictly checks audiodownload_allowed === true per track."""

    provider_id = "jamendo"
    BASE_URL = "https://api.jamendo.com/v3.0"

    def __init__(
        self,
        client_id: Optional[str] = None,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.client_id = client_id if client_id is not None else get_settings().JAMENDO_CLIENT_ID
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.25)
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_id.strip())

    def capabilities(self) -> ProviderCapabilities:
        configured = self.is_configured()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Jamendo Music (v3.0)",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            requires_auth=True,
            auth_configured=configured,
            missing_credentials=[] if configured else ["JAMENDO_CLIENT_ID"],
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=True,
            supports_download=True,
            formats=["MP3 (VBR/320)", "OGG", "FLAC (quando habilitado)"],
            rate_limit_info="Requer JAMENDO_CLIENT_ID gratuito (portal dev Jamendo).",
            cost_info="Gratuito para uso pessoal/CC; licenciamento comercial via Jamendo Licensing",
            restrictions="Presença de licença CC NÃO garante download; exige audiodownload_allowed=true e URL audiodownload válida.",
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
        params: dict[str, Any] = {
            "client_id": self.client_id.strip(),
            "format": "json",
            "limit": limit,
            "include": "musicinfo+licenses",
        }
        if search_type == "artist":
            params["artist_name"] = query.strip()
        elif search_type == "album":
            params["album_name"] = query.strip()
        else:
            params["namesearch"] = query.strip()

        results: list[NormalizedTrackResult] = []
        async with self._build_client() as client:
            resp = await client.get(f"{self.BASE_URL}/tracks/", params=params)
            if resp.status_code != 200:
                return []
            rows = resp.json().get("results") or []
            for item in rows[:limit]:
                tid = str(item.get("id") or "")
                title = str(item.get("name") or "Unknown")
                artist = str(item.get("artist_name") or "Unknown Artist")
                allowed = item.get("audiodownload_allowed") is True
                dl_url = str(item.get("audiodownload") or "").strip() if allowed else ""
                stream_url = item.get("audio") or None
                lic_url = item.get("license_ccurl")
                dur_sec = item.get("duration")

                if allowed and dl_url:
                    perm = DownloadPermission(
                        status=PermissionStatus.ALLOWED_FREE,
                        downloadable=True,
                        requires_payment=False,
                        license_name="Creative Commons (Jamendo)",
                        license_url=lic_url,
                        reason="audiodownload_allowed=true confirmado pela API Jamendo.",
                    )
                    fmts = [FormatOption(codec="mp3", container="mp3", is_lossless=False, download_url=dl_url)]
                else:
                    perm = DownloadPermission(
                        status=PermissionStatus.NOT_DOWNLOADABLE,
                        downloadable=False,
                        requires_payment=False,
                        license_name="Creative Commons (Stream Only)" if lic_url else None,
                        license_url=lic_url,
                        reason="audiodownload_allowed=false na API Jamendo; download bloqueado pelo artista.",
                    )
                    fmts = []

                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Jamendo Music",
                        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
                        source_item_id=tid,
                        title=title,
                        artist=artist,
                        album=item.get("album_name"),
                        duration_ms=int(float(dur_sec) * 1000) if dur_sec else None,
                        version_type=TrackMatcher.detect_version_type(title),
                        cover_url=item.get("album_image") or item.get("image"),
                        preview_url=stream_url,
                        download_url=dl_url or None,
                        is_preview_only=False,
                        permission=perm,
                        formats=fmts,
                        declared_codec="mp3" if (allowed and dl_url) else None,
                        origin_classification="LOSSY_SOURCE" if (allowed and dl_url) else "UNKNOWN_SOURCE",
                        license_info=lic_url or "Jamendo",
                        raw_metadata={"id": tid, "audiodownload_allowed": allowed},
                    )
                )
        return results

    async def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "status": "requires_credentials", "detail": "Configure JAMENDO_CLIENT_ID"}
        try:
            async with self._build_client() as client:
                r = await client.get(f"{self.BASE_URL}/tracks/", params={"client_id": self.client_id.strip(), "format": "json", "limit": 1})
                ok = r.status_code == 200
                return {"ok": ok, "status": "active" if ok else f"http_{r.status_code}", "detail": "Jamendo API v3.0 conectada"}
        except Exception as e:
            return {"ok": False, "status": "unreachable", "detail": str(e)}
