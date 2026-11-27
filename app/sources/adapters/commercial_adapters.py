from typing import Any, Optional
import httpx

from app.config import get_settings
from app.core.matcher import TrackMatcher
from app.sources.base import (
    DownloadPermission,
    FormatOption,
    NormalizedTrackResult,
    PermissionStatus,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderCategory,
)


class _BaseCommercialDeliveryAdapter(ProviderAdapter):
    """Base for B2B commercial delivery adapters: never fakes availability when credentials are missing."""

    category = ProviderCategory.COMMERCIAL_DELIVERY
    default_formats: list[str] = ["FLAC", "WAV", "MP3 320"]

    def _missing_creds(self) -> list[str]:
        return []

    def is_configured(self) -> bool:
        return len(self._missing_creds()) == 0

    async def health_check(self) -> dict[str, Any]:
        missing = self._missing_creds()
        if missing:
            return {
                "ok": False,
                "status": "requires_credentials",
                "detail": f"Contrato B2B / credenciais pendentes: {', '.join(missing)}",
            }
        return {"ok": True, "status": "configured", "detail": "Credenciais comerciais configuradas (requer aprovação explícita antes de cobrança)."}


class SevenDigitalMassiveMusicAdapter(_BaseCommercialDeliveryAdapter):
    """7digital / MassiveMusic B2B commercial delivery adapter."""

    provider_id = "sevendigital"
    BASE_URL = "https://api.7digital.com/1.2"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        cfg = get_settings()
        self.api_key = api_key if api_key is not None else cfg.SEVENDIGITAL_API_KEY
        self.api_secret = api_secret if api_secret is not None else cfg.SEVENDIGITAL_API_SECRET
        self.timeout = timeout
        self._transport = transport

    def _missing_creds(self) -> list[str]:
        missing = []
        if not self.api_key.strip():
            missing.append("SEVENDIGITAL_API_KEY")
        if not self.api_secret.strip():
            missing.append("SEVENDIGITAL_API_SECRET")
        return missing

    def capabilities(self) -> ProviderCapabilities:
        missing = self._missing_creds()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="7digital / MassiveMusic B2B",
            category=ProviderCategory.COMMERCIAL_DELIVERY,
            requires_auth=True,
            auth_configured=len(missing) == 0,
            missing_credentials=missing,
            supports_search_tracks=True,
            supports_search_artists=True,
            supports_search_albums=True,
            supports_streaming=True,
            supports_download=True,
            formats=["FLAC 16/24-bit", "MP3 320", "AAC"],
            rate_limit_info="Definido por contrato comercial Songtradr/MassiveMusic.",
            cost_info="Pago / Contrato B2B (licenciamento + entrega por faixa)",
            restrictions="Exige acordo comercial ativo; aquisições pagas exigem aprovação explícita do usuário.",
        )

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        if not self.is_configured() or not query.strip():
            return []
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport

        results: list[NormalizedTrackResult] = []
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(
                f"{self.BASE_URL}/track/search",
                params={"q": query.strip(), "oauth_consumer_key": self.api_key.strip(), "pagesize": limit},
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                return []
            items = (((resp.json().get("searchResults") or {}).get("searchResult")) or [])
            for row in items[:limit]:
                trk = row.get("track") or row
                tid = str(trk.get("id") or "")
                title = str(trk.get("title") or "Unknown")
                artist = str(((trk.get("artist") or {}).get("name")) or "Unknown Artist")
                price_info = (trk.get("price") or {}).get("formattedPrice") or "Sob contrato/compra"
                dl_url = trk.get("downloadUrl")
                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="7digital / MassiveMusic",
                        category=ProviderCategory.COMMERCIAL_DELIVERY,
                        source_item_id=tid,
                        title=title,
                        artist=artist,
                        album=(trk.get("release") or {}).get("title"),
                        duration_ms=int(trk["duration"]) * 1000 if trk.get("duration") else None,
                        isrc=trk.get("isrc"),
                        version_type=TrackMatcher.detect_version_type(title),
                        cover_url=(trk.get("release") or {}).get("image"),
                        download_url=dl_url,
                        permission=DownloadPermission(
                            status=PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL,
                            downloadable=bool(dl_url),
                            requires_payment=True,
                            requires_credentials=True,
                            estimated_cost_label=str(price_info),
                            license_name="7digital Commercial Delivery",
                            reason="Entrega comercial licenciada; exige aprovação explícita antes da compra.",
                        ),
                        formats=[
                            FormatOption(codec="flac", container="flac", is_lossless=True, download_url=dl_url)
                        ]
                        if dl_url
                        else [],
                        declared_codec="flac",
                        origin_classification="LOSSLESS_SOURCE",
                        requires_payment=True,
                        estimated_cost_label=str(price_info),
                    )
                )
        return results


