import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
from typing import Any, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.config import get_settings
from app.core.database import get_session, engine
from app.core.models import ExportConfig, Playlist, UnifiedTrack
from app.engines.audio_analyzer import AudioAnalyzer
from app.engines.deduplicator import Deduplicator
from app.engines.dj_intelligence import DJIntelligenceEngine
from app.engines.exporter import PlaylistExporter
from app.engines.lyrics_engine import LyricsEngine
from app.engines.metadata_enrichment import MetadataEnrichmentEngine
from app.engines.musical_analysis import MusicalAnalysisEngine
from app.engines.technical_analysis import TechnicalAnalysisEngine
from app.providers.acoustid import AcoustIDProvider
from app.providers.deezer import DeezerProvider
from app.providers.itunes import ITunesProvider
from app.providers.lastfm import LastFMProvider
from app.providers.listenbrainz import ListenBrainzProvider
from app.providers.musicbrainz import MusicBrainzProvider

router = APIRouter(prefix="/api", tags=["api"])
exporter = PlaylistExporter()
lyrics_engine = LyricsEngine()
deezer_provider = DeezerProvider()
itunes_provider = ITunesProvider()
musicbrainz_provider = MusicBrainzProvider()
acoustid_provider = AcoustIDProvider()
lastfm_provider = LastFMProvider()
listenbrainz_provider = ListenBrainzProvider()
deduplicator = Deduplicator()
tech_engine = TechnicalAnalysisEngine()
musical_engine = MusicalAnalysisEngine()
enrichment_engine = MetadataEnrichmentEngine()
dj_intelligence = DJIntelligenceEngine()


class ConnectionManager:
    """Manages active WebSocket connections for progress events."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


ws_manager = ConnectionManager()


@router.websocket("/ws/progress")
async def websocket_progress_endpoint(websocket: WebSocket):
    """WebSocket endpoint streaming live sync, download, and matching events."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep alive and receive client signals
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@router.get("/tracks", response_model=list[UnifiedTrack])
def list_tracks(offset: int = 0, limit: int = 500, session: Session = Depends(get_session)):
    """Fetch stored tracks paginated."""
    return session.exec(select(UnifiedTrack).offset(offset).limit(limit)).all()


@router.get("/playlists", response_model=list[Playlist])
def list_playlists(session: Session = Depends(get_session)):
    """Fetch all playlists."""
    return session.exec(select(Playlist)).all()


@router.get("/playlists/{playlist_id}")
def get_playlist_details(playlist_id: int, session: Session = Depends(get_session)):
    """Get single playlist and its assigned tracks."""
    playlist = session.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"playlist": playlist, "tracks": playlist.tracks}


