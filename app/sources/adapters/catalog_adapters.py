from typing import Any, Optional
import httpx

from app.config import get_settings
from app.core.matcher import TrackMatcher
from app.providers.deezer import DeezerProvider
from app.providers.itunes import ITunesProvider
from app.providers.musicbrainz import MusicBrainzProvider
from app.providers.rate_limiter import AsyncRateLimiter
from app.sources.base import (
    DownloadPermission,
    NormalizedTrackResult,
    PermissionStatus,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderCategory,
)


class ITunesDiscoveryAdapter(ProviderAdapter):
    """iTunes Search API adapter — PREVIEW_STREAMING only (30s AAC preview, NEVER full file download)."""

    provider_id = "itunes"

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._provider = ITunesProvider(transport=transport)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="iTunes Search API",
            category=ProviderCategory.PREVIEW_STREAMING,
            requires_auth=False,
            auth_configured=True,
            supports_search_tracks=True,
            supports_search_albums=True,
            supports_streaming=True,
            supports_download=False,
            formats=["AAC 256 (Prévia 30s)"],
            rate_limit_info="~20 req/min público sem chave.",
            cost_info="Gratuito (Catálogo & Prévia 30s)",
            restrictions="Fornece apenas prévia de 30s; NÃO disponibiliza arquivo completo.",
        )

    async def search_tracks(
        self, query: str, limit: int = 10, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        matches = await self._provider.search_tracks(query, limit=limit)
        out: list[NormalizedTrackResult] = []
        for idx, m in enumerate(matches):
            if not m.title or not m.artist:
                continue
            out.append(
                NormalizedTrackResult(
                    provider_id=self.provider_id,
                    provider_name="iTunes Search API",
                    category=ProviderCategory.PREVIEW_STREAMING,
                    source_item_id=f"itunes-{idx}-{m.artist}-{m.title}",
                    title=m.title,
                    artist=m.artist,
                    album=m.album,
                    release_year=m.release_year,
                    version_type=TrackMatcher.detect_version_type(m.title, m.album),
                    genres=[m.genre] if m.genre else [],
                    cover_url=m.hd_cover_url,
                    preview_url=m.preview_url,
                    download_url=None,
                    is_preview_only=True,
                    permission=DownloadPermission(
                        status=PermissionStatus.PREVIEW_ONLY,
                        downloadable=False,
                        requires_payment=False,
                        reason="iTunes fornece apenas prévia AAC de 30s (não permite download integral).",
                    ),
                    declared_codec="aac",
                    declared_bitrate_kbps=256,
                    origin_classification="LOSSY_SOURCE",
                )
            )
        return out

    async def health_check(self) -> dict[str, Any]:
        return {"ok": True, "status": "active", "detail": "iTunes Search API pública pronta (apenas prévia 30s)"}


class DeezerDiscoveryAdapter(ProviderAdapter):
    """Deezer Public API adapter — PREVIEW_STREAMING only (30s MP3 preview + ISRC/BPM metadata)."""

    provider_id = "deezer"

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        self._provider = DeezerProvider(transport=transport)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Deezer Catalog API",
            category=ProviderCategory.PREVIEW_STREAMING,
            requires_auth=False,
            auth_configured=True,
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=True,
            supports_download=False,
            formats=["MP3 128 (Prévia 30s)"],
            rate_limit_info="API pública sem chave (~50 req/5s).",
            cost_info="Gratuito (Metadados, ISRC & Prévia 30s)",
            restrictions="Termos proíbem cache offline ou download de faixas completas via API.",
        )

    async def search_tracks(
        self, query: str, limit: int = 10, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        tracks = await self._provider.search_tracks(query, limit=limit)
        out: list[NormalizedTrackResult] = []
        for t in tracks:
            out.append(
                NormalizedTrackResult(
                    provider_id=self.provider_id,
                    provider_name="Deezer API",
                    category=ProviderCategory.PREVIEW_STREAMING,
                    source_item_id=t.deezer_id or f"{t.artist}-{t.title}",
                    title=t.title,
                    artist=t.artist,
                    album=t.album,
                    duration_ms=t.duration_ms,
                    isrc=t.isrc,
                    release_year=t.release_year,
                    version_type=TrackMatcher.detect_version_type(t.title, t.album),
                    cover_url=t.hd_cover_url or t.cover_url,
                    preview_url=t.preview_url,
                    download_url=None,
                    is_preview_only=True,
                    permission=DownloadPermission(
                        status=PermissionStatus.PREVIEW_ONLY,
                        downloadable=False,
                        requires_payment=False,
                        reason="Deezer API disponibiliza apenas prévia de 30s; termos não permitem download completo.",
                    ),
                    declared_codec="mp3",
                    declared_bitrate_kbps=128,
                    origin_classification="LOSSY_SOURCE",
                )
            )
        return out

    async def health_check(self) -> dict[str, Any]:
        return {"ok": True, "status": "active", "detail": "Deezer API pública pronta (descoberta + prévia 30s)"}


class MusicBrainzDiscoveryAdapter(ProviderAdapter):
    """MusicBrainz + Cover Art Archive adapter — DISCOVERY only (ISRC, MBID, release dates, HD cover)."""

    provider_id = "musicbrainz"

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None, rate_limiter: Optional[AsyncRateLimiter] = None):
        self._provider = MusicBrainzProvider(transport=transport, rate_limiter=rate_limiter)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="MusicBrainz + Cover Art Archive",
            category=ProviderCategory.DISCOVERY,
            requires_auth=False,
            auth_configured=True,
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=False,
            supports_download=False,
            formats=[],
            rate_limit_info="Estrito 1 req/s com User-Agent obrigatório.",
            cost_info="Gratuito (CC0 / Dados abertos)",
            restrictions="Base de metadados canônicos e capas; não hospeda nem distribui áudio.",
        )

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        q_str = f"isrc:{query.strip()}" if search_type == "isrc" else query.strip()
        matches = await self._provider.search_recordings(q_str, limit=limit)
        out: list[NormalizedTrackResult] = []
        for m in matches:
            if not m.title or not m.artist:
                continue
            out.append(
                NormalizedTrackResult(
                    provider_id=self.provider_id,
                    provider_name="MusicBrainz",
                    category=ProviderCategory.DISCOVERY,
                    source_item_id=m.recording_id or f"{m.artist}-{m.title}",
                    title=m.title,
                    artist=m.artist,
                    album=m.album,
                    isrc=m.isrc,
                    mbid=m.recording_id,
                    release_year=m.release_year,
                    version_type=TrackMatcher.detect_version_type(m.title, m.album),
                    cover_url=m.hd_cover_url,
                    download_url=None,
                    is_preview_only=False,
                    permission=DownloadPermission(
                        status=PermissionStatus.NOT_DOWNLOADABLE,
                        downloadable=False,
                        requires_payment=False,
                        reason="MusicBrainz é provedor exclusivo de metadados/ISRC (sem arquivos de áudio).",
                    ),
                )
            )
        return out

    async def health_check(self) -> dict[str, Any]:
        return {"ok": True, "status": "active", "detail": "MusicBrainz WS2 ativo (1 req/s + User-Agent)"}


