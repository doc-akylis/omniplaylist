import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.api import routes as base_routes
from app.api import v21_routes
from app.core.models import Playlist, UnifiedTrack
from app.engines.dj_intelligence import DJIntelligenceEngine
from app.engines.download_studio import AuthorizedSourceProvider, DownloadStudioEngine
from app.engines.upgrade_engine import CandidateSource


def _make_wav(path: Path, freqs: list[float], duration_sec: float = 1.5) -> Path:
    sr = 44100
    n = int(sr * duration_sec)
    t = np.linspace(0, duration_sec, n, endpoint=False)
    sig = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs) * 0.35
    pcm = (sig * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.column_stack([pcm, pcm]).flatten().tobytes())
    return path


def test_transition_analysis_eq_assist_and_ab_comparison():
    dj = DJIntelligenceEngine()
    t_a = UnifiedTrack(
        id=1,
        title="Deck A Track",
        artist="DJ A",
        bpm=126.0,
        camelot_code="8A",
        energy=0.82,
        integrated_lufs=-8.0,
        true_peak_dbfs=-0.2,
        sub_bass_energy=0.22,
        mid_bass_energy=0.25,
        high_freq_energy=0.28,
        codec="mp3",
        bitrate_kbps=192,
        source_classification="LOSSY_SOURCE",
        car_audio_score=74.0,
        duration_ms=240000,
    )
    t_b = UnifiedTrack(
        id=2,
        title="Deck B Track",
        artist="DJ B",
        bpm=128.0,
        camelot_code="9A",
        energy=0.86,
        integrated_lufs=-11.2,
        true_peak_dbfs=-0.3,
        sub_bass_energy=0.24,
        mid_bass_energy=0.26,
        high_freq_energy=0.30,
        codec="flac",
        bitrate_kbps=950,
        source_classification="LOSSLESS_SOURCE",
        car_audio_score=95.0,
        duration_ms=240000,
    )

    trans = dj.analyze_transition(t_a, t_b)
    assert trans["is_harmonic_compatible"] is True
    assert trans["delta_bpm"] == 2.0
    assert trans["delta_lufs"] == -3.2
    assert trans["bass_overlap_score"] is not None and trans["bass_overlap_score"] > 0.7
    assert trans["combined_clipping_is_estimate"] is True
    assert trans["estimated_combined_peak_dbfs"] is not None
    assert len(trans["eq_suggestions"]) >= 2  # Low bass overlap + loudness balance + highs

    ab = dj.compare_track_versions(t_a, t_b)
    assert ab["recommended_track_id"] == 2
    assert len(ab["differences"]) >= 4


@pytest.mark.asyncio
async def test_end_to_end_v21_workflow(tmp_path: Path):
    """Validate integrated workflow: create/analyze -> upgrade/download -> playlist -> sequence -> transition -> dashboard."""
    db_file = tmp_path / "e2e_v21.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)

    wav_a = _make_wav(tmp_path / "track_a.wav", [60.0, 440.0, 8000.0, 20000.0])
    wav_b = _make_wav(tmp_path / "track_b.wav", [75.0, 520.0, 9000.0, 20200.0])

    app = FastAPI()
    app.include_router(base_routes.router)
    app.include_router(v21_routes.router)
    app.dependency_overrides[base_routes.get_session] = lambda: Session(eng)
    client = TestClient(app)

    try:
        with Session(eng) as s:
            t1 = UnifiedTrack(title="E2E One", artist="Artist 1", bpm=124.0, camelot_code="8A", energy=0.7, local_path=str(wav_a))
            t2 = UnifiedTrack(title="E2E Two", artist="Artist 2", bpm=125.0, camelot_code="9A", energy=0.8, is_preview=True, local_path=str(wav_b))
            s.add_all([t1, t2])
            s.commit()
            s.refresh(t1)
            s.refresh(t2)
            id1, id2 = t1.id, t2.id

        # 1. Analyze quality on both tracks
        q1 = client.post(f"/api/tracks/{id1}/analyze-quality?force=true")
        q2 = client.post(f"/api/tracks/{id2}/analyze-quality?force=true")
        assert q1.status_code == 200 and q2.status_code == 200
        assert q1.json()["quality_intelligence"]["source_classification"] == "LOSSLESS_SOURCE"

        # 2. Download Studio local conversion upgrade (FLAC_ARCHIVE) on track 2
        studio = DownloadStudioEngine(
            output_dir=tmp_path / "dl_out",
            backup_dir=tmp_path / "dl_bkp",
            provider=AuthorizedSourceProvider(),
        )
        with Session(eng) as s:
            cand = CandidateSource(
                provider="local_conversion",
                local_source_path=str(wav_b),
                title="E2E Two",
                artist="Artist 2",
                codec="pcm_s16le",
                origin_classification="LOSSLESS_SOURCE",
            )
            job = studio.enqueue_job(s, id2, cand, profile="FLAC_ARCHIVE")
            assert job.status == "QUEUED"
            job_id = job.id
        done = await studio.run_job(job_id, lambda: Session(eng))
        assert done is not None and done.status == "COMPLETED"

        # 3. Create playlist, reorder, preview & apply smart sequence
        pl_res = client.post("/api/playlists", json={"name": "E2E Set", "track_ids": [id2, id1]})
        assert pl_res.status_code == 200
        pl_id = pl_res.json()["id"]

        seq_prev = client.post(f"/api/playlists/{pl_id}/sequence/preview", json={"mode": "harmonic_flow"})
        assert seq_prev.status_code == 200
        ordered_ids = [t["id"] for t in seq_prev.json()["ordered_tracks"]]
        assert len(ordered_ids) == 2

        seq_apply = client.post(f"/api/playlists/{pl_id}/sequence/apply", json={"ordered_track_ids": ordered_ids})
        assert seq_apply.status_code == 200 and seq_apply.json()["can_restore"] is True

        # 4. Transition analysis + A/B compare + Quality Dashboard
        tr_res = client.post("/api/dj/transition-analysis", json={"track_a_id": id1, "track_b_id": id2})
        assert tr_res.status_code == 200
        assert tr_res.json()["is_harmonic_compatible"] is True

        cmp_res = client.get(f"/api/tracks/compare?track_a_id={id1}&track_b_id={id2}")
        assert cmp_res.status_code == 200

        dash_res = client.get("/api/quality/dashboard")
        assert dash_res.status_code == 200
        assert dash_res.json()["total_tracks"] == 2
        assert dash_res.json()["complete_files"] == 2
    finally:
        eng.dispose()
