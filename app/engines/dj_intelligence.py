import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.models import AudioProvenance, Playlist, PlaylistTrackLink, UnifiedTrack
from app.engines.audio_analyzer import AudioAnalyzer


class SequencerConfig(BaseModel):
    """Configuration for whole-playlist Smart Sequencer optimization."""

    mode: str = "balanced_dj_flow"  # bpm_progression, energy_progression, harmonic_flow, balanced_dj_flow, custom
    start_bpm: Optional[float] = None
    end_bpm: Optional[float] = None
    start_energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    end_energy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    harmonic_priority: float = Field(default=0.8, ge=0.0, le=1.0)
    bpm_tolerance_pct: float = Field(default=6.0, ge=0.5, le=30.0)
    allow_half_time: bool = True
    allow_double_time: bool = True
    energy_tolerance: float = Field(default=0.35, ge=0.05, le=1.0)
    allow_repeated_artists: bool = False
    required_track_ids: list[int] = Field(default_factory=list)
    forbidden_track_ids: list[int] = Field(default_factory=list)
    weight_harmonic: float = Field(default=0.40, ge=0.0, le=1.0)
    weight_bpm: float = Field(default=0.35, ge=0.0, le=1.0)
    weight_energy: float = Field(default=0.15, ge=0.0, le=1.0)
    weight_tags: float = Field(default=0.10, ge=0.0, le=1.0)


