from abc import ABC, abstractmethod
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Callable, Optional
from urllib.parse import urljoin
import httpx
from sqlmodel import Session, select

from app.config import get_settings
from app.core.models import AudioProvenance, DownloadJob, UnifiedTrack
from app.core.security import (
    MAX_DOWNLOAD_BYTES,
    SecurityValidationError,
    compute_sha256,
    safe_join_path,
    validate_audio_magic_bytes,
    validate_external_url,
)
from app.engines.audio_quality_intelligence import AudioQualityIntelligenceEngine
from app.engines.conversion_engine import ConversionEngine
from app.engines.tagging_engine import TaggingEngine
from app.engines.technical_analysis import TechnicalAnalysisEngine
from app.engines.upgrade_engine import CandidateSource, UpgradeEngine


class BaseAcquisitionProvider(ABC):
    """Pluggable interface for authorized audio source acquisition (no DRM/paywall bypass)."""

    provider_name: str = "base"

    @abstractmethod
    async def acquire(
        self,
        job: DownloadJob,
        temp_dir: Path,
        progress_cb: Callable[[float, Optional[float], Optional[float], Optional[int]], None],
        cancel_event: asyncio.Event,
        pause_event: asyncio.Event,
    ) -> tuple[Optional[Path], Optional[str]]:
        """Download or stage source audio into temp_dir. Returns (staged_path, error_message)."""
        pass


class AuthorizedSourceProvider(BaseAcquisitionProvider):
    """Acquires audio from authorized HTTP/HTTPS direct URLs or local files without DRM bypass."""

    provider_name: str = "authorized_url"

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None, timeout: float = 60.0):
        self._transport = transport
        self.timeout = timeout

    async def acquire(
        self,
        job: DownloadJob,
        temp_dir: Path,
        progress_cb: Callable[[float, Optional[float], Optional[float], Optional[int]], None],
        cancel_event: asyncio.Event,
        pause_event: asyncio.Event,
    ) -> tuple[Optional[Path], Optional[str]]:
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 1. Local file source staging (for profile conversions or verified local upgrades)
        if job.source_path:
            src = Path(job.source_path)
            if not src.exists():
                return None, f"Arquivo de origem local não encontrado: {src}"
            size = src.stat().st_size
            dest = temp_dir / f"job_{job.id}_src{src.suffix}"
            await asyncio.to_thread(shutil.copy2, src, dest)
            progress_cb(0.45, None, 0.0, size)
            return dest, None

        # 2. Authorized HTTP/HTTPS source URL
        if job.requires_approval and not job.approved_by_user:
            return None, "Aquisição comercial bloqueada: aprovação explícita do usuário obrigatória antes do download."

        url = (job.source_url or "").strip()
        if not url:
            return None, "Nenhuma URL autorizada ou arquivo local fornecido; APIs de catálogo sem áudio completo não podem ser baixadas."

        try:
            current_url = validate_external_url(url)
        except SecurityValidationError as sec_err:
            return None, f"URL rejeitada pela política de segurança: {sec_err}"

        ext = Path(current_url.split("?")[0]).suffix.lower() or ".audio"
        if len(ext) > 6 or not ext.startswith("."):
            ext = ".audio"
        try:
            dest = safe_join_path(temp_dir, f"job_{job.id}_dl{ext}")
        except SecurityValidationError as sec_err:
            return None, f"Caminho de destino inseguro: {sec_err}"

        client_kwargs: dict[str, Any] = {"timeout": self.timeout, "follow_redirects": False}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                max_hops = 5
                hops = 0
                while True:
                    async with client.stream("GET", current_url) as resp:
                        if resp.status_code in (301, 302, 303, 307, 308):
                            if hops >= max_hops:
                                return None, "Número máximo de redirecionamentos HTTP excedido."
                            loc = resp.headers.get("Location")
                            if not loc:
                                return None, "Redirecionamento HTTP sem cabeçalho Location."
                            next_url = urljoin(current_url, loc)
                            try:
                                current_url = validate_external_url(next_url)
                            except SecurityValidationError as sec_err:
                                return None, f"Redirecionamento bloqueado pela política anti-SSRF: {sec_err}"
                            hops += 1
                            continue

                        if resp.status_code != 200:
                            return None, f"Fonte retornou HTTP {resp.status_code}."

                        content_type = resp.headers.get("Content-Type")
                        total_bytes = int(resp.headers.get("Content-Length") or 0) or None
                        if total_bytes and total_bytes > MAX_DOWNLOAD_BYTES:
                            return None, f"Arquivo excede o limite de segurança ({MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB)."

                        downloaded = 0
                        started = time.monotonic()

                        with open(dest, "wb") as f:
                            async for chunk in resp.aiter_bytes(chunk_size=32768):
                                while pause_event.is_set():
                                    if cancel_event.is_set():
                                        break
                                    await asyncio.sleep(0.15)
                                if cancel_event.is_set():
                                    return None, "Download cancelado pelo usuário."
                                if not chunk:
                                    continue
                                downloaded += len(chunk)
                                if downloaded > MAX_DOWNLOAD_BYTES:
                                    return None, f"Download abortado: excedeu limite máximo de {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB."
                                f.write(chunk)
                                elapsed = max(0.001, time.monotonic() - started)
                                speed = downloaded / elapsed
                                eta = ((total_bytes - downloaded) / speed) if (total_bytes and speed > 0) else None
                                pct = min(0.55, (downloaded / total_bytes) * 0.55) if total_bytes else 0.30
                                progress_cb(pct, speed, eta, total_bytes)
                        break

            if not dest.exists() or dest.stat().st_size == 0:
                return None, "Arquivo baixado está vazio."

            valid_audio, magic_detail = validate_audio_magic_bytes(dest, content_type=content_type)
            if not valid_audio:
                dest.unlink(missing_ok=True)
                return None, f"Validação de assinatura binária falhou: {magic_detail}"

            return dest, None
        except Exception as e:
            if dest.exists():
                dest.unlink(missing_ok=True)
            return None, f"Falha na aquisição HTTP: {e}"


