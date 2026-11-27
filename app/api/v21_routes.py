from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.routes import dj_intelligence, engine, tech_engine, ws_manager
from app.core.database import get_session
from app.core.models import (
    AudioProvenance,
    DownloadJob,
    ExportFormat,
    Playlist,
    UnifiedTrack,
)
from app.engines.audio_quality_intelligence import AudioQualityIntelligenceEngine
from app.engines.conversion_engine import AUDIO_PROFILES
from app.engines.dj_intelligence import SequencerConfig
from app.engines.download_studio import DownloadStudioEngine
from app.engines.exporter import PlaylistExporter
from app.engines.playlist_manager import PlaylistManagerEngine
from app.engines.upgrade_engine import CandidateSource, UpgradeEngine

router = APIRouter(prefix="/api", tags=["v2.1"])


async def _broadcast_ws(message: dict[str, Any]) -> None:
    await ws_manager.broadcast(message)


quality_engine = AudioQualityIntelligenceEngine(tech_engine=tech_engine)
upgrade_engine = UpgradeEngine()
download_studio = DownloadStudioEngine(
    tech_engine=tech_engine,
    quality_engine=quality_engine,
    upgrade_engine=upgrade_engine,
    ws_broadcast=_broadcast_ws,
)
playlist_manager = PlaylistManagerEngine()
playlist_exporter = PlaylistExporter()


# ============ Request Schemas ============

class UpgradeCheckRequest(BaseModel):
    track_id: Optional[int] = None
    candidate: CandidateSource
    profile: str = "ORIGINAL"


class EnqueueDownloadRequest(BaseModel):
    track_id: Optional[int] = None
    candidate: CandidateSource
    profile: str = "ORIGINAL"
    target_sample_rate_hz: Optional[int] = None
    allow_downgrade_or_same: bool = False


class PlaylistCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    cover_url: Optional[str] = None
    track_ids: list[int] = []


class PlaylistUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None


class PlaylistDuplicateRequest(BaseModel):
    name: Optional[str] = None


class PlaylistTracksModifyRequest(BaseModel):
    track_ids: list[int]


class PlaylistReorderRequest(BaseModel):
    ordered_track_ids: list[int]


class PlaylistSortRequest(BaseModel):
    sort_by: str
    persist: bool = True


class PlaylistExportM3URequest(BaseModel):
    format: ExportFormat = ExportFormat.M3U8
    output_directory: Optional[str] = None


class SequenceApplyRequest(BaseModel):
    ordered_track_ids: list[int]


class TransitionAnalysisRequest(BaseModel):
    track_a_id: int
    track_b_id: int
    deck_a_pitch: float = 1.0
    deck_b_pitch: float = 1.0


# ============ Phase 1 & 6: Audio Quality Intelligence & Dashboard ============