class DiscogsDiscoveryAdapter(ProviderAdapter):
    """Discogs Database API adapter — DISCOVERY only (physical/digital releases, matrix, labels, versions)."""

    provider_id = "discogs"
    BASE_URL = "https://api.discogs.com"
    USER_AGENT = "OmniPlaylist/2.2 (+https://github.com/doc-akylis/omniplaylist)"

    def __init__(
        self,
        token: Optional[str] = None,
        timeout: float = 8.0,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.token = token if token is not None else get_settings().DISCOGS_TOKEN
        self.timeout = timeout
        self._rate_limiter = rate_limiter or AsyncRateLimiter(min_interval_sec=1.0)
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.token and self.token.strip())

    def capabilities(self) -> ProviderCapabilities:
        configured = self.is_configured()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Discogs Database",
            category=ProviderCategory.DISCOVERY,
            requires_auth=True,
            auth_configured=configured,
            missing_credentials=[] if configured else ["DISCOGS_TOKEN"],
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=False,
            supports_download=False,
            formats=[],
            rate_limit_info="60 req/min autenticado (DISCOGS_TOKEN) com User-Agent.",
            cost_info="Gratuito (Metadados de lançamentos e edições)",
            restrictions="Banco de catálogo/marketplace; não fornece streaming nem download de áudio.",
        )

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        if not self.is_configured() or not query.strip():
            return []
        await self._rate_limiter.acquire()
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "headers": {
                "User-Agent": self.USER_AGENT,
                "Authorization": f"Discogs token={self.token.strip()}",
            },
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport

        results: list[NormalizedTrackResult] = []
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(
                f"{self.BASE_URL}/database/search",
                params={"q": query.strip(), "type": "release", "per_page": min(limit, 8)},
            )
            if resp.status_code != 200:
                return []
            for item in (resp.json().get("results") or [])[:limit]:
                full_title = str(item.get("title") or "Unknown")
                if " - " in full_title:
                    artist, title = full_title.split(" - ", 1)
                else:
                    artist, title = "Discogs Artist", full_title
                year = None
                try:
                    year = int(item["year"]) if item.get("year") else None
                except (ValueError, TypeError):
                    pass
                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Discogs",
                        category=ProviderCategory.DISCOVERY,
                        source_item_id=str(item.get("id") or full_title),
                        title=title.strip(),
                        artist=artist.strip(),
                        release_year=year,
                        version_type=TrackMatcher.detect_version_type(title),
                        genres=[str(g) for g in (item.get("genre") or [])],
                        cover_url=item.get("cover_image") or item.get("thumb"),
                        permission=DownloadPermission(
                            status=PermissionStatus.NOT_DOWNLOADABLE,
                            downloadable=False,
                            reason="Discogs é catálogo de lançamentos; não disponibiliza arquivos de áudio.",
                        ),
                    )
                )
        return results

    async def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "status": "requires_credentials", "detail": "Configure DISCOGS_TOKEN"}
        return {"ok": True, "status": "active", "detail": "Discogs API configurada"}


