import asyncio
import wave
from pathlib import Path

import httpx
import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.models import AudioProcessingHistory, AudioProvenance, DownloadJob, UnifiedTrack
from app.engines.audio_quality_intelligence import AudioQualityIntelligenceEngine
from app.engines.conversion_engine import ConversionEngine
from app.engines.download_studio import AuthorizedSourceProvider, DownloadStudioEngine
from app.engines.tagging_engine import TaggingEngine
from app.engines.technical_analysis import TechnicalAnalysisEngine
from app.engines.upgrade_engine import CandidateSource, UpgradeEngine


def _make_wav(path: Path, freq: float = 440.0, duration_sec: float = 1.5, sr: int = 44100) -> Path:
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    sig = 0.35 * np.sin(2 * np.pi * freq * t)
    pcm = (sig * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.column_stack([pcm, pcm]).flatten().tobytes())
    return path


@pytest.fixture
def dl_db(tmp_path: Path):
    db_file = tmp_path / "test_dl.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


def test_upgrade_engine_decisions(tmp_path: Path):
    ue = UpgradeEngine()
    existing_preview = UnifiedTrack(
        id=1,
        title="Midnight City",
        artist="M83",
        isrc="FR10S1100123",
        codec="mp3",
        bitrate_kbps=128,
        duration_ms=240000,
        is_preview=True,
        local_path=str(_make_wav(tmp_path / "prev.wav")),
    )

    # 1. Lossy AAC 128 preview candidate for MP3 320 -> NOT justified
    cand_aac = CandidateSource(
        title="Midnight City",
        artist="M83",
        isrc="FR10S1100123",
        codec="aac",
        bitrate_kbps=128,
        is_preview=True,
        origin_classification="LOSSY_SOURCE",
    )
    ev1 = ue.evaluate_upgrade(existing_preview, cand_aac, requested_profile="MP3_320")
    assert ev1.decision == "NO_QUALITY_IMPROVEMENT"
    assert ev1.is_justified is False

    # 2. Lossy 128 non-preview candidate vs existing non-preview MP3 256 -> NO_QUALITY_IMPROVEMENT + warning
    existing_256 = UnifiedTrack(
        id=2,
        title="Midnight City",
        artist="M83",
        isrc="FR10S1100123",
        codec="mp3",
        bitrate_kbps=256,
        duration_ms=240000,
        is_preview=False,
        local_path=existing_preview.local_path,
    )
    cand_128 = CandidateSource(
        title="Midnight City",
        artist="M83",
        isrc="FR10S1100123",
        codec="aac",
        bitrate_kbps=128,
        is_preview=False,
        origin_classification="LOSSY_SOURCE",
    )
    ev2 = ue.evaluate_upgrade(existing_256, cand_128, requested_profile="MP3_320")
    assert ev2.decision == "NO_QUALITY_IMPROVEMENT"
    assert any("320 kbps" in w or "não recupera" in w for w in ev2.warnings)

    # 3. Full verified FLAC candidate -> UPGRADE_AVAILABLE
    cand_flac = CandidateSource(
        title="Midnight City",
        artist="M83",
        isrc="FR10S1100123",
        codec="flac",
        sample_rate_hz=44100,
        bit_depth=16,
        is_preview=False,
        origin_classification="LOSSLESS_SOURCE",
    )
    ev3 = ue.evaluate_upgrade(existing_preview, cand_flac, requested_profile="FLAC_ARCHIVE")
    assert ev3.decision == "UPGRADE_AVAILABLE"
    assert ev3.is_justified is True

    # 4. Different version by duration mismatch
    cand_live = CandidateSource(
        title="Midnight City",
        artist="M83",
        codec="flac",
        duration_ms=340000,
        origin_classification="LOSSLESS_SOURCE",
    )
    ev4 = ue.evaluate_upgrade(existing_256, cand_live, requested_profile="FLAC_ARCHIVE")
    assert ev4.decision == "DIFFERENT_VERSION"

    # 5. Unverified source
    cand_unv = CandidateSource(title="Midnight City", artist="M83", verified_source=False, origin_classification="UNKNOWN_SOURCE")
    ev5 = ue.evaluate_upgrade(existing_256, cand_unv)
    assert ev5.decision == "SOURCE_UNVERIFIED"


