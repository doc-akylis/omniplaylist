import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, delete

import app.core.database as db_module
from app.core.models import UnifiedTrack
from main import fastapi_app

_test_engine = None


@pytest.fixture(scope="session", autouse=True)
def setup_isolated_db(tmp_path_factory):
    """Use an isolated temporary SQLite DB for DJ Mode API tests."""
    global _test_engine
    db_path = tmp_path_factory.mktemp("dj_mode_db") / "test_dj_mode.db"
    _test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    mp = pytest.MonkeyPatch()
    mp.setattr(db_module, "engine", _test_engine)

    def _test_get_session():
        with Session(_test_engine) as session:
            yield session

    mp.setattr(db_module, "get_session", _test_get_session)
    fastapi_app.dependency_overrides[db_module.get_session] = _test_get_session
    db_module.init_db()

    yield _test_engine
    fastapi_app.dependency_overrides.clear()
    mp.undo()
    _test_engine.dispose()


@pytest.fixture(autouse=True)
def clean_tracks():
    """Clear tracks between tests."""
    if _test_engine is not None:
        with Session(_test_engine) as session:
            session.exec(delete(UnifiedTrack))
            session.commit()


def _compute_six_band_levels_py(freq_bytes: list[int], sample_rate: int, fft_size: int) -> dict[str, float]:
    """Reference implementation matching computeSixBandLevels() in dj_realtime_engine.js."""
    bands = [
        ("sub_bass", 20, 60),
        ("bass", 60, 250),
        ("low_mid", 250, 500),
        ("mid", 500, 2000),
        ("high_mid", 2000, 6000),
        ("high", 6000, 20000),
    ]
    bin_hz = sample_rate / fft_size
    max_bin = len(freq_bytes) - 1
    out: dict[str, float] = {}
    for key, min_hz, max_hz in bands:
        start_bin = max(1, int(min_hz // bin_hz))
        end_bin = min(max_bin, int(-(-max_hz // bin_hz)))  # ceil
        vals = freq_bytes[start_bin : end_bin + 1]
        out[key] = (sum(vals) / (len(vals) * 255.0)) if vals else 0.0
    return out


class TestStaticWebAudioAssets:
    """Verify AudioWorklet and Web Audio JS files exist, are served, and contain valid constructs."""

    def test_js_files_exist_and_contain_required_logic(self):
        project_root = Path(__file__).resolve().parents[1]
        worklet_path = project_root / "app" / "ui" / "static" / "js" / "dj_audio_worklet.js"
        engine_path = project_root / "app" / "ui" / "static" / "js" / "dj_realtime_engine.js"

        assert worklet_path.exists()
        assert engine_path.exists()

        worklet_src = worklet_path.read_text(encoding="utf-8")
        assert "extends AudioWorkletProcessor" in worklet_src
        assert 'registerProcessor("dj-audio-meter-processor"' in worklet_src
        assert "0.999" in worklet_src

        engine_src = engine_path.read_text(encoding="utf-8")
        assert "createMediaElementSource" in engine_src
        assert "fftSize = 4096" in engine_src
        assert "__omniAudioGraph" in engine_src
        for freq_range in ["20–60 Hz", "60–250 Hz", "250–500 Hz", "500 Hz–2 kHz", "2–6 kHz", "6–20 kHz"]:
            assert freq_range in engine_src

    def test_static_js_served_over_http(self):
        client = TestClient(fastapi_app)
        r1 = client.get("/static/js/dj_audio_worklet.js")
        r2 = client.get("/static/js/dj_realtime_engine.js")
        assert r1.status_code == 200
        assert "DjAudioMeterProcessor" in r1.text
        assert r2.status_code == 200
        assert "OmniDjRealtime" in r2.text

    def test_six_band_frequency_math(self):
        """Verify 6-band FFT bin aggregation isolates energy in target bands."""
        sample_rate = 44100
        fft_size = 4096
        bin_hz = sample_rate / fft_size  # ~10.7666 Hz/bin
        freq_bytes = [0] * (fft_size // 2)

        # Inject energy at ~43 Hz (sub_bass) and ~1000 Hz (mid)
        freq_bytes[int(round(43.0 / bin_hz))] = 255
        freq_bytes[int(round(1000.0 / bin_hz))] = 255

        levels = _compute_six_band_levels_py(freq_bytes, sample_rate, fft_size)
        assert levels["sub_bass"] > 0.0
        assert levels["mid"] > 0.0
        assert levels["bass"] == 0.0
        assert levels["high"] == 0.0


class TestDjProfileEndpointAndUI:
    """Verify consolidated /dj-profile API and DJ Mode 2.0 UI module."""

    def test_dj_profile_endpoint_returns_consolidated_telemetry(self):
        with Session(_test_engine) as session:
            track = UnifiedTrack(
                title="Midnight Groove",
                artist="DJ Test",
                album="Club Sessions",
                duration_ms=240000,
                codec="flac",
                bitrate_kbps=980,
                sample_rate_hz=44100,
                bit_depth=16,
                channels=2,
                integrated_lufs=-9.5,
                momentary_lufs=-8.2,
                short_term_lufs=-9.1,
                loudness_range_lu=5.4,
                true_peak_dbfs=-0.8,
                dynamic_range_db=8.5,
                crest_factor_db=9.2,
                replay_gain=-4.5,
                clipping_count=0,
                analyzed_at=datetime.now(timezone.utc),
                bpm=124.0,
                bpm_stability=0.96,
                key="8A",
                camelot_code="8A",
                energy=0.82,
                danceability=0.88,
                beatgrid_json=json.dumps({"beats_sec": [0.5, 1.0], "downbeats_sec": [0.5], "time_signature": "4/4", "total_beats": 2}),
                sections_json=json.dumps([{"label": "intro", "start_sec": 0.0, "end_sec": 30.0, "relative_energy": 0.5, "confidence": 0.65}]),
                musical_analysis_confidence=0.91,
                musical_analyzed_at=datetime.now(timezone.utc),
            )
            session.add(track)
            session.commit()
            session.refresh(track)
            track_id = track.id

        client = TestClient(fastapi_app)
        resp = client.get(f"/api/tracks/{track_id}/dj-profile")
        assert resp.status_code == 200
        data = resp.json()

        assert data["track"]["title"] == "Midnight Groove"
        assert data["technical"]["source"] == "ffmpeg_ffprobe"
        assert data["technical"]["is_measured"] is True
        assert data["technical"]["integrated_lufs"] == -9.5
        assert data["musical"]["source"] == "librosa_krumhansl_schmuckler"
        assert data["musical"]["is_estimated"] is True
        assert data["musical"]["camelot_code"] == "8A"
        assert data["musical"]["confidence"] == 0.91

        missing_resp = client.get("/api/tracks/999999/dj-profile")
        assert missing_resp.status_code == 404

    def test_dj_mode_page_and_player_imports(self):
        import app.ui.pages.dj_mode_page as dj_page
        import app.ui.player as player_mod

        assert hasattr(dj_page, "render_dj_mode_page")
        assert len(dj_page.SIX_BAND_META) == 6
        player_src = Path(player_mod.__file__).read_text(encoding="utf-8")
        assert 'crossorigin="anonymous"' in player_src
