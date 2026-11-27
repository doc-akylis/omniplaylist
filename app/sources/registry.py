from datetime import datetime, timezone
from typing import Any, Optional
from sqlmodel import Session, select

from app.core.models import MusicProviderConfig
from app.sources.adapters.audius import AudiusAdapter
from app.sources.adapters.catalog_adapters import (
    DeezerDiscoveryAdapter,
    DiscogsDiscoveryAdapter,
    ITunesDiscoveryAdapter,
    MusicBrainzDiscoveryAdapter,
    SpotifyDiscoveryAdapter,
)
from app.sources.adapters.commercial_adapters import (
    QobuzPartnerAdapter,
    SevenDigitalMassiveMusicAdapter,
    TheRightsFoundryAdapter,
)
from app.sources.adapters.freesound import FreesoundAdapter
from app.sources.adapters.internet_archive import InternetArchiveAdapter
from app.sources.adapters.jamendo import JamendoAdapter
from app.sources.adapters.soundcloud import SoundCloudAdapter
from app.sources.adapters.wikimedia_commons import WikimediaCommonsAdapter
from app.sources.base import ProviderAdapter


class MusicSourceRegistry:
    """Central registry of all discovery, preview, authorized download, and commercial delivery adapters."""

    def __init__(self, adapters: Optional[list[ProviderAdapter]] = None):
        self._adapters: dict[str, ProviderAdapter] = {}
        default_list = adapters or self._build_default_adapters()
        for ad in default_list:
            self.register(ad)

    @staticmethod
    def _build_default_adapters() -> list[ProviderAdapter]:
        return [
            # Authorized Download (Free/Open/Creator-Authorized)
            InternetArchiveAdapter(),
            WikimediaCommonsAdapter(),
            AudiusAdapter(),
            JamendoAdapter(),
            SoundCloudAdapter(),
            FreesoundAdapter(),
            # Commercial Delivery (B2B / Paid Approval Required)
            SevenDigitalMassiveMusicAdapter(),
            TheRightsFoundryAdapter(),
            QobuzPartnerAdapter(),
            # Preview / Streaming (NEVER treated as full-file download)
            ITunesDiscoveryAdapter(),
            DeezerDiscoveryAdapter(),
            # Discovery Only (Metadata / ISRC / Versions)
            MusicBrainzDiscoveryAdapter(),
            DiscogsDiscoveryAdapter(),
            SpotifyDiscoveryAdapter(),
        ]

    def register(self, adapter: ProviderAdapter) -> None:
        self._adapters[adapter.provider_id] = adapter

    def refresh_defaults(self) -> None:
        """Reload adapters after .env credential updates."""
        for ad in self._build_default_adapters():
            self._adapters[ad.provider_id] = ad

    def get_adapter(self, provider_id: str) -> Optional[ProviderAdapter]:
        return self._adapters.get(provider_id)

    def all_adapters(self) -> list[ProviderAdapter]:
        return list(self._adapters.values())

    def _get_or_create_config(self, session: Session, provider_id: str) -> MusicProviderConfig:
        cfg = session.exec(
            select(MusicProviderConfig).where(MusicProviderConfig.provider_id == provider_id)
        ).first()
        if cfg:
            return cfg
        cfg = MusicProviderConfig(provider_id=provider_id, enabled=True, priority=100)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
        return cfg

    def list_providers(self, session: Optional[Session] = None) -> list[dict[str, Any]]:
        """Return merged capabilities + DB config state without exposing secret values."""
        cfg_map: dict[str, MusicProviderConfig] = {}
        if session is not None:
            for row in session.exec(select(MusicProviderConfig)).all():
                cfg_map[row.provider_id] = row

        out: list[dict[str, Any]] = []
        for pid, adapter in self._adapters.items():
            caps = adapter.capabilities()
            db_cfg = cfg_map.get(pid)
            out.append(
                {
                    **caps.model_dump(),
                    "enabled": db_cfg.enabled if db_cfg is not None else True,
                    "priority": db_cfg.priority if db_cfg is not None else 100,
                    "last_health_status": db_cfg.last_health_status if db_cfg else None,
                    "last_health_check_at": db_cfg.last_health_check_at if db_cfg else None,
                }
            )
        return out

    def set_provider_config(
        self,
        session: Session,
        provider_id: str,
        enabled: Optional[bool] = None,
        priority: Optional[int] = None,
    ) -> Optional[MusicProviderConfig]:
        if provider_id not in self._adapters:
            return None
        cfg = self._get_or_create_config(session, provider_id)
        if enabled is not None:
            cfg.enabled = enabled
        if priority is not None:
            cfg.priority = priority
        cfg.updated_at = datetime.now(timezone.utc)
        session.add(cfg)
        session.commit()
        session.refresh(cfg)
        return cfg

    def get_enabled_adapters(
        self,
        session: Optional[Session] = None,
        provider_ids: Optional[list[str]] = None,
    ) -> list[ProviderAdapter]:
        cfg_map: dict[str, MusicProviderConfig] = {}
        if session is not None:
            for row in session.exec(select(MusicProviderConfig)).all():
                cfg_map[row.provider_id] = row

        target_set = set(provider_ids) if provider_ids else None
        selected: list[tuple[int, ProviderAdapter]] = []
        for pid, adapter in self._adapters.items():
            if target_set and pid not in target_set:
                continue
            db_cfg = cfg_map.get(pid)
            if db_cfg is not None and not db_cfg.enabled:
                continue
            prio = db_cfg.priority if db_cfg is not None else 100
            selected.append((prio, adapter))

        selected.sort(key=lambda item: item[0])
        return [ad for _, ad in selected]

    async def run_health_check(self, session: Session, provider_id: str) -> dict[str, Any]:
        adapter = self._adapters.get(provider_id)
        if not adapter:
            return {"ok": False, "status": "unknown_provider", "detail": "Provedor não registrado"}
        res = await adapter.health_check()
        cfg = self._get_or_create_config(session, provider_id)
        cfg.last_health_status = str(res.get("status", "unknown"))
        cfg.last_health_check_at = datetime.now(timezone.utc)
        cfg.updated_at = datetime.now(timezone.utc)
        session.add(cfg)
        session.commit()
        return {"provider_id": provider_id, **res}