@router.post("/playlists/export")
def export_playlist(config: ExportConfig, session: Session = Depends(get_session)):
    """Trigger multi-format export for a given playlist."""
    playlist = session.get(Playlist, config.playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    file_path = exporter.export(playlist, playlist.tracks, config)
    return {
        "status": "success",
        "format": config.format,
        "exported_file": str(file_path),
    }


@router.get("/audio/stream/{track_id}")
def stream_audio(track_id: int, session: Session = Depends(get_session)):
    """Stream local audio file for playback in the NiceGUI player."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if not track.local_path or not Path(track.local_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not downloaded locally")

    file_path = Path(track.local_path)
    return FileResponse(
        path=file_path,
        media_type="audio/mpeg",
        filename=file_path.name,
    )


@router.get("/lyrics/{track_id}")
async def get_lyrics(track_id: int, session: Session = Depends(get_session)):
    """Get lyrics (synced LRC and plain text), fetching on-demand if missing."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    if not track.lyrics_synced and not track.lyrics_plain:
        synced, plain = await lyrics_engine.fetch_lyrics(track)
        if synced or plain:
            track.lyrics_synced = synced
            track.lyrics_plain = plain
            session.add(track)
            session.commit()
            session.refresh(track)

    return {
        "track_id": track.id,
        "title": track.title,
        "artist": track.artist,
        "synced": track.lyrics_synced,
        "plain": track.lyrics_plain,
    }


@router.get("/search/deezer")
async def search_deezer(q: str = Query(..., min_length=1), limit: int = 15):
    """Search Deezer catalog directly without requiring authentication."""
    tracks = await deezer_provider.search_tracks(query=q, limit=limit)
    return tracks


@router.post("/tracks/import_deezer/{deezer_id}")
async def import_deezer_track(deezer_id: str, session: Session = Depends(get_session)):
    """Import a track from Deezer directly into the local SQLite database."""
    track = await deezer_provider.get_track(deezer_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found on Deezer")

    # Check if already exists by ISRC or deezer_id
    existing = None
    if track.isrc:
        existing = session.exec(
            select(UnifiedTrack).where(UnifiedTrack.isrc == track.isrc)
        ).first()
    if not existing:
        existing = session.exec(
            select(UnifiedTrack).where(UnifiedTrack.deezer_id == str(deezer_id))
        ).first()

    if existing:
        return {"status": "already_exists", "track": existing}

    session.add(track)
    session.commit()
    session.refresh(track)
    return {"status": "imported", "track": track}


# ============ Technical Analysis Endpoints ============

@router.post("/tracks/{track_id}/analyze")
async def analyze_track(track_id: int, force: bool = False, session: Session = Depends(get_session)):
    """Dispara análise técnica sob demanda para uma faixa (FFmpeg/ffprobe single-pass)."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if not track.local_path or not Path(track.local_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not downloaded locally")

    result = await tech_engine.analyze_and_persist(track, session, force=force)
    return {"status": "success" if result else "skipped", "track_id": track_id, "analyzed": result}


@router.post("/library/analyze")
async def analyze_library(background: BackgroundTasks, force: bool = False):
    """Dispara análise técnica em background para toda a biblioteca com local_path."""
    async def run_analysis():
        stats = await tech_engine.analyze_library(
            session_factory=lambda: Session(engine),
            force=force,
        )
        await ws_manager.broadcast({
            "type": "analysis_complete",
            "stats": stats,
        })

    background.add_task(run_analysis)
    return {"status": "started", "message": "Análise técnica iniciada em background"}


@router.get("/tracks/{track_id}/technical")
def get_technical_info(track_id: int, session: Session = Depends(get_session)):
    """Retorna todas as métricas técnicas persistidas para uma faixa."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    return {
        "track_id": track.id,
        "title": track.title,
        "artist": track.artist,
        # FFprobe info
        "codec": track.codec,
        "bitrate_kbps": track.bitrate_kbps,
        "sample_rate_hz": track.sample_rate_hz,
        "bit_depth": track.bit_depth,
        "channels": track.channels,
        "file_size_bytes": track.file_size_bytes,
        "duration_ms": track.duration_ms,
        # Loudness (EBU R128)
        "integrated_lufs": track.integrated_lufs,
        "true_peak_dbfs": track.true_peak_dbfs,
        "momentary_lufs": track.momentary_lufs,
        "short_term_lufs": track.short_term_lufs,
        "loudness_range_lu": track.loudness_range_lu,
        # Dynamics
        "dynamic_range_db": track.dynamic_range_db,
        "crest_factor_db": track.crest_factor_db,
        "clipping_count": track.clipping_count,
        # Silence
        "silence_start_ms": track.silence_start_ms,
        "silence_end_ms": track.silence_end_ms,
        # ReplayGain
        "replay_gain": track.replay_gain,
        # Quality
        "is_corrupted": track.is_corrupted,
        "quality_warning": track.quality_warning,
        # Meta
        "analysis_version": track.analysis_version,
        "analyzed_at": track.analyzed_at,
    }


# ============ Musical Analysis Endpoints (DJ Mode 2.0) ============

@router.post("/tracks/{track_id}/analyze-musical")
async def analyze_track_musical(
    track_id: int, force: bool = False, session: Session = Depends(get_session)
):
    """Dispara análise musical prévia (BPM, beatgrid, Camelot, seções) em thread worker."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if not track.local_path or not Path(track.local_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not downloaded locally")

    result = await musical_engine.analyze_and_persist(track, session, force=force)
    return {
        "status": "success" if result else "skipped",
        "track_id": track_id,
        "analyzed": result,
        "bpm": track.bpm,
        "camelot_code": track.camelot_code,
        "energy": track.energy,
        "danceability": track.danceability,
    }


@router.post("/library/analyze-musical")
async def analyze_library_musical(background: BackgroundTasks, force: bool = False):
    """Dispara análise musical em background para toda a biblioteca com local_path."""
    async def run_musical_analysis():
        stats = await musical_engine.analyze_library(
            session_factory=lambda: Session(engine),
            force=force,
        )
        await ws_manager.broadcast({
            "type": "musical_analysis_complete",
            "stats": stats,
        })

    background.add_task(run_musical_analysis)
    return {"status": "started", "message": "Análise musical iniciada em background"}


@router.get("/tracks/{track_id}/dj-profile")
def get_dj_profile(track_id: int, session: Session = Depends(get_session)):
    """Retorna telemetria consolidada (metadados, análise técnica FFmpeg e musical Librosa) para o DJ Mode 2.0."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    return {
        "track": {
            "id": track.id,
            "title": track.title,
            "artist": track.artist,
            "album": track.album,
            "duration_ms": track.duration_ms,
            "cover_url": track.cover_url,
            "local_path": track.local_path,
        },
        "technical": {
            "source": "ffmpeg_ffprobe",
            "is_measured": track.analyzed_at is not None,
            "codec": track.codec,
            "bitrate_kbps": track.bitrate_kbps,
            "sample_rate_hz": track.sample_rate_hz,
            "bit_depth": track.bit_depth,
            "channels": track.channels,
            "integrated_lufs": track.integrated_lufs,
            "momentary_lufs": track.momentary_lufs,
            "short_term_lufs": track.short_term_lufs,
            "loudness_range_lu": track.loudness_range_lu,
            "true_peak_dbfs": track.true_peak_dbfs,
            "dynamic_range_db": track.dynamic_range_db,
            "crest_factor_db": track.crest_factor_db,
            "replay_gain": track.replay_gain,
            "clipping_count": track.clipping_count,
            "quality_warning": track.quality_warning,
            "analyzed_at": track.analyzed_at,
        },
        "musical": {
            "source": "librosa_krumhansl_schmuckler",
            "is_estimated": True,
            "confidence": track.musical_analysis_confidence,
            "bpm": track.bpm,
            "bpm_stability": track.bpm_stability,
            "key": track.key,
            "camelot_code": track.camelot_code,
            "energy": track.energy,
            "danceability": track.danceability,
            "beatgrid_json": track.beatgrid_json,
            "sections_json": track.sections_json,
            "musical_analyzed_at": track.musical_analyzed_at,
        },
    }


