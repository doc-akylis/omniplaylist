"""End-to-end, security, comparison, approval gating, and API integration tests for OmniPlaylist 2.2."""

from __future__ import annotations

import asyncio
from pathlib import Path
import wave

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.database import get_session
from app.core.matcher import TrackMatcher
from app.core.models import (
    AcquisitionRecord,
    AudioProcessingHistory,
    AudioProvenance,
    DownloadJob,
    MusicSearchSession,
    UnifiedTrack,
)
from app.core.security import (
    SecurityValidationError,
    safe_join_path,
    validate_audio_magic_bytes,
    validate_external_url,
)
from app.engines.acquisition_engine import AcquisitionEngine
from app.engines.audio_quality_intelligence import AudioQualityIntelligenceEngine
from app.engines.conversion_engine import ConversionEngine
from app.engines.download_studio import AuthorizedSourceProvider, DownloadStudioEngine
from app.engines.music_search_engine import AsyncRateLimiter, MusicSearchEngine
from app.engines.source_quality_comparator import SourceQualityComparator
from app.engines.tagging_engine import TaggingEngine
from app.engines.technical_analysis import TechnicalAnalysisEngine
from app.engines.upgrade_engine import UpgradeEngine
from app.sources.base import (
    DownloadPermission,
    NormalizedTrackResult,
    PermissionStatus,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderCategory,
)
from app.sources.registry import MusicSourceRegistry
from main import fastapi_app


def _make_wav_bytes(freq: float = 440.0, duration_sec: float = 1.0, sr: int = 44100) -> bytes:
    """Create a valid PCM WAV payload in memory."""
    import io

    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    sig = 0.35 * np.sin(2 * np.pi * freq * t)
    pcm = (sig * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.column_stack([pcm, pcm]).flatten().tobytes())
    return buf.getvalue()


@pytest.fixture
def isolated_db(tmp_path: Path):
    db_file = tmp_path / "v22_test.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


class _FakeAdapter(ProviderAdapter):
    def __init__(self, pid: str, name: str, cat: ProviderCategory, items=None, fail_exc=None, delay: float = 0.0):
        self.provider_id = pid
        self._name = name
        self._cat = cat
        self._items = items or []
        self._fail_exc = fail_exc
        self._delay = delay
        self.calls = 0

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_id=self.provider_id,
            name=self._name,
            category=self._cat,
            supports_download=self._cat in (ProviderCategory.AUTHORIZED_DOWNLOAD, ProviderCategory.COMMERCIAL_DELIVERY),
        )

    async def search_tracks(self, query: str, limit: int = 10, search_type: str = "track"):
        self.calls += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._fail_exc is not None:
            raise self._fail_exc
        return self._items[:limit]

    async def health_check(self):
        return {"ok": self._fail_exc is None, "status": "active" if not self._fail_exc else "error", "detail": "test"}


# ---------------------------------------------------------------------------
# 1. Security Hardening Tests (SSRF, Redirect SSRF, Path Traversal, Magic Bytes)
# ---------------------------------------------------------------------------
def test_ssrf_and_path_traversal_blocked(tmp_path: Path):
    for bad_url in [
        "http://localhost:8000/secret.flac",
        "http://127.0.0.1/track.mp3",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/audio.wav",
        "http://192.168.1.10/song.flac",
        "http://metadata.google.internal/computeMetadata/v1/",
        "file:///etc/passwd",
        "ftp://archive.org/file.flac",
    ]:
        with pytest.raises(SecurityValidationError):
            validate_external_url(bad_url, resolve_dns=False)

    assert validate_external_url("https://archive.org/download/item/song.flac", resolve_dns=False).startswith("https://")

    for bad_path in ["../../etc/passwd", "..\\..\\Windows\\system32\\cmd.exe", "."]:
        with pytest.raises(SecurityValidationError):
            safe_join_path(tmp_path, bad_path)

    ok_path = safe_join_path(tmp_path, "valid_song.flac")
    assert ok_path.parent == tmp_path.resolve()


