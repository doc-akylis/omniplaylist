import json
from pathlib import Path
from xml.etree import ElementTree as ET
from app.core.models import ExportConfig, ExportFormat, Playlist, UnifiedTrack
from app.engines.ai_curator import AICurator
from app.engines.analytics_engine import AnalyticsEngine
from app.engines.audio_analyzer import AudioAnalyzer
from app.engines.deduplicator import Deduplicator
from app.engines.dj_exporter import DjExporter
from app.engines.exporter import PlaylistExporter
from app.engines.genre_engine import GenreEngine
from app.engines.smart_links import SmartLinkEngine
from app.engines.usb_exporter import UsbCarExporter


def test_genre_engine():
    engine = GenreEngine()
    assert engine.normalize_tag(" Synth-Wave ") == "synth wave"
    assert engine.get_parent_genre("synthwave") == "Electronic"
    assert engine.get_parent_genre("indie rock") == "Rock"
    assert engine.get_parent_genre("trap") == "Hip Hop"

    tracks = [
        UnifiedTrack(title="T1", artist="A1", genres_raw="techno, synthwave"),
        UnifiedTrack(title="T2", artist="A2", genres_raw="indie rock"),
    ]
    tree = engine.build_genre_tree(tracks)
    assert "Electronic" in tree
    assert "Rock" in tree
    assert tree["Electronic"]["tracks_count"] == 2


def test_playlist_exporter(tmp_path: Path):
    exporter = PlaylistExporter(default_output_dir=tmp_path)
    pl = Playlist(id=1, name="Synthwave Classics")
    tracks = [
        UnifiedTrack(id=1, title="Midnight City", artist="M83", duration_ms=243000, isrc="FR01T1100523"),
        UnifiedTrack(id=2, title="Resonance", artist="HOME", duration_ms=212000),
    ]

    # Test M3U8
    m3u8_file = exporter.export(pl, tracks, ExportConfig(playlist_id=1, format=ExportFormat.M3U8, output_directory=str(tmp_path)))
    assert m3u8_file.exists()
    content = m3u8_file.read_text(encoding="utf-8")
    assert "#EXTM3U" in content
    assert "M83 - Midnight City" in content

    # Test CSV
    csv_file = exporter.export(pl, tracks, ExportConfig(playlist_id=1, format=ExportFormat.CSV, output_directory=str(tmp_path)))
    assert csv_file.exists()
    assert "Title,Artist" in csv_file.read_text(encoding="utf-8")

    # Test JSON
    json_file = exporter.export(pl, tracks, ExportConfig(playlist_id=1, format=ExportFormat.JSON, output_directory=str(tmp_path)))
    assert json_file.exists()
    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(data["tracks"]) == 2

    # Test XSPF
    xspf_file = exporter.export(pl, tracks, ExportConfig(playlist_id=1, format=ExportFormat.XSPF, output_directory=str(tmp_path)))
    assert xspf_file.exists()
    assert "<playlist" in xspf_file.read_text(encoding="utf-8")


def test_dj_exporter_rekordbox_xml(tmp_path: Path):
    dj_exp = DjExporter()
    pl = Playlist(name="Club Set 2026")
    tracks = [
        UnifiedTrack(id=1, title="Track 1", artist="DJ A", bpm=124.0, key="8A", duration_ms=300000),
        UnifiedTrack(id=2, title="Track 2", artist="DJ B", bpm=126.0, key="9A", duration_ms=280000),
    ]

    xml_path = tmp_path / "rekordbox_test.xml"
    dj_exp.export_rekordbox_xml(pl, tracks, xml_path)
    assert xml_path.exists()

    tree = ET.parse(xml_path)
    root = tree.getroot()
    assert root.tag == "DJ_PLAYLISTS"
    tracks_node = root.find("COLLECTION")
    assert tracks_node is not None
    assert tracks_node.attrib["Entries"] == "2"


def test_usb_car_exporter(tmp_path: Path):
    usb_exp = UsbCarExporter()
    assert usb_exp.sanitize_fat32('Artista: "Banda"? / Rock*') == "Artista Banda  Rock"

    # Create dummy local file to simulate download
    dummy_audio = tmp_path / "source.mp3"
    dummy_audio.write_text("dummy audio", encoding="utf-8")

    pl = Playlist(name="Car Mix")
    tracks = [
        UnifiedTrack(
            id=1,
            title="Drive Safe",
            artist="Synth Driver",
            album="Neon Nights",
            release_year=2024,
            local_path=str(dummy_audio),
        )
    ]

    usb_dest = tmp_path / "usb_stick"
    stats = usb_exp.export_to_usb(pl, tracks, usb_dest)
    assert stats["copied"] == 1
    m3u_file = usb_dest / "Car Mix.m3u"
    assert m3u_file.exists()


