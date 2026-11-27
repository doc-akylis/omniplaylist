from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Optional
from pydantic import BaseModel
from rapidfuzz import fuzz

from app.core.models import AudioProvenance, UnifiedTrack
from app.engines.audio_quality_intelligence import LOSSLESS_CODECS
from app.engines.conversion_engine import ConversionEngine

UPGRADE_DECISIONS = {
    "NO_UPGRADE_NEEDED",
    "UPGRADE_AVAILABLE",
    "POSSIBLE_UPGRADE",
    "NO_QUALITY_IMPROVEMENT",
    "DIFFERENT_VERSION",
    "SOURCE_UNVERIFIED",
    "REVIEW_REQUIRED",
}


class CandidateSource(BaseModel):
    """Metadata and technical descriptor of a candidate audio source for acquisition or upgrade."""

    provider: str = "authorized_url"
    source_url: Optional[str] = None
    local_source_path: Optional[str] = None
    title: str
    artist: str
    isrc: Optional[str] = None
    acoustid_id: Optional[str] = None
    duration_ms: Optional[int] = None
    codec: Optional[str] = None
    bitrate_kbps: Optional[int] = None
    sample_rate_hz: Optional[int] = None
    bit_depth: Optional[int] = None
    is_preview: bool = False
    origin_classification: str = "UNKNOWN_SOURCE"
    verified_source: bool = True


@dataclass
class UpgradeEvaluation:
    """Explainable decision from comparing an existing track against a candidate source."""

    decision: str
    is_justified: bool
    reason: str
    warnings: list[str] = field(default_factory=list)
    existing_rank: int = 0
    candidate_rank: int = 0