@pytest.mark.asyncio
async def test_redirect_ssrf_and_html_magic_bytes_rejected(tmp_path: Path):
    # Case A: external URL redirects to AWS/cloud metadata endpoint -> MUST block!
    def redirect_to_ssrf(req: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data/"})

    prov = AuthorizedSourceProvider(transport=httpx.MockTransport(redirect_to_ssrf))
    job = DownloadJob(id=1, provider="test", source_url="https://public.example.org/dl.flac")
    path, err = await prov.acquire(
        job, tmp_path, lambda *a: None, asyncio.Event(), asyncio.Event()
    )
    assert path is None
    assert err is not None and "anti-SSRF" in err

    # Case B: external URL returns HTML masked as .mp3 -> magic byte validation rejects
    def html_payload(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=b"<!DOCTYPE html><html><body>Not audio</body></html>",
        )

    prov_html = AuthorizedSourceProvider(transport=httpx.MockTransport(html_payload))
    job2 = DownloadJob(id=2, provider="test", source_url="https://cdn.example.org/fake.mp3")
    path2, err2 = await prov_html.acquire(
        job2, tmp_path, lambda *a: None, asyncio.Event(), asyncio.Event()
    )
    assert path2 is None
    assert err2 is not None and "assinatura binária" in err2

    # Case C: direct magic bytes inspection helper check
    bad_exe = tmp_path / "payload.flac"
    bad_exe.write_bytes(b"MZ" + b"\x00" * 30)
    ok_exe, _ = validate_audio_magic_bytes(bad_exe)
    assert ok_exe is False


# ---------------------------------------------------------------------------
# 2. Version Grouping & Anti-Transcode Comparator Tests
# ---------------------------------------------------------------------------
def test_version_detection_and_separation_in_grouping():
    matcher = TrackMatcher()
    assert matcher.detect_version_type("Midnight City") == "original"
    assert matcher.detect_version_type("Midnight City (Live at Wembley)") == "live"
    assert matcher.detect_version_type("Midnight City (Eric Prydz Remix)") == "remix"
    assert matcher.detect_version_type("Midnight City (Extended Mix)") == "extended"
    assert matcher.detect_version_type("Midnight City (2021 Remaster)") == "remaster"

    def _mk(pid: str, title: str, isrc: str | None = None):
        return NormalizedTrackResult(
            provider_id=pid,
            provider_name=pid,
            category=ProviderCategory.DISCOVERY,
            source_item_id=f"{pid}-{title}",
            title=title,
            artist="M83",
            duration_ms=243000,
            isrc=isrc,
            version_type=matcher.detect_version_type(title),
            permission=DownloadPermission(status=PermissionStatus.NOT_DOWNLOADABLE, downloadable=False),
        )

    groups = matcher.group_recordings(
        [
            _mk("spotify", "Midnight City", "FR10S1100123"),
            _mk("deezer", "Midnight City", "FR10S1100123"),
            _mk("internet_archive", "Midnight City (Live at Wembley)"),
            _mk("soundcloud", "Midnight City (Eric Prydz Remix)"),
        ]
    )
    # Original merged into 1 group, Live and Remix kept strictly separate!
    assert len(groups) == 3
    by_ver = {g.version_type: g for g in groups}
    assert len(by_ver["original"].candidates) == 2
    assert len(by_ver["live"].candidates) == 1
    assert len(by_ver["remix"].candidates) == 1


def test_comparator_ranks_verified_flac_above_mp3_320_above_suspected_transcode():
    comp = SourceQualityComparator()
    matcher = TrackMatcher()

    cand_a_mp3_320 = NormalizedTrackResult(
        provider_id="audius",
        provider_name="Audius",
        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
        source_item_id="a1",
        title="Horizon",
        artist="Aero",
        duration_ms=200000,
        download_url="https://audius.example.org/a1.mp3",
        permission=DownloadPermission(status=PermissionStatus.ALLOWED_FREE, downloadable=True),
        declared_codec="mp3",
        declared_bitrate_kbps=320,
        origin_classification="LOSSY_SOURCE",
    )
    cand_b_fake_flac = NormalizedTrackResult(
        provider_id="archive_deriv",
        provider_name="Archive Suspect",
        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
        source_item_id="b1",
        title="Horizon",
        artist="Aero",
        duration_ms=200000,
        download_url="https://archive.example.org/b1.flac",
        permission=DownloadPermission(status=PermissionStatus.ALLOWED_FREE, downloadable=True),
        declared_codec="flac",
        origin_classification="SUSPECTED_TRANSCODE",
        suspected_transcode=True,
    )
    cand_c_real_flac = NormalizedTrackResult(
        provider_id="internet_archive",
        provider_name="Internet Archive",
        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
        source_item_id="c1",
        title="Horizon",
        artist="Aero",
        duration_ms=200000,
        download_url="https://archive.example.org/c1.flac",
        permission=DownloadPermission(status=PermissionStatus.ALLOWED_FREE, downloadable=True),
        declared_codec="flac",
        origin_classification="LOSSLESS_SOURCE",
    )
    cand_preview = NormalizedTrackResult(
        provider_id="itunes",
        provider_name="iTunes",
        category=ProviderCategory.PREVIEW_STREAMING,
        source_item_id="it1",
        title="Horizon",
        artist="Aero",
        duration_ms=200000,
        preview_url="https://itunes.example.org/prev.m4a",
        is_preview_only=True,
        permission=DownloadPermission(status=PermissionStatus.PREVIEW_ONLY, downloadable=False),
        declared_codec="aac",
        declared_bitrate_kbps=256,
    )

    grp = matcher.group_recordings([cand_a_mp3_320, cand_b_fake_flac, cand_c_real_flac, cand_preview])[0]
    res = comp.compare_group(grp)

    assert res.best_authorized is not None
    assert res.best_authorized.source_item_id == "c1"  # Verified FLAC wins

    order = [b.source_item_id for b in res.ranked_candidates]
    assert order.index("c1") < order.index("a1") < order.index("b1") < order.index("it1")
    # Never treats preview as downloadable
    it_bd = next(b for b in res.ranked_candidates if b.source_item_id == "it1")
    assert it_bd.downloadable is False


# ---------------------------------------------------------------------------
# 3. Parallel Search Isolation & Cache Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parallel_search_partial_failure_isolation_and_ttl_cache(isolated_db):
    ok_item = NormalizedTrackResult(
        provider_id="internet_archive",
        provider_name="Internet Archive",
        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
        source_item_id="ia1",
        title="Solar Wind",
        artist="Nebula",
        duration_ms=190000,
        download_url="https://archive.org/download/ia1/solar.wav",
        permission=DownloadPermission(status=PermissionStatus.ALLOWED_FREE, downloadable=True),
        declared_codec="wav",
        origin_classification="LOSSLESS_SOURCE",
    )
    ad_ok = _FakeAdapter("internet_archive", "Internet Archive", ProviderCategory.AUTHORIZED_DOWNLOAD, items=[ok_item])
    ad_slow = _FakeAdapter("deezer", "Deezer", ProviderCategory.PREVIEW_STREAMING, delay=1.2)
    ad_boom = _FakeAdapter("discogs", "Discogs", ProviderCategory.DISCOVERY, fail_exc=RuntimeError("500 upstream"))

    reg = MusicSourceRegistry(adapters=[ad_ok, ad_slow, ad_boom])
    engine = MusicSearchEngine(
        registry=reg,
        rate_limiter=AsyncRateLimiter(min_intervals_sec={}),
        per_provider_timeout_sec=0.15,
        max_retries=0,
        cache_ttl_sec=120,
    )

    with Session(isolated_db) as session:
        res1 = await engine.search("Solar Wind", session=session)
        assert res1["total_groups"] == 1
        assert res1["downloadable_groups"] == 1
        statuses = {s["provider_id"]: s["status"] for s in res1["provider_statuses"]}
        assert statuses["internet_archive"] == "ok"
        assert statuses["deezer"] == "timeout"
        assert statuses["discogs"] == "error"

        # Cache hit on second identical search -> does not call adapter again
        res2 = await engine.search("Solar Wind", session=session)
        assert res2["cached"] is True
        assert ad_ok.calls == 1

        # Persisted MusicSearchSession row
        saved_sessions = session.exec(select(MusicSearchSession)).all()
        assert len(saved_sessions) == 1
        assert saved_sessions[0].downloadable_count == 1


# ---------------------------------------------------------------------------
# 4. E2E Free Authorized Acquisition & Commercial Approval Gating Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_e2e_free_authorized_acquisition_into_library_and_quality_engine(isolated_db, tmp_path: Path):
    wav_bytes = _make_wav_bytes(freq=440.0, duration_sec=1.2)

    def dl_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "audio/wav"}, content=wav_bytes)

    free_item = NormalizedTrackResult(
        provider_id="internet_archive",
        provider_name="Internet Archive",
        category=ProviderCategory.AUTHORIZED_DOWNLOAD,
        source_item_id="ia-free-01",
        title="Orbital Echo",
        artist="Deep Cosmos",
        album="Void Tape",
        release_year=2022,
        isrc="QM1234567890",
        duration_ms=1200,
        download_url="https://archive.org/download/ia-free-01/orbital.wav",
        permission=DownloadPermission(
            status=PermissionStatus.ALLOWED_FREE,
            downloadable=True,
            license_name="CC BY 4.0",
        ),
        declared_codec="wav",
        origin_classification="LOSSLESS_SOURCE",
        license_info="CC BY 4.0",
    )

    ad_free = _FakeAdapter("internet_archive", "Internet Archive", ProviderCategory.AUTHORIZED_DOWNLOAD, items=[free_item])
    reg = MusicSourceRegistry(adapters=[ad_free])
    search_eng = MusicSearchEngine(registry=reg, rate_limiter=AsyncRateLimiter(min_intervals_sec={}))

    tech = TechnicalAnalysisEngine()
    q_eng = AudioQualityIntelligenceEngine(tech_engine=tech)
    dl_eng = DownloadStudioEngine(
        output_dir=tmp_path / "downloads",
        backup_dir=tmp_path / "backups",
        temp_dir=tmp_path / "tmp",
        provider=AuthorizedSourceProvider(transport=httpx.MockTransport(dl_handler)),
        conversion_engine=ConversionEngine(),
        tagging_engine=TaggingEngine(),
        tech_engine=tech,
        quality_engine=q_eng,
        upgrade_engine=UpgradeEngine(),
    )
    acq_eng = AcquisitionEngine(search_engine=search_eng, download_studio=dl_eng)

    def sf() -> Session:
        return Session(isolated_db)

    with sf() as session:
        out = await acq_eng.acquire_track(
            session=session,
            query="Orbital Echo",
            mode="ASK_BEFORE_PAID",
            profile="FLAC_ARCHIVE",
            session_factory=sf,
            execute_now=True,
        )
        assert out["status"] == "COMPLETED"
        job = out["job"]
        assert job["file_sha256"] and len(job["file_sha256"]) == 64

        track = session.get(UnifiedTrack, job["track_id"])
        assert track is not None
        assert track.local_path and Path(track.local_path).exists()
        assert track.is_preview is False
        assert track.is_corrupted is False
        assert track.car_audio_score is not None

        prov = session.exec(select(AudioProvenance).where(AudioProvenance.track_id == track.id)).first()
        assert prov is not None
        assert prov.file_sha256 == job["file_sha256"]
        assert prov.license_info == "CC BY 4.0"
        assert prov.verification_status == "VERIFIED"
        assert prov.declared_metadata_json and prov.extracted_metadata_json and prov.inferences_json

        hist = session.exec(select(AudioProcessingHistory).where(AudioProcessingHistory.track_id == track.id)).all()
        assert len(hist) >= 1

        dash = q_eng.get_quality_dashboard(session)
        assert dash["total_tracks"] == 1
        assert dash["complete_files"] == 1


