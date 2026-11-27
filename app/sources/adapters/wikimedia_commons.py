import re
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


class WikimediaCommonsAdapter(ProviderAdapter):
    """Wikimedia Commons Audio adapter — public MediaWiki Action API, CC/Public Domain FLAC/OGG/WAV/MP3."""

    provider_id = "wikimedia_commons"
    API_URL = "https://commons.wikimedia.org/w/api.php"
    USER_AGENT = "OmniPlaylist/2.2 (https://github.com/doc-akylis/omniplaylist)"

    def __init__(
        self,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=0.3)
        self._transport = transport

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Wikimedia Commons Audio",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            requires_auth=False,
            auth_configured=True,
            supports_search_tracks=True,
            supports_streaming=True,
            supports_download=True,
            formats=["FLAC", "OGG", "WAV", "MP3"],
            rate_limit_info="MediaWiki Action API pública com User-Agent identificador.",
            cost_info="Gratuito (Domínio Público / CC0 / CC BY-SA)",
            restrictions="Exige atribuição de autor conforme extmetadata.Artist / LicenseShortName.",
        )

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "headers": {"User-Agent": self.USER_AGENT},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _strip_html(val: str) -> str:
        return re.sub(r"<[^>]+>", "", val or "").strip()

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        clean = query.strip()
        if not clean:
            return []

        await self._rate_limiter.acquire()
        params = {
            "action": "query",
            "generator": "search",
            "gsrnamespace": 6,  # File: namespace
            "gsrsearch": f"filetype:audio {clean}",
            "gsrlimit": min(limit, 10),
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "format": "json",
        }
        results: list[NormalizedTrackResult] = []
        async with self._build_client() as client:
            resp = await client.get(self.API_URL, params=params)
            if resp.status_code != 200:
                return []
            pages = ((resp.json().get("query") or {}).get("pages")) or {}
            for page_id, page in pages.items():
                iinfo_list = page.get("imageinfo") or []
                if not iinfo_list:
                    continue
                ii = iinfo_list[0]
                file_url = ii.get("url")
                mime = str(ii.get("mime") or "")
                if not file_url or not mime.startswith(("audio/", "application/ogg")):
                    continue

                ext = file_url.rsplit(".", 1)[-1].lower() if "." in file_url else "ogg"
                is_lossless = ext in ("flac", "wav")
                extmeta = ii.get("extmetadata") or {}
                license_name = self._strip_html((extmeta.get("LicenseShortName") or {}).get("value", "CC/PD"))
                license_url = (extmeta.get("LicenseUrl") or {}).get("value")
                artist_raw = self._strip_html((extmeta.get("Artist") or {}).get("value", "")) or "Wikimedia Commons"
                raw_title = str(page.get("title") or "").replace("File:", "").rsplit(".", 1)[0]

                dur_sec = None
                try:
                    dur_val = (extmeta.get("Duration") or {}).get("value")
                    if dur_val:
                        dur_sec = float(dur_val)
                except (ValueError, TypeError):
                    pass

                fmt = FormatOption(
                    codec="pcm_s16le" if ext == "wav" else ext,
                    container=ext,
                    file_size_bytes=ii.get("size"),
                    is_lossless=is_lossless,
                    download_url=file_url,
                )
                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Wikimedia Commons Audio",
                        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
                        source_item_id=str(page_id),
                        title=raw_title,
                        artist=artist_raw[:100],
                        duration_ms=int(dur_sec * 1000) if dur_sec else None,
                        version_type=TrackMatcher.detect_version_type(raw_title),
                        preview_url=file_url,
                        download_url=file_url,
                        is_preview_only=False,
                        permission=DownloadPermission(
                            status=PermissionStatus.ALLOWED_FREE,
                            downloadable=True,
                            requires_payment=False,
                            license_name=license_name,
                            license_url=license_url,
                            reason=f"Download autorizado ({license_name}).",
                        ),
                        formats=[fmt],
                        declared_codec=fmt.codec,
                        origin_classification="LOSSLESS_SOURCE" if is_lossless else "LOSSY_SOURCE",
                        license_info=license_name,
                        raw_metadata={"mime": mime, "page_id": page_id},
                    )
                )
        return results[:limit]

    async def health_check(self) -> dict[str, Any]:
        try:
            async with self._build_client() as client:
                r = await client.get(self.API_URL, params={"action": "query", "meta": "siteinfo", "format": "json"})
                ok = r.status_code == 200
                return {"ok": ok, "status": "active" if ok else f"http_{r.status_code}", "detail": "Wikimedia Commons API acessível"}
        except Exception as e:
            return {"ok": False, "status": "unreachable", "detail": str(e)}