# ============ Metadata Enrichment & DJ Intelligence Endpoints ============

@router.post("/tracks/{track_id}/enrich")
async def enrich_track(
    track_id: int, force: bool = False, session: Session = Depends(get_session)
):
    """Enriquece metadados, capa HD, ISRC, letras LRCLIB e tags via cadeia de fallbacks."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    result = await enrichment_engine.enrich_track(track, session, force=force)
    return {
        **result,
        "track_id": track.id,
        "isrc": track.isrc,
        "musicbrainz_recording_id": track.musicbrainz_recording_id,
        "acoustid_id": track.acoustid_id,
        "hd_cover_url": track.hd_cover_url,
        "preview_url": track.preview_url,
        "release_year": track.release_year,
        "has_synced_lyrics": bool(track.lyrics_synced),
        "has_plain_lyrics": bool(track.lyrics_plain),
        "lastfm_tags": track.lastfm_tags,
        "metadata_enriched_at": track.metadata_enriched_at,
    }


@router.post("/library/enrich")
async def enrich_library(background: BackgroundTasks, force: bool = False):
    """Dispara enriquecimento de metadados em background para toda a biblioteca."""
    async def run_enrichment():
        stats = await enrichment_engine.enrich_library(
            session_factory=lambda: Session(engine),
            force=force,
        )
        await ws_manager.broadcast({
            "type": "enrichment_complete",
            "stats": stats,
        })

    background.add_task(run_enrichment)
    return {"status": "started", "message": "Enriquecimento de metadados iniciado em background"}


@router.get("/tracks/{track_id}/next-recommendations")
def get_next_track_recommendations(
    track_id: int,
    limit: int = Query(8, ge=1, le=25),
    session: Session = Depends(get_session),
):
    """Retorna recomendações ordenadas de próxima faixa (Camelot, BPM, energia e pontos de transição)."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    catalog = session.exec(select(UnifiedTrack)).all()
    recs = dj_intelligence.recommend_next_tracks(track, catalog, limit=limit)
    serialized = [
        {k: v for k, v in rec.items() if k != "track"}
        for rec in recs
    ]
    return {
        "track_id": track.id,
        "title": track.title,
        "artist": track.artist,
        "bpm": track.bpm,
        "camelot_code": track.camelot_code,
        "recommendations": serialized,
    }


# ============ Omnichannel Search, AcoustID, Discovery & Provider Health ============

class OnlineTrackImportRequest(BaseModel):
    """Payload to import an online track into the unified SQLite library."""

    title: str
    artist: str
    album: Optional[str] = None
    isrc: Optional[str] = None
    duration_ms: Optional[int] = None
    cover_url: Optional[str] = None
    hd_cover_url: Optional[str] = None
    preview_url: Optional[str] = None
    release_year: Optional[int] = None
    deezer_id: Optional[str] = None
    musicbrainz_recording_id: Optional[str] = None
    genres_raw: str = ""
    lyrics_synced: Optional[str] = None
    lyrics_plain: Optional[str] = None
    enrich: bool = True


