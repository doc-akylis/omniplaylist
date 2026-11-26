import pytest
from pathlib import Path
from app.engines.loudness_engine import LoudnessEngine


@pytest.mark.asyncio
async def test_loudness_engine_analysis_fallback(tmp_path):
    engine = LoudnessEngine(default_target_lufs=-14.0)
    dummy_file = tmp_path / "dummy.mp3"
    dummy_file.write_text("audio bytes", encoding="utf-8")

    report = await engine.analyze_file_loudness(dummy_file)
    assert report is not None
    assert report.target_lufs == -14.0
    assert report.applied_gain_db is not None