class DJIntelligenceEngine:
    """Layer 3 DJ Intelligence: Camelot harmony, beatmatching, transition points, and next-track ranking."""

    @staticmethod
    def _parse_camelot(key_or_code: Optional[str]) -> Optional[tuple[int, str]]:
        if not key_or_code:
            return None
        code = AudioAnalyzer.normalize_to_camelot(key_or_code)
        if not code:
            return None
        match = re.fullmatch(r"(\d{1,2})([AB])", code.strip().upper())
        if not match:
            return None
        num = int(match.group(1))
        letter = match.group(2)
        if not (1 <= num <= 12):
            return None
        return num, letter

    @classmethod
    def camelot_compatibility(
        cls, key1: Optional[str], key2: Optional[str]
    ) -> tuple[float, str, bool]:
        """Compute Camelot harmonic compatibility score (0.0-1.0), reason, and strict compatibility flag."""
        c1 = cls._parse_camelot(key1)
        c2 = cls._parse_camelot(key2)
        if not c1 or not c2:
            return 0.5, "Clave ausente", False

        n1, l1 = c1
        n2, l2 = c2

        if n1 == n2 and l1 == l2:
            return 1.0, f"Mesma Clave ({n1}{l1})", True
        if n1 == n2 and l1 != l2:
            return 0.9, f"Relativa Maior/Menor ({n1}{l1} ↔ {n2}{l2})", True

        diff = min((n1 - n2) % 12, (n2 - n1) % 12)
        if l1 == l2 and diff == 1:
            return 0.85, f"Adjacente ±1 ({n1}{l1} → {n2}{l2})", True
        if (l1 == l2 and diff == 2) or (l1 != l2 and diff == 1):
            return 0.55, f"Transição Diagonal ({n1}{l1} → {n2}{l2})", False

        return 0.15, f"Divergência Tonal ({n1}{l1} → {n2}{l2})", False

    @staticmethod
    def bpm_compatibility(
        bpm1: Optional[float], bpm2: Optional[float]
    ) -> tuple[float, float, str]:
        """Evaluate beatmatching compatibility including half-time and double-time detection.

        Returns: (score 0.0-1.0, signed_delta_pct, relation_label)
        """
        if not bpm1 or not bpm2 or bpm1 <= 0 or bpm2 <= 0:
            return 0.5, 0.0, "unknown"

        candidates = [
            ("direct", bpm2),
            ("double_time", bpm2 * 2.0),
            ("half_time", bpm2 / 2.0),
        ]
        best_relation = "direct"
        best_signed_pct = ((bpm2 - bpm1) / bpm1) * 100.0
        best_abs_pct = abs(best_signed_pct)

        for rel, effective_bpm in candidates:
            signed_pct = ((effective_bpm - bpm1) / bpm1) * 100.0
            abs_pct = abs(signed_pct)
            if abs_pct < best_abs_pct:
                best_abs_pct = abs_pct
                best_signed_pct = signed_pct
                best_relation = rel

        if best_abs_pct <= 3.0:
            base = 1.0 if best_relation == "direct" else 0.9
            score = round(base - (best_abs_pct / 3.0) * 0.05, 3)
        elif best_abs_pct <= 6.0:
            # Linearly scale from 0.85 (at 3%) down to 0.65 (at 6%)
            score = round(0.85 - ((best_abs_pct - 3.0) / 3.0) * 0.20, 3)
        elif best_abs_pct <= 10.0:
            score = round(0.50 - ((best_abs_pct - 6.0) / 4.0) * 0.25, 3)
        else:
            score = 0.1

        return max(0.0, min(1.0, score)), round(best_signed_pct, 2), best_relation

    @staticmethod
    def _parse_json_safe(raw: Optional[str], default: Any) -> Any:
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    @staticmethod
    def _snap_to_downbeat(target_sec: float, downbeats: list[float]) -> float:
        if not downbeats:
            return round(target_sec, 2)
        nearest = min(downbeats, key=lambda d: abs(float(d) - target_sec))
        return round(float(nearest), 2)

    @classmethod
    def suggest_transition_points(
        cls, current_track: UnifiedTrack, next_track: Optional[UnifiedTrack] = None
    ) -> dict[str, Any]:
        """Suggest mix-out point for current_track and mix-in point for next_track using sections & beatgrid."""
        curr_sections = cls._parse_json_safe(current_track.sections_json, [])
        curr_beatgrid = cls._parse_json_safe(current_track.beatgrid_json, {})
        curr_downbeats = curr_beatgrid.get("downbeats_sec", []) if isinstance(curr_beatgrid, dict) else []

        duration_sec = (current_track.duration_ms or 0) / 1000.0
        mix_out_sec = round(duration_sec * 0.82, 2) if duration_sec > 0 else 0.0
        mix_out_label = "outro_estimado"

        if isinstance(curr_sections, list) and curr_sections:
            outros = [s for s in curr_sections if str(s.get("label", "")).lower() == "outro"]
            breakdowns = [s for s in curr_sections if str(s.get("label", "")).lower() == "breakdown"]
            if outros:
                mix_out_sec = float(outros[-1].get("start_sec", mix_out_sec))
                mix_out_label = "outro"
            elif breakdowns:
                mix_out_sec = float(breakdowns[-1].get("start_sec", mix_out_sec))
                mix_out_label = "breakdown"
            else:
                mix_out_sec = float(curr_sections[-1].get("start_sec", mix_out_sec))
                mix_out_label = str(curr_sections[-1].get("label", "final"))

        if curr_downbeats:
            mix_out_sec = cls._snap_to_downbeat(mix_out_sec, curr_downbeats)

        mix_in_sec = 0.0
        mix_in_label = "intro"
        if next_track is not None:
            next_sections = cls._parse_json_safe(next_track.sections_json, [])
            next_beatgrid = cls._parse_json_safe(next_track.beatgrid_json, {})
            next_downbeats = next_beatgrid.get("downbeats_sec", []) if isinstance(next_beatgrid, dict) else []

            if isinstance(next_sections, list) and next_sections:
                intros = [s for s in next_sections if str(s.get("label", "")).lower() == "intro"]
                verses = [s for s in next_sections if str(s.get("label", "")).lower() == "verse"]
                if intros:
                    mix_in_sec = float(intros[0].get("start_sec", 0.0))
                    mix_in_label = "intro"
                elif verses:
                    mix_in_sec = float(verses[0].get("start_sec", 0.0))
                    mix_in_label = "verse"
                else:
                    mix_in_sec = float(next_sections[0].get("start_sec", 0.0))
                    mix_in_label = str(next_sections[0].get("label", "inicio"))

            if next_downbeats:
                mix_in_sec = cls._snap_to_downbeat(mix_in_sec, next_downbeats)

        return {
            "mix_out_sec": mix_out_sec,
            "mix_out_label": mix_out_label,
            "mix_in_sec": mix_in_sec,
            "mix_in_label": mix_in_label,
        }

    @staticmethod
    def _track_tags_set(track: UnifiedTrack) -> set[str]:
        tags = {g.strip().lower() for g in track.genres if g.strip()}
        if track.lastfm_tags:
            tags.update(t.strip().lower() for t in track.lastfm_tags.split(",") if t.strip())
        return tags

    @classmethod
    def tag_affinity(cls, track1: UnifiedTrack, track2: UnifiedTrack) -> float:
        """Jaccard similarity across genres and Last.fm tags."""
        t1 = cls._track_tags_set(track1)
        t2 = cls._track_tags_set(track2)
        if not t1 or not t2:
            return 0.5
        intersection = len(t1 & t2)
        union = len(t1 | t2)
        return round(intersection / union, 3) if union > 0 else 0.5

    def recommend_next_tracks(
        self,
        current_track: UnifiedTrack,
        catalog: list[UnifiedTrack],
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Rank candidate tracks from the local library for the next DJ transition."""
        recommendations: list[dict[str, Any]] = []
        curr_key = current_track.camelot_code or current_track.key

        for cand in catalog:
            if cand.id is not None and current_track.id is not None and cand.id == current_track.id:
                continue
            if cand is current_track:
                continue

            cand_key = cand.camelot_code or cand.key
            harmonic_score, harmonic_reason, is_harmonic = self.camelot_compatibility(curr_key, cand_key)
            bpm_score, bpm_delta_pct, bpm_relation = self.bpm_compatibility(current_track.bpm, cand.bpm)

            if current_track.energy is not None and cand.energy is not None:
                energy_delta = round(cand.energy - current_track.energy, 3)
                energy_score = max(0.0, 1.0 - abs(energy_delta))
            else:
                energy_delta = 0.0
                energy_score = 0.5

            tags_score = self.tag_affinity(current_track, cand)

            total_score = round(
                0.40 * harmonic_score
                + 0.35 * bpm_score
                + 0.15 * energy_score
                + 0.10 * tags_score,
                3,
            )

            transition_pts = self.suggest_transition_points(current_track, cand)

            recommendations.append(
                {
                    "track": cand,
                    "track_id": cand.id,
                    "title": cand.title,
                    "artist": cand.artist,
                    "bpm": cand.bpm,
                    "camelot_code": cand.camelot_code or AudioAnalyzer.normalize_to_camelot(cand.key),
                    "score": total_score,
                    "harmonic_score": harmonic_score,
                    "harmonic_reason": harmonic_reason,
                    "is_harmonic_compatible": is_harmonic,
                    "bpm_score": bpm_score,
                    "bpm_delta_pct": bpm_delta_pct,
                    "bpm_relation": bpm_relation,
                    "energy_delta": energy_delta,
                    "tag_affinity": tags_score,
                    "transition_points": transition_pts,
                }
            )

        recommendations.sort(key=lambda item: item["score"], reverse=True)
        return recommendations[:limit]

    # ============ PHASE 4: SMART PLAYLIST SEQUENCER ============

    def _effective_weights(self, config: SequencerConfig) -> tuple[float, float, float, float]:
        if config.mode == "bpm_progression":
            wh, wb, we, wt = 0.20 * config.harmonic_priority, 0.60, 0.12, 0.08
        elif config.mode == "energy_progression":
            wh, wb, we, wt = 0.20 * config.harmonic_priority, 0.20, 0.52, 0.08
        elif config.mode == "harmonic_flow":
            wh, wb, we, wt = 0.58, 0.25, 0.10, 0.07
        elif config.mode == "custom":
            wh, wb, we, wt = config.weight_harmonic, config.weight_bpm, config.weight_energy, config.weight_tags
        else:
            wh = config.weight_harmonic * (0.5 + 0.5 * config.harmonic_priority)
            wb, we, wt = config.weight_bpm, config.weight_energy, config.weight_tags
        total = max(1e-6, wh + wb + we + wt)
        return wh / total, wb / total, we / total, wt / total

    def _score_pair_for_sequencer(
        self,
        a: UnifiedTrack,
        b: UnifiedTrack,
        step_idx: int,
        total_steps: int,
        config: SequencerConfig,
    ) -> dict[str, Any]:
        wh, wb, we, wt = self._effective_weights(config)
        key_a = a.camelot_code or a.key
        key_b = b.camelot_code or b.key
        h_score, h_reason, is_harmonic = self.camelot_compatibility(key_a, key_b)

        b_score, delta_pct, bpm_rel = self.bpm_compatibility(a.bpm, b.bpm)
        if bpm_rel == "half_time" and not config.allow_half_time:
            b_score = 0.15
        elif bpm_rel == "double_time" and not config.allow_double_time:
            b_score = 0.15

        alerts: list[str] = []
        if a.bpm and b.bpm and abs(delta_pct) > config.bpm_tolerance_pct:
            b_score *= 0.45
            alerts.append(f"Delta de BPM ({delta_pct:+.1f}%) acima da tolerância de {config.bpm_tolerance_pct:.1f}%.")

        # Target progression curves across the playlist
        progress_ratio = step_idx / max(1, total_steps - 1)
        if a.energy is not None and b.energy is not None:
            e_delta = round(b.energy - a.energy, 3)
            if config.start_energy is not None and config.end_energy is not None:
                target_e = config.start_energy + progress_ratio * (config.end_energy - config.start_energy)
                e_score = max(0.0, 1.0 - abs(b.energy - target_e) * 1.4)
            elif config.mode == "energy_progression":
                e_score = 1.0 if e_delta >= -0.05 else max(0.1, 1.0 - abs(e_delta) * 2.0)
            else:
                e_score = max(0.0, 1.0 - abs(e_delta))
            if abs(e_delta) > config.energy_tolerance:
                e_score *= 0.6
                alerts.append(f"Salto de energia ({e_delta:+.2f}) acima da tolerância ({config.energy_tolerance:.2f}).")
        else:
            e_delta = 0.0
            e_score = 0.5

        if config.mode == "bpm_progression" and a.bpm and b.bpm:
            if b.bpm >= a.bpm - 1.5:
                b_score = min(1.0, b_score + 0.05)
            else:
                b_score *= 0.65
                alerts.append("Queda de BPM durante modo de progressão crescente.")

        if config.start_bpm and config.end_bpm and b.bpm:
            target_bpm = config.start_bpm + progress_ratio * (config.end_bpm - config.start_bpm)
            curve_err = abs(b.bpm - target_bpm) / max(1.0, target_bpm)
            b_score = max(0.0, b_score - min(0.35, curve_err))

        t_score = self.tag_affinity(a, b)
        artist_penalty = 0.0
        if not config.allow_repeated_artists and a.artist.strip().lower() == b.artist.strip().lower():
            artist_penalty = 0.18
            alerts.append(f"Artista consecutivo repetido ({b.artist}).")

        total_score = round(max(0.0, min(1.0, wh * h_score + wb * b_score + we * e_score + wt * t_score - artist_penalty)), 3)
        trans_pts = self.suggest_transition_points(a, b)

        # Data-backed human explanation
        parts: list[str] = []
        if key_a and key_b:
            parts.append(f"harmonia {h_reason}")
        else:
            parts.append("clave não analisada em uma das faixas")
        if a.bpm and b.bpm:
            parts.append(f"variação de BPM de {abs(delta_pct):.1f}% ({bpm_rel})")
        else:
            parts.append("BPM ausente para comparação rítmica")
        if a.energy is not None and b.energy is not None:
            if e_delta > 0.03:
                parts.append(f"aumento gradual de energia ({e_delta:+.2f})")
            elif e_delta < -0.03:
                parts.append(f"redução controlada de energia ({e_delta:+.2f})")
            else:
                parts.append("estabilidade energética")
        if t_score > 0.55:
            parts.append("afinidade de gênero/tags")

        justification = f"Transição {'recomendada' if total_score >= 0.7 else 'aceitável' if total_score >= 0.5 else 'desafiadora'}: " + ", ".join(parts) + "."
        delta_bpm = round((b.bpm - a.bpm), 2) if (a.bpm and b.bpm) else None

        return {
            "track_a_id": a.id,
            "track_b_id": b.id,
            "title_a": a.title,
            "title_b": b.title,
            "artist_a": a.artist,
            "artist_b": b.artist,
            "bpm_a": a.bpm,
            "bpm_b": b.bpm,
            "delta_bpm": delta_bpm,
            "delta_bpm_pct": delta_pct if (a.bpm and b.bpm) else None,
            "camelot_a": AudioAnalyzer.normalize_to_camelot(key_a),
            "camelot_b": AudioAnalyzer.normalize_to_camelot(key_b),
            "energy_a": a.energy,
            "energy_b": b.energy,
            "compatibility": is_harmonic,
            "score": total_score,
            "justification": justification,
            "alerts": alerts,
            "mix_out_sec": trans_pts["mix_out_sec"],
            "mix_in_sec": trans_pts["mix_in_sec"],
        }

    def generate_sequence(
        self, tracks: list[UnifiedTrack], config: Optional[SequencerConfig] = None
    ) -> dict[str, Any]:
        """Optimize full playlist order considering global context, targets, constraints, and transition explainability."""
        cfg = config or SequencerConfig()
        forbidden = set(cfg.forbidden_track_ids)
        pool = [t for t in tracks if t.id not in forbidden]
        warnings: list[str] = []

        if not pool:
            return {"ordered_tracks": [], "transitions": [], "average_score": 0.0, "warnings": ["Nenhuma faixa elegível após aplicar restrições."]}

        if len(pool) == 1:
            return {"ordered_tracks": pool, "transitions": [], "average_score": 1.0, "warnings": []}

        # Anchor selection
        def _anchor_cost(t: UnifiedTrack) -> tuple[float, float]:
            cost = 0.0
            if cfg.start_bpm and t.bpm:
                cost += abs(t.bpm - cfg.start_bpm)
            elif cfg.mode == "bpm_progression" and t.bpm:
                cost += t.bpm
            if cfg.start_energy is not None and t.energy is not None:
                cost += abs(t.energy - cfg.start_energy) * 100.0
            elif cfg.mode == "energy_progression" and t.energy is not None:
                cost += t.energy * 100.0
            missing_penalty = 50.0 if (t.bpm is None and not t.camelot_code) else 0.0
            return (missing_penalty, cost)

        remaining = list(pool)
        anchor = min(remaining, key=_anchor_cost)
        ordered = [anchor]
        remaining.remove(anchor)

        while remaining:
            last = ordered[-1]
            step_idx = len(ordered)
            best_cand = max(
                remaining,
                key=lambda cand: self._score_pair_for_sequencer(last, cand, step_idx, len(pool), cfg)["score"],
            )
            ordered.append(best_cand)
            remaining.remove(best_cand)

        # Light 2-opt refinement on adjacent swaps when playlist size is manageable
        def _seq_total_score(seq: list[UnifiedTrack]) -> float:
            if len(seq) < 2:
                return 1.0
            return sum(
                self._score_pair_for_sequencer(seq[i], seq[i + 1], i + 1, len(seq), cfg)["score"]
                for i in range(len(seq) - 1)
            )

        if 4 <= len(ordered) <= 45:
            improved = True
            iters = 0
            while improved and iters < 3:
                improved = False
                iters += 1
                base_total = _seq_total_score(ordered)
                for i in range(1, len(ordered) - 1):
                    for j in range(i + 1, len(ordered)):
                        candidate_seq = list(ordered)
                        candidate_seq[i], candidate_seq[j] = candidate_seq[j], candidate_seq[i]
                        new_total = _seq_total_score(candidate_seq)
                        if new_total > base_total + 0.01:
                            ordered = candidate_seq
                            base_total = new_total
                            improved = True

        transitions = [
            self._score_pair_for_sequencer(ordered[i], ordered[i + 1], i + 1, len(ordered), cfg)
            for i in range(len(ordered) - 1)
        ]
        avg_score = round(sum(tr["score"] for tr in transitions) / len(transitions), 3) if transitions else 1.0

        missing_bpm_count = sum(1 for t in ordered if t.bpm is None)
        if missing_bpm_count:
            warnings.append(f"{missing_bpm_count} faixa(s) sem BPM analisado receberam pontuação neutra de ritmo.")

        return {
            "ordered_tracks": ordered,
            "transitions": transitions,
            "average_score": avg_score,
            "warnings": warnings,
        }

    def apply_sequence_to_playlist(
        self, session: Session, playlist_id: int, ordered_track_ids: list[int]
    ) -> Optional[Playlist]:
        """Persist sequenced order to PlaylistTrackLink while preserving original order for rollback."""
        pl = session.get(Playlist, playlist_id)
        if not pl:
            return None

        links = session.exec(
            select(PlaylistTrackLink)
            .where(PlaylistTrackLink.playlist_id == playlist_id)
            .order_by(PlaylistTrackLink.position.asc())
        ).all()
        if not pl.original_order_json:
            pl.original_order_json = json.dumps([lnk.track_id for lnk in links])

        by_tid = {lnk.track_id: lnk for lnk in links}
        pos = 0
        seen: set[int] = set()
        for tid in ordered_track_ids:
            if tid in by_tid and tid not in seen:
                by_tid[tid].position = pos
                session.add(by_tid[tid])
                seen.add(tid)
                pos += 1
        for lnk in links:
            if lnk.track_id not in seen:
                lnk.position = pos
                session.add(lnk)
                pos += 1

        pl.updated_at = datetime.now(timezone.utc)
        session.add(pl)
        session.commit()
        session.refresh(pl)
        return pl

    def restore_playlist_order(self, session: Session, playlist_id: int) -> tuple[bool, list[int]]:
        """Restore the original track order saved prior to smart sequencing."""
        pl = session.get(Playlist, playlist_id)
        if not pl or not pl.original_order_json:
            return False, []
        try:
            orig_ids = [int(x) for x in json.loads(pl.original_order_json)]
        except Exception:
            return False, []

        links = session.exec(
            select(PlaylistTrackLink).where(PlaylistTrackLink.playlist_id == playlist_id)
        ).all()
        by_tid = {lnk.track_id: lnk for lnk in links}
        pos = 0
        seen: set[int] = set()
        for tid in orig_ids:
            if tid in by_tid and tid not in seen:
                by_tid[tid].position = pos
                session.add(by_tid[tid])
                seen.add(tid)
                pos += 1
        for lnk in links:
            if lnk.track_id not in seen:
                lnk.position = pos
                session.add(lnk)
                pos += 1

        pl.updated_at = datetime.now(timezone.utc)
        session.add(pl)
        session.commit()
        return True, orig_ids

    # ============ PHASE 5: DJ TECHNICAL ANALYZER ============

    def generate_eq_suggestions(
        self, track_a: UnifiedTrack, track_b: UnifiedTrack, analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Generate non-destructive, data-backed EQ Assist suggestions for Deck A/B transitions."""
        suggestions: list[dict[str, Any]] = []

        sub_a = track_a.sub_bass_energy or 0.0
        sub_b = track_b.sub_bass_energy or 0.0
        mid_bass_a = track_a.mid_bass_energy or 0.0
        mid_bass_b = track_b.mid_bass_energy or 0.0
        high_a = track_a.high_freq_energy or 0.0
        high_b = track_b.high_freq_energy or 0.0

        bass_a = sub_a + mid_bass_a
        bass_b = sub_b + mid_bass_b

        if bass_a > 0.25 and bass_b > 0.25:
            suggestions.append(
                {
                    "id": "eq_low_swap_b",
                    "target_deck": "B",
                    "band": "low",
                    "suggested_db": -10.0,
                    "reason": (
                        f"Sobreposição elevada de graves (Deck A {int(bass_a * 100)}% vs Deck B {int(bass_b * 100)}% na faixa 20–250 Hz). "
                        "Reduza o Low do Deck B durante o Mix-In para evitar embolamento e excesso de pico."
                    ),
                }
            )

        delta_lufs = analysis.get("delta_lufs")
        if delta_lufs is not None and abs(delta_lufs) >= 2.5:
            hotter_deck = "B" if delta_lufs > 0 else "A"
            suggestions.append(
                {
                    "id": "eq_loudness_balance",
                    "target_deck": hotter_deck,
                    "band": "mid",
                    "suggested_db": -2.5,
                    "reason": (
                        f"Diferença de loudness de {delta_lufs:+.1f} LUFS entre os decks. "
                        f"Atenuar levemente médios/ganho no Deck {hotter_deck} suaviza a transição percebida."
                    ),
                }
            )

        if high_a > 0.25 and high_b > 0.25:
            suggestions.append(
                {
                    "id": "eq_high_tame_b",
                    "target_deck": "B",
                    "band": "high",
                    "suggested_db": -4.0,
                    "reason": "Ambas as faixas possuem alta densidade de agudos (4–20 kHz); suavizar High no Deck B evita sibilância na entrada.",
                }
            )

        return suggestions

    def analyze_transition(
        self,
        track_a: UnifiedTrack,
        track_b: UnifiedTrack,
        deck_a_pitch: float = 1.0,
        deck_b_pitch: float = 1.0,
    ) -> dict[str, Any]:
        """Compute comprehensive Deck A -> Deck B transition telemetry, bass overlap, clipping estimate, and EQ Assist."""
        eff_bpm_a = round(track_a.bpm * deck_a_pitch, 2) if track_a.bpm else None
        eff_bpm_b = round(track_b.bpm * deck_b_pitch, 2) if track_b.bpm else None
        delta_bpm = round(eff_bpm_b - eff_bpm_a, 2) if (eff_bpm_a and eff_bpm_b) else None
        bpm_score, delta_bpm_pct, bpm_relation = self.bpm_compatibility(eff_bpm_a, eff_bpm_b)

        key_a = track_a.camelot_code or track_a.key
        key_b = track_b.camelot_code or track_b.key
        h_score, h_reason, is_harmonic = self.camelot_compatibility(key_a, key_b)

        delta_energy = (
            round(track_b.energy - track_a.energy, 3)
            if (track_a.energy is not None and track_b.energy is not None)
            else None
        )
        delta_lufs = (
            round(track_b.integrated_lufs - track_a.integrated_lufs, 2)
            if (track_a.integrated_lufs is not None and track_b.integrated_lufs is not None)
            else None
        )

        # Bass overlap (20-250 Hz descriptive share)
        bass_a = (track_a.sub_bass_energy or 0.0) + (track_a.mid_bass_energy or 0.0)
        bass_b = (track_b.sub_bass_energy or 0.0) + (track_b.mid_bass_energy or 0.0)
        if bass_a > 0 and bass_b > 0:
            bass_overlap = round(min(1.0, (min(bass_a, bass_b) / 0.5)), 3)
        else:
            bass_overlap = None

        conflicting_bands: list[str] = []
        if (track_a.sub_bass_energy or 0.0) > 0.12 and (track_b.sub_bass_energy or 0.0) > 0.12:
            conflicting_bands.append("Subgrave (20–60 Hz)")
        if (track_a.mid_bass_energy or 0.0) > 0.18 and (track_b.mid_bass_energy or 0.0) > 0.18:
            conflicting_bands.append("Grave / Mid-bass (60–250 Hz)")
        if (track_a.high_freq_energy or 0.0) > 0.25 and (track_b.high_freq_energy or 0.0) > 0.25:
            conflicting_bands.append("Agudos (4–20 kHz)")

        # Combined peak estimate (non-assertive: depends on phase, gain, and overlap moment)
        estimated_combined_peak_dbfs: Optional[float] = None
        clipping_risk_note = "Dados de True Peak insuficientes para estimar soma de sinais."
        if track_a.true_peak_dbfs is not None and track_b.true_peak_dbfs is not None:
            lin_a = 10.0 ** (track_a.true_peak_dbfs / 20.0)
            lin_b = 10.0 ** (track_b.true_peak_dbfs / 20.0)
            # RMS-like uncorrelated sum estimate (+3 dB style) rather than worst-case coherent +6 dB
            rms_sum = math.sqrt(lin_a ** 2 + lin_b ** 2)
            estimated_combined_peak_dbfs = round(20.0 * math.log10(max(1e-6, rms_sum)), 2)
            clipping_risk_note = (
                "Estimativa baseada em soma não-correlacionada de True Peak; a ocorrência real de clipping "
                "depende da fase instantânea, posição dos faders e corte de EQ durante a sobreposição."
            )

        trans_pts = self.suggest_transition_points(track_a, track_b)
        alerts: list[str] = []
        risk = "LOW"
        if not is_harmonic and key_a and key_b:
            alerts.append(f"Divergência harmônica ({h_reason}).")
            risk = "MEDIUM"
        if eff_bpm_a and eff_bpm_b and abs(delta_bpm_pct) > 6.0:
            alerts.append(f"Diferença de BPM elevada ({delta_bpm_pct:+.1f}%); considere usar Sync ou transição por breakdown.")
            risk = "HIGH"
        if estimated_combined_peak_dbfs is not None and estimated_combined_peak_dbfs > 0.0:
            alerts.append(f"Pico combinado estimado de {estimated_combined_peak_dbfs:+.2f} dBFS sem atenuação de EQ/trim.")
            risk = "HIGH" if risk != "LOW" else "MEDIUM"
        if conflicting_bands:
            alerts.append(f"Sobreposição espectral provável em: {', '.join(conflicting_bands)}.")

        result = {
            "track_a_id": track_a.id,
            "track_b_id": track_b.id,
            "effective_bpm_a": eff_bpm_a,
            "effective_bpm_b": eff_bpm_b,
            "delta_bpm": delta_bpm,
            "delta_bpm_pct": delta_bpm_pct if (eff_bpm_a and eff_bpm_b) else None,
            "bpm_relation": bpm_relation,
            "bpm_score": bpm_score,
            "camelot_a": AudioAnalyzer.normalize_to_camelot(key_a),
            "camelot_b": AudioAnalyzer.normalize_to_camelot(key_b),
            "harmonic_score": h_score,
            "harmonic_reason": h_reason,
            "is_harmonic_compatible": is_harmonic,
            "delta_energy": delta_energy,
            "delta_lufs": delta_lufs,
            "true_peak_a": track_a.true_peak_dbfs,
            "true_peak_b": track_b.true_peak_dbfs,
            "bass_overlap_score": bass_overlap,
            "conflicting_bands": conflicting_bands,
            "estimated_combined_peak_dbfs": estimated_combined_peak_dbfs,
            "combined_clipping_is_estimate": True,
            "clipping_risk_note": clipping_risk_note,
            "mix_out_sec": trans_pts["mix_out_sec"],
            "mix_in_sec": trans_pts["mix_in_sec"],
            "risk_level": risk,
            "alerts": alerts,
        }
        result["eq_suggestions"] = self.generate_eq_suggestions(track_a, track_b, result)
        return result

    @staticmethod
    def compare_track_versions(
        track_a: UnifiedTrack,
        track_b: UnifiedTrack,
        prov_a: Optional[AudioProvenance] = None,
        prov_b: Optional[AudioProvenance] = None,
    ) -> dict[str, Any]:
        """Structured A/B technical & provenance quality comparison between two track versions."""
        def _snapshot(t: UnifiedTrack, p: Optional[AudioProvenance]) -> dict[str, Any]:
            return {
                "track_id": t.id,
                "title": t.title,
                "artist": t.artist,
                "is_preview": t.is_preview,
                "codec": t.codec,
                "bitrate_kbps": t.bitrate_kbps,
                "sample_rate_hz": t.sample_rate_hz,
                "bit_depth": t.bit_depth,
                "integrated_lufs": t.integrated_lufs,
                "true_peak_dbfs": t.true_peak_dbfs,
                "dynamic_range_db": t.dynamic_range_db,
                "spectral_cutoff_hz": t.spectral_cutoff_hz,
                "clipping_count": t.clipping_count,
                "upscale_status": t.upscale_status,
                "source_classification": (p.origin_classification if p else t.source_classification) or "UNKNOWN_SOURCE",
                "car_audio_score": t.car_audio_score,
                "local_path": t.local_path,
            }

        snap_a = _snapshot(track_a, prov_a)
        snap_b = _snapshot(track_b, prov_b)
        differences: list[str] = []

        for field_name, label in [
            ("codec", "Codec"),
            ("bitrate_kbps", "Bitrate (kbps)"),
            ("sample_rate_hz", "Sample Rate (Hz)"),
            ("bit_depth", "Bit Depth"),
            ("integrated_lufs", "LUFS Integrado"),
            ("true_peak_dbfs", "True Peak (dBFS)"),
            ("dynamic_range_db", "Dynamic Range (dB)"),
            ("spectral_cutoff_hz", "Corte Espectral (Hz)"),
            ("clipping_count", "Clipping (amostras)"),
            ("source_classification", "Proveniência de Origem"),
            ("is_preview", "Modo Preview"),
        ]:
            if snap_a[field_name] != snap_b[field_name]:
                differences.append(f"{label}: A = {snap_a[field_name]} vs B = {snap_b[field_name]}")

        score_a = (track_a.car_audio_score or 0.0) + (20.0 if snap_a["source_classification"] == "LOSSLESS_SOURCE" else 0.0) - (30.0 if track_a.is_preview else 0.0)
        score_b = (track_b.car_audio_score or 0.0) + (20.0 if snap_b["source_classification"] == "LOSSLESS_SOURCE" else 0.0) - (30.0 if track_b.is_preview else 0.0)
        recommended_id = track_a.id if score_a >= score_b else track_b.id

        return {
            "version_a": snap_a,
            "version_b": snap_b,
            "differences": differences,
            "recommended_track_id": recommended_id,
            "summary": (
                f"Versão {'A' if recommended_id == track_a.id else 'B'} apresenta melhor perfil técnico/proveniência "
                f"com {len(differences)} diferença(s) detectada(s)."
            ),
        }
