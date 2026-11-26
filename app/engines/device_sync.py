from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from typing import Any, Optional

from app.core.models import DeviceSyncProfile, Playlist, UnifiedTrack
from app.engines.usb_exporter import UsbCarExporter


@dataclass
class SyncItemPreview:
    """Preview of an individual file action during synchronization."""

    track_id: int
    title: str
    artist: str
    action: str  # "copy_new", "already_synced", "update_modified", "orphan_on_device"
    source_path: Optional[str]
    target_rel_path: str
    file_size_bytes: int


@dataclass
class SyncPlanPreview:
    """Pre-sync audit calculating space requirements and file actions."""

    target_dir: str
    total_playlist_tracks: int
    new_to_copy_count: int
    already_synced_count: int
    orphan_files_count: int
    total_bytes_needed: int
    available_bytes_on_device: int
    has_sufficient_space: bool
    items: list[SyncItemPreview] = field(default_factory=list)


class DeviceSyncEngine:
    """Smart device and USB sync manager with space auditing, FAT32 safety, and operation previews."""

    def __init__(self):
        self.usb_exporter = UsbCarExporter()

    def generate_sync_plan(
        self,
        tracks: list[UnifiedTrack],
        target_dir: Path,
        profile: Optional[DeviceSyncProfile] = None,
    ) -> SyncPlanPreview:
        """Analyze differences between playlist tracks and target drive/folder."""
        items: list[SyncItemPreview] = []
        new_count = 0
        synced_count = 0
        bytes_needed = 0

        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Map existing files in target directory
        existing_target_files: dict[str, Path] = {}
        for f in target_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in [".mp3", ".flac", ".wav", ".m4a", ".ogg"]:
                rel = str(f.relative_to(target_dir)).replace("\\", "/")
                existing_target_files[rel.lower()] = f

        # 2. Check each track in playlist
        for idx, t in enumerate(tracks, 1):
            if not t.local_path or not Path(t.local_path).exists():
                continue

            src = Path(t.local_path)
            src_size = src.stat().st_size

            # Target relative path
            safe_artist = self.usb_exporter.sanitize_fat32(t.artist) or "Varios Artistas"
            safe_album = self.usb_exporter.sanitize_fat32(t.album or "Singles")
            safe_title = self.usb_exporter.sanitize_fat32(t.title) or f"Faixa_{idx}"
            target_rel = f"{safe_artist}/{safe_album}/{idx:02d} - {safe_title}{src.suffix}".replace("\\", "/")

            if target_rel.lower() in existing_target_files:
                target_f = existing_target_files[target_rel.lower()]
                # Check if size matches
                if abs(target_f.stat().st_size - src_size) < 1024:
                    synced_count += 1
                    action = "already_synced"
                else:
                    new_count += 1
                    bytes_needed += src_size
                    action = "update_modified"
                # Remove from existing map to track orphans
                del existing_target_files[target_rel.lower()]
            else:
                new_count += 1
                bytes_needed += src_size
                action = "copy_new"

            items.append(
                SyncItemPreview(
                    track_id=t.id or idx,
                    title=t.title,
                    artist=t.artist,
                    action=action,
                    source_path=str(src),
                    target_rel_path=target_rel,
                    file_size_bytes=src_size,
                )
            )

        # 3. Identify orphan files remaining on target
        orphan_count = len(existing_target_files)
        for rel_low, f_path in existing_target_files.items():
            items.append(
                SyncItemPreview(
                    track_id=0,
                    title=f_path.stem,
                    artist="Dispositivo",
                    action="orphan_on_device",
                    source_path=None,
                    target_rel_path=str(f_path.relative_to(target_dir)).replace("\\", "/"),
                    file_size_bytes=f_path.stat().st_size,
                )
            )

        # 4. Check disk usage
        try:
            usage = shutil.disk_usage(target_dir)
            available_bytes = usage.free
        except Exception:
            available_bytes = 10 * 1024 * 1024 * 1024  # Default fallback 10GB

        sufficient = available_bytes >= (bytes_needed + 10 * 1024 * 1024)

        return SyncPlanPreview(
            target_dir=str(target_dir),
            total_playlist_tracks=len(tracks),
            new_to_copy_count=new_count,
            already_synced_count=synced_count,
            orphan_files_count=orphan_count,
            total_bytes_needed=bytes_needed,
            available_bytes_on_device=available_bytes,
            has_sufficient_space=sufficient,
            items=items,
        )

    def execute_sync(
        self,
        plan: SyncPlanPreview,
        playlist_name: str = "OmniPlaylist Sync",
        delete_orphans: bool = False,
    ) -> dict[str, int]:
        """Execute synchronization plan safely with atomic copying and relative M3U generation."""
        stats = {"copied": 0, "skipped": 0, "deleted_orphans": 0, "errors": 0}
        target_root = Path(plan.target_dir)

        if not target_root.exists():
            target_root.mkdir(parents=True, exist_ok=True)

        m3u_lines = ["#EXTM3U", f"#PLAYLIST:{playlist_name}"]

        for item in plan.items:
            # Handle orphan deletion only if explicitly permitted
            if item.action == "orphan_on_device":
                if delete_orphans:
                    orphan_file = target_root / item.target_rel_path
                    if orphan_file.exists():
                        try:
                            orphan_file.unlink()
                            stats["deleted_orphans"] += 1
                        except Exception:
                            stats["errors"] += 1
                continue

            if item.action in ("copy_new", "update_modified") and item.source_path:
                src = Path(item.source_path)
                dest = target_root / item.target_rel_path
                dest.parent.mkdir(parents=True, exist_ok=True)

                try:
                    # Atomic copy
                    temp_dest = dest.with_suffix(".tmp_sync")
                    shutil.copy2(src, temp_dest)
                    temp_dest.replace(dest)
                    stats["copied"] += 1
                except Exception as e:
                    print(f"[SmartSync] Copy error: {e}")
                    stats["errors"] += 1
            else:
                stats["skipped"] += 1

            # Add relative entry to M3U
            m3u_lines.append(f"#EXTINF:-1,{item.artist} - {item.title}")
            m3u_lines.append(item.target_rel_path)

        # Generate relative M3U playlist file
        safe_pl_name = self.usb_exporter.sanitize_fat32(playlist_name)
        m3u_file = target_root / f"{safe_pl_name}.m3u"
        m3u_file.write_text("\n".join(m3u_lines), encoding="utf-8")

        return stats
