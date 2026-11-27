from typing import Any, Optional
from urllib.parse import quote
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


class InternetArchiveAdapter(ProviderAdapter):
    """Internet Archive (archive.org) audio adapter — public, keyless, FLAC/WAV/MP3/OGG."""

    provider_id = "internet_archive"
    SEARCH_URL = "https://archive.org/advancedsearch.php"
    META_URL = "https://archive.org/metadata"
    DOWNLOAD_BASE = "https://archive.org/download"

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
            name="Internet Archive Audio",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            requires_auth=False,
            auth_configured=True,
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=True,
            supports_download=True,
            formats=["FLAC", "WAV", "MP3 (VBR)", "OGG"],
            rate_limit_info="Público sem chave; rate limit suave recomendado (0.3s).",
            cost_info="Gratuito (Acervo público / Creative Commons / Live Music Archive)",
            restrictions="Respeitar licença individual do item (licenseurl); derivativos MP3 marcados como is_derivative=True.",
        )

    def _build_client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    @staticmethod
    def _parse_audio_formats(identifier: str, files: list[dict[str, Any]]) -> list[FormatOption]:
        formats: list[FormatOption] = []
        for f in files:
            name = str(f.get("name") or "")
            fmt = str(f.get("format") or "").lower()
            source = str(f.get("source") or "original").lower()
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in ("flac", "wav", "mp3", "ogg", "m4a"):
                continue
            is_lossless = ext in ("flac", "wav") or "flac" in fmt
            is_deriv = source == "derivative"
            size_bytes = None
            try:
                size_bytes = int(f["size"]) if f.get("size") else None
            except (ValueError, TypeError):
                pass
            bitrate = None
            try:
                bitrate = int(float(f["bitrate"])) if f.get("bitrate") else None
            except (ValueError, TypeError):
                pass
            dl_url = f"{InternetArchiveAdapter.DOWNLOAD_BASE}/{quote(identifier)}/{quote(name)}"
            formats.append(
                FormatOption(
                    codec="pcm_s16le" if ext == "wav" else ext,
                    container=ext,
                    bitrate_kbps=bitrate,
                    file_size_bytes=size_bytes,
                    is_lossless=is_lossless and not is_deriv,
                    is_derivative=is_deriv,
                    download_url=dl_url,
                )
            )
        # Prefer original lossless first, then original lossy, then derivative
        formats.sort(key=lambda o: (o.is_lossless, not o.is_derivative, o.bitrate_kbps or 0), reverse=True)
        return formats

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        clean = query.strip()
        if not clean:
            return []

        await self._rate_limiter.acquire()
        q_expr = f"mediatype:audio AND ({clean})"
        if search_type == "live":
            q_expr = f"mediatype:audio AND collection:etree AND ({clean})"
        elif search_type == "album":
            q_expr = f"mediatype:audio AND title:({clean})"

        results: list[NormalizedTrackResult] = []
        async with self._build_client() as client:
            resp = await client.get(
                self.SEARCH_URL,
                params={
                    "q": q_expr,
                    "fl[]": ["identifier", "title", "creator", "date", "licenseurl"],
                    "rows": min(limit, 8),
                    "output": "json",
                },
            )
            if resp.status_code != 200:
                return []
            docs = ((resp.json().get("response") or {}).get("docs")) or []
            for doc in docs[: min(limit, 5)]:
                ident = doc.get("identifier")
                if not ident:
                    continue
                detail = await self._fetch_item(client, ident, doc)
                if detail:
                    results.append(detail)
        return results

    async def _fetch_item(
        self, client: httpx.AsyncClient, identifier: str, summary_doc: Optional[dict[str, Any]] = None
    ) -> Optional[NormalizedTrackResult]:
        await self._rate_limiter.acquire()
        resp = await client.get(f"{self.META_URL}/{identifier}")
        if resp.status_code != 200:
            return None
        payload = resp.json()
        meta = {**(summary_doc or {}), **(payload.get("metadata") or {})}
        files = payload.get("files") or []
        formats = self._parse_audio_formats(identifier, files)
        if not formats:
            return None

        best = formats[0]
        raw_title = meta.get("title") or identifier
        if isinstance(raw_title, list):
            raw_title = raw_title[0]
        raw_creator = meta.get("creator") or meta.get("artist") or "Internet Archive Artist"
        if isinstance(raw_creator, list):
            raw_creator = raw_creator[0]
        license_url = meta.get("licenseurl")
        if isinstance(license_url, list):
            license_url = license_url[0]

        year = None
        date_val = str(meta.get("date") or meta.get("year") or "")
        if len(date_val) >= 4 and date_val[:4].isdigit():
            year = int(date_val[:4])

        # Compute duration from first audio file metadata if present
        dur_ms = None
        for f in files:
            if f.get("length"):
                try:
                    dur_ms = int(float(f["length"]) * 1000)
                    break
                except (ValueError, TypeError):
                    pass

        origin_cls = "LOSSLESS_SOURCE" if (best.is_lossless and not best.is_derivative) else "LOSSY_SOURCE"
        return NormalizedTrackResult(
            provider_id=self.provider_id,
            provider_name="Internet Archive Audio",
            category=ProviderCategory.AUTHORIZED_DOWNLOAD,
            source_item_id=identifier,
            title=str(raw_title),
            artist=str(raw_creator),
            album=str(meta.get("album")) if meta.get("album") else None,
            duration_ms=dur_ms,
            release_year=year,
            version_type=TrackMatcher.detect_version_type(str(raw_title)),
            cover_url=f"https://archive.org/services/img/{identifier}",
            preview_url=best.download_url,
            download_url=best.download_url,
            is_preview_only=False,
            permission=DownloadPermission(
                status=PermissionStatus.ALLOWED_FREE,
                downloadable=True,
                requires_payment=False,
                license_name="Internet Archive Public/CC",
                license_url=str(license_url) if license_url else None,
                reason="Download autorizado disponível via Internet Archive.",
            ),
            formats=formats,
            declared_codec=best.codec,
            declared_bitrate_kbps=best.bitrate_kbps,
            origin_classification=origin_cls,
            suspected_transcode=False,
            license_info=str(license_url) if license_url else "Internet Archive Public Audio",
            raw_metadata={"identifier": identifier, "file_count": len(formats)},
        )

    async def get_track_details(self, item_id: str) -> Optional[NormalizedTrackResult]:
        async with self._build_client() as client:
            return await self._fetch_item(client, item_id)

    async def health_check(self) -> dict[str, Any]:
        try:
            async with self._build_client() as client:
                r = await client.get(self.SEARCH_URL, params={"q": "mediatype:audio", "rows": 1, "output": "json"})
                ok = r.status_code == 200
                return {"ok": ok, "status": "active" if ok else f"http_{r.status_code}", "detail": "Archive.org API acessível"}
        except Exception as e:
            return {"ok": False, "status": "unreachable", "detail": str(e)}
