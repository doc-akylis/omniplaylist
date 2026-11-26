import pytest
import asyncio
import subprocess
from pathlib import Path
from sqlmodel import Session, SQLModel, create_engine, delete, select

import app.core.database as db_module
import app.engines.technical_analysis as tech_module
from app.core.models import UnifiedTrack
from app.engines.technical_analysis import TechnicalAnalysisEngine, _resolve_ffmpeg_binary

_test_engine = None


@pytest.fixture(scope="session", autouse=True)
def setup_database(tmp_path_factory):
    """Create an isolated temporary SQLite database and monkeypatch app.core.database."""
    global _test_engine
    db_path = tmp_path_factory.mktemp("db") / "test_omni.db"
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
    mp.setattr(tech_module, "get_session", _test_get_session)

    db_module.init_db()
    with _test_engine.connect() as conn:
        cursor = conn.exec_driver_sql("PRAGMA table_info(unifiedtrack)")
        cols = {row[1] for row in cursor.fetchall()}
        required = {
            "true_peak_dbfs", "dynamic_range_db", "crest_factor_db",
            "silence_start_ms", "silence_end_ms", "loudness_range_lu",
            "momentary_lufs", "short_term_lufs", "clipping_count",
            "analysis_version", "analyzed_at"
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    yield _test_engine
    mp.undo()
    _test_engine.dispose()


@pytest.fixture(autouse=True)
def clean_tracks_table():
    """Keep each test isolated by clearing UnifiedTrack rows before each test."""
    if _test_engine is not None:
        with Session(_test_engine) as session:
            session.exec(delete(UnifiedTrack))
            session.commit()


def _get_ffmpeg_path() -> str:
    """Get resolved ffmpeg path for test fixtures."""
    return _resolve_ffmpeg_binary("ffmpeg")


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    """Generate a synthetic WAV file using FFmpeg for testing."""
    ffmpeg = _get_ffmpeg_path()
    wav_path = tmp_path / "test_tone.wav"
    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=5:sample_rate=44100",
        "-af", "volume=-20dB",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(wav_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"FFmpeg not available: {result.stderr}")
    assert wav_path.exists()
    assert wav_path.stat().st_size > 1000
    return wav_path


@pytest.fixture
def sample_mp3(tmp_path: Path) -> Path:
    """Generate a synthetic MP3 file using FFmpeg for testing."""
    ffmpeg = _get_ffmpeg_path()
    mp3_path = tmp_path / "test_tone.mp3"
    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=3:sample_rate=44100",
        "-af", "volume=-15dB",
        "-ac", "2",
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(mp3_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"FFmpeg not available: {result.stderr}")
    assert mp3_path.exists()
    return mp3_path


@pytest.fixture
def silent_wav(tmp_path: Path) -> Path:
    """Generate a WAV with leading/trailing silence for silence detection test."""
    ffmpeg = _get_ffmpeg_path()
    wav_path = tmp_path / "silent_test.wav"
    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=44100",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo:d=1",
        "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1,volume=-10dB",
        "-c:a", "pcm_s16le",
        str(wav_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"FFmpeg not available: {result.stderr}")
    assert wav_path.exists()
    return wav_path


@pytest.fixture
def clipping_wav(tmp_path: Path) -> Path:
    """Generate a WAV with deliberate clipping for clipping detection test."""
    ffmpeg = _get_ffmpeg_path()
    wav_path = tmp_path / "clipping_test.wav"
    cmd = [
        ffmpeg, "-y", "-f", "lavfi",
        "-i", "sine=frequency=440:duration=2:sample_rate=44100",
        "-af", "volume=20dB",  # This will cause clipping
        "-c:a", "pcm_s16le",
        str(wav_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        pytest.skip(f"FFmpeg not available: {result.stderr}")
    assert wav_path.exists()
    return wav_path


class TestTechnicalAnalysisEngine:
    """Tests for TechnicalAnalysisEngine core functionality."""

    @pytest.mark.asyncio
    async def test_probe_file_wav(self, sample_wav: Path):
        """Test ffprobe extracts correct technical info from WAV."""
        analyzer = TechnicalAnalysisEngine()
        info = await analyzer.probe_file(sample_wav)

        assert info is not None, "ffprobe should return info for valid WAV"
        assert info.codec_name == "pcm_s16le"
        assert info.sample_rate_hz == 44100
        assert info.channels == 2
        assert info.bit_depth == 16
        assert 4.9 < info.duration_sec < 5.1
        assert info.bitrate_kbps > 1000
        assert info.size_bytes > 0

    @pytest.mark.asyncio
    async def test_probe_file_mp3(self, sample_mp3: Path):
        """Test ffprobe extracts correct technical info from MP3."""
        analyzer = TechnicalAnalysisEngine()
        info = await analyzer.probe_file(sample_mp3)

        assert info is not None, "ffprobe should return info for valid MP3"
        assert info.codec_name == "mp3"
        assert info.sample_rate_hz == 44100
        assert info.channels == 2
        assert 2.9 < info.duration_sec < 3.1
        assert 125 <= info.bitrate_kbps <= 135

    @pytest.mark.asyncio
    async def test_probe_file_missing(self, tmp_path: Path):
        """Test ffprobe handles missing file gracefully."""
        analyzer = TechnicalAnalysisEngine()
        info = await analyzer.probe_file(tmp_path / "nonexistent.wav")
        assert info is None

    @pytest.mark.asyncio
    async def test_analyze_audio_wav(self, sample_wav: Path):
        """Test single-pass analysis extracts all metrics from WAV."""
        analyzer = TechnicalAnalysisEngine(target_lufs=-14.0)
        analysis = await analyzer.analyze_audio(sample_wav)

        assert analysis is not None, "Analysis should succeed for valid WAV"

        # EBU R128 metrics
        assert -50 < analysis.integrated_lufs < 0
        assert analysis.true_peak_dbfs <= 0
        assert analysis.momentary_lufs is not None
        assert analysis.short_term_lufs is not None
        assert analysis.loudness_range_lu >= 0

        # Dynamics metrics
        assert analysis.rms_level_db is not None
        assert analysis.peak_level_db is not None
        assert analysis.dynamic_range_db >= 0
        assert analysis.crest_factor_db >= 0
        assert isinstance(analysis.clipping_detected, bool)
        assert analysis.clipping_count >= 0

        # Silence metrics
        assert analysis.silence_start_ms >= 0
        assert analysis.silence_end_ms >= 0
        assert analysis.silence_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_analyze_audio_silence_detection(self, silent_wav: Path):
        """Test silence detection finds leading/trailing silence."""
        analyzer = TechnicalAnalysisEngine(silence_threshold_db=-50.0)
        analysis = await analyzer.analyze_audio(silent_wav)

        assert analysis is not None
        # Leading silence starts at 0ms, trailing silence ends around 4000ms
        assert analysis.silence_start_ms <= 100
        assert analysis.silence_end_ms >= 3900
        assert analysis.silence_duration_ms >= 1800

    @pytest.mark.asyncio
    async def test_analyze_audio_clipping_detection(self, clipping_wav: Path):
        """Test clipping detection works on overdriven audio."""
        analyzer = TechnicalAnalysisEngine()
        analysis = await analyzer.analyze_audio(clipping_wav)

        assert analysis is not None
        assert analysis.clipping_detected is True
        assert analysis.clipping_count > 0

    @pytest.mark.asyncio
    async def test_analyze_audio_missing_file(self, tmp_path: Path):
        """Test analysis handles missing file gracefully."""
        analyzer = TechnicalAnalysisEngine()
        analysis = await analyzer.analyze_audio(tmp_path / "nonexistent.wav")
        assert analysis is None


class TestAnalyzeAndPersist:
    """Tests for analyze_and_persist integration with database."""

    @pytest.mark.asyncio
    async def test_analyze_and_persist_new_track(self, sample_wav: Path):
        """Test full pipeline: probe + analyze + persist to DB."""
        analyzer = TechnicalAnalysisEngine(target_lufs=-14.0)

        with Session(_test_engine) as session:
            track = UnifiedTrack(
                title="Test Tone",
                artist="Test Artist",
                local_path=str(sample_wav),
            )
            session.add(track)
            session.commit()
            session.refresh(track)

            result = await analyzer.analyze_and_persist(track, session, force=True)
            assert result is True

            session.refresh(track)
            assert track.codec == "pcm_s16le"
            assert track.sample_rate_hz == 44100
            assert track.channels == 2
            assert track.bit_depth == 16
            assert track.duration_ms is not None
            assert 4900 < track.duration_ms < 5100

            # Loudness fields
            assert track.integrated_lufs is not None
            assert -50 < track.integrated_lufs < 0
            assert track.true_peak_dbfs is not None
            assert track.true_peak_dbfs <= 0
            assert track.momentary_lufs is not None
            assert track.short_term_lufs is not None
            assert track.loudness_range_lu >= 0

            # Dynamics fields
            assert track.dynamic_range_db is not None
            assert track.dynamic_range_db >= 0
            assert track.crest_factor_db is not None
            assert track.crest_factor_db >= 0
            assert track.clipping_count is not None
            assert track.clipping_count >= 0

            # Silence fields
            assert track.silence_start_ms is not None
            assert track.silence_end_ms is not None

            # ReplayGain
            assert track.replay_gain is not None
            assert track.replay_gain == round(-14.0 - track.integrated_lufs, 2)

            # Meta
            assert track.analysis_version == 1
            assert track.analyzed_at is not None

    @pytest.mark.asyncio
    async def test_analyze_and_persist_skip_if_exists(self, sample_wav: Path):
        """Test that analyze_and_persist skips already-analyzed tracks unless forced."""
        analyzer = TechnicalAnalysisEngine()

        with Session(_test_engine) as session:
            track = UnifiedTrack(
                title="Test Skip",
                artist="Test Artist",
                local_path=str(sample_wav),
                analyzed_at=None,
            )
            session.add(track)
            session.commit()
            session.refresh(track)

            # First analysis
            result1 = await analyzer.analyze_and_persist(track, session, force=False)
            assert result1 is True
            first_analyzed_at = track.analyzed_at

            # Second analysis without force - should skip
            session.expire_all()
            result2 = await analyzer.analyze_and_persist(track, session, force=False)
            assert result2 is False
            session.refresh(track)
            assert track.analyzed_at == first_analyzed_at

            # With force=True - should re-analyze
            result3 = await analyzer.analyze_and_persist(track, session, force=True)
            assert result3 is True
            session.refresh(track)
            assert track.analyzed_at != first_analyzed_at

    @pytest.mark.asyncio
    async def test_analyze_and_persist_no_local_path(self):
        """Test that tracks without local_path are skipped."""
        analyzer = TechnicalAnalysisEngine()

        with Session(_test_engine) as session:
            track = UnifiedTrack(
                title="No File",
                artist="Test Artist",
                local_path=None,
            )
            session.add(track)
            session.commit()
            session.refresh(track)

            result = await analyzer.analyze_and_persist(track, session)
            assert result is False


class TestAnalyzeLibrary:
    """Tests for batch library analysis."""

    @pytest.mark.asyncio
    async def test_analyze_library_batch(self, sample_wav: Path, sample_mp3: Path):
        """Test analyze_library processes multiple tracks with concurrency control."""
        analyzer = TechnicalAnalysisEngine(max_concurrent=2)

        with Session(_test_engine) as session:
            tracks = [
                UnifiedTrack(title=f"Track {i}", artist="Test", local_path=str(sample_wav))
                for i in range(3)
            ] + [
                UnifiedTrack(title=f"MP3 Track {i}", artist="Test", local_path=str(sample_mp3))
                for i in range(2)
            ]
            session.add_all(tracks)
            session.commit()

        stats = await analyzer.analyze_library(
            session_factory=lambda: Session(_test_engine),
            force=True,
            batch_size=2,
        )

        assert stats["analyzed"] == 5
        assert stats["skipped"] == 0
        assert stats["errors"] == 0

        with Session(_test_engine) as session:
            all_tracks = session.exec(select(UnifiedTrack)).all()
            for t in all_tracks:
                assert t.analyzed_at is not None
                assert t.integrated_lufs is not None


class TestDatabaseMigration:
    """Tests for database migration adding technical analysis columns."""

    def test_migration_adds_all_columns(self):
        """Verify migrate_db adds all required technical analysis columns."""
        with _test_engine.connect() as conn:
            cursor = conn.exec_driver_sql("PRAGMA table_info(unifiedtrack)")
            cols = {row[1]: row[2] for row in cursor.fetchall()}

            assert "true_peak_dbfs" in cols
            assert "dynamic_range_db" in cols
            assert "crest_factor_db" in cols
            assert "silence_start_ms" in cols
            assert "silence_end_ms" in cols
            assert "loudness_range_lu" in cols
            assert "momentary_lufs" in cols
            assert "short_term_lufs" in cols
            assert "clipping_count" in cols
            assert "analysis_version" in cols
            assert "analyzed_at" in cols

            assert cols["true_peak_dbfs"].upper() in ("REAL", "FLOAT")
            assert cols["dynamic_range_db"].upper() in ("REAL", "FLOAT")
            assert cols["silence_start_ms"].upper() == "INTEGER"
            assert cols["analysis_version"].upper() == "INTEGER"


class TestFFmpegParsing:
    """Unit tests for FFmpeg output parsing (regex validation)."""

    def test_parse_ebur128_output(self):
        """Test parsing of ebur128 filter output."""
        from app.engines.technical_analysis import TechnicalAnalysisEngine
        analyzer = TechnicalAnalysisEngine()

        sample_output = """
        Parsed_ebur128_0 @ 0x... Integrated loudness: I: -16.5 LUFS
        Parsed_ebur128_0 @ 0x... True peak: -1.2 dBFS
        Parsed_ebur128_0 @ 0x... Momentary loudness: M: -14.2 LUFS
        Parsed_ebur128_0 @ 0x... Short-term loudness: S: -15.8 LUFS
        Parsed_ebur128_0 @ 0x... Loudness range: LRA: 4.5 LU
        """

        result = analyzer._parse_combined_output(sample_output)

        assert result["integrated_lufs"] == -16.5
        assert result["true_peak_dbfs"] == -1.2
        assert result["momentary_lufs"] == -14.2
        assert result["short_term_lufs"] == -15.8
        assert result["loudness_range_lu"] == 4.5

    def test_parse_astats_output(self):
        """Test parsing of astats filter output."""
        from app.engines.technical_analysis import TechnicalAnalysisEngine
        analyzer = TechnicalAnalysisEngine()

        sample_output = """
        Parsed_astats_1 @ 0x... RMS level: -18.5 dB
        Parsed_astats_1 @ 0x... Peak level: -2.1 dB
        Parsed_astats_1 @ 0x... Clipping: 0
        """

        result = analyzer._parse_combined_output(sample_output)

        assert result["rms_level_db"] == -18.5
        assert result["peak_level_db"] == -2.1
        assert result["clipping_count"] == 0
        assert result["dynamic_range_db"] == 16.4
        assert result["crest_factor_db"] == 16.4

    def test_parse_silencedetect_output(self):
        """Test parsing of silencedetect filter output."""
        from app.engines.technical_analysis import TechnicalAnalysisEngine
        analyzer = TechnicalAnalysisEngine(silence_threshold_db=-50.0)

        sample_output = """
        silencedetect @ 0x... silence_start: 0.000000
        silencedetect @ 0x... silence_end: 1.500000
        silencedetect @ 0x... silence_duration: 1.500000
        silencedetect @ 0x... silence_start: 3.000000
        silencedetect @ 0x... silence_end: 4.000000
        silencedetect @ 0x... silence_duration: 1.000000
        """

        result = analyzer._parse_combined_output(sample_output)

        assert result["silence_start_ms"] == 0
        assert result["silence_end_ms"] == 4000
        assert result["silence_duration_ms"] == 2500


class TestIntegrationWithLocalScanner:
    """Integration test for LocalScanner with technical analysis."""

    @pytest.mark.asyncio
    async def test_scanner_with_technical_analysis(self, sample_wav: Path, tmp_path: Path):
        """Test LocalScanner.scan_directory with analyze_technical=True."""
        from app.engines.local_scanner import LocalScanner

        scan_dir = tmp_path / "scan_test"
        scan_dir.mkdir()
        test_file = scan_dir / "test.wav"
        import shutil
        shutil.copy2(sample_wav, test_file)

        scanner = LocalScanner(session_factory=lambda: Session(_test_engine))

        stats = await scanner.scan_directory_async(
            scan_dir,
            analyze_technical=True,
        )

        assert stats["scanned"] == 1
        assert stats["added"] == 1
        assert stats["analyzed"] == 1

        with Session(_test_engine) as session:
            track = session.exec(select(UnifiedTrack)).first()
            assert track is not None
            assert track.analyzed_at is not None
            assert track.integrated_lufs is not None