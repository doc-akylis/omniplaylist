import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Optional
import librosa
import numpy as np
from scipy import signal
from sqlmodel import Session, select

from app.core.models import AudioProcessingHistory, AudioProvenance, UnifiedTrack
from app.engines.technical_analysis import TechnicalAnalysisEngine

LOSSLESS_CODECS = {"flac", "alac", "wav", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "aiff", "ape", "wavpack"}
LOSSY_CODECS = {"mp3", "aac", "opus", "vorbis", "ogg", "m4a", "wma"}

# Documented descriptive frequency band limits (Hz)
SPECTRAL_BANDS_HZ = {
    "sub_bass": (20.0, 60.0),
    "mid_bass": (60.0, 250.0),
    "midrange": (250.0, 4000.0),
    "high_freq": (4000.0, 20000.0),
}


@dataclass
class CarAudioWeights:
    """Configurable penalties for Car Audio technical readiness (0-100 scale)."""

    corrupted_penalty: float = 100.0
    preview_penalty: float = 45.0
    severe_clipping_penalty: float = 25.0
    moderate_clipping_penalty: float = 12.0
    true_peak_over_zero_penalty: float = 15.0
    true_peak_hot_penalty: float = 6.0
    low_dynamic_range_penalty: float = 12.0
    fake_upscale_penalty: float = 22.0
    suspected_upscale_penalty: float = 10.0
    low_bitrate_penalty: float = 22.0
    medium_lossy_bitrate_penalty: float = 8.0
    extreme_loudness_penalty: float = 8.0
    ready_min_score: float = 65.0


@dataclass
class SpectralQualityResult:
    """Result of STFT/Welch spectral cutoff, fake upscale heuristic, and 4-band profile."""

    spectral_cutoff_hz: Optional[float]
    nyquist_hz: float
    upscale_status: str  # VERIFIED_LOSSLESS_SOURCE, VERIFIED_LOSSY_SOURCE, LIKELY_UPSCALE, SUSPECTED_UPSCALE, UNKNOWN
    confidence: float
    is_fake_upscale: bool
    sub_bass_energy: float
    mid_bass_energy: float
    midrange_energy: float
    high_freq_energy: float
    evidence: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    method: str = "scipy_welch_stft_v1"