class TheRightsFoundryAdapter(_BaseCommercialDeliveryAdapter):
    """The Rights Foundry B2B pre-cleared music licensing & master delivery adapter."""

    provider_id = "rights_foundry"
    BASE_URL = "https://api.therightsfoundry.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = api_key if api_key is not None else get_settings().RIGHTS_FOUNDRY_API_KEY
        self.timeout = timeout
        self._transport = transport

    def _missing_creds(self) -> list[str]:
        return [] if self.api_key.strip() else ["RIGHTS_FOUNDRY_API_KEY"]

    def capabilities(self) -> ProviderCapabilities:
        missing = self._missing_creds()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="The Rights Foundry",
            category=ProviderCategory.COMMERCIAL_DELIVERY,
            requires_auth=True,
            auth_configured=len(missing) == 0,
            missing_credentials=missing,
            supports_search_tracks=True,
            supports_streaming=True,
            supports_download=True,
            formats=["WAV 24-bit", "FLAC", "MP3 320"],
            rate_limit_info="Gerenciado por plano de API B2B.",
            cost_info="Pago / Licença Cleared-at-Source B2B",
            restrictions="Exige RIGHTS_FOUNDRY_API_KEY contratada e aprovação explícita de aquisição.",
        )

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        if not self.is_configured() or not query.strip():
            return []
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "headers": {"Authorization": f"Bearer {self.api_key.strip()}"},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport

        results: list[NormalizedTrackResult] = []
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(f"{self.BASE_URL}/tracks/search", params={"q": query.strip(), "limit": limit})
            if resp.status_code != 200:
                return []
            for item in (resp.json().get("tracks") or [])[:limit]:
                tid = str(item.get("id") or "")
                dl_url = item.get("master_download_url") or item.get("download_url")
                price_label = item.get("license_fee") or "Licença B2B"
                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="The Rights Foundry",
                        category=ProviderCategory.COMMERCIAL_DELIVERY,
                        source_item_id=tid,
                        title=str(item.get("title") or "Unknown"),
                        artist=str(item.get("artist") or "Unknown"),
                        isrc=item.get("isrc"),
                        duration_ms=item.get("duration_ms"),
                        version_type=TrackMatcher.detect_version_type(str(item.get("title") or "")),
                        download_url=dl_url,
                        permission=DownloadPermission(
                            status=PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL,
                            downloadable=bool(dl_url),
                            requires_payment=True,
                            requires_credentials=True,
                            estimated_cost_label=str(price_label),
                            license_name="The Rights Foundry Master/Sync License",
                            reason="Entrega comercial B2B; requer aprovação explícita do usuário.",
                        ),
                        formats=[FormatOption(codec="wav", container="wav", bit_depth=24, sample_rate_hz=48000, is_lossless=True, download_url=dl_url)]
                        if dl_url
                        else [],
                        declared_codec="wav",
                        declared_bit_depth=24,
                        declared_sample_rate_hz=48000,
                        origin_classification="LOSSLESS_SOURCE",
                        requires_payment=True,
                        estimated_cost_label=str(price_label),
                    )
                )
        return results