@pytest.mark.asyncio
async def test_commercial_acquisition_blocks_until_explicit_user_approval(isolated_db, tmp_path: Path):
    wav_bytes = _make_wav_bytes(freq=523.25, duration_sec=1.0)
    http_hits = {"count": 0}

    def dl_handler(req: httpx.Request) -> httpx.Response:
        http_hits["count"] += 1
        return httpx.Response(200, headers={"Content-Type": "audio/wav"}, content=wav_bytes)

    comm_item = NormalizedTrackResult(
        provider_id="qobuz_partner",
        provider_name="Qobuz Partner B2B",
        category=ProviderCategory.COMMERCIAL_DELIVERY,
        source_item_id="qb-999",
        title="Studio Masterpiece",
        artist="Commercial Artist",
        duration_ms=1000,
        download_url="https://partner-dl.qobuz.com/tracks/qb-999.wav",
        permission=DownloadPermission(
            status=PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL,
            downloadable=True,
            requires_payment=True,
            license_name="Commercial B2B Purchase",
            estimated_cost_label="Contrato B2B ($2.49)",
        ),
        declared_codec="wav",
        origin_classification="LOSSLESS_SOURCE",
        license_info="Commercial B2B Purchase",
        requires_payment=True,
        estimated_cost_label="$2.49",
    )

    ad_comm = _FakeAdapter("qobuz_partner", "Qobuz Partner B2B", ProviderCategory.COMMERCIAL_DELIVERY, items=[comm_item])
    reg = MusicSourceRegistry(adapters=[ad_comm])
    search_eng = MusicSearchEngine(registry=reg, rate_limiter=AsyncRateLimiter(min_intervals_sec={}))

    dl_eng = DownloadStudioEngine(
        output_dir=tmp_path / "downloads",
        backup_dir=tmp_path / "backups",
        temp_dir=tmp_path / "tmp",
        provider=AuthorizedSourceProvider(transport=httpx.MockTransport(dl_handler)),
    )
    acq_eng = AcquisitionEngine(search_engine=search_eng, download_studio=dl_eng)

    def sf() -> Session:
        return Session(isolated_db)

    with sf() as session:
        # Step 1: Must enter AWAITING_APPROVAL and NEVER hit HTTP download
        res = await acq_eng.acquire_track(
            session=session,
            query="Studio Masterpiece",
            mode="ASK_BEFORE_PAID",
            session_factory=sf,
            execute_now=True,
        )
        assert res["status"] == "AWAITING_APPROVAL"
        assert res["requires_approval"] is True
        assert http_hits["count"] == 0

        # Defense in depth: trying to force run_job directly while unapproved must remain blocked
        job_id = res["job"]["id"]
        blocked_res = await dl_eng.run_job(job_id, sf)
        assert blocked_res is not None and blocked_res.status == "AWAITING_APPROVAL"
        assert http_hits["count"] == 0

        # Step 2: Explicit user approval executes download & completes
        approved_res = await acq_eng.approve_and_start_job(job_id, session, session_factory=sf, execute_now=True)
        assert approved_res["approved"] is True
        assert approved_res["job"]["status"] == "COMPLETED"
        assert approved_res["job"]["approved_by_user"] is True
        assert http_hits["count"] == 1

        rec = session.exec(select(AcquisitionRecord).where(AcquisitionRecord.download_job_id == job_id)).first()
        assert rec is not None and rec.approved_by_user is True and rec.status == "COMPLETED"


