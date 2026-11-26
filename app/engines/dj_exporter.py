from pathlib import Path
from xml.etree import ElementTree as ET
from app.core.models import Playlist, UnifiedTrack


class DjExporter:
    """Exports playlists into Pioneer Rekordbox XML format compatible with Pioneer CDJs, Virtual DJ, and Engine DJ."""

    def export_rekordbox_xml(
        self, playlist: Playlist, tracks: list[UnifiedTrack], output_path: Path
    ) -> Path:
        """Generate a valid Rekordbox XML collection with BPM, tonal key, and file location."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        root = ET.Element("DJ_PLAYLISTS", Version="1.0.0")
        ET.SubElement(
            root,
            "PRODUCT",
            Name="OmniPlaylist",
            Version="1.0.0",
            Company="OmniPlaylist",
        )

        collection = ET.SubElement(root, "COLLECTION", Entries=str(len(tracks)))

        for idx, t in enumerate(tracks, 1):
            track_id = str(t.id or idx)
            loc = Path(t.local_path).as_uri() if t.local_path else f"https://streaming/{track_id}"
            duration_sec = str(int((t.duration_ms or 0) / 1000))

            ET.SubElement(
                collection,
                "TRACK",
                TrackID=track_id,
                Name=t.title,
                Artist=t.artist,
                Album=t.album or "",
                Genre=t.genres[0] if t.genres else "",
                TotalTime=duration_sec,
                AverageBpm=f"{t.bpm:.2f}" if t.bpm else "120.00",
                Tonality=t.key or "",
                Location=loc,
            )

        playlists_root = ET.SubElement(root, "PLAYLISTS")
        root_node = ET.SubElement(playlists_root, "NODE", Type="0", Name="ROOT")
        pl_node = ET.SubElement(
            root_node,
            "NODE",
            Name=playlist.name,
            Type="1",
            KeyType="0",
            Entries=str(len(tracks)),
        )

        for idx, t in enumerate(tracks, 1):
            track_id = str(t.id or idx)
            ET.SubElement(pl_node, "TRACK", Key=track_id)

        tree = ET.ElementTree(root)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        return output_path
