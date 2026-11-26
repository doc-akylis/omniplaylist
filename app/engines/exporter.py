import csv
import json
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET
from app.core.models import ExportConfig, ExportFormat, Playlist, UnifiedTrack


class PlaylistExporter:
    """Multi-format playlist exporter supporting M3U8, CSV, JSON, and XSPF."""

    def __init__(self, default_output_dir: Optional[Path] = None):
        self.default_output_dir = default_output_dir or Path("./downloads")

    def export(
        self, playlist: Playlist, tracks: list[UnifiedTrack], config: ExportConfig
    ) -> Path:
        """Export playlist according to supplied configuration."""
        target_dir = Path(config.output_directory) if config.output_directory else self.default_output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_name = playlist.name.replace(" ", "_").replace("/", "_").replace("\\", "_")

        if config.format == ExportFormat.M3U8:
            return self._export_m3u8(playlist, tracks, target_dir / f"{safe_name}.m3u8")
        elif config.format == ExportFormat.CSV:
            return self._export_csv(playlist, tracks, target_dir / f"{safe_name}.csv")
        elif config.format == ExportFormat.JSON:
            return self._export_json(playlist, tracks, target_dir / f"{safe_name}.json")
        elif config.format == ExportFormat.XSPF:
            return self._export_xspf(playlist, tracks, target_dir / f"{safe_name}.xspf")
        else:
            raise ValueError(f"Unsupported format: {config.format}")

    def _export_m3u8(self, playlist: Playlist, tracks: list[UnifiedTrack], output_file: Path) -> Path:
        """Generate standard Extended M3U8 file."""
        lines = ["#EXTM3U", f"#PLAYLIST:{playlist.name}"]
        for t in tracks:
            duration_sec = (t.duration_ms // 1000) if t.duration_ms else -1
            lines.append(f"#EXTINF:{duration_sec},{t.artist} - {t.title}")
            lines.append(t.local_path or f"https://www.youtube.com/watch?v={t.ytmusic_id or ''}")

        output_file.write_text("\n".join(lines), encoding="utf-8")
        return output_file

    def _export_csv(self, playlist: Playlist, tracks: list[UnifiedTrack], output_file: Path) -> Path:
        """Export tracks as tabular CSV."""
        with open(output_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Title", "Artist", "Album", "Duration_MS", "ISRC", "Genres", "Spotify_ID", "YTMusic_ID", "Local_Path"])
            for t in tracks:
                writer.writerow([
                    t.title,
                    t.artist,
                    t.album or "",
                    t.duration_ms or "",
                    t.isrc or "",
                    ", ".join(t.genres),
                    t.spotify_id or "",
                    t.ytmusic_id or "",
                    t.local_path or ""
                ])
        return output_file

    def _export_json(self, playlist: Playlist, tracks: list[UnifiedTrack], output_file: Path) -> Path:
        """Export playlist and tracks to JSON document."""
        data = {
            "playlist": {
                "id": playlist.id,
                "name": playlist.name,
                "description": playlist.description,
                "track_count": len(tracks)
            },
            "tracks": [t.model_dump(exclude={"playlists"}) for t in tracks]
        }
        output_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return output_file

    def _export_xspf(self, playlist: Playlist, tracks: list[UnifiedTrack], output_file: Path) -> Path:
        """Export to XML Shareable Playlist Format (XSPF)."""
        playlist_el = ET.Element("playlist", version="1", xmlns="http://xspf.org/ns/0/")
        title_el = ET.SubElement(playlist_el, "title")
        title_el.text = playlist.name

        track_list_el = ET.SubElement(playlist_el, "trackList")
        for t in tracks:
            tr = ET.SubElement(track_list_el, "track")
            ET.SubElement(tr, "title").text = t.title
            ET.SubElement(tr, "creator").text = t.artist
            if t.album:
                ET.SubElement(tr, "album").text = t.album
            if t.duration_ms:
                ET.SubElement(tr, "duration").text = str(t.duration_ms)
            if t.local_path:
                ET.SubElement(tr, "location").text = Path(t.local_path).as_uri()

        tree = ET.ElementTree(playlist_el)
        tree.write(output_file, encoding="utf-8", xml_declaration=True)
        return output_file
