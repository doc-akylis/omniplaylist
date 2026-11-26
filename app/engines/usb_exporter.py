from pathlib import Path
import re
import shutil
from typing import Optional
from app.core.models import Playlist, UnifiedTrack


class UsbCarExporter:
    """Exports and structures music files for USB flash drives and car stereo infotainment systems."""

    FAT32_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')

    @classmethod
    def sanitize_fat32(cls, name: str) -> str:
        """Strip illegal characters for FAT32 filesystem compatibility."""
        sanitized = cls.FAT32_ILLEGAL_CHARS.sub("", name).strip()
        # Limit folder/file name length to 64 chars to avoid automotive firmware crashes
        return sanitized[:64].rstrip(". ")

    def export_to_usb(
        self,
        playlist: Playlist,
        tracks: list[UnifiedTrack],
        usb_root: Path,
        generate_m3u: bool = True,
    ) -> dict[str, int]:
        """Copy local track files into organized artist/album hierarchy and generate automotive .m3u playlist."""
        stats = {"copied": 0, "skipped_no_local": 0}
        usb_root.mkdir(parents=True, exist_ok=True)

        m3u_lines = ["#EXTM3U", f"#PLAYLIST:{playlist.name}"]

        for idx, track in enumerate(tracks, 1):
            if not track.local_path or not Path(track.local_path).exists():
                stats["skipped_no_local"] += 1
                continue

            src_file = Path(track.local_path)

            artist_folder = self.sanitize_fat32(track.artist) or "Varios Artistas"
            album_folder = (
                f"{track.release_year} - {self.sanitize_fat32(track.album)}"
                if track.album and track.release_year
                else self.sanitize_fat32(track.album or "Singles")
            )

            dest_dir = usb_root / artist_folder / album_folder
            dest_dir.mkdir(parents=True, exist_ok=True)

            safe_title = self.sanitize_fat32(track.title) or f"Faixa_{idx}"
            dest_filename = f"{idx:02d} - {safe_title}{src_file.suffix}"
            dest_file = dest_dir / dest_filename

            if not dest_file.exists():
                shutil.copy2(src_file, dest_file)
            stats["copied"] += 1

            if generate_m3u:
                rel_path = dest_file.relative_to(usb_root)
                duration_sec = (track.duration_ms // 1000) if track.duration_ms else -1
                m3u_lines.append(f"#EXTINF:{duration_sec},{track.artist} - {track.title}")
                m3u_lines.append(str(rel_path).replace("\\", "/"))

        if generate_m3u and stats["copied"] > 0:
            safe_pl_name = self.sanitize_fat32(playlist.name)
            m3u_file = usb_root / f"{safe_pl_name}.m3u"
            m3u_file.write_text("\n".join(m3u_lines), encoding="utf-8")

        return stats