def test_audio_analyzer_camelot():
    analyzer = AudioAnalyzer()
    assert analyzer.normalize_to_camelot("Am") == "8A"
    assert analyzer.normalize_to_camelot("C") == "8B"
    assert analyzer.normalize_to_camelot("F#m") == "11A"

    # Harmonic compatibility checks
    assert analyzer.are_keys_compatible("8A", "8A") is True   # Same key
    assert analyzer.are_keys_compatible("8A", "7A") is True   # Adjacent -1
    assert analyzer.are_keys_compatible("8A", "9A") is True   # Adjacent +1
    assert analyzer.are_keys_compatible("8A", "8B") is True   # Relative switch
    assert analyzer.are_keys_compatible("8A", "2A") is False  # Incompatible

    # DJ playlist sorting
    tracks = [
        UnifiedTrack(id=1, title="Intro", artist="A", bpm=128.0, key="8A"),
        UnifiedTrack(id=2, title="Peak", artist="B", bpm=120.0, key="8A"),
        UnifiedTrack(id=3, title="Mid", artist="C", bpm=124.0, key="9A"),
    ]
    sorted_tracks = analyzer.sort_playlist_for_dj(tracks)
    bpms = [t.bpm for t in sorted_tracks]
    assert bpms == [120.0, 124.0, 128.0]


def test_ai_curator():
    curator = AICurator()
    parsed = curator.parse_prompt("rock animado anos 80 para correr com 135 bpm")
    assert parsed["bpm_range"] == (125.0, 150.0)
    assert parsed["year_range"] == (1980, 1989)
    assert "rock" in parsed["target_genres"]

    catalog = [
        UnifiedTrack(id=1, title="Eye of the Tiger", artist="Survivor", release_year=1982, bpm=109.0, genres_raw="rock"),
        UnifiedTrack(id=2, title="Runaway", artist="Bon Jovi", release_year=1984, bpm=135.0, genres_raw="rock"),
        UnifiedTrack(id=3, title="Chill Lofi", artist="Lofi Beat", release_year=2021, bpm=80.0, genres_raw="lo-fi"),
    ]
    playlist = curator.build_playlist("rock anos 80 135 bpm", catalog)
    assert len(playlist) > 0
    assert playlist[0].title == "Runaway"  # Highest match score


def test_deduplicator():
    dedup = Deduplicator()
    t1 = UnifiedTrack(id=1, title="Song Title", artist="Artist Name", duration_ms=200000)
    t2 = UnifiedTrack(id=2, title="Song Title (Remastered 2020)", artist="Artist Name", duration_ms=201000)
    t3 = UnifiedTrack(id=3, title="Completely Different", artist="Other Artist")

    groups = dedup.find_duplicate_groups([t1, t2, t3])
    assert len(groups) == 1
    assert groups[0]["primary"].id == 1
    assert groups[0]["candidates"][0].id == 2


def test_analytics_engine():
    analytics = AnalyticsEngine()
    tracks = [
        UnifiedTrack(id=1, title="T1", artist="Artist Alpha", release_year=1985, duration_ms=180000, genres_raw="synthwave", bpm=120.0, local_path="a.mp3"),
        UnifiedTrack(id=2, title="T2", artist="Artist Alpha", release_year=1988, duration_ms=240000, genres_raw="techno", bpm=130.0),
        UnifiedTrack(id=3, title="T3", artist="Artist Beta", release_year=2022, duration_ms=120000, genres_raw="indie rock"),
    ]
    stats = analytics.generate_stats(tracks)
    assert stats["total_tracks"] == 3
    assert stats["total_duration_minutes"] == 9.0
    assert stats["top_artists"][0] == ("Artist Alpha", 2)
    assert "1980s" in stats["decade_distribution"]
    assert stats["decade_distribution"]["1980s"] == 2
    assert stats["average_bpm"] == 125.0


def test_smart_links():
    smart = SmartLinkEngine()
    t_spot = UnifiedTrack(title="T", artist="A", spotify_id="abc12345")
    assert smart.get_quick_universal_url(t_spot) == "https://song.link/s/abc12345"

    t_deez = UnifiedTrack(title="T", artist="A", deezer_id="998877")
    assert smart.get_quick_universal_url(t_deez) == "https://song.link/d/998877"
