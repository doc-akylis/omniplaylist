from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from sqlmodel import Session, select

from app.core.models import UnifiedTrack
from app.engines.lyrics_engine import LyricsEngine
from app.providers.acoustid import AcoustIDProvider
from app.providers.deezer import DeezerProvider
from app.providers.itunes import ITunesProvider
from app.providers.lastfm import LastFMProvider
from app.providers.listenbrainz import ListenBrainzProvider
from app.providers.musicbrainz import MusicBrainzProvider


class MetadataEnrichmentEngine:
    """Cascade metadata, artwork, lyrics, and acoustic fingerprint enrichment orchestrator.

    Priority order (never using Spotify for audio analysis):
    1. AcoustID (optional key + fpcalc) for untagged local files
    2. MusicBrainz + Cover Art Archive (no key, strict 1 req/s, User-Agent)
    3. iTunes Search API & Deezer API (no key) fallback for HD cover, preview_url, ISRC, year
    4. LRCLIB (no key, soft rate limit) for synced (.lrc) & plain lyrics
    5. Last.fm & ListenBrainz (optional keys) for genre tags and discovery metadata
    """

    def __init__(
        self,
        musicbrainz: Optional[MusicBrainzProvider] = None,
        itunes: Optional[ITunesProvider] = None,
        deezer: Optional[DeezerProvider] = None,
        lyrics: Optional[LyricsEngine] = None,
        acoustid: Optional[AcoustIDProvider] = None,
        lastfm: Optional[LastFMProvider] = None,
        listenbrainz: Optional[ListenBrainzProvider] = None,
    ):
        self.musicbrainz = musicbrainz or MusicBrainzProvider()
        self.itunes = itunes or ITunesProvider()
        self.deezer = deezer or DeezerProvider()
        self.lyrics = lyrics or LyricsEngine()
        self.acoustid = acoustid or AcoustIDProvider()
        self.lastfm = lastfm or LastFMProvider()
        self.listenbrainz = listenbrainz or ListenBrainzProvider()

    async def enrich_track(
        self,
        track: UnifiedTrack,
        session: Session,
        force: bool = False,
    ) -> dict[str, Any]:
        """Enrich a single UnifiedTrack via cascade fallbacks and persist to SQLite."""
        if track.metadata_enriched_at is not None and not force:
            return {
                "enriched": False,
                "skipped": True,
                "sources_used": [],
            }

        sources_used: list[str] = []

        # 1. AcoustID (if local file exists and AcoustID + fpcalc are available)
        if track.local_path and not track.acoustid_id:
            local_file = Path(track.local_path)
            if local_file.exists():
                ac_match = await self.acoustid.identify_file(local_file)
                if ac_match:
                    sources_used.append("acoustid")
                    if ac_match.acoustid_id:
                        track.acoustid_id = ac_match.acoustid_id
                    if ac_match.musicbrainz_recording_id and not track.musicbrainz_recording_id:
                        track.musicbrainz_recording_id = ac_match.musicbrainz_recording_id
                    if ac_match.title and track.title in ("", "Unknown", "Unknown Title"):
                        track.title = ac_match.title
                    if ac_match.artist and track.artist in ("", "Unknown", "Unknown Artist"):
                        track.artist = ac_match.artist

        # 2. MusicBrainz + Cover Art Archive
        mb_match = None
        if track.isrc:
            mb_match = await self.musicbrainz.lookup_by_isrc(track.isrc)
        if mb_match is None and (track.artist or track.title):
            mb_match = await self.musicbrainz.search_recording(track.artist, track.title)

        if mb_match:
            sources_used.append("musicbrainz")
            if mb_match.recording_id and not track.musicbrainz_recording_id:
                track.musicbrainz_recording_id = mb_match.recording_id
            if mb_match.isrc and not track.isrc:
                track.isrc = mb_match.isrc
            if mb_match.album and not track.album:
                track.album = mb_match.album
            if mb_match.release_year and not track.release_year:
                track.release_year = mb_match.release_year
            if mb_match.hd_cover_url:
                sources_used.append("cover_art_archive")
                if not track.hd_cover_url:
                    track.hd_cover_url = mb_match.hd_cover_url
                if not track.cover_url:
                    track.cover_url = mb_match.hd_cover_url

        # 3a. Fallback: iTunes Search API (HD cover, preview, year, genre)
        needs_catalog_fallback = (
            not track.hd_cover_url
            or not track.preview_url
            or not track.release_year
            or not track.album
        )
        if needs_catalog_fallback and (track.artist or track.title):
            it_match = await self.itunes.search_track(track.artist, track.title)
            if it_match:
                sources_used.append("itunes")
                if it_match.hd_cover_url and not track.hd_cover_url:
                    track.hd_cover_url = it_match.hd_cover_url
                if it_match.hd_cover_url and not track.cover_url:
                    track.cover_url = it_match.hd_cover_url
                if it_match.preview_url and not track.preview_url:
                    track.preview_url = it_match.preview_url
                if it_match.release_year and not track.release_year:
                    track.release_year = it_match.release_year
                if it_match.album and not track.album:
                    track.album = it_match.album
                if it_match.genre and not track.genres_raw:
                    track.genres_raw = it_match.genre

        # 3b. Fallback: Deezer API (ISRC, HD cover, preview, release_year)
        needs_deezer_fallback = (
            not track.hd_cover_url
            or not track.preview_url
            or not track.isrc
            or not track.release_year
        )
        if needs_deezer_fallback and (track.artist or track.title):
            dz_results = await self.deezer.search_tracks(f"{track.artist} {track.title}".strip(), limit=1)
            if dz_results:
                dz_match = dz_results[0]
                if dz_match.deezer_id and not dz_match.isrc:
                    detailed = await self.deezer.get_track(dz_match.deezer_id)
                    if detailed:
                        dz_match = detailed
                sources_used.append("deezer")
                if dz_match.deezer_id and not track.deezer_id:
                    track.deezer_id = dz_match.deezer_id
                if dz_match.isrc and not track.isrc:
                    track.isrc = dz_match.isrc
                if dz_match.hd_cover_url and not track.hd_cover_url:
                    track.hd_cover_url = dz_match.hd_cover_url
                if dz_match.cover_url and not track.cover_url:
                    track.cover_url = dz_match.cover_url
                if dz_match.preview_url and not track.preview_url:
                    track.preview_url = dz_match.preview_url
                if dz_match.release_year and not track.release_year:
                    track.release_year = dz_match.release_year

        # 4. Lyrics via LRCLIB
        if not track.lyrics_synced or not track.lyrics_plain:
            synced, plain = await self.lyrics.fetch_lyrics(track)
            if synced or plain:
                sources_used.append("lrclib")
                if synced and not track.lyrics_synced:
                    track.lyrics_synced = synced
                if plain and not track.lyrics_plain:
                    track.lyrics_plain = plain

        # 5. Optional Last.fm tags & ListenBrainz discovery
        if self.lastfm.is_configured() and track.artist and track.title:
            tags = await self.lastfm.get_track_tags(track.artist, track.title)
            if tags:
                sources_used.append("lastfm")
                track.lastfm_tags = ", ".join(tags)
                if not track.genres_raw:
                    track.genres_raw = ", ".join(tags[:4])

        if self.listenbrainz.is_configured() and track.musicbrainz_recording_id:
            similar_lb = await self.listenbrainz.get_similar_recordings(
                track.musicbrainz_recording_id, limit=5
            )
            if similar_lb:
                sources_used.append("listenbrainz")

        now = datetime.now(timezone.utc)
        track.metadata_enriched_at = now
        track.updated_at = now
        session.add(track)
        session.commit()
        session.refresh(track)

        return {
            "enriched": True,
            "skipped": False,
            "sources_used": sources_used,
            "track_id": track.id,
        }

    async def enrich_library(
        self,
        session_factory: Callable[[], Session],
        force: bool = False,
    ) -> dict[str, int]:
        """Enrich all tracks in the library asynchronously without blocking the event loop."""
        stats = {"total": 0, "enriched": 0, "skipped": 0, "failed": 0}
        with session_factory() as session:
            tracks = session.exec(select(UnifiedTrack)).all()
            track_ids = [t.id for t in tracks if t.id is not None]

        stats["total"] = len(track_ids)
        for tid in track_ids:
            with session_factory() as session:
                track = session.get(UnifiedTrack, tid)
                if not track:
                    continue
                try:
                    res = await self.enrich_track(track, session, force=force)
                    if res.get("enriched"):
                        stats["enriched"] += 1
                    else:
                        stats["skipped"] += 1
                except Exception as e:
                    print(f"[MetadataEnrichmentEngine] Failed track {tid}: {e}")
                    stats["failed"] += 1

        return stats