class AudioQualityIntelligenceEngine:
    """Unified Audio Quality Intelligence: provenance, origin, fake upscale detection, bass profile, and Car Audio score."""

    ENGINE_NAME = "AudioQualityIntelligenceEngine"
    ENGINE_VERSION = "2.1.0"

    def __init__(
        self,
        tech_engine: Optional[TechnicalAnalysisEngine] = None,
        weights: Optional[CarAudioWeights] = None,
    ):
        self.tech_engine = tech_engine or TechnicalAnalysisEngine()
        self.weights = weights or CarAudioWeights()

    @staticmethod
    def _is_lossless_codec(codec: Optional[str]) -> Optional[bool]:
        if not codec:
            return None
        c = codec.strip().lower()
        if c in LOSSLESS_CODECS or c.startswith("pcm_"):
            return True
        if c in LOSSY_CODECS:
            return False
        return None

    @classmethod
    def classify_origin(
        cls,
        codec: Optional[str],
        provenance: Optional[AudioProvenance] = None,
        upscale_status: Optional[str] = None,
    ) -> str:
        """Classify true origin quality without confusing container format with source fidelity."""
        if provenance and provenance.origin_classification in ("LOSSLESS_SOURCE", "LOSSY_SOURCE"):
            return provenance.origin_classification

        if upscale_status in ("LIKELY_UPSCALE", "VERIFIED_LOSSY_SOURCE"):
            return "LOSSY_SOURCE"

        is_lossless = cls._is_lossless_codec(codec)
        if is_lossless is False:
            return "LOSSY_SOURCE"
        if is_lossless is True:
            if upscale_status == "VERIFIED_LOSSLESS_SOURCE":
                return "LOSSLESS_SOURCE"
            return "UNKNOWN_SOURCE"
        return "UNKNOWN_SOURCE"

    @classmethod
    def _analyze_spectrum_sync(
        cls,
        file_path: Path,
        codec: Optional[str],
        bitrate_kbps: Optional[int],
        prior_origin: Optional[str] = None,
    ) -> Optional[SpectralQualityResult]:
        """Run non-blocking STFT/Welch spectral analysis in a worker thread."""
        if not file_path.exists():
            return None

        try:
            total_dur = librosa.get_duration(path=str(file_path))
            offset = max(0.0, (total_dur - 45.0) / 2.0) if total_dur > 45.0 else 0.0
            y, sr = librosa.load(
                str(file_path),
                sr=None,
                mono=True,
                offset=offset,
                duration=min(45.0, total_dur) if total_dur > 0 else 45.0,
            )
        except Exception as e:
            print(f"[AudioQualityIntelligence] Failed loading spectrum for {file_path}: {e}")
            return None

        if y is None or y.size < 2048 or sr <= 0:
            return None

        nyquist = float(sr) / 2.0
        nperseg = min(4096, len(y))
        freqs, psd = signal.welch(y, fs=sr, nperseg=nperseg, window="hann", scaling="spectrum")
        psd = np.maximum(psd, 1e-18)
        psd_db = 10.0 * np.log10(psd)

        def band_power(low_hz: float, high_hz: float) -> float:
            mask = (freqs >= low_hz) & (freqs < min(high_hz, nyquist))
            if not np.any(mask):
                return 0.0
            return float(np.sum(psd[mask]))

        sub_p = band_power(*SPECTRAL_BANDS_HZ["sub_bass"])
        mid_bass_p = band_power(*SPECTRAL_BANDS_HZ["mid_bass"])
        mid_p = band_power(*SPECTRAL_BANDS_HZ["midrange"])
        high_p = band_power(*SPECTRAL_BANDS_HZ["high_freq"])
        total_p = max(1e-18, sub_p + mid_bass_p + mid_p + high_p)

        sub_norm = round(sub_p / total_p, 4)
        mid_bass_norm = round(mid_bass_p / total_p, 4)
        mid_norm = round(mid_p / total_p, 4)
        high_norm = round(high_p / total_p, 4)

        # Reference mid/upper-mid peak active level (500 Hz - 4 kHz)
        ref_mask = (freqs >= 500.0) & (freqs <= min(4000.0, nyquist))

        # Smooth linear PSD in ~180 Hz windows (never zero-pad dB values, which injects 0 dBFS boundary artifacts)
        bin_hz = freqs[1] - freqs[0] if len(freqs) > 1 else 1.0
        smooth_bins = max(3, int(round(180.0 / max(bin_hz, 0.1))))
        kernel = np.ones(smooth_bins) / smooth_bins
        smoothed_psd = np.convolve(psd, kernel, mode="same")
        smoothed_db = 10.0 * np.log10(np.maximum(smoothed_psd, 1e-18))

        ref_db = float(np.max(smoothed_db[ref_mask])) if np.any(ref_mask) else float(np.max(smoothed_db))

        # Floor threshold relative to peak active reference (avoids noise-floor distortion on sparse harmonics)
        active_threshold_db = ref_db - 48.0
        above_mask = (freqs >= 1000.0) & (smoothed_db >= active_threshold_db)
        cutoff_hz = float(np.max(freqs[above_mask])) if np.any(above_mask) else float(min(nyquist, 4000.0))

        # Measure cliff steepness around estimated cutoff (±1.8 kHz)
        below_band = (freqs >= max(1500.0, cutoff_hz - 1800.0)) & (freqs <= cutoff_hz)
        above_band = (freqs > cutoff_hz + 400.0) & (freqs <= min(nyquist, cutoff_hz + 2200.0))
        cliff_drop_db = 0.0
        if np.any(below_band) and np.any(above_band):
            cliff_drop_db = float(np.max(smoothed_db[below_band]) - np.max(smoothed_db[above_band]))

        # Check active mid-high content (4-10 kHz) to distinguish acoustic/low-treble instruments from brickwall transcodes
        mid_high_mask = (freqs >= 4000.0) & (freqs <= min(10000.0, nyquist))
        mid_high_db = float(np.max(smoothed_db[mid_high_mask])) if np.any(mid_high_mask) else -120.0
        has_rich_upper_mids = (ref_db - mid_high_db) < 38.0

        is_lossless = cls._is_lossless_codec(codec)
        evidence: list[str] = [
            f"Frequência de corte estimada: {cutoff_hz:.0f} Hz (Nyquist: {nyquist:.0f} Hz)",
            f"Queda espectral pós-corte: {cliff_drop_db:.1f} dB",
        ]
        limitations: list[str] = [
            "Análise baseada em janela amostral de até 45s via STFT/Welch.",
            "Gravações acústicas, vintage ou masterizadas com low-pass intencional podem apresentar corte natural.",
        ]

        upscale_status = "UNKNOWN"
        confidence = 0.45
        is_fake = False

        if prior_origin == "LOSSY_SOURCE" and is_lossless is True:
            upscale_status = "LIKELY_UPSCALE"
            confidence = 0.95
            is_fake = True
            evidence.append("Proveniência registrada indica origem originalmente lossy convertida para container lossless.")
        elif is_lossless is False:
            upscale_status = "VERIFIED_LOSSY_SOURCE"
            confidence = 0.95
            is_fake = False
            evidence.append(f"Codec lossy nativo ({codec}, {bitrate_kbps or '?'} kbps).")
        elif is_lossless is True:
            if not has_rich_upper_mids:
                upscale_status = "UNKNOWN"
                confidence = 0.38
                is_fake = False
                evidence.append("Conteúdo com baixa energia natural entre 4–10 kHz (ex.: acústico/vocal/clássico).")
                limitations.append("Evidência insuficiente para distinguir limitação de origem de timbre natural.")
            elif nyquist >= 21000.0 and cutoff_hz < 17600.0 and cliff_drop_db >= 20.0:
                upscale_status = "LIKELY_UPSCALE"
                confidence = round(min(0.92, 0.72 + (cliff_drop_db - 20.0) / 80.0), 2)
                is_fake = True
                evidence.append("Corte abrupto (brickwall) compatível com transcodificação MP3/AAC prévia.")
            elif nyquist >= 21000.0 and cutoff_hz < 18500.0 and cliff_drop_db >= 12.0:
                upscale_status = "SUSPECTED_UPSCALE"
                confidence = 0.62
                is_fake = True
                evidence.append("Corte espectral moderado abaixo de 18.5 kHz em arquivo lossless.")
            elif cutoff_hz >= 19200.0:
                upscale_status = "VERIFIED_LOSSLESS_SOURCE"
                confidence = 0.90 if cutoff_hz >= 20000.0 else 0.80
                is_fake = False
                evidence.append("Energia espectral preservada até próximo da frequência de Nyquist.")
            else:
                upscale_status = "UNKNOWN"
                confidence = 0.50
                is_fake = False
                evidence.append("Decaimento espectral gradual sem assinatura conclusiva de encoder lossy.")

        return SpectralQualityResult(
            spectral_cutoff_hz=round(cutoff_hz, 1),
            nyquist_hz=round(nyquist, 1),
            upscale_status=upscale_status,
            confidence=round(confidence, 2),
            is_fake_upscale=is_fake,
            sub_bass_energy=sub_norm,
            mid_bass_energy=mid_bass_norm,
            midrange_energy=mid_norm,
            high_freq_energy=high_norm,
            evidence=evidence,
            limitations=limitations,
        )

    def compute_car_audio_score(
        self,
        track: UnifiedTrack,
        origin_classification: str,
        spectral: Optional[SpectralQualityResult] = None,
    ) -> dict[str, Any]:
        """Compute explainable Car Audio technical readiness score (0-100) without penalizing low sub-bass."""
        w = self.weights
        score = 100.0
        penalties: list[dict[str, Any]] = []
        positives: list[str] = []

        if track.is_corrupted:
            score -= w.corrupted_penalty
            penalties.append({"criterion": "file_integrity", "points": -w.corrupted_penalty, "reason": "Arquivo corrompido ou ilegível."})

        is_prev = bool(track.is_preview or (track.duration_ms and track.duration_ms < 45000 and track.preview_url and not track.local_path))
        if is_prev:
            score -= w.preview_penalty
            penalties.append({"criterion": "preview_only", "points": -w.preview_penalty, "reason": "Apenas prévia de catálogo (não é arquivo completo)."})

        clips = track.clipping_count or 0
        if clips > 50:
            score -= w.severe_clipping_penalty
            penalties.append({"criterion": "clipping", "points": -w.severe_clipping_penalty, "reason": f"Clipping severo detectado ({clips} amostras)."})
        elif clips > 0:
            score -= w.moderate_clipping_penalty
            penalties.append({"criterion": "clipping", "points": -w.moderate_clipping_penalty, "reason": f"Clipping leve detectado ({clips} amostras)."})
        elif track.analyzed_at is not None:
            positives.append("Zero amostras de clipping detectadas pelo FFmpeg.")

        if track.true_peak_dbfs is not None:
            if track.true_peak_dbfs > 0.0:
                score -= w.true_peak_over_zero_penalty
                penalties.append({"criterion": "true_peak", "points": -w.true_peak_over_zero_penalty, "reason": f"True Peak acima de 0 dBFS ({track.true_peak_dbfs:.2f} dBFS) pode distorcer DACs automotivos."})
            elif track.true_peak_dbfs > -0.3:
                score -= w.true_peak_hot_penalty
                penalties.append({"criterion": "true_peak", "points": -w.true_peak_hot_penalty, "reason": f"True Peak muito próximo de 0 dBFS ({track.true_peak_dbfs:.2f} dBFS)."})
            else:
                positives.append(f"Headroom seguro de True Peak ({track.true_peak_dbfs:.2f} dBFS).")

        if track.dynamic_range_db is not None:
            if track.dynamic_range_db < 4.0:
                score -= w.low_dynamic_range_penalty
                penalties.append({"criterion": "dynamic_range", "points": -w.low_dynamic_range_penalty, "reason": f"Dynamic Range muito comprimido ({track.dynamic_range_db:.1f} dB)."})
            elif track.dynamic_range_db >= 7.0:
                positives.append(f"Dinâmica saudável ({track.dynamic_range_db:.1f} dB).")

        if track.integrated_lufs is not None and track.integrated_lufs > -6.5:
            score -= w.extreme_loudness_penalty
            penalties.append({"criterion": "loudness", "points": -w.extreme_loudness_penalty, "reason": f"Loudness extremo ({track.integrated_lufs:.1f} LUFS) reduz margem dinâmica."})

        upscale_status = spectral.upscale_status if spectral else track.upscale_status
        if upscale_status == "LIKELY_UPSCALE":
            score -= w.fake_upscale_penalty
            penalties.append({"criterion": "fake_upscale", "points": -w.fake_upscale_penalty, "reason": "Indício forte de transcodificação lossy empacotada em container lossless."})
        elif upscale_status == "SUSPECTED_UPSCALE":
            score -= w.suspected_upscale_penalty
            penalties.append({"criterion": "fake_upscale", "points": -w.suspected_upscale_penalty, "reason": "Corte espectral suspeito de possível upscale."})

        is_lossless = self._is_lossless_codec(track.codec)
        if is_lossless is False and track.bitrate_kbps:
            if track.bitrate_kbps < 160:
                score -= w.low_bitrate_penalty
                penalties.append({"criterion": "bitrate", "points": -w.low_bitrate_penalty, "reason": f"Bitrate lossy baixo ({track.bitrate_kbps} kbps)."})
            elif track.bitrate_kbps < 256:
                score -= w.medium_lossy_bitrate_penalty
                penalties.append({"criterion": "bitrate", "points": -w.medium_lossy_bitrate_penalty, "reason": f"Bitrate lossy intermediário ({track.bitrate_kbps} kbps)."})
            elif track.bitrate_kbps >= 320:
                positives.append(f"Bitrate lossy elevado ({track.bitrate_kbps} kbps).")

        if origin_classification == "LOSSLESS_SOURCE":
            positives.append("Origem lossless verificada por análise espectral e cabeçalho.")

        final_score = round(max(0.0, min(100.0, score)), 1)
        if track.is_corrupted:
            status = "POOR"
        elif final_score >= 85.0:
            status = "EXCELLENT"
        elif final_score >= 70.0:
            status = "GOOD"
        elif final_score >= 55.0:
            status = "ACCEPTABLE"
        elif final_score >= 35.0:
            status = "REVIEW_REQUIRED"
        else:
            status = "POOR"

        car_ready = bool(
            not track.is_corrupted
            and not is_prev
            and final_score >= w.ready_min_score
            and upscale_status != "LIKELY_UPSCALE"
            and clips <= 20
        )

        return {
            "car_audio_score": final_score,
            "car_audio_status": status,
            "car_audio_ready": car_ready,
            "penalties": penalties,
            "positives": positives,
            "weights_used": asdict(w),
            "note": "Score técnico de reprodução automotiva; não penaliza baixa energia de subgrave nem mede preferência musical.",
        }

    def record_provenance(
        self,
        session: Session,
        track: UnifiedTrack,
        acquisition_source: str = "local_scan",
        provider: Optional[str] = None,
        source_url: Optional[str] = None,
        requested_profile: Optional[str] = None,
        origin_classification: Optional[str] = None,
        evidence: Optional[list[str]] = None,
    ) -> AudioProvenance:
        """Create or update structured AudioProvenance while preserving prior lossy origin."""
        existing = session.exec(
            select(AudioProvenance).where(AudioProvenance.track_id == track.id)
        ).first()

        now = datetime.now(timezone.utc)
        if existing:
            # Never erase known LOSSY_SOURCE origin when converting to a lossless container
            if existing.origin_classification == "LOSSY_SOURCE":
                final_origin = "LOSSY_SOURCE"
            elif origin_classification and origin_classification != "UNKNOWN_SOURCE":
                final_origin = origin_classification
            else:
                final_origin = existing.origin_classification

            existing.current_container = Path(track.local_path).suffix.lstrip(".").lower() if track.local_path else existing.current_container
            existing.current_codec = track.codec or existing.current_codec
            if requested_profile:
                existing.requested_profile = requested_profile
            if provider and not existing.provider:
                existing.provider = provider
            if source_url and not existing.source_url:
                existing.source_url = source_url
            existing.origin_classification = final_origin
            if evidence is not None:
                existing.evidence_json = json.dumps(evidence, ensure_ascii=False)
            existing.analyzed_at = now
            existing.updated_at = now
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing

        container = Path(track.local_path).suffix.lstrip(".").lower() if track.local_path else None
        prov = AudioProvenance(
            track_id=track.id or 0,
            acquisition_source=acquisition_source,
            provider=provider,
            source_url=source_url,
            original_codec=track.codec,
            original_bitrate_kbps=track.bitrate_kbps,
            original_sample_rate_hz=track.sample_rate_hz,
            original_bit_depth=track.bit_depth,
            origin_classification=origin_classification or "UNKNOWN_SOURCE",
            current_container=container,
            current_codec=track.codec,
            requested_profile=requested_profile,
            evidence_json=json.dumps(evidence or [], ensure_ascii=False),
            engine_name=self.ENGINE_NAME,
            engine_version=self.ENGINE_VERSION,
            acquired_at=now,
            analyzed_at=now,
            updated_at=now,
        )
        session.add(prov)
        session.commit()
        session.refresh(prov)
        return prov

    def record_processing_event(
        self,
        session: Session,
        track_id: int,
        operation: str,
        provenance_id: Optional[int] = None,
        from_codec: Optional[str] = None,
        to_codec: Optional[str] = None,
        from_bitrate_kbps: Optional[int] = None,
        to_bitrate_kbps: Optional[int] = None,
        profile: Optional[str] = None,
        source_path: Optional[str] = None,
        dest_path: Optional[str] = None,
        backup_path: Optional[str] = None,
        was_lossy_to_lossless: bool = False,
        warnings: Optional[list[str]] = None,
        engine_name: str = "AudioQualityIntelligenceEngine",
    ) -> AudioProcessingHistory:
        """Append immutable processing history record."""
        item = AudioProcessingHistory(
            track_id=track_id,
            provenance_id=provenance_id,
            operation=operation,
            from_codec=from_codec,
            to_codec=to_codec,
            from_bitrate_kbps=from_bitrate_kbps,
            to_bitrate_kbps=to_bitrate_kbps,
            profile=profile,
            source_path=source_path,
            dest_path=dest_path,
            backup_path=backup_path,
            was_lossy_to_lossless=was_lossy_to_lossless,
            warnings_json=json.dumps(warnings or [], ensure_ascii=False),
            engine_name=engine_name,
            engine_version=self.ENGINE_VERSION,
            created_at=datetime.now(timezone.utc),
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item

    async def analyze_track_quality(
        self,
        track: UnifiedTrack,
        session: Session,
        force: bool = False,
    ) -> dict[str, Any]:
        """Execute full Layer-1 technical + spectral + provenance + Car Audio Intelligence pipeline."""
        if track.quality_analyzed_at is not None and not force:
            return self.build_quality_report(track, session)

        if track.local_path and Path(track.local_path).exists():
            await self.tech_engine.analyze_and_persist(track, session, force=force)
            session.refresh(track)
        elif track.local_path:
            track.is_corrupted = True
            track.quality_warning = "Arquivo local ausente no disco."

        prior_prov = session.exec(
            select(AudioProvenance).where(AudioProvenance.track_id == track.id)
        ).first()
        prior_origin = prior_prov.origin_classification if prior_prov else None

        spectral: Optional[SpectralQualityResult] = None
        if track.local_path and Path(track.local_path).exists() and not track.is_corrupted:
            spectral = await asyncio.to_thread(
                self._analyze_spectrum_sync,
                Path(track.local_path),
                track.codec,
                track.bitrate_kbps,
                prior_origin,
            )

        upscale_status = spectral.upscale_status if spectral else "UNKNOWN"
        origin_cls = self.classify_origin(track.codec, prior_prov, upscale_status)

        if spectral:
            track.spectral_cutoff_hz = spectral.spectral_cutoff_hz
            track.upscale_status = spectral.upscale_status
            track.upscale_confidence = spectral.confidence
            track.is_fake_upscale = spectral.is_fake_upscale
            track.sub_bass_energy = spectral.sub_bass_energy
            track.mid_bass_energy = spectral.mid_bass_energy
            track.midrange_energy = spectral.midrange_energy
            track.high_freq_energy = spectral.high_freq_energy
        else:
            track.upscale_status = upscale_status
            track.upscale_confidence = 0.0
            track.is_fake_upscale = False

        track.source_classification = origin_cls
        if track.duration_ms and track.duration_ms < 45000 and track.preview_url and not track.local_path:
            track.is_preview = True

        car_eval = self.compute_car_audio_score(track, origin_cls, spectral)
        track.car_audio_score = car_eval["car_audio_score"]
        track.car_audio_status = car_eval["car_audio_status"]
        track.car_audio_ready = car_eval["car_audio_ready"]

        intel_payload = {
            "origin_classification": origin_cls,
            "spectral": asdict(spectral) if spectral else None,
            "car_audio": car_eval,
            "engine": self.ENGINE_NAME,
            "version": self.ENGINE_VERSION,
        }
        track.quality_intelligence_json = json.dumps(intel_payload, ensure_ascii=False)
        track.quality_analyzed_at = datetime.now(timezone.utc)
        track.updated_at = datetime.now(timezone.utc)

        session.add(track)
        session.commit()
        session.refresh(track)

        prov = self.record_provenance(
            session=session,
            track=track,
            acquisition_source=prior_prov.acquisition_source if prior_prov else ("local_scan" if track.local_path else "online_import"),
            origin_classification=origin_cls,
            evidence=spectral.evidence if spectral else ["Sem arquivo local para análise espectral."],
        )
        self.record_processing_event(
            session=session,
            track_id=track.id or 0,
            operation="quality_analyze",
            provenance_id=prov.id,
            from_codec=track.codec,
            to_codec=track.codec,
            from_bitrate_kbps=track.bitrate_kbps,
            to_bitrate_kbps=track.bitrate_kbps,
            source_path=track.local_path,
            warnings=spectral.limitations if spectral else [],
            engine_name=self.ENGINE_NAME,
        )

        return self.build_quality_report(track, session)

    def build_quality_report(self, track: UnifiedTrack, session: Session) -> dict[str, Any]:
        """Return structured Quality Intelligence + Provenance + History payload for API/UI."""
        prov = session.exec(
            select(AudioProvenance).where(AudioProvenance.track_id == track.id)
        ).first()
        history = session.exec(
            select(AudioProcessingHistory)
            .where(AudioProcessingHistory.track_id == track.id)
            .order_by(AudioProcessingHistory.created_at.desc())
        ).all()

        intel = {}
        if track.quality_intelligence_json:
            try:
                intel = json.loads(track.quality_intelligence_json)
            except Exception:
                intel = {}

        return {
            "track_id": track.id,
            "title": track.title,
            "artist": track.artist,
            "file": {
                "local_path": track.local_path,
                "exists": bool(track.local_path and Path(track.local_path).exists()),
                "is_preview": track.is_preview,
                "is_corrupted": track.is_corrupted,
                "codec": track.codec,
                "bitrate_kbps": track.bitrate_kbps,
                "sample_rate_hz": track.sample_rate_hz,
                "bit_depth": track.bit_depth,
                "channels": track.channels,
                "file_size_bytes": track.file_size_bytes,
                "duration_ms": track.duration_ms,
            },
            "technical": {
                "integrated_lufs": track.integrated_lufs,
                "momentary_lufs": track.momentary_lufs,
                "short_term_lufs": track.short_term_lufs,
                "loudness_range_lu": track.loudness_range_lu,
                "true_peak_dbfs": track.true_peak_dbfs,
                "dynamic_range_db": track.dynamic_range_db,
                "crest_factor_db": track.crest_factor_db,
                "replay_gain": track.replay_gain,
                "clipping_count": track.clipping_count,
                "silence_start_ms": track.silence_start_ms,
                "silence_end_ms": track.silence_end_ms,
                "quality_warning": track.quality_warning,
            },
            "quality_intelligence": {
                "source_classification": track.source_classification or "UNKNOWN_SOURCE",
                "spectral_cutoff_hz": track.spectral_cutoff_hz,
                "upscale_status": track.upscale_status or "UNKNOWN",
                "upscale_confidence": track.upscale_confidence,
                "is_fake_upscale": track.is_fake_upscale,
                "bass_profile": {
                    "sub_bass_20_60": track.sub_bass_energy,
                    "mid_bass_60_250": track.mid_bass_energy,
                    "midrange_250_4000": track.midrange_energy,
                    "high_freq_4000_20000": track.high_freq_energy,
                },
                "car_audio_score": track.car_audio_score,
                "car_audio_status": track.car_audio_status,
                "car_audio_ready": track.car_audio_ready,
                "details": intel,
                "quality_analyzed_at": track.quality_analyzed_at,
            },
            "provenance": prov.model_dump() if prov else None,
            "processing_history": [h.model_dump() for h in history],
        }

    async def analyze_library_quality(
        self,
        session_factory: Callable[[], Session],
        force: bool = False,
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
    ) -> dict[str, int]:
        """Batch-analyze all library tracks for Quality Intelligence without blocking the event loop."""
        stats = {"total": 0, "analyzed": 0, "skipped": 0, "failed": 0}
        with session_factory() as session:
            ids = [t.id for t in session.exec(select(UnifiedTrack)).all() if t.id is not None]

        stats["total"] = len(ids)
        for idx, tid in enumerate(ids, start=1):
            with session_factory() as session:
                trk = session.get(UnifiedTrack, tid)
                if not trk:
                    continue
                if trk.quality_analyzed_at is not None and not force:
                    stats["skipped"] += 1
                    continue
                try:
                    await self.analyze_track_quality(trk, session, force=force)
                    stats["analyzed"] += 1
                except Exception as e:
                    print(f"[AudioQualityIntelligence] Batch error track {tid}: {e}")
                    stats["failed"] += 1
                if progress_callback:
                    progress_callback(idx, stats["total"], trk.title)
        return stats

    def get_quality_dashboard(self, session: Session) -> dict[str, Any]:
        """Aggregate real Quality Dashboard metrics and distributions across the entire library."""
        tracks = session.exec(select(UnifiedTrack)).all()
        total = len(tracks)

        complete_files = 0
        previews = 0
        missing_files = 0
        lossless_source = 0
        lossy_source = 0
        unknown_source = 0
        suspected_fake_upscale = 0
        corrupted = 0
        clipping = 0
        critical_true_peak = 0
        unanalyzed = 0
        upgrades_available = 0
        car_scores: list[float] = []

        codec_dist: dict[str, int] = {}
        bitrate_dist = {"<128k": 0, "128k-255k": 0, "256k-320k": 0, "Lossless": 0, "Desconhecido": 0}
        sr_dist: dict[str, int] = {}
        car_status_dist: dict[str, int] = {}

        for t in tracks:
            has_local = bool(t.local_path and Path(t.local_path).exists())
            if t.local_path and not has_local:
                missing_files += 1
            elif t.is_preview or (not has_local and t.preview_url):
                previews += 1
            elif has_local:
                complete_files += 1

            if t.is_corrupted:
                corrupted += 1
            if (t.clipping_count or 0) > 0:
                clipping += 1
            if t.true_peak_dbfs is not None and t.true_peak_dbfs > -0.1:
                critical_true_peak += 1
            if t.quality_analyzed_at is None:
                unanalyzed += 1

            src_cls = t.source_classification or "UNKNOWN_SOURCE"
            if src_cls == "LOSSLESS_SOURCE":
                lossless_source += 1
            elif src_cls == "LOSSY_SOURCE":
                lossy_source += 1
            else:
                unknown_source += 1

            if t.is_fake_upscale or t.upscale_status in ("LIKELY_UPSCALE", "SUSPECTED_UPSCALE"):
                suspected_fake_upscale += 1

            if (
                t.is_preview
                or (t.is_fake_upscale)
                or (t.bitrate_kbps is not None and 0 < t.bitrate_kbps < 256 and self._is_lossless_codec(t.codec) is False)
            ):
                upgrades_available += 1

            if t.car_audio_score is not None:
                car_scores.append(t.car_audio_score)
            if t.car_audio_status:
                car_status_dist[t.car_audio_status] = car_status_dist.get(t.car_audio_status, 0) + 1

            c_key = (t.codec or "DESCONHECIDO").upper()
            codec_dist[c_key] = codec_dist.get(c_key, 0) + 1

            if self._is_lossless_codec(t.codec) is True:
                bitrate_dist["Lossless"] += 1
            elif t.bitrate_kbps is None or t.bitrate_kbps <= 0:
                bitrate_dist["Desconhecido"] += 1
            elif t.bitrate_kbps < 128:
                bitrate_dist["<128k"] += 1
            elif t.bitrate_kbps < 256:
                bitrate_dist["128k-255k"] += 1
            else:
                bitrate_dist["256k-320k"] += 1

            sr_key = f"{t.sample_rate_hz} Hz" if t.sample_rate_hz else "Desconhecido"
            sr_dist[sr_key] = sr_dist.get(sr_key, 0) + 1

        avg_car = round(sum(car_scores) / len(car_scores), 1) if car_scores else None
        return {
            "total_tracks": total,
            "complete_files": complete_files,
            "previews": previews,
            "missing_files": missing_files,
            "lossless_source": lossless_source,
            "lossy_source": lossy_source,
            "unknown_source": unknown_source,
            "suspected_fake_upscale": suspected_fake_upscale,
            "corrupted": corrupted,
            "clipping": clipping,
            "critical_true_peak": critical_true_peak,
            "unanalyzed": unanalyzed,
            "upgrades_available": upgrades_available,
            "avg_car_audio_score": avg_car,
            "codec_distribution": codec_dist,
            "bitrate_distribution": bitrate_dist,
            "sample_rate_distribution": sr_dist,
            "car_audio_status_distribution": car_status_dist,
        }
