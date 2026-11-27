from pathlib import Path
import wave
import numpy as np
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app.core.models import ExportFormat, Playlist, UnifiedTrack
from app.engines.dj_intelligence import DJIntelligenceEngine, SequencerConfig
from app.engines.exporter import PlaylistExporter
from app.engines.playlist_manager import PlaylistManagerEngine


def _make_wav(path: Path) -> Path:
    n = 44100
    t = np.linspace(0, 1.0, n, endpoint=False)
    pcm = (0.3 * np.sin(2 * np.pi * 440.0 * t) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(np.column_stack([pcm, pcm]).flatten().tobytes())
    return path


@pytest.fixture
def pl_db(tmp_path: Path):
    db_file = tmp_path / "test_pl.db"
    eng = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


def test_playlist_crud_nn_reorder_sort_metrics_and_export(tmp_path: Path, pl_db):
    pm = PlaylistManagerEngine()
    exporter = PlaylistExporter(default_output_dir=tmp_path / "exports")
    wav1 = _make_wav(tmp_path / "t1.wav")
    wav2 = _make_wav(tmp_path / "t2.wav")

    with Session(pl_db) as s:
        t1 = UnifiedTrack(title="Alpha", artist="Art A", bpm=128.0, camelot_code="8A", energy=0.7, duration_ms=200000, local_path=str(wav1), integrated_lufs=-9.0, car_audio_score=90.0)
        t2 = UnifiedTrack(title="Beta", artist="Art B", bpm=124.0, camelot_code="9A", energy=0.5, duration_ms=180000, local_path=str(wav2), integrated_lufs=-10.0, car_audio_score=85.0)
        t3 = UnifiedTrack(title="Missing Preview", artist="Art C", bpm=None, camelot_code=None, energy=None, duration_ms=30000, is_preview=True, local_path=str(tmp_path / "missing.mp3"))
        s.add_all([t1, t2, t3])
        s.commit()
        for t in (t1, t2, t3):
            s.refresh(t)

        # Create, duplicate, N:N membership
        p1 = pm.create_playlist(s, "Club Set", "Warmup to Peak", track_ids=[t1.id, t2.id, t3.id])
        p2 = pm.create_playlist(s, "Second List", track_ids=[t1.id])  # t1 belongs to 2 playlists (N:N)
        p_dup = pm.duplicate_playlist(s, p1.id, "Club Set Copy")
        assert p_dup is not None and p_dup.id != p1.id

        # Reorder & persistence
        pm.reorder_tracks(s, p1.id, [t3.id, t2.id, t1.id])
        ordered = pm.get_ordered_tracks(s, p1.id)
        assert [t.id for t in ordered] == [t3.id, t2.id, t1.id]

        # Sort by BPM ascending
        sorted_bpm = pm.sort_playlist(s, p1.id, "bpm_asc", persist=True)
        assert [t.id for t in sorted_bpm] == [t2.id, t1.id, t3.id]

        # Real metrics
        metrics = pm.compute_playlist_metrics(sorted_bpm)
        assert metrics["total_tracks"] == 3
        assert metrics["avg_bpm"] == 126.0
        assert metrics["complete_count"] == 2
        assert metrics["missing_count"] == 1
        assert len(metrics["metrics_notes"]) >= 1

        # Export M3U with missing-file report
        rep = exporter.export_m3u_with_report(p1, sorted_bpm, output_dir=tmp_path / "exports", fmt=ExportFormat.M3U)
        assert Path(rep["exported_file"]).exists()
        assert rep["exported_local_count"] == 2
        assert len(rep["missing_files"]) == 1

        # Deleting playlist must NOT delete UnifiedTrack records
        assert pm.delete_playlist(s, p_dup.id) is True
        assert len(s.exec(select(UnifiedTrack)).all()) == 3
        assert len(pm.get_ordered_tracks(s, p2.id)) == 1


def test_smart_sequencer_modes_constraints_explainability_and_restore(pl_db):
    pm = PlaylistManagerEngine()
    dj = DJIntelligenceEngine()

    with Session(pl_db) as s:
        t1 = UnifiedTrack(title="Opener", artist="A1", bpm=120.0, camelot_code="8A", energy=0.45, genres_raw="deep house")
        t2 = UnifiedTrack(title="Builder", artist="A2", bpm=123.0, camelot_code="9A", energy=0.65, genres_raw="deep house")
        t3 = UnifiedTrack(title="Peak", artist="A3", bpm=126.0, camelot_code="10A", energy=0.88, genres_raw="tech house")
        t4 = UnifiedTrack(title="Banned", artist="A1", bpm=140.0, camelot_code="2B", energy=0.95, genres_raw="techno")
        t5 = UnifiedTrack(title="NoData", artist="A4", bpm=None, camelot_code=None, energy=None)
        s.add_all([t1, t2, t3, t4, t5])
        s.commit()
        for t in (t1, t2, t3, t4, t5):
            s.refresh(t)

        pl = pm.create_playlist(s, "Flow Test", track_ids=[t3.id, t1.id, t2.id, t4.id, t5.id])
        tracks = pm.get_ordered_tracks(s, pl.id)

        # Test BPM progression & forbidden_track_ids
        cfg = SequencerConfig(
            mode="bpm_progression",
            start_bpm=120.0,
            end_bpm=126.0,
            forbidden_track_ids=[t4.id],
        )
        res = dj.generate_sequence(tracks, cfg)
        ids = [t.id for t in res["ordered_tracks"]]
        assert t4.id not in ids
        assert ids[:3] == [t1.id, t2.id, t3.id]
        assert len(res["transitions"]) == 3
        assert "harmonia" in res["transitions"][0]["justification"]
        assert len(res["warnings"]) >= 1  # t5 missing BPM

        # Apply sequence & restore original order
        dj.apply_sequence_to_playlist(s, pl.id, ids)
        after_apply = [t.id for t in pm.get_ordered_tracks(s, pl.id)]
        assert after_apply[:3] == [t1.id, t2.id, t3.id]

        ok, orig_ids = dj.restore_playlist_order(s, pl.id)
        assert ok is True
        assert orig_ids == [t3.id, t1.id, t2.id, t4.id, t5.id]
        after_restore = [t.id for t in pm.get_ordered_tracks(s, pl.id)]
        assert after_restore == [t3.id, t1.id, t2.id, t4.id, t5.id]

        # Test energy_progression, harmonic_flow, custom modes
        for m in ("energy_progression", "harmonic_flow", "custom"):
            r_mode = dj.generate_sequence([t1, t2, t3], SequencerConfig(mode=m))
            assert len(r_mode["ordered_tracks"]) == 3
