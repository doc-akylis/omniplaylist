from pathlib import Path
from typing import Any
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.core.database import get_session, engine
from app.core.models import ExportConfig, Playlist, UnifiedTrack
from app.engines.exporter import PlaylistExporter
from app.engines.lyrics_engine import LyricsEngine
from app.engines.musical_analysis import MusicalAnalysisEngine
from app.engines.technical_analysis import TechnicalAnalysisEngine
from app.providers.deezer import DeezerProvider

router = APIRouter(prefix="/api", tags=["api"])
exporter = PlaylistExporter()
lyrics_engine = LyricsEngine()
deezer_provider = DeezerProvider()
tech_engine = TechnicalAnalysisEngine()
musical_engine = MusicalAnalysisEngine()


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
def list_tracks(offset: int = 0, limit: int = 50, session: Session = Depends(get_session)):
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
