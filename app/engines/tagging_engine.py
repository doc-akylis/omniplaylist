from pathlib import Path
from typing import Optional
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TXXX, USLT
from mutagen.mp4 import MP4, MP4Cover

from app.core.models import UnifiedTrack


class TaggingEngine:
    """Multi-format audio metadata tagging via Mutagen preserving existing valid tags."""

    def apply_tags(
        self,
        file_path: Path,
        track: UnifiedTrack,
        cover_bytes: Optional[bytes] = None,
        preserve_existing: bool = True,
    ) -> tuple[bool, list[str]]:
        """Apply UnifiedTrack metadata, ReplayGain, Camelot, lyrics, and cover art to file_path."""
        if not file_path.exists():
            return False, ["Arquivo não existe para gravação de tags."]

        ext = file_path.suffix.lower().lstrip(".")
        warnings: list[str] = []

        try:
            if ext in ("mp3", "wav"):
                return self._tag_id3(file_path, track, cover_bytes, preserve_existing), warnings
            if ext == "flac":
                return self._tag_flac(file_path, track, cover_bytes, preserve_existing), warnings
            if ext in ("m4a", "mp4"):
                return self._tag_mp4(file_path, track, cover_bytes, preserve_existing), warnings
            # Generic fallback attempt
            audio = mutagen.File(str(file_path), easy=True)
            if audio is not None:
                self._assign_easy_map(audio, track, preserve_existing)
                audio.save()
                return True, warnings
            return False, [f"Formato .{ext} não possui suporte de gravação de tags."]
        except Exception as e:
            return False, [f"Falha ao gravar tags: {e}"]

    @staticmethod
    def _set_if_needed(mapping: dict, key: str, value: Optional[str], preserve_existing: bool) -> None:
        if not value:
            return
        if preserve_existing and mapping.get(key):
            return
        mapping[key] = value

    def _assign_easy_map(self, mapping: dict, track: UnifiedTrack, preserve_existing: bool) -> None:
        self._set_if_needed(mapping, "title", track.title, preserve_existing)
        self._set_if_needed(mapping, "artist", track.artist, preserve_existing)
        self._set_if_needed(mapping, "album", track.album, preserve_existing)
        self._set_if_needed(mapping, "albumartist", track.artist, preserve_existing)
        if track.genres:
            self._set_if_needed(mapping, "genre", track.genres[0], preserve_existing)
        if track.release_year:
            self._set_if_needed(mapping, "date", str(track.release_year), preserve_existing)
        if track.track_number:
            self._set_if_needed(mapping, "tracknumber", str(track.track_number), preserve_existing)
        if track.isrc:
            self._set_if_needed(mapping, "isrc", track.isrc, preserve_existing)
        if track.bpm:
            self._set_if_needed(mapping, "bpm", str(int(round(track.bpm))), preserve_existing)

    def _tag_id3(
        self,
        file_path: Path,
        track: UnifiedTrack,
        cover_bytes: Optional[bytes],
        preserve_existing: bool,
    ) -> bool:
        if file_path.suffix.lower() == ".mp3":
            try:
                easy = EasyID3(str(file_path))
            except ID3NoHeaderError:
                easy = EasyID3()
            self._assign_easy_map(easy, track, preserve_existing)
            easy.save(str(file_path))

        try:
            tags = ID3(str(file_path))
        except ID3NoHeaderError:
            tags = ID3()

        if track.key or track.camelot_code:
            val = track.camelot_code or track.key or ""
            if not (preserve_existing and tags.getall("TXXX:CAMELOT")):
                tags.delall("TXXX:CAMELOT")
                tags.add(TXXX(encoding=3, desc="CAMELOT", text=val))

        if track.replay_gain is not None:
            if not (preserve_existing and tags.getall("TXXX:replaygain_track_gain")):
                tags.delall("TXXX:replaygain_track_gain")
                tags.add(TXXX(encoding=3, desc="replaygain_track_gain", text=f"{track.replay_gain:+.2f} dB"))

        lyrics = track.lyrics_synced or track.lyrics_plain
        if lyrics and not (preserve_existing and tags.getall("USLT")):
            tags.delall("USLT")
            tags.add(USLT(encoding=3, lang="eng", desc="Lyrics", text=lyrics))

        if cover_bytes and not (preserve_existing and tags.getall("APIC")):
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes))

        tags.save(str(file_path))
        return True

    def _tag_flac(
        self,
        file_path: Path,
        track: UnifiedTrack,
        cover_bytes: Optional[bytes],
        preserve_existing: bool,
    ) -> bool:
        flac = FLAC(str(file_path))
        self._assign_easy_map(flac, track, preserve_existing)
        if track.camelot_code or track.key:
            self._set_if_needed(flac, "initialkey", track.camelot_code or track.key, preserve_existing)
        if track.replay_gain is not None:
            self._set_if_needed(flac, "replaygain_track_gain", f"{track.replay_gain:+.2f} dB", preserve_existing)
        lyrics = track.lyrics_synced or track.lyrics_plain
        if lyrics:
            self._set_if_needed(flac, "lyrics", lyrics, preserve_existing)

        if cover_bytes and not (preserve_existing and flac.pictures):
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = cover_bytes
            flac.clear_pictures()
            flac.add_picture(pic)

        flac.save()
        return True

    def _tag_mp4(
        self,
        file_path: Path,
        track: UnifiedTrack,
        cover_bytes: Optional[bytes],
        preserve_existing: bool,
    ) -> bool:
        mp4 = MP4(str(file_path))
        if mp4.tags is None:
            mp4.add_tags()

        def set_atom(atom: str, val: Optional[str]) -> None:
            if not val:
                return
            if preserve_existing and mp4.tags.get(atom):
                return
            mp4.tags[atom] = [val]

        set_atom("\xa9nam", track.title)
        set_atom("\xa9ART", track.artist)
        set_atom("\xa9alb", track.album)
        set_atom("aART", track.artist)
        if track.genres:
            set_atom("\xa9gen", track.genres[0])
        if track.release_year:
            set_atom("\xa9day", str(track.release_year))
        lyrics = track.lyrics_synced or track.lyrics_plain
        if lyrics:
            set_atom("\xa9lyr", lyrics)
        if track.bpm and not (preserve_existing and mp4.tags.get("tmpo")):
            mp4.tags["tmpo"] = [int(round(track.bpm))]
        if cover_bytes and not (preserve_existing and mp4.tags.get("covr")):
            mp4.tags["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]

        mp4.save()
        return True