# ---------------------------------------------------------------------------
# 5. FastAPI v2.2 Endpoints Integration & Credential Hygiene Tests
# ---------------------------------------------------------------------------
def test_v22_api_routes_and_credential_hygiene(isolated_db, tmp_path: Path, monkeypatch):
    def _override_session():
        with Session(isolated_db) as s:
            yield s

    fastapi_app.dependency_overrides[get_session] = _override_session
    # Redirect BASE_DIR in v22_routes so credentials test doesn't touch real workspace .env
    import app.api.v22_routes as v22_routes

    monkeypatch.setattr(v22_routes, "BASE_DIR", tmp_path)

    try:
        with TestClient(fastapi_app) as client:
            r_src = client.get("/api/sources")
            assert r_src.status_code == 200
            data_src = r_src.json()
            assert data_src["total"] == 14

            # Save credentials to isolated .env
            r_cred = client.post(
                "/api/sources/credentials",
                json={"credentials": {"DISCOGS_TOKEN": "top-secret-demo-token"}},
            )
            assert r_cred.status_code == 200
            assert "DISCOGS_TOKEN" in r_cred.json()["updated_keys"]
            # Ensure secret is NEVER returned in plaintext by GET /api/sources or POST /api/sources/credentials
            assert "top-secret-demo-token" not in r_cred.text
            r_src_after = client.get("/api/sources")
            assert "top-secret-demo-token" not in r_src_after.text
            discogs_row = next(p for p in r_src_after.json()["providers"] if p["provider_id"] == "discogs")
            assert discogs_row["auth_configured"] is True

            # Toggle source off & on
            r_tog = client.patch("/api/sources/discogs", json={"enabled": False, "priority": 99})
            assert r_tog.status_code == 200
            assert r_tog.json()["enabled"] is False
            client.patch("/api/sources/discogs", json={"enabled": True, "priority": 50})

            # Records endpoint
            r_rec = client.get("/api/acquisition/records")
            assert r_rec.status_code == 200
            assert "records" in r_rec.json()
    finally:
        fastapi_app.dependency_overrides.clear()
        import os

        os.environ.pop("DISCOGS_TOKEN", None)
        from app.config import get_settings

        get_settings.cache_clear()
        v22_routes.source_registry.refresh_defaults()
