from pathlib import Path
from app.core.models import UnifiedTrack
from app.engines.device_sync import DeviceSyncEngine


def test_device_sync_plan_and_execution(tmp_path: Path):
    engine = DeviceSyncEngine()
    source_dir = tmp_path / "music_src"
    source_dir.mkdir()
    f1 = source_dir / "song1.mp3"
    f1.write_text("audio content 1", encoding="utf-8")

    tracks = [
        UnifiedTrack(id=1, title="Song One", artist="Artist A", album="Album A", local_path=str(f1)),
    ]

    target_dir = tmp_path / "usb_device"

    # 1. Plan generation
    plan = engine.generate_sync_plan(tracks, target_dir)
    assert plan.new_to_copy_count == 1
    assert plan.already_synced_count == 0
    assert plan.has_sufficient_space is True

    # 2. Execution
    stats = engine.execute_sync(plan, playlist_name="My Car Mix")
    assert stats["copied"] == 1
    assert (target_dir / "My Car Mix.m3u").exists()

    # 3. Second plan should detect as already synced
    second_plan = engine.generate_sync_plan(tracks, target_dir)
    assert second_plan.already_synced_count == 1
    assert second_plan.new_to_copy_count == 0