class TrackUpdateRequest(BaseModel):
    """Editable track metadata fields (Beets-style manager)."""

    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    genres_raw: Optional[str] = None
    release_year: Optional[int] = None
    isrc: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    camelot_code: Optional[str] = None


class MergeDuplicatesRequest(BaseModel):
    """Merge duplicate track IDs into a primary track."""

    primary_id: int
    duplicate_ids: list[int]


class ProviderSettingsRequest(BaseModel):
    """Optional API keys persisted to .env."""

    LISTENBRAINZ_TOKEN: str = ""
    LASTFM_API_KEY: str = ""
    ACOUSTID_API_KEY: str = ""


def _norm_meta_key(artist: Optional[str], title: Optional[str]) -> str:
    a = re.sub(r"\W+", " ", (artist or "").lower()).strip()
    t = re.sub(r"\W+", " ", (title or "").lower()).strip()
    return f"{a}::{t}"


async def _safe_with_timeout(coro: Any, timeout: float = 4.0, default: Any = None) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except Exception:
        return default


@router.get("/search/omni")
async def omni_search(
    q: str = Query(..., min_length=1),
    mode: str = Query("all", pattern="^(all|local|online)$"),
    session: Session = Depends(get_session),
):
    """Simultaneous omnichannel search across Local SQLite, iTunes, Deezer, MusicBrainz+CAA, and LRCLIB."""
    query_clean = q.strip()
    query_lower = query_clean.lower()

    local_tracks = session.exec(select(UnifiedTrack)).all()
    local_by_isrc: dict[str, UnifiedTrack] = {
        t.isrc.strip().upper(): t for t in local_tracks if t.isrc
    }
    local_by_meta: dict[str, UnifiedTrack] = {
        _norm_meta_key(t.artist, t.title): t for t in local_tracks
    }

    local_hits: list[UnifiedTrack] = []
    if mode in ("all", "local"):
        for t in local_tracks:
            haystack = f"{t.title} {t.artist} {t.album or ''} {t.isrc or ''} {t.genres_raw}".lower()
            if query_lower in haystack:
                local_hits.append(t)

    itunes_hits: list[Any] = []
    deezer_hits: list[UnifiedTrack] = []
    mb_hits: list[Any] = []
    lrc_hits: list[dict[str, Any]] = []

    if mode in ("all", "online"):
        itunes_hits, deezer_hits, mb_hits, lrc_hits = await asyncio.gather(
            _safe_with_timeout(itunes_provider.search_tracks(query_clean, limit=8), 4.0, []),
            _safe_with_timeout(deezer_provider.search_tracks(query_clean, limit=8), 4.0, []),
            _safe_with_timeout(musicbrainz_provider.search_recordings(query_clean, limit=6), 4.0, []),
            _safe_with_timeout(lyrics_engine.search_lyrics(query_clean, limit=6), 4.0, []),
        )

    merged: dict[str, dict[str, Any]] = {}
    meta_to_merged_key: dict[str, str] = {}

    def _upsert(item: dict[str, Any]) -> None:
        isrc_key = f"isrc:{item['isrc'].strip().upper()}" if item.get("isrc") else None
        meta_key = f"meta:{_norm_meta_key(item.get('artist'), item.get('title'))}"

        existing_key = None
        if isrc_key and isrc_key in merged:
            existing_key = isrc_key
        elif meta_key in merged:
            existing_key = meta_key
        elif meta_key in meta_to_merged_key and meta_to_merged_key[meta_key] in merged:
            existing_key = meta_to_merged_key[meta_key]

        if existing_key:
            cur = merged[existing_key]
            for src in item.get("sources", []):
                if src not in cur["sources"]:
                    cur["sources"].append(src)
            for field in (
                "isrc",
                "album",
                "duration_ms",
                "hd_cover_url",
                "cover_url",
                "preview_url",
                "release_year",
                "deezer_id",
                "musicbrainz_recording_id",
                "lyrics_synced",
                "lyrics_plain",
                "genres_raw",
                "local_track_id",
                "bpm",
                "camelot_code",
            ):
                if not cur.get(field) and item.get(field):
                    cur[field] = item[field]
            cur["has_synced_lyrics"] = bool(cur.get("has_synced_lyrics") or item.get("has_synced_lyrics"))
            cur["in_library"] = bool(cur.get("in_library") or item.get("in_library"))
            if isrc_key and existing_key != isrc_key:
                merged[isrc_key] = merged.pop(existing_key)
                meta_to_merged_key[meta_key] = isrc_key
            else:
                meta_to_merged_key[meta_key] = existing_key
        else:
            key = isrc_key or meta_key
            merged[key] = item
            meta_to_merged_key[meta_key] = key

    # 1. Local hits
    for t in local_hits:
        _upsert(
            {
                "id": f"local-{t.id}",
                "local_track_id": t.id,
                "in_library": True,
                "title": t.title,
                "artist": t.artist,
                "album": t.album,
                "isrc": t.isrc,
                "duration_ms": t.duration_ms,
                "cover_url": t.cover_url,
                "hd_cover_url": t.hd_cover_url or t.cover_url,
                "preview_url": f"/api/audio/stream/{t.id}" if t.local_path else t.preview_url,
                "release_year": t.release_year,
                "deezer_id": t.deezer_id,
                "musicbrainz_recording_id": t.musicbrainz_recording_id,
                "genres_raw": t.genres_raw,
                "has_synced_lyrics": bool(t.lyrics_synced),
                "lyrics_synced": t.lyrics_synced,
                "lyrics_plain": t.lyrics_plain,
                "bpm": t.bpm,
                "camelot_code": t.camelot_code,
                "sources": ["local"],
            }
        )

    # 2. Deezer hits
    for d in deezer_hits or []:
        matched_local = (
            local_by_isrc.get(d.isrc.strip().upper()) if d.isrc else None
        ) or local_by_meta.get(_norm_meta_key(d.artist, d.title))
        _upsert(
            {
                "id": f"deezer-{d.deezer_id or _norm_meta_key(d.artist, d.title)}",
                "local_track_id": matched_local.id if matched_local else None,
                "in_library": matched_local is not None,
                "title": d.title,
                "artist": d.artist,
                "album": d.album,
                "isrc": d.isrc,
                "duration_ms": d.duration_ms,
                "cover_url": d.cover_url,
                "hd_cover_url": d.hd_cover_url or d.cover_url,
                "preview_url": d.preview_url,
                "release_year": d.release_year,
                "deezer_id": d.deezer_id,
                "musicbrainz_recording_id": None,
                "genres_raw": d.genres_raw,
                "has_synced_lyrics": bool(matched_local and matched_local.lyrics_synced),
                "lyrics_synced": matched_local.lyrics_synced if matched_local else None,
                "lyrics_plain": matched_local.lyrics_plain if matched_local else None,
                "bpm": d.bpm,
                "camelot_code": matched_local.camelot_code if matched_local else None,
                "sources": ["deezer"],
            }
        )

    # 3. iTunes hits
    for it in itunes_hits or []:
        if not it.title or not it.artist:
            continue
        matched_local = local_by_meta.get(_norm_meta_key(it.artist, it.title))
        _upsert(
            {
                "id": f"itunes-{_norm_meta_key(it.artist, it.title)}",
                "local_track_id": matched_local.id if matched_local else None,
                "in_library": matched_local is not None,
                "title": it.title,
                "artist": it.artist,
                "album": it.album,
                "isrc": None,
                "duration_ms": None,
                "cover_url": it.hd_cover_url,
                "hd_cover_url": it.hd_cover_url,
                "preview_url": it.preview_url,
                "release_year": it.release_year,
                "deezer_id": None,
                "musicbrainz_recording_id": None,
                "genres_raw": it.genre or "",
                "has_synced_lyrics": bool(matched_local and matched_local.lyrics_synced),
                "lyrics_synced": matched_local.lyrics_synced if matched_local else None,
                "lyrics_plain": matched_local.lyrics_plain if matched_local else None,
                "bpm": matched_local.bpm if matched_local else None,
                "camelot_code": matched_local.camelot_code if matched_local else None,
                "sources": ["itunes"],
            }
        )

    # 4. MusicBrainz + Cover Art Archive hits
    for mb in mb_hits or []:
        if not mb.title or not mb.artist:
            continue
        matched_local = (
            local_by_isrc.get(mb.isrc.strip().upper()) if mb.isrc else None
        ) or local_by_meta.get(_norm_meta_key(mb.artist, mb.title))
        mb_sources = ["musicbrainz"] + (["cover_art_archive"] if mb.hd_cover_url else [])
        _upsert(
            {
                "id": f"mb-{mb.recording_id or _norm_meta_key(mb.artist, mb.title)}",
                "local_track_id": matched_local.id if matched_local else None,
                "in_library": matched_local is not None,
                "title": mb.title,
                "artist": mb.artist,
                "album": mb.album,
                "isrc": mb.isrc,
                "duration_ms": None,
                "cover_url": mb.hd_cover_url,
                "hd_cover_url": mb.hd_cover_url,
                "preview_url": None,
                "release_year": mb.release_year,
                "deezer_id": None,
                "musicbrainz_recording_id": mb.recording_id,
                "genres_raw": "",
                "has_synced_lyrics": bool(matched_local and matched_local.lyrics_synced),
                "lyrics_synced": matched_local.lyrics_synced if matched_local else None,
                "lyrics_plain": matched_local.lyrics_plain if matched_local else None,
                "bpm": matched_local.bpm if matched_local else None,
                "camelot_code": matched_local.camelot_code if matched_local else None,
                "sources": mb_sources,
            }
        )

    # 5. LRCLIB hits
    for lrc in lrc_hits or []:
        l_title = lrc.get("trackName") or lrc.get("name")
        l_artist = lrc.get("artistName")
        if not l_title or not l_artist:
            continue
        matched_local = local_by_meta.get(_norm_meta_key(l_artist, l_title))
        synced = lrc.get("syncedLyrics")
        plain = lrc.get("plainLyrics")
        _upsert(
            {
                "id": f"lrclib-{lrc.get('id') or _norm_meta_key(l_artist, l_title)}",
                "local_track_id": matched_local.id if matched_local else None,
                "in_library": matched_local is not None,
                "title": l_title,
                "artist": l_artist,
                "album": lrc.get("albumName"),
                "isrc": None,
                "duration_ms": int(lrc["duration"] * 1000) if lrc.get("duration") else None,
                "cover_url": None,
                "hd_cover_url": None,
                "preview_url": None,
                "release_year": None,
                "deezer_id": None,
                "musicbrainz_recording_id": None,
                "genres_raw": "",
                "has_synced_lyrics": bool(synced),
                "lyrics_synced": synced,
                "lyrics_plain": plain,
                "bpm": matched_local.bpm if matched_local else None,
                "camelot_code": matched_local.camelot_code if matched_local else None,
                "sources": ["lrclib"],
            }
        )

    results = list(merged.values())
    results.sort(key=lambda x: (x.get("in_library", False), len(x.get("sources", []))), reverse=True)
    return {"query": query_clean, "mode": mode, "count": len(results), "results": results}