@router.post("/tracks/{track_id}/analyze-quality")
async def analyze_track_quality(
    track_id: int, force: bool = False, session: Session = Depends(get_session)
):
    """Run unified Audio Quality Intelligence (FFmpeg + STFT fake upscale + provenance + Car Audio score)."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return await quality_engine.analyze_track_quality(track, session, force=force)


@router.post("/library/analyze-quality")
async def analyze_library_quality(background: BackgroundTasks, force: bool = False):
    """Trigger background Audio Quality Intelligence analysis across the library."""
    async def _run():
        stats = await quality_engine.analyze_library_quality(
            session_factory=lambda: Session(engine),
            force=force,
        )
        await ws_manager.broadcast({"type": "quality_analysis_complete", "stats": stats})

    background.add_task(_run)
    return {"status": "started", "message": "Análise de qualidade v2.1 iniciada em background."}


@router.get("/tracks/{track_id}/quality")
def get_track_quality(track_id: int, session: Session = Depends(get_session)):
    """Return structured quality metrics, provenance, and processing history for a track."""
    track = session.get(UnifiedTrack, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return quality_engine.build_quality_report(track, session)


@router.get("/quality/dashboard")
def get_quality_dashboard(session: Session = Depends(get_session)):
    """Return aggregated real quality metrics and distributions across the library."""
    return quality_engine.get_quality_dashboard(session)


@router.get("/tracks/compare")
def compare_tracks_ab(
    track_a_id: int = Query(...),
    track_b_id: int = Query(...),
    session: Session = Depends(get_session),
):
    """Compare two track versions (A vs B) across codec, loudness, cutoff, clipping, and provenance."""
    track_a = session.get(UnifiedTrack, track_a_id)
    track_b = session.get(UnifiedTrack, track_b_id)
    if not track_a or not track_b:
        raise HTTPException(status_code=404, detail="One or both tracks not found")
    prov_a = session.exec(select(AudioProvenance).where(AudioProvenance.track_id == track_a_id)).first()
    prov_b = session.exec(select(AudioProvenance).where(AudioProvenance.track_id == track_b_id)).first()
    return dj_intelligence.compare_track_versions(track_a, track_b, prov_a, prov_b)


# ============ Phase 2: Download Studio, Queue, Conversion & Upgrade Engine ============

@router.get("/downloads/profiles")
def list_audio_profiles():
    """Return supported Download Studio conversion profiles."""
    return {"profiles": list(AUDIO_PROFILES.values())}


@router.post("/downloads/check-upgrade")
def check_upgrade(payload: UpgradeCheckRequest, session: Session = Depends(get_session)):
    """Evaluate UpgradeEngine decision before queuing a download/conversion job."""
    track = session.get(UnifiedTrack, payload.track_id) if payload.track_id else None
    prov = (
        session.exec(select(AudioProvenance).where(AudioProvenance.track_id == payload.track_id)).first()
        if payload.track_id
        else None
    )
    ev = upgrade_engine.evaluate_upgrade(
        existing_track=track,
        candidate=payload.candidate,
        requested_profile=payload.profile,
        existing_provenance=prov,
    )
    return {
        "decision": ev.decision,
        "is_justified": ev.is_justified,
        "reason": ev.reason,
        "warnings": ev.warnings,
        "existing_rank": ev.existing_rank,
        "candidate_rank": ev.candidate_rank,
    }


@router.post("/downloads/jobs")
async def enqueue_download_job(
    payload: EnqueueDownloadRequest,
    session: Session = Depends(get_session),
):
    """Create persistent DownloadJob and launch background acquisition/conversion pipeline."""
    job = download_studio.enqueue_job(
        session=session,
        track_id=payload.track_id,
        candidate=payload.candidate,
        profile=payload.profile,
        target_sample_rate_hz=payload.target_sample_rate_hz,
        allow_downgrade_or_same=payload.allow_downgrade_or_same,
    )
    if job.status == "QUEUED" and job.id is not None:
        download_studio.start_job_background(job.id, lambda: Session(engine))
    return job


@router.get("/downloads/jobs")
def list_download_jobs(limit: int = 50, session: Session = Depends(get_session)):
    """List persistent Download Studio jobs ordered newest first."""
    jobs = session.exec(
        select(DownloadJob).order_by(DownloadJob.created_at.desc()).limit(limit)
    ).all()
    return {"jobs": jobs}


@router.get("/downloads/jobs/{job_id}")
def get_download_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


@router.post("/downloads/jobs/{job_id}/cancel")
def cancel_download_job(job_id: int, session: Session = Depends(get_session)):
    job = download_studio.cancel_job(job_id, session)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


@router.post("/downloads/jobs/{job_id}/pause")
def pause_download_job(job_id: int, session: Session = Depends(get_session)):
    job = download_studio.pause_job(job_id, session)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


@router.post("/downloads/jobs/{job_id}/resume")
def resume_download_job(job_id: int, session: Session = Depends(get_session)):
    job = download_studio.resume_job(job_id, session)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


@router.post("/downloads/jobs/{job_id}/retry")
async def retry_download_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(DownloadJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    job.status = "QUEUED"
    job.current_stage = "RETRY_QUEUED"
    job.error_message = None
    job.attempts = 0
    job.progress = 0.0
    session.add(job)
    session.commit()
    session.refresh(job)
    download_studio.start_job_background(job.id, lambda: Session(engine))
    return job


# ============ Phase 3 & 4: Playlist Manager & Smart Sequencer ============

@router.post("/playlists", response_model=Playlist)
def create_playlist(payload: PlaylistCreateRequest, session: Session = Depends(get_session)):
    return playlist_manager.create_playlist(
        session=session,
        name=payload.name,
        description=payload.description,
        cover_url=payload.cover_url,
        track_ids=payload.track_ids,
    )


@router.patch("/playlists/{playlist_id}", response_model=Playlist)
def update_playlist(
    playlist_id: int, payload: PlaylistUpdateRequest, session: Session = Depends(get_session)
):
    pl = playlist_manager.update_playlist(
        session=session,
        playlist_id=playlist_id,
        name=payload.name,
        description=payload.description,
        cover_url=payload.cover_url,
    )
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return pl


@router.delete("/playlists/{playlist_id}")
def delete_playlist(playlist_id: int, session: Session = Depends(get_session)):
    ok = playlist_manager.delete_playlist(session, playlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"deleted": True, "playlist_id": playlist_id}


@router.post("/playlists/{playlist_id}/duplicate", response_model=Playlist)
def duplicate_playlist(
    playlist_id: int,
    payload: Optional[PlaylistDuplicateRequest] = None,
    session: Session = Depends(get_session),
):
    dup = playlist_manager.duplicate_playlist(
        session, playlist_id, new_name=payload.name if payload else None
    )
    if not dup:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return dup


@router.get("/playlists/{playlist_id}/details")
def get_playlist_full_details(
    playlist_id: int,
    status_filter: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Return ordered tracks, per-track quality status flags, and real playlist metrics."""
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    tracks = playlist_manager.get_ordered_tracks(session, playlist_id)
    metrics = playlist_manager.compute_playlist_metrics(tracks)

    track_entries = []
    for idx, t in enumerate(tracks):
        statuses = playlist_manager.classify_track_status(t)
        if status_filter and status_filter != "ALL" and status_filter not in statuses:
            continue
        track_entries.append(
            {
                "position": idx,
                "track": t,
                "quality_statuses": statuses,
            }
        )

    return {
        "playlist": pl,
        "metrics": metrics,
        "tracks": track_entries,
        "has_original_order_snapshot": bool(pl.original_order_json),
    }


