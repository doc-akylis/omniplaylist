"""Unified automatic & manual multi-source acquisition orchestrator with commercial approval gating."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Callable, Optional

from sqlmodel import Session, select

from app.core.models import AcquisitionRecord, DownloadJob, UnifiedTrack
from app.engines.download_studio import DownloadStudioEngine
from app.engines.music_search_engine import MusicSearchEngine
from app.engines.source_quality_comparator import (
    CandidateScoreBreakdown,
    SourceComparisonResult,
    SourceQualityComparator,
)
from app.engines.upgrade_engine import CandidateSource
from app.sources.base import GroupedRecording, NormalizedTrackResult, PermissionStatus


class AcquisitionEngine:
    """Selects best authorized source per recording, gates commercial spend, and enqueues DownloadStudioEngine jobs."""

    MODES = {
        "AUTO_BEST_SOURCE",
        "ASK_BEFORE_PAID",
        "FREE_AUTHORIZED_ONLY",
        "MANUAL_SOURCE_SELECTION",
    }

    def __init__(
        self,
        search_engine: Optional[MusicSearchEngine] = None,
        comparator: Optional[SourceQualityComparator] = None,
        download_studio: Optional[DownloadStudioEngine] = None,
    ):
        self.search_engine = search_engine or MusicSearchEngine()
        self.comparator = comparator or SourceQualityComparator()
        self.download_studio = download_studio or DownloadStudioEngine()

    def _select_candidate(
        self,
        group: GroupedRecording,
        comparison: SourceComparisonResult,
        mode: str,
        preferred_provider_id: Optional[str] = None,
        preferred_source_item_id: Optional[str] = None,
    ) -> tuple[Optional[NormalizedTrackResult], Optional[CandidateScoreBreakdown], str]:
        """Apply policy mode to pick an authorized candidate or explain why none is available."""
        mode_norm = (mode or "ASK_BEFORE_PAID").upper()

        if mode_norm == "MANUAL_SOURCE_SELECTION":
            if not preferred_provider_id:
                return None, None, "Modo manual exige provider_id selecionado."
            for c in group.candidates:
                if c.provider_id == preferred_provider_id and (
                    not preferred_source_item_id or c.source_item_id == preferred_source_item_id
                ):
                    if not self.comparator.is_candidate_downloadable(c):
                        return (
                            None,
                            None,
                            c.permission.reason
                            or f"Fonte '{c.provider_name}' não autoriza download do arquivo completo ({c.permission.status.value}).",
                        )
                    bd = next(
                        (
                            b
                            for b in comparison.ranked_candidates
                            if b.provider_id == c.provider_id and b.source_item_id == c.source_item_id
                        ),
                        None,
                    )
                    return c, bd, f"Fonte manual autorizada selecionada: {c.provider_name}."
            return None, None, f"Candidato '{preferred_provider_id}' não encontrado neste grupo."

        if mode_norm == "FREE_AUTHORIZED_ONLY":
            if not comparison.best_free:
                return (
                    None,
                    None,
                    "Nenhuma fonte gratuita com download autorizado direto encontrada (apenas prévia, catálogo ou comercial).",
                )
            bd = comparison.best_free
            cand = next(
                (
                    c
                    for c in group.candidates
                    if c.provider_id == bd.provider_id and c.source_item_id == bd.source_item_id
                ),
                None,
            )
            return cand, bd, f"Selecionada melhor fonte gratuita autorizada: {bd.provider_name}."

        if mode_norm == "ASK_BEFORE_PAID":
            if comparison.best_free:
                bd = comparison.best_free
                cand = next(
                    (
                        c
                        for c in group.candidates
                        if c.provider_id == bd.provider_id and c.source_item_id == bd.source_item_id
                    ),
                    None,
                )
                return cand, bd, f"Priorizada fonte gratuita autorizada: {bd.provider_name}."
            if comparison.best_commercial:
                bd = comparison.best_commercial
                cand = next(
                    (
                        c
                        for c in group.candidates
                        if c.provider_id == bd.provider_id and c.source_item_id == bd.source_item_id
                    ),
                    None,
                )
                return (
                    cand,
                    bd,
                    f"Entrega comercial disponível via {bd.provider_name} ({bd.estimated_cost_label or 'paga'}); requer aprovação do usuário.",
                )
            return None, None, comparison.selection_reason

        # AUTO_BEST_SOURCE: pick highest-ranked downloadable overall (still gated if commercial)
        if comparison.best_authorized:
            bd = comparison.best_authorized
            cand = next(
                (
                    c
                    for c in group.candidates
                    if c.provider_id == bd.provider_id and c.source_item_id == bd.source_item_id
                ),
                None,
            )
            return cand, bd, comparison.selection_reason

        return None, None, comparison.selection_reason

    def _upsert_metadata_track(
        self,
        session: Session,
        group: GroupedRecording,
        cand: NormalizedTrackResult,
        existing_track_id: Optional[int] = None,
    ) -> UnifiedTrack:
        """Attach discovery metadata to an existing UnifiedTrack or create a metadata entry cleanly."""
        if existing_track_id:
            track = session.get(UnifiedTrack, existing_track_id)
            if track:
                if not track.album and (cand.album or group.album):
                    track.album = cand.album or group.album
                if not track.isrc and (cand.isrc or group.isrc):
                    track.isrc = cand.isrc or group.isrc
                if not track.musicbrainz_recording_id and (cand.mbid or group.mbid):
                    track.musicbrainz_recording_id = cand.mbid or group.mbid
                if not track.hd_cover_url and (cand.cover_url or group.cover_url):
                    track.hd_cover_url = cand.cover_url or group.cover_url
                if not track.release_year and cand.release_year:
                    track.release_year = cand.release_year
                session.add(track)
                session.commit()
                session.refresh(track)
                return track

        track = UnifiedTrack(
            title=cand.title or group.title,
            artist=cand.artist or group.artist,
            album=cand.album or group.album,
            duration_ms=cand.duration_ms or group.duration_ms,
            isrc=cand.isrc or group.isrc,
            musicbrainz_recording_id=cand.mbid or group.mbid,
            release_year=cand.release_year,
            hd_cover_url=cand.cover_url or group.cover_url,
            preview_url=cand.preview_url or group.candidates[0].preview_url if group.candidates else None,
            is_preview=False,
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        return track

    async def acquire_from_group(
        self,
        group: GroupedRecording,
        session: Session,
        mode: str = "ASK_BEFORE_PAID",
        profile: str = "ORIGINAL",
        target_sample_rate_hz: Optional[int] = None,
        track_id: Optional[int] = None,
        preferred_provider_id: Optional[str] = None,
        preferred_source_item_id: Optional[str] = None,
        allow_downgrade_or_same: bool = False,
        session_factory: Optional[Callable[[], Session]] = None,
        execute_now: bool = False,
    ) -> dict[str, Any]:
        """Compare a recording group, select authorized source, gate paid delivery, and enqueue job."""
        comparison = self.comparator.compare_group(group)
        cand, breakdown, reason = self._select_candidate(
            group=group,
            comparison=comparison,
            mode=mode,
            preferred_provider_id=preferred_provider_id,
            preferred_source_item_id=preferred_source_item_id,
        )

        if cand is None or breakdown is None:
            summary_payload = {
                "group_key": group.group_key,
                "query": f"{group.artist} - {group.title}",
                "reason": reason,
                "comparison": comparison.model_dump(mode="json"),
            }
            record = AcquisitionRecord(
                track_id=track_id,
                provider_id=preferred_provider_id or "none",
                source_item_id=preferred_source_item_id,
                acquisition_mode=mode.upper(),
                status="UNAVAILABLE",
                comparison_summary_json=json.dumps(summary_payload, ensure_ascii=False),
                error_message=reason,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return {
                "accepted": False,
                "status": "UNAVAILABLE",
                "reason": reason,
                "job": None,
                "record": record.model_dump(mode="json"),
                "comparison": comparison.model_dump(mode="json"),
            }

        is_commercial = cand.permission.status == PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL or cand.requires_payment
        requires_approval = bool(is_commercial)

        target_track = self._upsert_metadata_track(
            session=session,
            group=group,
            cand=cand,
            existing_track_id=track_id,
        )

        cand_src = CandidateSource(
            provider=cand.provider_id,
            title=cand.title,
            artist=cand.artist,
            codec=cand.declared_codec,
            bitrate_kbps=cand.declared_bitrate_kbps,
            sample_rate_hz=cand.declared_sample_rate_hz,
            bit_depth=cand.declared_bit_depth,
            origin_classification=cand.origin_classification,
            is_preview=False,
            source_url=cand.download_url,
            source_label=f"{cand.artist} - {cand.title} ({cand.provider_name})",
        )

        job = self.download_studio.enqueue_job(
            session=session,
            track_id=target_track.id,
            candidate=cand_src,
            profile=profile,
            target_sample_rate_hz=target_sample_rate_hz,
            allow_downgrade_or_same=allow_downgrade_or_same,
            source_item_id=cand.source_item_id,
            acquisition_mode=mode.upper(),
            requires_approval=requires_approval,
            approved_by_user=False,
            estimated_cost_label=cand.estimated_cost_label or cand.permission.estimated_cost_label,
            license_info=cand.license_info or cand.permission.license_name,
        )

        rec_status = (
            "AWAITING_APPROVAL"
            if job.status == "AWAITING_APPROVAL"
            else ("FAILED" if job.status == "FAILED" else "QUEUED")
        )
        summary_payload = {
            "group_key": group.group_key,
            "query": f"{group.artist} - {group.title}",
            "reason": reason,
            "estimated_cost_label": job.estimated_cost_label,
            "comparison": comparison.model_dump(mode="json"),
        }
        record = AcquisitionRecord(
            track_id=target_track.id,
            download_job_id=job.id,
            provider_id=cand.provider_id,
            source_item_id=cand.source_item_id,
            acquisition_mode=mode.upper(),
            was_paid=is_commercial,
            approved_by_user=False,
            license_info=job.license_info,
            comparison_summary_json=json.dumps(summary_payload, ensure_ascii=False),
            status=rec_status,
            error_message=job.error_message,
        )
        session.add(record)
        session.commit()
        session.refresh(record)

        if execute_now and job.status == "QUEUED" and session_factory is not None:
            await self.download_studio.run_job(job.id, session_factory)
            session.expire_all()
            fresh_job = session.get(DownloadJob, job.id)
            if fresh_job:
                session.refresh(fresh_job)
                job = fresh_job
                record.status = job.status
                record.file_sha256 = job.file_sha256
                record.error_message = job.error_message
                record.updated_at = datetime.now(timezone.utc)
                session.add(record)
                session.commit()
                session.refresh(record)
                session.refresh(job)

        return {
            "accepted": job.status not in ("FAILED",),
            "status": job.status,
            "reason": reason,
            "requires_approval": requires_approval,
            "job": job.model_dump(mode="json"),
            "record": record.model_dump(mode="json"),
            "comparison": comparison.model_dump(mode="json"),
        }

    async def acquire_track(
        self,
        session: Session,
        query: str = "",
        artist: Optional[str] = None,
        title: Optional[str] = None,
        album: Optional[str] = None,
        isrc: Optional[str] = None,
        search_type: str = "track",
        provider_ids: Optional[list[str]] = None,
        mode: str = "ASK_BEFORE_PAID",
        profile: str = "ORIGINAL",
        target_sample_rate_hz: Optional[int] = None,
        track_id: Optional[int] = None,
        preferred_provider_id: Optional[str] = None,
        preferred_source_item_id: Optional[str] = None,
        group_payload: Optional[dict[str, Any]] = None,
        allow_downgrade_or_same: bool = False,
        session_factory: Optional[Callable[[], Session]] = None,
        execute_now: bool = False,
    ) -> dict[str, Any]:
        """Search multi-source (or reuse supplied grouped recording) and execute acquisition policy."""
        if group_payload is not None:
            group = GroupedRecording.model_validate(group_payload)
            return await self.acquire_from_group(
                group=group,
                session=session,
                mode=mode,
                profile=profile,
                target_sample_rate_hz=target_sample_rate_hz,
                track_id=track_id,
                preferred_provider_id=preferred_provider_id,
                preferred_source_item_id=preferred_source_item_id,
                allow_downgrade_or_same=allow_downgrade_or_same,
                session_factory=session_factory,
                execute_now=execute_now,
            )

        search_res = await self.search_engine.search(
            query=query,
            session=session,
            search_type=search_type,
            artist=artist,
            title=title,
            album=album,
            isrc=isrc,
            provider_ids=provider_ids,
        )
        groups_raw = search_res.get("groups") or []
        if not groups_raw:
            return {
                "accepted": False,
                "status": "NO_RESULTS",
                "reason": "Nenhum resultado encontrado nas fontes habilitadas.",
                "job": None,
                "record": None,
                "search_summary": {
                    "total_raw_results": search_res.get("total_raw_results", 0),
                    "provider_statuses": search_res.get("provider_statuses", []),
                },
            }

        # Pick first downloadable group when available, otherwise top group to report cleanly
        chosen_raw = next((g for g in groups_raw if g.get("has_downloadable_source")), groups_raw[0])
        group = GroupedRecording.model_validate(chosen_raw)
        result = await self.acquire_from_group(
            group=group,
            session=session,
            mode=mode,
            profile=profile,
            target_sample_rate_hz=target_sample_rate_hz,
            track_id=track_id,
            preferred_provider_id=preferred_provider_id,
            preferred_source_item_id=preferred_source_item_id,
            allow_downgrade_or_same=allow_downgrade_or_same,
            session_factory=session_factory,
            execute_now=execute_now,
        )
        result["search_summary"] = {
            "total_raw_results": search_res.get("total_raw_results", 0),
            "total_groups": search_res.get("total_groups", 0),
            "provider_statuses": search_res.get("provider_statuses", []),
        }
        return result

    async def approve_and_start_job(
        self,
        job_id: int,
        session: Session,
        session_factory: Optional[Callable[[], Session]] = None,
        execute_now: bool = False,
    ) -> dict[str, Any]:
        """Explicitly approve a commercial AWAITING_APPROVAL job and transition it to QUEUED."""
        job = session.get(DownloadJob, job_id)
        if not job:
            raise ValueError(f"DownloadJob #{job_id} não encontrado.")
        if job.status != "AWAITING_APPROVAL":
            raise ValueError(f"Job #{job_id} não está aguardando aprovação (status atual: {job.status}).")

        job.approved_by_user = True
        job.status = "QUEUED"
        job.current_stage = "QUEUED"
        job.updated_at = datetime.now(timezone.utc)
        self.download_studio._append_log(job, "Aquisição comercial aprovada explicitamente pelo usuário.")
        session.add(job)

        rec = session.exec(select(AcquisitionRecord).where(AcquisitionRecord.download_job_id == job_id)).first()
        if rec:
            rec.approved_by_user = True
            rec.status = "QUEUED"
            rec.updated_at = datetime.now(timezone.utc)
            session.add(rec)

        session.commit()
        session.refresh(job)

        if execute_now and session_factory is not None:
            await self.download_studio.run_job(job.id, session_factory)
            session.expire_all()
            fresh_job = session.get(DownloadJob, job.id)
            if fresh_job:
                session.refresh(fresh_job)
                job = fresh_job
                if rec:
                    rec.status = job.status
                    rec.file_sha256 = job.file_sha256
                    rec.error_message = job.error_message
                    rec.updated_at = datetime.now(timezone.utc)
                    session.add(rec)
                    session.commit()
                session.refresh(job)

        return {
            "approved": True,
            "job": job.model_dump(mode="json"),
        }

    async def acquire_batch(
        self,
        items: list[dict[str, Any]],
        session: Session,
        mode: str = "ASK_BEFORE_PAID",
        profile: str = "ORIGINAL",
        session_factory: Optional[Callable[[], Session]] = None,
        execute_now: bool = False,
    ) -> dict[str, Any]:
        """Run discovery & acquisition policy sequentially/cleanly across a list of tracks."""
        results: list[dict[str, Any]] = []
        queued = 0
        awaiting_approval = 0
        unavailable = 0

        for item in items:
            res = await self.acquire_track(
                session=session,
                query=item.get("query") or "",
                artist=item.get("artist"),
                title=item.get("title"),
                album=item.get("album"),
                isrc=item.get("isrc"),
                search_type=item.get("search_type") or "track",
                mode=item.get("mode") or mode,
                profile=item.get("profile") or profile,
                track_id=item.get("track_id"),
                session_factory=session_factory,
                execute_now=execute_now,
            )
            st = res.get("status")
            if st == "AWAITING_APPROVAL":
                awaiting_approval += 1
            elif st in ("QUEUED", "COMPLETED"):
                queued += 1
            else:
                unavailable += 1
            results.append(res)

        return {
            "total": len(items),
            "queued_or_completed": queued,
            "awaiting_approval": awaiting_approval,
            "unavailable_or_failed": unavailable,
            "items": results,
        }