class UpgradeEngine:
    """Evaluates whether acquiring/converting a candidate source produces a genuine audio quality upgrade."""

    @staticmethod
    def _is_lossless(codec: Optional[str]) -> bool:
        if not codec:
            return False
        c = codec.strip().lower()
        return c in LOSSLESS_CODECS or c.startswith("pcm_")

    @staticmethod
    def _clean_text(val: Optional[str]) -> str:
        return " ".join(re.sub(r"[^\w\s]", " ", (val or "").lower()).split())

    @classmethod
    def quality_tier_rank(
        cls,
        codec: Optional[str],
        bitrate_kbps: Optional[int],
        sample_rate_hz: Optional[int],
        bit_depth: Optional[int],
        is_preview: bool,
        origin_classification: Optional[str],
        is_fake_upscale: bool = False,
    ) -> int:
        """Compute comparable technical tier rank without trusting fake lossless containers."""
        if is_preview:
            return 10
        if is_fake_upscale or origin_classification == "LOSSY_SOURCE":
            # Fake upscale or known lossy origin cannot rank above high-bitrate lossy
            if bitrate_kbps and bitrate_kbps < 192:
                return 25
            return 45
        if cls._is_lossless(codec):
            base = 80
            if bit_depth and bit_depth >= 24:
                base += 8
            if sample_rate_hz and sample_rate_hz >= 48000:
                base += 5
            return base
        br = bitrate_kbps or 0
        if br >= 300:
            return 55
        if br >= 220:
            return 45
        if br >= 160:
            return 35
        if br > 0:
            return 22
        return 30

    def evaluate_upgrade(
        self,
        existing_track: Optional[UnifiedTrack],
        candidate: CandidateSource,
        requested_profile: str = "ORIGINAL",
        existing_provenance: Optional[AudioProvenance] = None,
    ) -> UpgradeEvaluation:
        """Compare existing track & provenance against candidate source and requested profile."""
        profile = ConversionEngine.get_profile(requested_profile)
        warnings: list[str] = []

        if candidate.is_preview:
            return UpgradeEvaluation(
                decision="NO_QUALITY_IMPROVEMENT",
                is_justified=False,
                reason="A fonte candidata é apenas uma prévia (preview) e não um arquivo completo.",
                warnings=["Fontes de catálogo (ex.: iTunes/Deezer) fornecem apenas prévias de 30s sem áudio completo autorizado."],
            )

        if not candidate.verified_source and candidate.origin_classification == "UNKNOWN_SOURCE":
            return UpgradeEvaluation(
                decision="SOURCE_UNVERIFIED",
                is_justified=False,
                reason="Origem da fonte candidata não verificada; não é possível comprovar melhoria real.",
            )

        # Fresh acquisition when no local track exists yet
        if existing_track is None or not existing_track.local_path or not Path(existing_track.local_path).exists():
            if not candidate.codec and not candidate.bitrate_kbps and candidate.origin_classification == "UNKNOWN_SOURCE":
                return UpgradeEvaluation(
                    decision="POSSIBLE_UPGRADE",
                    is_justified=True,
                    reason="Nenhum arquivo local completo encontrado; aquisição inicial recomendada (metadados técnicos da origem pendentes).",
                )
            return UpgradeEvaluation(
                decision="UPGRADE_AVAILABLE",
                is_justified=True,
                reason="Faixa ainda não possui arquivo local completo; fonte disponível para aquisição.",
            )

        # 1. Check track identity / version equivalence (ISRC, AcoustID, fuzzy title/artist, duration)
        same_isrc = bool(
            existing_track.isrc
            and candidate.isrc
            and existing_track.isrc.strip().upper() == candidate.isrc.strip().upper()
        )
        same_acoustid = bool(
            existing_track.acoustid_id
            and candidate.acoustid_id
            and existing_track.acoustid_id == candidate.acoustid_id
        )
        if not same_isrc and not same_acoustid:
            title_sim = fuzz.token_sort_ratio(
                self._clean_text(existing_track.title),
                self._clean_text(candidate.title),
            )
            artist_sim = fuzz.token_sort_ratio(
                self._clean_text(existing_track.artist),
                self._clean_text(candidate.artist),
            )
            if title_sim < 80 or artist_sim < 75:
                return UpgradeEvaluation(
                    decision="DIFFERENT_VERSION",
                    is_justified=False,
                    reason=f"Título/artista da fonte candidata divergem do arquivo atual (sim: título {title_sim}%, artista {artist_sim}%).",
                )

        if existing_track.duration_ms and candidate.duration_ms:
            delta_sec = abs(existing_track.duration_ms - candidate.duration_ms) / 1000.0
            if delta_sec > 15.0 and not existing_track.is_preview:
                return UpgradeEvaluation(
                    decision="DIFFERENT_VERSION",
                    is_justified=False,
                    reason=f"Duração diverge em {delta_sec:.1f}s; provável versão diferente (ex.: edit vs extended/live).",
                )

        # 2. Rank comparison
        existing_origin = (
            existing_provenance.origin_classification
            if existing_provenance
            else (existing_track.source_classification or "UNKNOWN_SOURCE")
        )
        existing_rank = self.quality_tier_rank(
            codec=existing_track.codec,
            bitrate_kbps=existing_track.bitrate_kbps,
            sample_rate_hz=existing_track.sample_rate_hz,
            bit_depth=existing_track.bit_depth,
            is_preview=existing_track.is_preview,
            origin_classification=existing_origin,
            is_fake_upscale=existing_track.is_fake_upscale,
        )
        candidate_rank = self.quality_tier_rank(
            codec=candidate.codec,
            bitrate_kbps=candidate.bitrate_kbps,
            sample_rate_hz=candidate.sample_rate_hz,
            bit_depth=candidate.bit_depth,
            is_preview=candidate.is_preview,
            origin_classification=candidate.origin_classification,
            is_fake_upscale=False,
        )

        # Warn explicitly when lossy candidate is requested in higher bitrate / lossless profile
        cand_lossless = self._is_lossless(candidate.codec)
        if not cand_lossless and profile["id"] in ("MP3_320", "FLAC_ARCHIVE", "WAV_16", "WAV_24"):
            if candidate.bitrate_kbps and candidate.bitrate_kbps <= 192:
                warnings.append(
                    f"A fonte candidata ({candidate.codec or 'lossy'} {candidate.bitrate_kbps} kbps) não oferece melhoria real; "
                    f"converter para {profile['name']} não recupera informações perdidas."
                )

        if existing_track.is_preview and not candidate.is_preview:
            return UpgradeEvaluation(
                decision="UPGRADE_AVAILABLE",
                is_justified=True,
                reason="Substitui prévia por arquivo completo de fonte verificável.",
                warnings=warnings,
                existing_rank=existing_rank,
                candidate_rank=candidate_rank,
            )

        if existing_track.is_corrupted:
            return UpgradeEvaluation(
                decision="UPGRADE_AVAILABLE",
                is_justified=True,
                reason="Arquivo atual está corrompido; substituição recomendada.",
                warnings=warnings,
                existing_rank=existing_rank,
                candidate_rank=candidate_rank,
            )

        if candidate_rank > existing_rank + 5:
            return UpgradeEvaluation(
                decision="UPGRADE_AVAILABLE",
                is_justified=True,
                reason=(
                    f"Upgrade real disponível: {existing_track.codec or '?'} ({existing_track.bitrate_kbps or '?'} kbps) "
                    f"→ {candidate.codec or '?'} ({candidate.bitrate_kbps or 'lossless'})."
                ),
                warnings=warnings,
                existing_rank=existing_rank,
                candidate_rank=candidate_rank,
            )

        if candidate_rank == existing_rank and existing_rank >= 80:
            return UpgradeEvaluation(
                decision="NO_UPGRADE_NEEDED",
                is_justified=False,
                reason="Arquivo atual já está em qualidade equivalente ou lossless verificada.",
                warnings=warnings,
                existing_rank=existing_rank,
                candidate_rank=candidate_rank,
            )

        if candidate_rank <= existing_rank:
            return UpgradeEvaluation(
                decision="NO_QUALITY_IMPROVEMENT",
                is_justified=False,
                reason=(
                    f"Fonte candidata ({candidate.codec or '?'} {candidate.bitrate_kbps or '?'} kbps) "
                    f"não supera o arquivo atual ({existing_track.codec or '?'} {existing_track.bitrate_kbps or '?'} kbps)."
                ),
                warnings=warnings,
                existing_rank=existing_rank,
                candidate_rank=candidate_rank,
            )

        return UpgradeEvaluation(
            decision="REVIEW_REQUIRED",
            is_justified=False,
            reason="Diferença marginal ou metadados técnicos incompletos; revisão manual recomendada.",
            warnings=warnings,
            existing_rank=existing_rank,
            candidate_rank=candidate_rank,
        )