@router.post("/playlists/{playlist_id}/tracks")
def add_tracks_to_playlist(
    playlist_id: int, payload: PlaylistTracksModifyRequest, session: Session = Depends(get_session)
):
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    added = playlist_manager.add_tracks(session, playlist_id, payload.track_ids)
    return {"added": added, "playlist_id": playlist_id}


@router.delete("/playlists/{playlist_id}/tracks")
def remove_tracks_from_playlist(
    playlist_id: int, payload: PlaylistTracksModifyRequest, session: Session = Depends(get_session)
):
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    removed = playlist_manager.remove_tracks(session, playlist_id, payload.track_ids)
    return {"removed": removed, "playlist_id": playlist_id}


@router.put("/playlists/{playlist_id}/reorder")
def reorder_playlist_tracks(
    playlist_id: int, payload: PlaylistReorderRequest, session: Session = Depends(get_session)
):
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    ordered = playlist_manager.reorder_tracks(session, playlist_id, payload.ordered_track_ids)
    return {"playlist_id": playlist_id, "count": len(ordered)}


@router.post("/playlists/{playlist_id}/sort")
def sort_playlist_tracks(
    playlist_id: int, payload: PlaylistSortRequest, session: Session = Depends(get_session)
):
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    ordered = playlist_manager.sort_playlist(
        session, playlist_id, sort_by=payload.sort_by, persist=payload.persist
    )
    return {"playlist_id": playlist_id, "sort_by": payload.sort_by, "tracks": ordered}


@router.post("/playlists/{playlist_id}/export-m3u")
def export_playlist_m3u(
    playlist_id: int,
    payload: Optional[PlaylistExportM3URequest] = None,
    session: Session = Depends(get_session),
):
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    tracks = playlist_manager.get_ordered_tracks(session, playlist_id)
    fmt = payload.format if payload else ExportFormat.M3U8
    out_dir = Path(payload.output_directory) if (payload and payload.output_directory) else None
    return playlist_exporter.export_m3u_with_report(pl, tracks, output_dir=out_dir, fmt=fmt)


@router.post("/playlists/{playlist_id}/sequence/preview")
def preview_smart_sequence(
    playlist_id: int,
    config: Optional[SequencerConfig] = None,
    session: Session = Depends(get_session),
):
    pl = session.get(Playlist, playlist_id)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    tracks = playlist_manager.get_ordered_tracks(session, playlist_id)
    return dj_intelligence.generate_sequence(tracks, config)


@router.post("/playlists/{playlist_id}/sequence/apply")
def apply_smart_sequence(
    playlist_id: int, payload: SequenceApplyRequest, session: Session = Depends(get_session)
):
    pl = dj_intelligence.apply_sequence_to_playlist(session, playlist_id, payload.ordered_track_ids)
    if not pl:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"applied": True, "playlist_id": playlist_id, "can_restore": bool(pl.original_order_json)}


@router.post("/playlists/{playlist_id}/sequence/restore")
def restore_smart_sequence(playlist_id: int, session: Session = Depends(get_session)):
    ok, orig_ids = dj_intelligence.restore_playlist_order(session, playlist_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No saved original order found for this playlist")
    return {"restored": True, "playlist_id": playlist_id, "ordered_track_ids": orig_ids}


# ============ Phase 5: DJ Technical Analyzer ============

@router.post("/dj/transition-analysis")
def analyze_dj_transition(
    payload: TransitionAnalysisRequest, session: Session = Depends(get_session)
):
    """Analyze Deck A -> Deck B transition risks, bass overlap, clipping estimate, and EQ Assist."""
    track_a = session.get(UnifiedTrack, payload.track_a_id)
    track_b = session.get(UnifiedTrack, payload.track_b_id)
    if not track_a or not track_b:
        raise HTTPException(status_code=404, detail="Track A or Track B not found")
    return dj_intelligence.analyze_transition(
        track_a,
        track_b,
        deck_a_pitch=payload.deck_a_pitch,
        deck_b_pitch=payload.deck_b_pitch,
    )