class SpotifyDiscoveryAdapter(ProviderAdapter):
    """Spotify Web API adapter — DISCOVERY only (catalog/ISRC metadata; ToS strictly forbids audio download)."""

    provider_id = "spotify"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    SEARCH_URL = "https://api.spotify.com/v1/search"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        cfg = get_settings()
        self.client_id = client_id if client_id is not None else cfg.SPOTIFY_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else cfg.SPOTIFY_CLIENT_SECRET
        self.timeout = timeout
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self.client_id.strip() and self.client_secret.strip())

    def capabilities(self) -> ProviderCapabilities:
        configured = self.is_configured()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Spotify Web API",
            category=ProviderCategory.DISCOVERY,
            requires_auth=True,
            auth_configured=configured,
            missing_credentials=[] if configured else ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=False,
            supports_download=False,
            formats=[],
            rate_limit_info="OAuth Client Credentials (ToS proíbe download/ripping).",
            cost_info="Gratuito para catálogo/playlists (App Developer)",
            restrictions="Uso restrito a descoberta, ISRC e playlists; download de áudio proibido pelos Termos.",
        )

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        if not self.is_configured() or not query.strip():
            return []
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport

        q_val = f"isrc:{query.strip()}" if search_type == "isrc" else query.strip()
        async with httpx.AsyncClient(**kwargs) as client:
            tok_resp = await client.post(
                self.TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id.strip(), self.client_secret.strip()),
            )
            if tok_resp.status_code != 200:
                return []
            token = tok_resp.json().get("access_token")
            if not token:
                return []
            resp = await client.get(
                self.SEARCH_URL,
                params={"q": q_val, "type": "track", "limit": min(limit, 10)},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                return []
            items = ((resp.json().get("tracks") or {}).get("items")) or []
            out: list[NormalizedTrackResult] = []
            for item in items:
                artists = item.get("artists") or []
                artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name")) or "Unknown"
                album = item.get("album") or {}
                images = album.get("images") or []
                ext_ids = item.get("external_ids") or {}
                title = str(item.get("name") or "Unknown")
                out.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Spotify Web API",
                        category=ProviderCategory.DISCOVERY,
                        source_item_id=str(item.get("id") or title),
                        title=title,
                        artist=artist_name,
                        album=album.get("name"),
                        duration_ms=item.get("duration_ms"),
                        isrc=ext_ids.get("isrc"),
                        version_type=TrackMatcher.detect_version_type(title, album.get("name")),
                        cover_url=images[0].get("url") if images else None,
                        preview_url=item.get("preview_url"),
                        download_url=None,
                        is_preview_only=bool(item.get("preview_url")),
                        permission=DownloadPermission(
                            status=PermissionStatus.STREAMING_ONLY,
                            downloadable=False,
                            reason="Spotify Web API não permite download de faixas (ToS).",
                        ),
                    )
                )
            return out

    async def health_check(self) -> dict[str, Any]:
        if not self.is_configured():
            return {"ok": False, "status": "requires_credentials", "detail": "Configure SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET"}
        return {"ok": True, "status": "active", "detail": "Credenciais Spotify configuradas (apenas descoberta)"}
