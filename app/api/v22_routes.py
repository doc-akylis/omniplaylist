"""OmniPlaylist 2.2 API routes: Multi-source Discovery, Provider Config/Health, Comparison, and Acquisition."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.v21_routes import download_studio
from app.config import get_settings
from app.core.database import engine, get_session

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _session_factory() -> Session:
    return Session(engine)
from app.core.matcher import TrackMatcher
from app.core.models import AcquisitionRecord
from app.engines.acquisition_engine import AcquisitionEngine
from app.engines.music_search_engine import MusicSearchEngine
from app.engines.source_quality_comparator import SourceQualityComparator
from app.sources.registry import MusicSourceRegistry

router = APIRouter(prefix="/api", tags=["OmniPlaylist 2.2 Discovery & Acquisition"])

source_registry = MusicSourceRegistry()
source_comparator = SourceQualityComparator()
source_matcher = TrackMatcher()
music_search_engine = MusicSearchEngine(
    registry=source_registry,
    matcher=source_matcher,
    comparator=source_comparator,
)
acquisition_engine = AcquisitionEngine(
    search_engine=music_search_engine,
    comparator=source_comparator,
    download_studio=download_studio,
)

ALLOWED_ENV_CREDENTIAL_KEYS = {
    "DISCOGS_TOKEN",
    "JAMENDO_CLIENT_ID",
    "SOUNDCLOUD_CLIENT_ID",
    "FREESOUND_API_KEY",
    "TIDAL_CLIENT_ID",
    "TIDAL_CLIENT_SECRET",
    "SEVENDIGITAL_API_KEY",
    "SEVENDIGITAL_API_SECRET",
    "RIGHTS_FOUNDRY_API_KEY",
    "QOBUZ_APP_ID",
    "QOBUZ_USER_TOKEN",
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "ACOUSTID_API_KEY",
    "LASTFM_API_KEY",
    "LISTENBRAINZ_TOKEN",
}


class SourceToggleRequest(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=1, le=500)


class CredentialsSaveRequest(BaseModel):
    credentials: dict[str, str]


class DiscoverySearchRequest(BaseModel):
    query: str = ""
    search_type: str = "track"
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    isrc: Optional[str] = None
    provider_ids: Optional[list[str]] = None
    limit_per_provider: int = Field(default=10, ge=1, le=30)
    only_downloadable: bool = False
    use_cache: bool = True


class BatchDiscoveryRequest(BaseModel):
    queries: list[str]
    search_type: str = "track"
    only_downloadable: bool = False
    limit_per_provider: int = Field(default=6, ge=1, le=20)


class AutoAcquisitionRequest(BaseModel):
    query: str = ""
    artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    isrc: Optional[str] = None
    search_type: str = "track"
    provider_ids: Optional[list[str]] = None
    mode: str = "ASK_BEFORE_PAID"
    profile: str = "ORIGINAL"
    target_sample_rate_hz: Optional[int] = None
    track_id: Optional[int] = None
    preferred_provider_id: Optional[str] = None
    preferred_source_item_id: Optional[str] = None
    group_payload: Optional[dict[str, Any]] = None
    allow_downgrade_or_same: bool = False


class BatchAcquisitionRequest(BaseModel):
    items: list[dict[str, Any]]
    mode: str = "ASK_BEFORE_PAID"
    profile: str = "ORIGINAL"


def _persist_env_keys(updates: dict[str, str]) -> list[str]:
    """Update whitelisted credential keys in .env and process env without storing secrets in SQLite."""
    env_path = Path(BASE_DIR) / ".env"
    existing_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    applied: list[str] = []
    clean_updates: dict[str, str] = {}
    for k, v in updates.items():
        if k not in ALLOWED_ENV_CREDENTIAL_KEYS:
            raise HTTPException(status_code=400, detail=f"Chave de credencial não permitida: {k}")
        val = (v or "").strip()
        if "\n" in val or "\r" in val:
            raise HTTPException(status_code=400, detail=f"Valor inválido para {k}.")
        clean_updates[k] = val

    out_lines: list[str] = []
    seen_keys: set[str] = set()
    key_pattern = re.compile(r"^([A-Z0-9_]+)\s*=")
    for line in existing_lines:
        m = key_pattern.match(line.strip())
        if m and m.group(1) in clean_updates:
            k = m.group(1)
            out_lines.append(f"{k}={clean_updates[k]}")
            seen_keys.add(k)
        else:
            out_lines.append(line)

    for k, val in clean_updates.items():
        if k not in seen_keys:
            out_lines.append(f"{k}={val}")
        os.environ[k] = val
        applied.append(k)

    env_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
    get_settings.cache_clear()
    source_registry.refresh_defaults()
    return applied


@router.get("/sources")
async def list_sources(session: Session = Depends(get_session)) -> dict[str, Any]:
    """List all registered discovery, preview, authorized, and commercial adapters with safe auth flags."""
    providers = source_registry.list_providers(session)
    return {
        "total": len(providers),
        "providers": providers,
        "credential_keys": sorted(ALLOWED_ENV_CREDENTIAL_KEYS),
    }


@router.patch("/sources/{provider_id}")
async def update_source_config(
    provider_id: str,
    body: SourceToggleRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Enable/disable or adjust priority of a registered provider."""
    try:
        cfg = source_registry.set_provider_config(
            session=session,
            provider_id=provider_id,
            enabled=body.enabled,
            priority=body.priority,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {
        "provider_id": cfg.provider_id,
        "enabled": cfg.enabled,
        "priority": cfg.priority,
    }


@router.post("/sources/{provider_id}/health-check")
async def health_check_source(
    provider_id: str,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Run live health check against a single source adapter."""
    try:
        return await source_registry.run_health_check(session, provider_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/sources/credentials")
async def save_source_credentials(
    body: CredentialsSaveRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Persist optional API keys in .env only (never returned in plaintext or written to SQLite)."""
    updated_keys = _persist_env_keys(body.credentials)
    return {
        "updated_keys": updated_keys,
        "providers": source_registry.list_providers(session),
    }


@router.post("/discovery/search")
async def discovery_search(
    body: DiscoverySearchRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Search simultaneously across all enabled providers, group by version, and compare audio quality."""
    return await music_search_engine.search(
        query=body.query,
        session=session,
        search_type=body.search_type,
        artist=body.artist,
        title=body.title,
        album=body.album,
        isrc=body.isrc,
        provider_ids=body.provider_ids,
        limit_per_provider=body.limit_per_provider,
        only_downloadable=body.only_downloadable,
        use_cache=body.use_cache,
    )


@router.post("/discovery/search/batch")
async def discovery_batch_search(
    body: BatchDiscoveryRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Execute concurrent discovery across multiple track queries."""
    results = await music_search_engine.batch_search(
        queries=body.queries[:25],
        session=session,
        search_type=body.search_type,
        only_downloadable=body.only_downloadable,
        limit_per_provider=body.limit_per_provider,
    )
    return {"total": len(results), "results": results}


@router.post("/acquisition/auto")
async def acquire_track_auto(
    body: AutoAcquisitionRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Automatically select best authorized source (or hold commercial for approval) and queue DownloadJob."""
    result = await acquisition_engine.acquire_track(
        session=session,
        query=body.query,
        artist=body.artist,
        title=body.title,
        album=body.album,
        isrc=body.isrc,
        search_type=body.search_type,
        provider_ids=body.provider_ids,
        mode=body.mode,
        profile=body.profile,
        target_sample_rate_hz=body.target_sample_rate_hz,
        track_id=body.track_id,
        preferred_provider_id=body.preferred_provider_id,
        preferred_source_item_id=body.preferred_source_item_id,
        group_payload=body.group_payload,
        allow_downgrade_or_same=body.allow_downgrade_or_same,
        execute_now=False,
    )
    job = result.get("job")
    if job and job.get("status") == "QUEUED":
        download_studio.start_job_background(job["id"], _session_factory)
    return result


@router.post("/acquisition/batch")
async def acquire_tracks_batch(
    body: BatchAcquisitionRequest,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Batch discover and acquire multiple tracks; starts QUEUED free jobs in background."""
    summary = await acquisition_engine.acquire_batch(
        items=body.items[:30],
        session=session,
        mode=body.mode,
        profile=body.profile,
        execute_now=False,
    )
    for item in summary["items"]:
        job = item.get("job")
        if job and job.get("status") == "QUEUED":
            download_studio.start_job_background(job["id"], _session_factory)
    return summary


@router.post("/acquisition/jobs/{job_id}/approve")
async def approve_commercial_job(
    job_id: int,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Approve an AWAITING_APPROVAL commercial acquisition job and launch it."""
    try:
        res = await acquisition_engine.approve_and_start_job(
            job_id=job_id,
            session=session,
            execute_now=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job = res.get("job")
    if job and job.get("status") == "QUEUED":
        download_studio.start_job_background(job["id"], _session_factory)
    return res


@router.get("/acquisition/records")
async def list_acquisition_records(
    limit: int = 50,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """List multi-source acquisition decision & provenance audit records."""
    rows = session.exec(
        select(AcquisitionRecord).order_by(AcquisitionRecord.created_at.desc()).limit(limit)
    ).all()
    return {
        "total": len(rows),
        "records": [r.model_dump(mode="json") for r in rows],
    }