class QobuzPartnerAdapter(_BaseCommercialDeliveryAdapter):
    """Qobuz Hi-Res partner delivery adapter (requires official Qobuz App ID + authorized token)."""

    provider_id = "qobuz"
    BASE_URL = "https://www.qobuz.com/api.json/0.2"

    def __init__(
        self,
        app_id: Optional[str] = None,
        user_token: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        cfg = get_settings()
        self.app_id = app_id if app_id is not None else cfg.QOBUZ_APP_ID
        self.user_token = user_token if user_token is not None else cfg.QOBUZ_USER_TOKEN
        self.timeout = timeout
        self._transport = transport

    def _missing_creds(self) -> list[str]:
        missing = []
        if not self.app_id.strip():
            missing.append("QOBUZ_APP_ID")
        if not self.user_token.strip():
            missing.append("QOBUZ_USER_TOKEN")
        return missing

    def capabilities(self) -> ProviderCapabilities:
        missing = self._missing_creds()
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name="Qobuz Hi-Res Partner",
            category=ProviderCategory.COMMERCIAL_DELIVERY,
            requires_auth=True,
            auth_configured=len(missing) == 0,
            missing_credentials=missing,
            supports_search_tracks=True,
            supports_search_albums=True,
            supports_streaming=True,
            supports_download=True,
            formats=["FLAC 24-bit/192kHz", "FLAC 16-bit/44.1kHz"],
            rate_limit_info="Parceria oficial Qobuz obrigatória.",
            cost_info="Pago / Compra Hi-Res ou Parceria Comercial",
            restrictions="Qobuz não possui API pública de download gratuito; exige parceria oficial e compra autorizada.",
        )

    async def search_tracks(
        self, query: str, limit: int = 8, search_type: str = "track"
    ) -> list[NormalizedTrackResult]:
        if not self.is_configured() or not query.strip():
            return []
        kwargs: dict[str, Any] = {
            "timeout": self.timeout,
            "headers": {"X-App-Id": self.app_id.strip(), "X-User-Auth-Token": self.user_token.strip()},
        }
        if self._transport is not None:
            kwargs["transport"] = self._transport

        results: list[NormalizedTrackResult] = []
        async with httpx.AsyncClient(**kwargs) as client:
            resp = await client.get(f"{self.BASE_URL}/track/search", params={"query": query.strip(), "limit": limit})
            if resp.status_code != 200:
                return []
            items = ((resp.json().get("tracks") or {}).get("items")) or []
            for item in items[:limit]:
                tid = str(item.get("id") or "")
                title = str(item.get("title") or "Unknown")
                artist = str(((item.get("performer") or {}).get("name")) or "Unknown")
                dl_url = item.get("authorized_download_url")
                bit_depth = item.get("maximum_bit_depth") or 16
                sr_khz = item.get("maximum_sampling_rate") or 44.1
                sr_hz = int(float(sr_khz) * 1000) if float(sr_khz) < 1000 else int(sr_khz)
                results.append(
                    NormalizedTrackResult(
                        provider_id=self.provider_id,
                        provider_name="Qobuz Hi-Res",
                        category=ProviderCategory.COMMERCIAL_DELIVERY,
                        source_item_id=tid,
                        title=title,
                        artist=artist,
                        album=(item.get("album") or {}).get("title"),
                        duration_ms=int(item["duration"]) * 1000 if item.get("duration") else None,
                        isrc=item.get("isrc"),
                        version_type=TrackMatcher.detect_version_type(title),
                        download_url=dl_url,
                        permission=DownloadPermission(
                            status=PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL,
                            downloadable=bool(dl_url),
                            requires_payment=True,
                            requires_credentials=True,
                            estimated_cost_label="Compra Hi-Res Qobuz",
                            license_name="Qobuz Commercial Purchase",
                            reason="Entrega comercial Hi-Res; requer aprovação explícita do usuário.",
                        ),
                        formats=[
                            FormatOption(
                                codec="flac",
                                container="flac",
                                bit_depth=int(bit_depth),
                                sample_rate_hz=sr_hz,
                                is_lossless=True,
                                download_url=dl_url,
                            )
                        ]
                        if dl_url
                        else [],
                        declared_codec="flac",
                        declared_bit_depth=int(bit_depth),
                        declared_sample_rate_hz=sr_hz,
                        origin_classification="LOSSLESS_SOURCE",
                        requires_payment=True,
                        estimated_cost_label="Compra Hi-Res Qobuz",
                    )
                )
        return results
