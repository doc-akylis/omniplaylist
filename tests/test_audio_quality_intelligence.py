import math
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from app.api import routes as base_routes
from app.api import v21_routes
from app.core.models import AudioProcessingHistory, AudioProvenance, UnifiedTrack
from app.engines.audio_quality_intelligence import AudioQualityIntelligenceEngine
from app.engines.technical_analysis import _resolve_ffmpeg_binary


def _write_wav(
    path: Path,
    sr: int = 44100,
    duration_sec: float = 2.5,
    freqs: list[float] | None = None,
    amp: float = 0.35,
    clipping: bool = False,
    silence_only: bool = False,
) -> Path:
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    if silence_only:
        sig = np.zeros(n, dtype=np.float64)
    else:
        sig = np.zeros(n, dtype=np.float64)
        for f in (freqs or [100.0, 1000.0, 8000.0, 20200.0]):
            if f < sr / 2.0:
                sig += np.sin(2 * np.pi * f * t)
        sig = sig / max(1, len(freqs or [1]))
        if clipping:
            sig = sig * 4.5
        else:
            sig = sig * amp
    pcm = np.clip(sig * 32767.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        stereo = np.column_stack([pcm, pcm]).flatten()
        wf.writeframes(stereo.tobytes())
    return path


def _transcode_ffmpeg(src: Path, dest: Path, codec_args: list[str]) -> Path:
    ffmpeg = _resolve_ffmpeg_binary("ffmpeg")
    cmd = [ffmpeg, "-y", "-i", str(src), *codec_args, str(dest)]
    res = subprocess.run(cmd, capture_output=True)
    assert res.returncode == 0, res.stderr.decode("utf-8", errors="ignore")
    return dest


@pytest.fixture
def quality_db(tmp_path: Path):
    db_file = tmp_path / "test_quality.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.mark.asyncio
async def test_pcm_lossless_mp3_aac_and_sample_rates(tmp_path: Path, quality_db):
    qi = AudioQualityIntelligenceEngine()

    wav_44 = _write_wav(tmp_path / "full_44k.wav", sr=44100, freqs=[55.0, 440.0, 5000.0, 14000.0, 20200.0])
    wav_48 = _write_wav(tmp_path / "full_48k.wav", sr=48000, freqs=[100.0, 1200.0, 9000.0, 21500.0])
    mp3_128 = _transcode_ffmpeg(wav_44, tmp_path / "lossy_128.mp3", ["-codec:a", "libmp3lame", "-b:a", "128k"])
    aac_192 = _transcode_ffmpeg(wav_44, tmp_path / "lossy_192.m4a", ["-codec:a", "aac", "-b:a", "192k"])

    with Session(quality_db) as s:
        t_wav = UnifiedTrack(title="Lossless 44k", artist="Tester", local_path=str(wav_44))
        t_wav48 = UnifiedTrack(title="Lossless 48k", artist="Tester", local_path=str(wav_48))
        t_mp3 = UnifiedTrack(title="MP3 128", artist="Tester", local_path=str(mp3_128))
        t_aac = UnifiedTrack(title="AAC 192", artist="Tester", local_path=str(aac_192))
        s.add_all([t_wav, t_wav48, t_mp3, t_aac])
        s.commit()
        for t in (t_wav, t_wav48, t_mp3, t_aac):
            s.refresh(t)

        r_wav = await qi.analyze_track_quality(t_wav, s, force=True)
        r_48 = await qi.analyze_track_quality(t_wav48, s, force=True)
        r_mp3 = await qi.analyze_track_quality(t_mp3, s, force=True)
        r_aac = await qi.analyze_track_quality(t_aac, s, force=True)

        assert r_wav["quality_intelligence"]["source_classification"] == "LOSSLESS_SOURCE"
        assert r_wav["quality_intelligence"]["upscale_status"] == "VERIFIED_LOSSLESS_SOURCE"
        assert r_48["file"]["sample_rate_hz"] == 48000
        assert r_mp3["quality_intelligence"]["source_classification"] == "LOSSY_SOURCE"
        assert r_mp3["quality_intelligence"]["upscale_status"] == "VERIFIED_LOSSY_SOURCE"
        assert r_aac["quality_intelligence"]["source_classification"] == "LOSSY_SOURCE"
        assert r_wav["quality_intelligence"]["car_audio_score"] > r_mp3["quality_intelligence"]["car_audio_score"]


@pytest.mark.asyncio
async def test_fake_upscale_detection_and_acoustic_false_positive_guard(tmp_path: Path, quality_db):
    qi = AudioQualityIntelligenceEngine()

    # 1. Brickwall fake upscale: MP3 128k transcoded back to FLAC
    rich_wav = _write_wav(tmp_path / "rich.wav", sr=44100, freqs=[80.0, 600.0, 3500.0, 8000.0, 12500.0, 20000.0])
    mp3_low = _transcode_ffmpeg(rich_wav, tmp_path / "src_128.mp3", ["-codec:a", "libmp3lame", "-b:a", "128k"])
    fake_flac = _transcode_ffmpeg(mp3_low, tmp_path / "fake_upscale.flac", ["-codec:a", "flac"])

    # 2. Legitimate low-treble acoustic/bass-light WAV (only 440Hz & 880Hz, no brickwall transcode cliff)
    acoustic_wav = _write_wav(tmp_path / "acoustic_no_bass.wav", sr=44100, freqs=[440.0, 880.0, 1760.0])

    with Session(quality_db) as s:
        t_fake = UnifiedTrack(title="Fake FLAC", artist="Upscaler", local_path=str(fake_flac))
        t_acoustic = UnifiedTrack(title="Acoustic Cello", artist="Classic", local_path=str(acoustic_wav))
        s.add_all([t_fake, t_acoustic])
        s.commit()
        s.refresh(t_fake)
        s.refresh(t_acoustic)

        rep_fake = await qi.analyze_track_quality(t_fake, s, force=True)
        rep_ac = await qi.analyze_track_quality(t_acoustic, s, force=True)

        assert rep_fake["quality_intelligence"]["upscale_status"] in ("LIKELY_UPSCALE", "SUSPECTED_UPSCALE")
        assert rep_fake["quality_intelligence"]["is_fake_upscale"] is True
        assert rep_fake["quality_intelligence"]["spectral_cutoff_hz"] < 18500.0

        # Acoustic track without high-freq harmonics must NOT be marked as fake upscale, nor penalized for low sub-bass!
        assert rep_ac["quality_intelligence"]["is_fake_upscale"] is False
        assert rep_ac["quality_intelligence"]["upscale_status"] == "UNKNOWN"
        penalties = rep_ac["quality_intelligence"]["details"]["car_audio"]["penalties"]
        assert not any("sub" in p["criterion"].lower() or "bass" in p["criterion"].lower() for p in penalties)
        assert rep_ac["quality_intelligence"]["car_audio_score"] >= 85.0


@pytest.mark.asyncio
async def test_clipping_silence_corrupted_and_provenance_survival(tmp_path: Path, quality_db):
    qi = AudioQualityIntelligenceEngine()

    clip_wav = _write_wav(tmp_path / "clip.wav", freqs=[100.0, 1000.0], clipping=True)
    silent_wav = _write_wav(tmp_path / "silent.wav", silence_only=True)
    corrupted = tmp_path / "broken.mp3"
    corrupted.write_bytes(b"NOT_AN_AUDIO_FILE_123456")

    with Session(quality_db) as s:
        t_clip = UnifiedTrack(title="Clipped", artist="A", local_path=str(clip_wav))
        t_sil = UnifiedTrack(title="Silent", artist="A", local_path=str(silent_wav))
        t_bad = UnifiedTrack(title="Corrupt", artist="A", local_path=str(corrupted))
        s.add_all([t_clip, t_sil, t_bad])
        s.commit()
        for t in (t_clip, t_sil, t_bad):
            s.refresh(t)

        r_clip = await qi.analyze_track_quality(t_clip, s, force=True)
        r_sil = await qi.analyze_track_quality(t_sil, s, force=True)
        r_bad = await qi.analyze_track_quality(t_bad, s, force=True)

        assert (r_clip["technical"]["clipping_count"] or 0) > 0
        assert r_clip["quality_intelligence"]["car_audio_score"] < 90.0
        assert r_sil["technical"]["silence_start_ms"] is not None
        assert r_bad["file"]["is_corrupted"] is True
        assert r_bad["quality_intelligence"]["car_audio_status"] == "POOR"
        assert r_bad["quality_intelligence"]["car_audio_ready"] is False

        # Provenance survival: LOSSY_SOURCE recorded originally remains LOSSY_SOURCE even after converting container to FLAC
        t_conv = UnifiedTrack(title="Converted", artist="B", local_path=str(_transcode_ffmpeg(clip_wav, tmp_path / "conv.flac", ["-codec:a", "flac"])))
        s.add(t_conv)
        s.commit()
        s.refresh(t_conv)
        qi.record_provenance(s, t_conv, acquisition_source="download_studio", origin_classification="LOSSY_SOURCE")
        r_conv = await qi.analyze_track_quality(t_conv, s, force=True)
        assert r_conv["quality_intelligence"]["source_classification"] == "LOSSY_SOURCE"
        assert r_conv["quality_intelligence"]["upscale_status"] == "LIKELY_UPSCALE"

        # Verify Quality Dashboard API
        app = FastAPI()
        app.include_router(base_routes.router)
        app.include_router(v21_routes.router)
        app.dependency_overrides[base_routes.get_session] = lambda: Session(quality_db)
        client = TestClient(app)
        dash = client.get("/api/quality/dashboard")
        assert dash.status_code == 200
        d = dash.json()
        assert d["total_tracks"] == 4
        assert d["corrupted"] >= 1