@router.post("/tracks/import-online")
async def import_online_track(
    payload: OnlineTrackImportRequest,
    session: Session = Depends(get_session),
):
    """Import an online track into UnifiedTrack and optionally trigger full cascade enrichment."""
    existing = None
    if payload.isrc:
        existing = session.exec(
            select(UnifiedTrack).where(UnifiedTrack.isrc == payload.isrc.strip().upper())
        ).first()
    if not existing and payload.deezer_id:
        existing = session.exec(
            select(UnifiedTrack).where(UnifiedTrack.deezer_id == payload.deezer_id)
        ).first()
    if not existing and payload.musicbrainz_recording_id:
        existing = session.exec(
            select(UnifiedTrack).where(
                UnifiedTrack.musicbrainz_recording_id == payload.musicbrainz_recording_id
            )
        ).first()
    if not existing:
        target_key = _norm_meta_key(payload.artist, payload.title)
        for t in session.exec(select(UnifiedTrack)).all():
            if _norm_meta_key(t.artist, t.title) == target_key:
                existing = t
                break

    if existing:
        track = existing
        status = "already_exists"
    else:
        track = UnifiedTrack(
            title=payload.title,
            artist=payload.artist,
            album=payload.album,
            isrc=payload.isrc.strip().upper() if payload.isrc else None,
            duration_ms=payload.duration_ms,
            cover_url=payload.cover_url or payload.hd_cover_url,
            hd_cover_url=payload.hd_cover_url or payload.cover_url,
            preview_url=payload.preview_url,
            release_year=payload.release_year,
            deezer_id=payload.deezer_id,
            musicbrainz_recording_id=payload.musicbrainz_recording_id,
            genres_raw=payload.genres_raw,
            lyrics_synced=payload.lyrics_synced,
            lyrics_plain=payload.lyrics_plain,
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        status = "imported"

    enrich_info = None
    if payload.enrich:
        enrich_info = await enrichment_engine.enrich_track(track, session, force=(status == "imported"))

    return {"status": status, "track": track, "enrichment": enrich_info}


@router.post("/tracks/{track_id}/identify-acoustid")
async def identify_track_acoustid(track_id: int, session: Session = Depends(get_session)):
    """Run on-demand AcoustID (fpcalc) acoustic fingerprint identification for a local track."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if not track.local_path or not Path(track.local_path).exists():
        raise HTTPException(status_code=404, detail="Audio file not available locally")

    if not acoustid_provider.is_available():
        return {
            "identified": False,
            "available": False,
            "reason": "ACOUSTID_API_KEY não configurada ou binário fpcalc não encontrado no PATH",
            "track_id": track_id,
        }

    match = await acoustid_provider.identify_file(Path(track.local_path))
    if not match:
        return {
            "identified": False,
            "available": True,
            "reason": "Nenhuma correspondência acústica encontrada no AcoustID",
            "track_id": track_id,
        }

    if match.acoustid_id:
        track.acoustid_id = match.acoustid_id
    if match.musicbrainz_recording_id and not track.musicbrainz_recording_id:
        track.musicbrainz_recording_id = match.musicbrainz_recording_id
    if match.title and track.title in ("", "Unknown", "Unknown Title"):
        track.title = match.title
    if match.artist and track.artist in ("", "Unknown", "Unknown Artist"):
        track.artist = match.artist
    track.updated_at = datetime.now(timezone.utc)
    session.add(track)
    session.commit()
    session.refresh(track)

    return {
        "identified": True,
        "available": True,
        "track_id": track.id,
        "acoustid_id": match.acoustid_id,
        "musicbrainz_recording_id": match.musicbrainz_recording_id,
        "title": match.title,
        "artist": match.artist,
        "score": match.score,
    }


@router.get("/discovery/recommendations")
async def get_discovery_recommendations(
    track_id: Optional[int] = None,
    limit: int = Query(10, ge=1, le=25),
    session: Session = Depends(get_session),
):
    """Combine DJIntelligenceEngine, Last.fm, and ListenBrainz for harmonic + online discovery."""
    catalog = session.exec(select(UnifiedTrack)).all()
    if not catalog:
        return {"seed_track": None, "local_dj_recommendations": [], "lastfm_similar": [], "listenbrainz_similar": [], "tags": []}

    seed = session.get(UnifiedTrack, track_id) if track_id else catalog[0]
    if not seed:
        raise HTTPException(status_code=404, detail="Seed track not found")

    dj_recs = dj_intelligence.recommend_next_tracks(seed, catalog, limit=limit)
    local_serialized = [{k: v for k, v in r.items() if k != "track"} for r in dj_recs]

    lfm = LastFMProvider()
    lb = ListenBrainzProvider()
    lastfm_similar, lastfm_tags, lb_similar = await asyncio.gather(
        _safe_with_timeout(lfm.get_similar_tracks(seed.artist, seed.title, limit=limit), 4.0, []),
        _safe_with_timeout(lfm.get_track_tags(seed.artist, seed.title, limit=10), 4.0, []),
        _safe_with_timeout(
            lb.get_similar_recordings(seed.musicbrainz_recording_id or "", limit=limit), 4.0, []
        ),
    )

    return {
        "seed_track": {
            "id": seed.id,
            "title": seed.title,
            "artist": seed.artist,
            "bpm": seed.bpm,
            "camelot_code": seed.camelot_code,
            "musicbrainz_recording_id": seed.musicbrainz_recording_id,
        },
        "local_dj_recommendations": local_serialized,
        "lastfm_similar": lastfm_similar or [],
        "listenbrainz_similar": lb_similar or [],
        "tags": lastfm_tags or ([t.strip() for t in (seed.lastfm_tags or "").split(",") if t.strip()]),
    }


@router.get("/health/providers")
def get_providers_health():
    """Report live readiness of all 8 metadata/discovery APIs plus FFmpeg and Librosa."""
    cfg = get_settings()
    fpcalc_path = shutil.which("fpcalc")
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    try:
        import librosa
        librosa_ver = getattr(librosa, "__version__", "installed")
    except Exception:
        librosa_ver = None

    has_lb = bool(cfg.LISTENBRAINZ_TOKEN and cfg.LISTENBRAINZ_TOKEN.strip())
    has_lfm = bool(cfg.LASTFM_API_KEY and cfg.LASTFM_API_KEY.strip())
    has_ac = bool(cfg.ACOUSTID_API_KEY and cfg.ACOUSTID_API_KEY.strip())

    providers = [
        {"id": "musicbrainz", "name": "MusicBrainz", "requires_key": False, "status": "active", "detail": "Rate limit estrito 1 req/s + User-Agent"},
        {"id": "cover_art_archive", "name": "Cover Art Archive", "requires_key": False, "status": "active", "detail": "Capas HD oficiais sem chave"},
        {"id": "lrclib", "name": "LRCLIB", "requires_key": False, "status": "active", "detail": "Letras sincronizadas (.lrc) e simples"},
        {"id": "itunes", "name": "iTunes Search API", "requires_key": False, "status": "active", "detail": "Capas 1400x1400 e prévias AAC 30s"},
        {"id": "deezer", "name": "Deezer API", "requires_key": False, "status": "active", "detail": "ISRC, BPM de catálogo e prévias 30s"},
        {
            "id": "listenbrainz",
            "name": "ListenBrainz",
            "requires_key": True,
            "status": "active" if has_lb else "optional_unconfigured",
            "configured": has_lb,
            "detail": "Token configurado" if has_lb else "Opcional — configure LISTENBRAINZ_TOKEN",
        },
        {
            "id": "lastfm",
            "name": "Last.fm",
            "requires_key": True,
            "status": "active" if has_lfm else "optional_unconfigured",
            "configured": has_lfm,
            "detail": "API Key configurada" if has_lfm else "Opcional — configure LASTFM_API_KEY",
        },
        {
            "id": "acoustid",
            "name": "AcoustID (fpcalc)",
            "requires_key": True,
            "status": "active" if (has_ac and fpcalc_path) else ("missing_fpcalc" if has_ac else "optional_unconfigured"),
            "configured": has_ac,
            "fpcalc_installed": bool(fpcalc_path),
            "detail": (
                "Chave + fpcalc prontos"
                if (has_ac and fpcalc_path)
                else ("Chave configurada, mas fpcalc ausente no PATH" if has_ac else "Opcional — configure ACOUSTID_API_KEY")
            ),
        },
    ]

    return {
        "providers": providers,
        "engines": {
            "ffmpeg": bool(ffmpeg_path),
            "ffprobe": bool(ffprobe_path),
            "librosa": librosa_ver,
        },
    }


@router.get("/library/duplicates")
def get_library_duplicates(session: Session = Depends(get_session)):
    """Detect duplicate track clusters by ISRC and fuzzy metadata (Beets-style manager)."""
    tracks = session.exec(select(UnifiedTrack)).all()
    groups = deduplicator.find_duplicate_groups(tracks)
    return {
        "total_tracks": len(tracks),
        "duplicate_groups": [
            {
                "primary": g["primary"],
                "candidates": g["candidates"],
                "count": g["count"],
            }
            for g in groups
        ],
    }


@router.post("/library/merge-duplicates")
def merge_library_duplicates(
    payload: MergeDuplicatesRequest, session: Session = Depends(get_session)
):
    """Merge selected duplicate tracks into a primary UnifiedTrack."""
    primary = session.get(UnifiedTrack, payload.primary_id)
    if not primary:
        raise HTTPException(status_code=404, detail="Primary track not found")

    dups = [session.get(UnifiedTrack, did) for did in payload.duplicate_ids]
    valid_dups = [d for d in dups if d is not None and d.id != primary.id]
    if not valid_dups:
        return {"merged": 0, "primary_id": primary.id}

    merged = deduplicator.merge_tracks(primary, valid_dups, session)
    return {"merged": len(valid_dups), "primary": merged}


@router.patch("/tracks/{track_id}", response_model=UnifiedTrack)
def update_track_metadata(
    track_id: int, payload: TrackUpdateRequest, session: Session = Depends(get_session)
):
    """Update editable metadata fields on a UnifiedTrack (Beets-style edit)."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(track, k, v)
    if "key" in data and data["key"] and not data.get("camelot_code"):
        track.camelot_code = AudioAnalyzer.normalize_to_camelot(data["key"])
    track.updated_at = datetime.now(timezone.utc)
    session.add(track)
    session.commit()
    session.refresh(track)
    return track


@router.post("/settings/providers")
def save_provider_settings(payload: ProviderSettingsRequest):
    """Persist optional API keys to .env and refresh cached Settings."""
    env_path = Path(".env")
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    updates = {
        "LISTENBRAINZ_TOKEN": payload.LISTENBRAINZ_TOKEN.strip(),
        "LASTFM_API_KEY": payload.LASTFM_API_KEY.strip(),
        "ACOUSTID_API_KEY": payload.ACOUSTID_API_KEY.strip(),
    }

    seen: set[str] = set()
    new_lines: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        replaced = False
        for k, v in updates.items():
            if stripped.startswith(f"{k}="):
                new_lines.append(f"{k}={v}")
                seen.add(k)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for k, v in updates.items():
        if k not in seen:
            new_lines.append(f"{k}={v}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    get_settings.cache_clear()

    # Refresh module-level singletons
    global acoustid_provider, lastfm_provider, listenbrainz_provider
    acoustid_provider = AcoustIDProvider(api_key=updates["ACOUSTID_API_KEY"])
    lastfm_provider = LastFMProvider(api_key=updates["LASTFM_API_KEY"])
    listenbrainz_provider = ListenBrainzProvider(token=updates["LISTENBRAINZ_TOKEN"])
    enrichment_engine.acoustid = acoustid_provider
    enrichment_engine.lastfm = lastfm_provider
    enrichment_engine.listenbrainz = listenbrainz_provider

    return {"status": "saved", "health": get_providers_health()}