class DownloadStudioEngine:
    """Persistent, concurrent, non-blocking Download, Conversion, Validation, and Atomic Upgrade orchestrator."""

    SAFE_NAME_RE = re.compile(r'[\\/:*?"<>|]')

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
        temp_dir: Optional[Path] = None,
        max_concurrent: int = 2,
        provider: Optional[BaseAcquisitionProvider] = None,
        conversion_engine: Optional[ConversionEngine] = None,
        tagging_engine: Optional[TaggingEngine] = None,
        tech_engine: Optional[TechnicalAnalysisEngine] = None,
        quality_engine: Optional[AudioQualityIntelligenceEngine] = None,
        upgrade_engine: Optional[UpgradeEngine] = None,
        ws_broadcast: Optional[Callable[[dict[str, Any]], Any]] = None,
    ):
        settings = get_settings()
        self.output_dir = Path(output_dir or settings.DOWNLOAD_DIR)
        self.temp_dir = Path(temp_dir) if temp_dir else (self.output_dir / ".tmp")
        self.backup_dir = Path(backup_dir or Path("./backups/replaced_audio"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self.provider = provider or AuthorizedSourceProvider()
        self.conversion_engine = conversion_engine or ConversionEngine()
        self.tagging_engine = tagging_engine or TaggingEngine()
        self.tech_engine = tech_engine or TechnicalAnalysisEngine()
        self.quality_engine = quality_engine or AudioQualityIntelligenceEngine(tech_engine=self.tech_engine)
        self.upgrade_engine = upgrade_engine or UpgradeEngine()
        self.ws_broadcast = ws_broadcast

        self._cancel_events: dict[int, asyncio.Event] = {}
        self._pause_events: dict[int, asyncio.Event] = {}
        self._running_tasks: dict[int, asyncio.Task[Any]] = {}

    @classmethod
    def _sanitize_filename(cls, raw: str) -> str:
        clean = cls.SAFE_NAME_RE.sub("_", raw).strip()
        return clean[:120] or "track"

    def _append_log(self, job: DownloadJob, message: str) -> None:
        try:
            logs = json.loads(job.logs_json or "[]")
        except Exception:
            logs = []
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        logs.append(f"[{ts}] {message}")
        job.logs_json = json.dumps(logs[-100:], ensure_ascii=False)

    async def _emit_progress(self, job: DownloadJob) -> None:
        if self.ws_broadcast:
            try:
                res = self.ws_broadcast(
                    {
                        "type": "download_job_update",
                        "job": job.model_dump(mode="json"),
                    }
                )
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass

    def recover_interrupted_jobs(self, session: Session) -> int:
        """Mark jobs left mid-flight from a prior crash/restart as FAILED so they can be retried cleanly."""
        active_states = ("SEARCHING", "QUEUED", "DOWNLOADING", "CONVERTING", "TAGGING", "ANALYZING", "VALIDATING")
        jobs = session.exec(select(DownloadJob).where(DownloadJob.status.in_(active_states))).all()
        count = 0
        for job in jobs:
            job.status = "FAILED"
            job.current_stage = "INTERRUPTED"
            job.error_message = "Aplicação reiniciada durante a execução; pronto para retry."
            self._append_log(job, "Job interrompido no restart anterior; marcado para retry.")
            job.updated_at = datetime.now(timezone.utc)
            session.add(job)
            count += 1
        if count:
            session.commit()
        return count

    def enqueue_job(
        self,
        session: Session,
        track_id: Optional[int],
        candidate: CandidateSource,
        profile: str = "ORIGINAL",
        target_sample_rate_hz: Optional[int] = None,
        max_attempts: int = 3,
        allow_downgrade_or_same: bool = False,
        source_item_id: Optional[str] = None,
        acquisition_mode: str = "manual",
        requires_approval: bool = False,
        approved_by_user: bool = False,
        estimated_cost_label: Optional[str] = None,
        license_info: Optional[str] = None,
    ) -> DownloadJob:
        """Validate upgrade decision and persist a new DownloadJob in SQLite."""
        track = session.get(UnifiedTrack, track_id) if track_id else None
        prov = (
            session.exec(select(AudioProvenance).where(AudioProvenance.track_id == track_id)).first()
            if track_id
            else None
        )
        eval_res = self.upgrade_engine.evaluate_upgrade(
            existing_track=track,
            candidate=candidate,
            requested_profile=profile,
            existing_provenance=prov,
        )

        initial_status = "AWAITING_APPROVAL" if (requires_approval and not approved_by_user) else "QUEUED"
        job = DownloadJob(
            track_id=track_id,
            provider=candidate.provider,
            source_url=candidate.source_url,
            source_path=candidate.local_source_path,
            source_label=f"{candidate.artist} - {candidate.title}",
            source_item_id=source_item_id,
            acquisition_mode=acquisition_mode,
            requires_approval=requires_approval,
            approved_by_user=approved_by_user,
            estimated_cost_label=estimated_cost_label,
            license_info=license_info,
            status=initial_status,
            profile=profile.upper(),
            target_sample_rate_hz=target_sample_rate_hz,
            current_stage=initial_status,
            max_attempts=max_attempts,
            upgrade_decision=eval_res.decision,
            upgrade_reason=eval_res.reason,
        )
        self._append_log(job, f"UpgradeEngine: {eval_res.decision} — {eval_res.reason}")
        if initial_status == "AWAITING_APPROVAL":
            self._append_log(
                job,
                f"Aguardando aprovação explícita do usuário para entrega comercial ({estimated_cost_label or 'paga'}).",
            )
        for w in eval_res.warnings:
            self._append_log(job, f"Aviso: {w}")

        if not eval_res.is_justified and not allow_downgrade_or_same:
            job.status = "FAILED"
            job.current_stage = "BLOCKED_BY_UPGRADE_POLICY"
            job.error_message = eval_res.reason
            job.finished_at = datetime.now(timezone.utc)

        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    def start_job_background(
        self, job_id: int, session_factory: Callable[[], Session]
    ) -> asyncio.Task[Any]:
        """Schedule job execution as a background asyncio.Task."""
        task = asyncio.create_task(self.run_job(job_id, session_factory))
        self._running_tasks[job_id] = task
        return task

    def cancel_job(self, job_id: int, session: Session) -> Optional[DownloadJob]:
        """Signal cancellation for a queued/running job and persist CANCELLED status."""
        ev = self._cancel_events.get(job_id)
        if ev:
            ev.set()
        job = session.get(DownloadJob, job_id)
        if job and job.status not in ("COMPLETED", "CANCELLED"):
            job.status = "CANCELLED"
            job.current_stage = "CANCELLED"
            job.finished_at = datetime.now(timezone.utc)
            job.updated_at = datetime.now(timezone.utc)
            self._append_log(job, "Cancelamento solicitado pelo usuário.")
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def pause_job(self, job_id: int, session: Session) -> Optional[DownloadJob]:
        ev = self._pause_events.get(job_id)
        if ev:
            ev.set()
        job = session.get(DownloadJob, job_id)
        if job and job.status in ("QUEUED", "DOWNLOADING"):
            job.status = "PAUSED"
            job.current_stage = "PAUSED"
            job.updated_at = datetime.now(timezone.utc)
            self._append_log(job, "Job pausado.")
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    def resume_job(self, job_id: int, session: Session) -> Optional[DownloadJob]:
        ev = self._pause_events.get(job_id)
        if ev:
            ev.clear()
        job = session.get(DownloadJob, job_id)
        if job and job.status == "PAUSED":
            job.status = "DOWNLOADING"
            job.current_stage = "RESUMED"
            job.updated_at = datetime.now(timezone.utc)
            self._append_log(job, "Job retomado.")
            session.add(job)
            session.commit()
            session.refresh(job)
        return job

    async def run_job(self, job_id: int, session_factory: Callable[[], Session]) -> Optional[DownloadJob]:
        """Execute full acquisition, validation, conversion, tagging, analysis, and atomic replacement pipeline."""
        cancel_ev = self._cancel_events.setdefault(job_id, asyncio.Event())
        pause_ev = self._pause_events.setdefault(job_id, asyncio.Event())

        async with self._semaphore:
            with session_factory() as session:
                job = session.get(DownloadJob, job_id)
                if not job or job.status in ("CANCELLED", "COMPLETED", "AWAITING_APPROVAL"):
                    return job
                if job.requires_approval and not job.approved_by_user:
                    job.status = "AWAITING_APPROVAL"
                    job.current_stage = "AWAITING_APPROVAL"
                    session.add(job)
                    session.commit()
                    return job
                if job.status == "FAILED" and job.current_stage == "BLOCKED_BY_UPGRADE_POLICY":
                    return job

                job.started_at = datetime.now(timezone.utc)
                job.error_message = None

                attempt = job.attempts
                while attempt < max(1, job.max_attempts):
                    attempt += 1
                    job.attempts = attempt
                    staged_path: Optional[Path] = None
                    converted_path: Optional[Path] = None

                    try:
                        if cancel_ev.is_set():
                            raise RuntimeError("Job cancelado.")

                        # Stage 1: Acquire into temp
                        job.status = "DOWNLOADING"
                        job.current_stage = "DOWNLOADING"
                        self._append_log(job, f"Tentativa {attempt}/{job.max_attempts}: adquirindo arquivo para staging temporário.")
                        session.add(job)
                        session.commit()
                        await self._emit_progress(job)

                        def _on_dl_prog(pct: float, speed: Optional[float], eta: Optional[float], total_b: Optional[int]) -> None:
                            job.progress = round(pct, 3)
                            job.speed_bps = speed
                            job.eta_sec = eta
                            if total_b:
                                job.estimated_bytes = total_b

                        staged_path, acq_err = await self.provider.acquire(
                            job, self.temp_dir, _on_dl_prog, cancel_ev, pause_ev
                        )
                        if acq_err or not staged_path or not staged_path.exists():
                            raise RuntimeError(acq_err or "Falha na aquisição do arquivo.")

                        # Stage 2: Validate integrity via ffprobe
                        job.status = "VALIDATING"
                        job.current_stage = "PROBE_VALIDATION"
                        job.progress = 0.60
                        session.add(job)
                        session.commit()
                        await self._emit_progress(job)

                        probe_src = await self.tech_engine.probe_file(staged_path)
                        if not probe_src or probe_src.duration_sec <= 0.2:
                            raise RuntimeError("Validação ffprobe falhou: arquivo inválido ou corrompido.")

                        # Stage 3: Convert according to profile
                        job.status = "CONVERTING"
                        job.current_stage = f"CONVERTING_{job.profile}"
                        job.progress = 0.68
                        self._append_log(job, f"Convertendo para perfil {job.profile}...")
                        session.add(job)
                        session.commit()
                        await self._emit_progress(job)

                        track = session.get(UnifiedTrack, job.track_id) if job.track_id else None
                        stem_base = f"{track.artist} - {track.title}" if track else (job.source_label or f"track_{job.id}")
                        safe_stem = self._sanitize_filename(stem_base)
                        conv_dir = self.temp_dir / f"conv_{job.id}"

                        conv_res = await self.conversion_engine.convert_file(
                            src_path=staged_path,
                            dest_dir=conv_dir,
                            profile_id=job.profile,
                            output_stem=safe_stem,
                            target_sample_rate_hz=job.target_sample_rate_hz,
                            source_bitrate_kbps=probe_src.bitrate_kbps,
                            cancel_event=cancel_ev,
                        )
                        if not conv_res.success or not conv_res.output_path:
                            raise RuntimeError(conv_res.error or "Falha na conversão FFmpeg.")
                        converted_path = conv_res.output_path
                        for w in conv_res.warnings:
                            self._append_log(job, w)

                        # Validate converted output
                        probe_out = await self.tech_engine.probe_file(converted_path)
                        if not probe_out or probe_out.duration_sec <= 0.2:
                            raise RuntimeError("Arquivo convertido falhou na validação final de integridade.")

                        # Stage 4: Apply metadata tags
                        job.status = "TAGGING"
                        job.current_stage = "TAGGING"
                        job.progress = 0.78
                        session.add(job)
                        session.commit()
                        await self._emit_progress(job)

                        if track:
                            tagged_ok, tag_warns = self.tagging_engine.apply_tags(converted_path, track, preserve_existing=True)
                            for w in tag_warns:
                                self._append_log(job, w)
                            if not tagged_ok:
                                self._append_log(job, "Aviso: nem todas as tags puderam ser gravadas no container.")

                        # Stage 5: Backup old file (if replacing) & Atomic Move to destination
                        final_dest = safe_join_path(self.output_dir, converted_path.name)
                        backup_path_str: Optional[str] = None
                        old_local = Path(track.local_path) if (track and track.local_path) else None
                        if old_local and old_local.exists():
                            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                            bkp = safe_join_path(self.backup_dir, f"{old_local.stem}_{ts}{old_local.suffix}")
                            await asyncio.to_thread(shutil.copy2, old_local, bkp)
                            backup_path_str = str(bkp)
                            job.backup_path = backup_path_str
                            self._append_log(job, f"Backup da versão anterior criado em {bkp.name}")

                        temp_final = safe_join_path(self.output_dir, f".atomic_{job.id}_{converted_path.name}")
                        await asyncio.to_thread(shutil.move, str(converted_path), str(temp_final))
                        os.replace(temp_final, final_dest)
                        if old_local and old_local.exists() and old_local.resolve() != final_dest.resolve():
                            old_local.unlink(missing_ok=True)

                        file_sha256 = await asyncio.to_thread(compute_sha256, final_dest)
                        job.file_sha256 = file_sha256

                        # Stage 6: Analyze technical + Audio Quality Intelligence & Provenance
                        job.status = "ANALYZING"
                        job.current_stage = "QUALITY_ANALYSIS"
                        job.progress = 0.88
                        session.add(job)
                        session.commit()
                        await self._emit_progress(job)

                        if track is None:
                            parsed_artist = "Unknown Artist"
                            parsed_title = job.source_label or safe_stem
                            if job.source_label and " - " in job.source_label:
                                parsed_artist, parsed_title = [p.strip() for p in job.source_label.split(" - ", 1)]
                            track = UnifiedTrack(
                                title=parsed_title or safe_stem,
                                artist=parsed_artist or "Unknown Artist",
                                local_path=str(final_dest),
                            )
                            session.add(track)
                            session.commit()
                            session.refresh(track)
                            job.track_id = track.id
                        else:
                            track.local_path = str(final_dest)
                            track.is_preview = False
                            track.is_corrupted = False
                            session.add(track)
                            session.commit()

                        # Record original acquisition provenance BEFORE running quality intelligence
                        src_lossy = probe_src.codec_name.lower() in {"mp3", "aac", "opus", "vorbis", "ogg", "m4a"}
                        prior_prov = session.exec(
                            select(AudioProvenance).where(AudioProvenance.track_id == track.id)
                        ).first()
                        origin_cls = (
                            "LOSSY_SOURCE"
                            if (src_lossy or (prior_prov and prior_prov.origin_classification == "LOSSY_SOURCE"))
                            else "UNKNOWN_SOURCE"
                        )
                        declared_meta = {
                            "provider": job.provider,
                            "source_item_id": job.source_item_id,
                            "license_info": job.license_info,
                            "acquisition_mode": job.acquisition_mode,
                        }
                        extracted_meta = {
                            "source_codec": probe_src.codec_name,
                            "source_bitrate_kbps": probe_src.bitrate_kbps,
                            "source_sample_rate_hz": probe_src.sample_rate_hz,
                            "source_bit_depth": probe_src.bit_depth,
                            "output_codec": probe_out.codec_name,
                            "output_bitrate_kbps": probe_out.bitrate_kbps,
                            "file_sha256": file_sha256,
                        }
                        prov = self.quality_engine.record_provenance(
                            session=session,
                            track=track,
                            acquisition_source="download_studio",
                            provider=job.provider,
                            source_url=job.source_url,
                            requested_profile=job.profile,
                            origin_classification=origin_cls,
                            evidence=[
                                f"Adquirido via {job.provider}; origem probe: {probe_src.codec_name} {probe_src.bitrate_kbps} kbps; SHA-256: {file_sha256[:16]}..."
                            ],
                        )
                        if prov.original_codec is None:
                            prov.original_codec = probe_src.codec_name
                            prov.original_bitrate_kbps = probe_src.bitrate_kbps
                            prov.original_sample_rate_hz = probe_src.sample_rate_hz
                            prov.original_bit_depth = probe_src.bit_depth
                        prov.source_item_id = job.source_item_id or prov.source_item_id
                        prov.file_sha256 = file_sha256
                        prov.license_info = job.license_info or prov.license_info
                        prov.declared_metadata_json = json.dumps(declared_meta, ensure_ascii=False)
                        prov.extracted_metadata_json = json.dumps(extracted_meta, ensure_ascii=False)
                        prov.verification_status = "VERIFIED"
                        session.add(prov)
                        session.commit()

                        await self.quality_engine.analyze_track_quality(track, session, force=True)
                        # Record engine inference separation after full quality run
                        session.refresh(prov)
                        prov.inferences_json = json.dumps(
                            {
                                "origin_classification": prov.origin_classification,
                                "upscale_status": track.upscale_status,
                                "car_audio_score": track.car_audio_score,
                                "car_audio_ready": track.car_audio_ready,
                            },
                            ensure_ascii=False,
                        )
                        session.add(prov)
                        session.commit()
                        self.quality_engine.record_processing_event(
                            session=session,
                            track_id=track.id or 0,
                            operation="upgrade_replace" if backup_path_str else "acquire",
                            provenance_id=prov.id,
                            from_codec=probe_src.codec_name,
                            to_codec=probe_out.codec_name,
                            from_bitrate_kbps=probe_src.bitrate_kbps,
                            to_bitrate_kbps=probe_out.bitrate_kbps,
                            profile=job.profile,
                            source_path=job.source_url or job.source_path,
                            dest_path=str(final_dest),
                            backup_path=backup_path_str,
                            was_lossy_to_lossless=conv_res.was_lossy_to_lossless,
                            warnings=conv_res.warnings,
                            engine_name="DownloadStudioEngine",
                        )

                        # Complete!
                        job.dest_path = str(final_dest)
                        job.final_bytes = final_dest.stat().st_size if final_dest.exists() else None
                        job.status = "COMPLETED"
                        job.current_stage = "COMPLETED"
                        job.progress = 1.0
                        job.eta_sec = 0.0
                        job.finished_at = datetime.now(timezone.utc)
                        job.updated_at = datetime.now(timezone.utc)
                        self._append_log(job, f"Concluído com sucesso: {final_dest.name}")
                        session.add(job)
                        session.commit()
                        session.refresh(job)
                        await self._emit_progress(job)
                        return job

                    except Exception as exc:
                        err_text = str(exc)
                        self._append_log(job, f"Erro na tentativa {attempt}: {err_text}")
                        if staged_path and staged_path.exists():
                            staged_path.unlink(missing_ok=True)
                        if converted_path and converted_path.exists():
                            converted_path.unlink(missing_ok=True)
                        conv_dir = self.temp_dir / f"conv_{job.id}"
                        if conv_dir.exists():
                            shutil.rmtree(conv_dir, ignore_errors=True)

                        if cancel_ev.is_set():
                            job.status = "CANCELLED"
                            job.current_stage = "CANCELLED"
                            job.error_message = "Cancelado pelo usuário."
                            job.finished_at = datetime.now(timezone.utc)
                            session.add(job)
                            session.commit()
                            await self._emit_progress(job)
                            return job

                        if attempt >= max(1, job.max_attempts):
                            job.status = "FAILED"
                            job.current_stage = "FAILED"
                            job.error_message = err_text
                            job.finished_at = datetime.now(timezone.utc)
                            job.updated_at = datetime.now(timezone.utc)
                            session.add(job)
                            session.commit()
                            await self._emit_progress(job)
                            return job

                        # Exponential backoff before retry
                        backoff = min(4.0, 0.25 * (2 ** (attempt - 1)))
                        job.status = "QUEUED"
                        job.current_stage = f"RETRY_BACKOFF_{attempt}"
                        job.error_message = err_text
                        session.add(job)
                        session.commit()
                        await asyncio.sleep(backoff)
                    finally:
                        if staged_path and staged_path.exists():
                            staged_path.unlink(missing_ok=True)
                        conv_dir = self.temp_dir / f"conv_{job.id}"
                        if conv_dir.exists():
                            shutil.rmtree(conv_dir, ignore_errors=True)

        return None
