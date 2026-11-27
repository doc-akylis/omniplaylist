"""Explainable multi-source audio quality, identity, and authorization comparator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.sources.base import (
    GroupedRecording,
    NormalizedTrackResult,
    PermissionStatus,
    ProviderCategory,
)


@dataclass
class ComparatorWeights:
    """Configurable weighting across identity, technical quality, and origin reliability."""

    identity_weight: float = 0.25
    technical_weight: float = 0.50
    reliability_weight: float = 0.25
    prefer_free_bonus: float = 4.0
    transcode_penalty: float = 48.0


class CandidateScoreBreakdown(BaseModel):
    """Detailed score breakdown for one candidate source within a grouped recording."""

    provider_id: str
    provider_name: str
    category: ProviderCategory
    source_item_id: str
    title: str
    artist: str
    version_type: str
    downloadable: bool
    permission_status: PermissionStatus
    requires_payment: bool
    requires_credentials: bool
    estimated_cost_label: Optional[str] = None
    license_info: Optional[str] = None
    declared_codec: Optional[str] = None
    declared_bitrate_kbps: Optional[int] = None
    declared_sample_rate_hz: Optional[int] = None
    declared_bit_depth: Optional[int] = None
    origin_classification: str = "UNKNOWN_SOURCE"
    suspected_transcode: bool = False
    identity_score: float
    technical_score: float
    reliability_score: float
    total_score: float
    download_url: Optional[str] = None
    preview_url: Optional[str] = None
    explanation: list[str] = Field(default_factory=list)


class SourceComparisonResult(BaseModel):
    """Complete multi-source comparison decision for a grouped recording."""

    group_key: str
    best_authorized: Optional[CandidateScoreBreakdown] = None
    best_free: Optional[CandidateScoreBreakdown] = None
    best_commercial: Optional[CandidateScoreBreakdown] = None
    best_quality_overall: Optional[CandidateScoreBreakdown] = None
    has_authorized_download: bool = False
    selection_reason: str = ""
    ranked_candidates: list[CandidateScoreBreakdown] = Field(default_factory=list)


class SourceQualityComparator:
    """Compares candidate sources across authorization, technical fidelity, transcode risk, and provenance."""

    LOSSLESS_CODECS = {"flac", "wav", "aiff", "alac", "pcm", "pcm_s16le", "pcm_s24le", "pcm_f32le"}
    HIGH_LOSSY_CODECS = {"mp3", "aac", "m4a", "ogg", "vorbis", "opus"}

    def __init__(self, weights: Optional[ComparatorWeights] = None):
        self.weights = weights or ComparatorWeights()

    def score_technical_quality(self, candidate: NormalizedTrackResult) -> tuple[float, list[str]]:
        """Score declared technical audio quality and strongly penalize suspected transcodes."""
        notes: list[str] = []
        codec = (candidate.declared_codec or "").strip().lower()
        bitrate = candidate.declared_bitrate_kbps
        sr = candidate.declared_sample_rate_hz
        bd = candidate.declared_bit_depth

        if not codec and candidate.formats:
            # Inspect highest format option declared by adapter
            top_fmt = candidate.formats[0]
            codec = (top_fmt.codec or "").strip().lower()
            bitrate = bitrate or top_fmt.bitrate_kbps
            sr = sr or top_fmt.sample_rate_hz
            bd = bd or top_fmt.bit_depth

        if candidate.is_preview_only or candidate.permission.status == PermissionStatus.PREVIEW_ONLY:
            notes.append("Apenas prévia de catálogo (30s) — não representa faixa completa.")
            return 15.0, notes

        base_score = 45.0
        if codec in self.LOSSLESS_CODECS:
            base_score = 92.0
            if (bd and bd >= 24) or (sr and sr >= 48000):
                base_score = 98.0
                notes.append(f"Áudio lossless Hi-Res declarado ({codec.upper()} {bd or 16}-bit/{sr or 44100}Hz).")
            else:
                notes.append(f"Áudio lossless declarado ({codec.upper()}).")
        elif codec in self.HIGH_LOSSY_CODECS:
            if bitrate and bitrate >= 320:
                base_score = 82.0
                notes.append(f"Lossy de alta fidelidade ({codec.upper()} {bitrate} kbps).")
            elif bitrate and bitrate >= 256:
                base_score = 74.0
                notes.append(f"Lossy bom ({codec.upper()} {bitrate} kbps).")
            elif bitrate and bitrate >= 160:
                base_score = 62.0
                notes.append(f"Lossy intermediário ({codec.upper()} {bitrate} kbps).")
            elif bitrate:
                base_score = 42.0
                notes.append(f"Lossy de bitrate baixo ({codec.upper()} {bitrate} kbps).")
            else:
                base_score = 56.0
                notes.append(f"Codec lossy declarado ({codec.upper()}, bitrate não informado).")
        elif codec:
            base_score = 52.0
            notes.append(f"Codec declarado: {codec.upper()}.")
        else:
            notes.append("Codec técnico não especificado pelo provedor antes da inspeção ffprobe.")

        if (
            candidate.suspected_transcode
            or candidate.origin_classification in ("SUSPECTED_TRANSCODE", "FAKE_LOSSLESS")
        ):
            base_score = max(10.0, base_score - self.weights.transcode_penalty)
            notes.append(
                "Penalizado: forte indício de transcodificação / derivado lossy empacotado como lossless."
            )

        return round(min(100.0, max(0.0, base_score)), 2), notes

    def score_identity(self, candidate: NormalizedTrackResult, group: GroupedRecording) -> tuple[float, list[str]]:
        """Score how faithfully the candidate matches the grouped recording and version."""
        notes: list[str] = []
        score = 72.0

        if group.isrc and candidate.isrc and group.isrc.upper() == candidate.isrc.upper():
            score += 18.0
            notes.append("ISRC correspondente exatamente ao grupo.")
        elif group.mbid and candidate.mbid and group.mbid.lower() == candidate.mbid.lower():
            score += 14.0
            notes.append("MusicBrainz Recording ID correspondente.")

        if candidate.version_type == group.version_type:
            score += 10.0
        else:
            score -= 20.0
            notes.append(f"Divergência de versão ({candidate.version_type} vs {group.version_type}).")

        if group.duration_ms and candidate.duration_ms:
            diff_sec = abs(group.duration_ms - candidate.duration_ms) / 1000.0
            if diff_sec <= 3.0:
                score += 4.0
            elif diff_sec > 10.0:
                score -= 12.0
                notes.append(f"Diferença de duração elevada ({diff_sec:.1f}s).")

        return round(min(100.0, max(0.0, score)), 2), notes

    def score_reliability(self, candidate: NormalizedTrackResult) -> tuple[float, list[str]]:
        """Score source authorization, licensing clarity, and origin trust."""
        notes: list[str] = []
        perm = candidate.permission
        score = 35.0

        if perm.downloadable and perm.status == PermissionStatus.ALLOWED_FREE:
            score = 86.0
            notes.append(f"Download gratuito autorizado ({perm.license_name or 'licença verificada'}).")
        elif perm.downloadable and perm.status == PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL:
            score = 92.0
            notes.append("Entrega comercial B2B oficial (requer aprovação explícita do usuário).")
        elif perm.status == PermissionStatus.REQUIRES_CREDENTIALS:
            score = 40.0
            notes.append("Requer credenciais configuradas no ambiente para entrega.")
        elif perm.status == PermissionStatus.PREVIEW_ONLY:
            score = 22.0
            notes.append("Apenas prévia de catálogo (30s).")
        elif perm.status == PermissionStatus.STREAMING_ONLY:
            score = 25.0
            notes.append("Plataforma apenas de streaming/descoberta; download proibido pelos termos.")
        else:
            score = 20.0
            notes.append(perm.reason or "Fonte não disponibiliza arquivo completo para download.")

        if candidate.origin_classification == "LOSSLESS_SOURCE":
            score = min(100.0, score + 8.0)
        elif candidate.origin_classification == "SUSPECTED_TRANSCODE":
            score = max(10.0, score - 25.0)
        elif candidate.origin_classification == "LOSSY_SOURCE":
            score = min(100.0, score + 2.0)

        if candidate.is_preview_only:
            score = min(score, 20.0)

        return round(min(100.0, max(0.0, score)), 2), notes

    @staticmethod
    def is_candidate_downloadable(candidate: NormalizedTrackResult) -> bool:
        """Mandatory prerequisite gate: source must explicitly allow full track download."""
        if candidate.is_preview_only:
            return False
        if not candidate.download_url:
            return False
        if not candidate.permission.downloadable:
            return False
        return candidate.permission.status in (
            PermissionStatus.ALLOWED_FREE,
            PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL,
        )

    def compare_group(self, group: GroupedRecording) -> SourceComparisonResult:
        """Rank all candidates in a recording group and pick best authorized/free/commercial/overall."""
        w = self.weights
        breakdowns: list[CandidateScoreBreakdown] = []

        for cand in group.candidates:
            id_score, id_notes = self.score_identity(cand, group)
            tech_score, tech_notes = self.score_technical_quality(cand)
            rel_score, rel_notes = self.score_reliability(cand)

            total = (
                id_score * w.identity_weight
                + tech_score * w.technical_weight
                + rel_score * w.reliability_weight
            )
            dl_ok = self.is_candidate_downloadable(cand)
            if dl_ok and cand.permission.status == PermissionStatus.ALLOWED_FREE:
                total += w.prefer_free_bonus

            breakdowns.append(
                CandidateScoreBreakdown(
                    provider_id=cand.provider_id,
                    provider_name=cand.provider_name,
                    category=cand.category,
                    source_item_id=cand.source_item_id,
                    title=cand.title,
                    artist=cand.artist,
                    version_type=cand.version_type,
                    downloadable=dl_ok,
                    permission_status=cand.permission.status,
                    requires_payment=cand.requires_payment or cand.permission.requires_payment,
                    requires_credentials=cand.permission.requires_credentials,
                    estimated_cost_label=cand.estimated_cost_label or cand.permission.estimated_cost_label,
                    license_info=cand.license_info or cand.permission.license_name,
                    declared_codec=cand.declared_codec,
                    declared_bitrate_kbps=cand.declared_bitrate_kbps,
                    declared_sample_rate_hz=cand.declared_sample_rate_hz,
                    declared_bit_depth=cand.declared_bit_depth,
                    origin_classification=cand.origin_classification,
                    suspected_transcode=cand.suspected_transcode,
                    identity_score=id_score,
                    technical_score=tech_score,
                    reliability_score=rel_score,
                    total_score=round(total, 2),
                    download_url=cand.download_url,
                    preview_url=cand.preview_url,
                    explanation=id_notes + tech_notes + rel_notes,
                )
            )

        # Sort downloadable first, then by total_score desc
        ranked = sorted(
            breakdowns,
            key=lambda b: (1 if b.downloadable else 0, b.total_score, b.technical_score),
            reverse=True,
        )
        downloadables = [b for b in ranked if b.downloadable]
        free_list = [b for b in downloadables if b.permission_status == PermissionStatus.ALLOWED_FREE]
        comm_list = [
            b for b in downloadables
            if b.permission_status == PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL
        ]
        overall_tech = max(breakdowns, key=lambda b: (b.technical_score, b.total_score)) if breakdowns else None

        best_auth = downloadables[0] if downloadables else None
        best_free = free_list[0] if free_list else None
        best_comm = comm_list[0] if comm_list else None

        if best_auth:
            reason = (
                f"Selecionado {best_auth.provider_name} ({(best_auth.declared_codec or 'N/A').upper()}"
                f"{f' {best_auth.declared_bitrate_kbps} kbps' if best_auth.declared_bitrate_kbps else ''}"
                f", score {best_auth.total_score})."
            )
        else:
            reason = "Nenhuma fonte gratuita ou comercial com download autorizado direto disponível neste grupo (apenas catálogo/prévia)."

        return SourceComparisonResult(
            group_key=group.group_key,
            best_authorized=best_auth,
            best_free=best_free,
            best_commercial=best_comm,
            best_quality_overall=overall_tech,
            has_authorized_download=best_auth is not None,
            selection_reason=reason,
            ranked_candidates=ranked,
        )