@pytest.mark.asyncio
async def test_download_studio_profiles_tagging_atomic_replace_and_retry(tmp_path: Path, dl_db):
    src_wav = _make_wav(tmp_path / "source_master.wav", freq=660.0)
    old_file = _make_wav(tmp_path / "old_preview.wav", freq=220.0)
    wav_bytes = src_wav.read_bytes()

    attempts_seen = 0

    def flaky_http_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts_seen
        attempts_seen += 1
        if attempts_seen == 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            content=wav_bytes,
            headers={"Content-Length": str(len(wav_bytes))},
        )

    out_dir = tmp_path / "downloads"
    bkp_dir = tmp_path / "backups"
    studio = DownloadStudioEngine(
        output_dir=out_dir,
        backup_dir=bkp_dir,
        provider=AuthorizedSourceProvider(transport=httpx.MockTransport(flaky_http_handler)),
        tech_engine=TechnicalAnalysisEngine(),
    )

    with Session(dl_db) as s:
        trk = UnifiedTrack(
            title="Test Master",
            artist="Studio Artist",
            album="Studio LP",
            isrc="USST2600001",
            bpm=124.0,
            camelot_code="8A",
            is_preview=True,
            local_path=str(old_file),
        )
        s.add(trk)
        s.commit()
        s.refresh(trk)

        cand = CandidateSource(
            provider="authorized_url",
            source_url="https://example.com/master.wav",
            title="Test Master",
            artist="Studio Artist",
            isrc="USST2600001",
            codec="pcm_s16le",
            sample_rate_hz=44100,
            bit_depth=16,
            origin_classification="LOSSLESS_SOURCE",
        )
        job = studio.enqueue_job(s, trk.id, cand, profile="FLAC_ARCHIVE", max_attempts=3)
        assert job.status == "QUEUED"
        job_id = job.id

    completed = await studio.run_job(job_id, lambda: Session(dl_db))
    assert completed is not None
    assert completed.status == "COMPLETED"
    assert completed.attempts == 2  # Retried once after HTTP 503
    assert completed.dest_path is not None and Path(completed.dest_path).exists()
    assert completed.backup_path is not None and Path(completed.backup_path).exists()
    assert list(studio.temp_dir.glob("*")) == []  # Temp files cleaned up

    with Session(dl_db) as s:
        updated_trk = s.get(UnifiedTrack, 1)
        assert updated_trk is not None
        assert updated_trk.codec == "flac"
        assert updated_trk.is_preview is False
        prov = s.exec(select(AudioProvenance).where(AudioProvenance.track_id == 1)).first()
        assert prov is not None
        hist = s.exec(select(AudioProcessingHistory).where(AudioProcessingHistory.track_id == 1)).all()
        assert len(hist) >= 1

    # Also test MP3_320, WAV_24, AAC_256 conversion profiles + Mutagen tagging directly
    conv = ConversionEngine()
    tagger = TaggingEngine()
    for prof_id in ("MP3_320", "WAV_24", "AAC_256"):
        res = await conv.convert_file(src_wav, tmp_path / f"out_{prof_id}", profile_id=prof_id, output_stem="sample")
        assert res.success is True and res.output_path is not None and res.output_path.exists()
        ok, _ = tagger.apply_tags(res.output_path, UnifiedTrack(title="Tag", artist="Art", bpm=120.0, camelot_code="8A"))
        assert ok is True


@pytest.mark.asyncio
async def test_download_rollback_on_failure_and_cancellation(tmp_path: Path, dl_db):
    old_valid = _make_wav(tmp_path / "keep_me.wav", freq=330.0)
    studio = DownloadStudioEngine(
        output_dir=tmp_path / "downloads",
        backup_dir=tmp_path / "backups",
        provider=AuthorizedSourceProvider(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"CORRUPTED_BYTES"))
        ),
    )

    with Session(dl_db) as s:
        trk = UnifiedTrack(title="Safe Track", artist="Safe", local_path=str(old_valid), is_preview=True)
        s.add(trk)
        s.commit()
        s.refresh(trk)

        cand = CandidateSource(
            source_url="https://example.com/bad.wav",
            title="Safe Track",
            artist="Safe",
            codec="wav",
            origin_classification="LOSSLESS_SOURCE",
        )
        job = studio.enqueue_job(s, trk.id, cand, profile="FLAC_ARCHIVE", max_attempts=1)
        job_id = job.id

    failed = await studio.run_job(job_id, lambda: Session(dl_db))
    assert failed is not None
    assert failed.status == "FAILED"
    assert old_valid.exists()  # Original file preserved!

    # Test cancellation persistence
    with Session(dl_db) as s:
        j2 = studio.enqueue_job(
            s,
            1,
            CandidateSource(source_url="https://example.com/a.wav", title="Safe Track", artist="Safe", codec="wav", origin_classification="LOSSLESS_SOURCE"),
            profile="ORIGINAL",
        )
        cancelled = studio.cancel_job(j2.id, s)
        assert cancelled is not None and cancelled.status == "CANCELLED"
