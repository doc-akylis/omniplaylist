import json
import wave
from pathlib import Path

import numpy as np
import pytest
from sqlmodel import Session, create_engine, delete, select

import app.core.database as db_module
from app.core.models import UnifiedTrack
from app.engines.musical_analysis import MusicalAnalysisEngine

_test_engine = None


@pytest.fixture(scope="session", autouse=True)
def setup_database(tmp_path_factory):
    """Create an isolated temporary SQLite database for musical analysis tests."""
    global _test_engine
    db_path = tmp_path_factory.mktemp("musical_db") / "test_musical_omni.db"
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
    db_module.init_db()

    with _test_engine.connect() as conn:
        cursor = conn.exec_driver_sql("PRAGMA table_info(unifiedtrack)")
        cols = {row[1] for row in cursor.fetchall()}
        required = {
            "bpm",
            "key",
            "energy",
            "camelot_code",
            "bpm_stability",
            "danceability",
            "beatgrid_json",
            "sections_json",
            "musical_analysis_confidence",
            "musical_analyzed_at",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    yield _test_engine
    mp.undo()
    _test_engine.dispose()


@pytest.fixture(autouse=True)
def clean_tracks_table():
    """Clear UnifiedTrack rows before each test for strict isolation."""
    if _test_engine is not None:
        with Session(_test_engine) as session:
            session.exec(delete(UnifiedTrack))
            session.commit()


def _write_wav(path: Path, samples: np.ndarray, sr: int = 22050) -> None:
    """Write mono float32/float64 samples in [-1, 1] to a 16-bit PCM WAV file."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _synthesize_rhythmic_chord(
    duration_sec: float,
    bpm: float,
    freqs_hz: list[float],
    sr: int = 22050,
    with_sections: bool = False,
) -> np.ndarray:
    """Synthesize a clean rhythmic track with percussive transients at exact BPM + harmonic chord."""
    n_samples = int(duration_sec * sr)
    t = np.linspace(0.0, duration_sec, n_samples, endpoint=False)

    # Harmonic chord bed
    chord = sum(np.sin(2.0 * np.pi * f * t) for f in freqs_hz) / max(len(freqs_hz), 1)

    # Percussive beat clicks at exact BPM intervals
    beat_interval = 60.0 / bpm
    envelope = np.full(n_samples, 0.18, dtype=np.float64)
    beat_idx = 0
    beat_time = 0.0
    click_len = int(0.045 * sr)
    while beat_time < duration_sec:
        start = int(beat_time * sr)
        end = min(start + click_len, n_samples)
        accent = 0.75 if beat_idx % 4 == 0 else 0.45
        decay = np.exp(-np.linspace(0.0, 5.0, end - start))
        envelope[start:end] += accent * decay
        beat_idx += 1
        beat_time = beat_idx * beat_interval

    signal = 0.45 * chord * envelope

    # Optional energy contour to create distinct intro / chorus / outro sections
    if with_sections and duration_sec >= 12.0:
        contour = np.ones(n_samples, dtype=np.float64)
        q1 = int(0.25 * n_samples)
        q3 = int(0.75 * n_samples)
        contour[:q1] = 0.45
        contour[q1:q3] = 1.0
        contour[q3:] = 0.4
        signal *= contour

    return signal


@pytest.fixture
def am_120bpm_wav(tmp_path: Path) -> Path:
    """16-second 120 BPM track in A minor (A3, C4, E4)."""
    wav_path = tmp_path / "am_120bpm.wav"
    samples = _synthesize_rhythmic_chord(
        duration_sec=16.0,
        bpm=120.0,
        freqs_hz=[220.0, 261.63, 329.63],
        with_sections=True,
    )
    _write_wav(wav_path, samples)
    return wav_path


@pytest.fixture
def c_major_128bpm_wav(tmp_path: Path) -> Path:
    """10-second 128 BPM track in C major (C4, E4, G4)."""
    wav_path = tmp_path / "c_major_128bpm.wav"
    samples = _synthesize_rhythmic_chord(
        duration_sec=10.0,
        bpm=128.0,
        freqs_hz=[261.63, 329.63, 392.00],
    )
    _write_wav(wav_path, samples)
    return wav_path


class TestMusicalAnalysisEngine:
    """Unit tests for MusicalAnalysisEngine feature extraction."""

    @pytest.mark.asyncio
    async def test_analyze_audio_bpm_beatgrid_and_am_camelot(self, am_120bpm_wav: Path):
        engine = MusicalAnalysisEngine()
        result = await engine.analyze_audio(am_120bpm_wav)

        assert result is not None
        assert 115.0 <= result.bpm <= 125.0
        assert 0.5 <= result.bpm_stability <= 1.0
        assert result.key == "Am"
        assert result.camelot_code == "8A"
        assert result.key_confidence > 0.5
        assert 0.0 <= result.energy <= 1.0
        assert 0.0 <= result.danceability <= 1.0
        assert result.is_estimated is True

        # Beatgrid checks
        assert result.beatgrid.time_signature == "4/4"
        assert result.beatgrid.total_beats >= 16
        assert len(result.beatgrid.beats_sec) == result.beatgrid.total_beats
        assert len(result.beatgrid.downbeats_sec) >= 4

        # Structural sections checks
        assert len(result.sections) >= 1
        valid_labels = {"intro", "verse", "chorus", "breakdown", "outro"}
        for sec in result.sections:
            assert sec.label in valid_labels
            assert sec.start_sec < sec.end_sec
            assert 0.0 <= sec.relative_energy <= 1.0

    @pytest.mark.asyncio
    async def test_analyze_audio_c_major_camelot(self, c_major_128bpm_wav: Path):
        engine = MusicalAnalysisEngine()
        result = await engine.analyze_audio(c_major_128bpm_wav)

        assert result is not None
        assert result.key == "C"
        assert result.camelot_code == "8B"
        assert 122.0 <= result.bpm <= 134.0

    @pytest.mark.asyncio
    async def test_missing_or_short_file_returns_none(self, tmp_path: Path):
        engine = MusicalAnalysisEngine()
        assert await engine.analyze_audio(tmp_path / "nonexistent.wav") is None

        short_wav = tmp_path / "too_short.wav"
        _write_wav(short_wav, np.zeros(1000, dtype=np.float64), sr=22050)
        assert await engine.analyze_audio(short_wav) is None


class TestMusicalPersistence:
    """Integration tests for persisting musical analysis into isolated SQLite."""

    @pytest.mark.asyncio
    async def test_analyze_and_persist_and_skip(self, am_120bpm_wav: Path):
        engine = MusicalAnalysisEngine()

        with Session(_test_engine) as session:
            track = UnifiedTrack(
                title="Synthetic Am 120",
                artist="Test Synth",
                local_path=str(am_120bpm_wav),
            )
            session.add(track)
            session.commit()
            session.refresh(track)

            ok = await engine.analyze_and_persist(track, session, force=False)
            assert ok is True
            session.refresh(track)

            assert track.bpm is not None and 115.0 <= track.bpm <= 125.0
            assert track.camelot_code == "8A"
            assert track.key == "8A"
            assert track.bpm_stability is not None
            assert track.energy is not None
            assert track.danceability is not None
            assert track.musical_analysis_confidence is not None
            assert track.musical_analyzed_at is not None

            beatgrid = json.loads(track.beatgrid_json or "{}")
            assert beatgrid["time_signature"] == "4/4"
            assert len(beatgrid["beats_sec"]) >= 16

            sections = json.loads(track.sections_json or "[]")
            assert len(sections) >= 1

            first_ts = track.musical_analyzed_at
            # Skip when already analyzed
            assert await engine.analyze_and_persist(track, session, force=False) is False
            # Re-analyze when forced
            assert await engine.analyze_and_persist(track, session, force=True) is True
            session.refresh(track)
            assert track.musical_analyzed_at != first_ts

    @pytest.mark.asyncio
    async def test_analyze_library_batch(
        self, am_120bpm_wav: Path, c_major_128bpm_wav: Path
    ):
        engine = MusicalAnalysisEngine(max_concurrent=2)

        with Session(_test_engine) as session:
            session.add_all(
                [
                    UnifiedTrack(title="Track Am", artist="Synth", local_path=str(am_120bpm_wav)),
                    UnifiedTrack(title="Track C", artist="Synth", local_path=str(c_major_128bpm_wav)),
                ]
            )
            session.commit()

        stats = await engine.analyze_library(
            session_factory=lambda: Session(_test_engine),
            force=True,
            batch_size=2,
        )
        assert stats["analyzed"] == 2
        assert stats["errors"] == 0

        with Session(_test_engine) as session:
            tracks = session.exec(select(UnifiedTrack)).all()
            assert len(tracks) == 2
            assert all(t.musical_analyzed_at is not None for t in tracks)
            assert {t.camelot_code for t in tracks} == {"8A", "8B"}
