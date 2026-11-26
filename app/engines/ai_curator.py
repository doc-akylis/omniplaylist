from dataclasses import dataclass, field
import re
from typing import Any, Optional
from rapidfuzz import fuzz

from app.core.models import UnifiedTrack
from app.engines.audio_analyzer import AudioAnalyzer
from app.engines.genre_engine import GenreEngine


@dataclass
class SmartDJFilter:
    """Structured musical curation criteria extracted from natural language or custom filters."""

    target_genres: list[str] = field(default_factory=list)
    year_range: Optional[tuple[int, int]] = None
    bpm_range: Optional[tuple[float, float]] = None
    energy_level: Optional[str] = None  # "low", "medium", "high", "progressive"
    mood: Optional[str] = None  # "festa", "relax", "treino", "romantico", "foco", "melancolico"
    language: Optional[str] = None  # "nacional", "internacional"
    target_duration_ms: Optional[int] = None
    track_count: int = 20
    required_artists: list[str] = field(default_factory=list)
    excluded_artists: list[str] = field(default_factory=list)
    unique_artists_only: bool = False
    transition_mode: str = "score"  # "score", "harmonic", "bpm_progression", "energy_curve", "combined"
    reference_tracks: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class ScoredTrack:
    """A candidate track paired with calculated relevance score and human-readable justification."""

    track: UnifiedTrack
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def justification(self) -> str:
        return " • ".join(self.reasons) if self.reasons else "Compatibilidade geral de acervo"


@dataclass
class SmartDJResult:
    """The final curated playlist ready for playback, editing, or export."""

    tracks: list[UnifiedTrack]
    justifications: dict[int, str]
    total_duration_ms: int
    average_bpm: Optional[float]
    transition_summary: str


class AICurator:
    """Smart DJ 2.0: Natural language curation, multi-criteria scoring, and transition sequencing."""

    DECADE_MAP = {
        "60": (1960, 1969),
        "70": (1970, 1979),
        "80": (1980, 1989),
        "90": (1990, 1999),
        "2000": (2000, 2009),
        "2010": (2010, 2019),
        "2020": (2020, 2029),
    }

    TEMPO_MAP = {
        "muito lenta": (0, 85),
        "lenta": (0, 95),
        "calma": (0, 100),
        "relaxar": (0, 105),
        "estudo": (60, 110),
        "foco": (60, 115),
        "media": (100, 125),
        "animada": (120, 160),
        "rapida": (128, 180),
        "treino": (128, 165),
        "correr": (130, 175),
        "corrida": (130, 175),
        "festa": (122, 140),
        "balada": (125, 145),
    }

    MOOD_KEYWORDS = {
        "festa": ["festa", "animad", "dançar", "balada", "alegre"],
        "relax": ["relax", "tranquil", "calm", "dormir", "paz", "chill"],
        "treino": ["trein", "correr", "corrida", "academia", "workout"],
        "romantico": ["romântic", "romantico", "amor", "love", "paixão"],
        "foco": ["estud", "foco", "programar", "codar", "trabalhar"],
        "melancolico": ["triste", "melancolic", "depr", "chuv", "saudade"],
    }

    def __init__(self):
        self.genre_engine = GenreEngine()
        self.audio_analyzer = AudioAnalyzer()

    # 1. Natural Language Parser
    def parse_prompt(self, prompt: str) -> dict[str, Any]:
        """Backward-compatible prompt parser returning dict of criteria."""
        obj = self.parse_prompt_to_filter(prompt)
        return {
            "bpm_range": obj.bpm_range,
            "year_range": obj.year_range,
            "target_genres": obj.target_genres,
            "keywords": obj.keywords,
            "track_count": obj.track_count,
            "unique_artists_only": obj.unique_artists_only,
            "required_artists": obj.required_artists,
            "excluded_artists": obj.excluded_artists,
            "transition_mode": obj.transition_mode,
        }

    def parse_prompt_to_filter(self, prompt: str) -> SmartDJFilter:
        """Stage 1 & 2: Parse natural language into structured SmartDJFilter."""
        p_lower = prompt.lower()
        filt = SmartDJFilter()

        # Track count detection (e.g. "20 musicas", "30 faixas", "15 cancoes")
        count_match = re.search(r"(\d{1,3})\s*(m[uú]sicas?|faixas?|can[çc][oõ]es?|tracks?)", p_lower)
        if count_match:
            filt.track_count = max(5, min(100, int(count_match.group(1))))

        # Duration detection (e.g. "2 horas", "90 minutos")
        dur_hours = re.search(r"(\d+)\s*hora[s]?", p_lower)
        dur_mins = re.search(r"(\d+)\s*minuto[s]?", p_lower)
        if dur_hours:
            filt.target_duration_ms = int(dur_hours.group(1)) * 3600 * 1000
        elif dur_mins:
            filt.target_duration_ms = int(dur_mins.group(1)) * 60 * 1000

        # Unique artists restriction
        if "sem repetir artista" in p_lower or "artistas diferentes" in p_lower or "um artista por faixa" in p_lower:
            filt.unique_artists_only = True

        # Progressive energy check
        if "aumente gradualmente a energia" in p_lower or "comece tranquila e aumente" in p_lower:
            filt.energy_level = "progressive"
            filt.transition_mode = "energy_curve"

        # Explicit BPM detection (e.g. "acima de 125 bpm", "130 bpm", "entre 120 e 135 bpm")
        range_bpm = re.search(r"entre\s*(\d{2,3})\s*e\s*(\d{2,3})\s*bpm", p_lower)
        above_bpm = re.search(r"acima de\s*(\d{2,3})\s*bpm", p_lower)
        single_bpm = re.search(r"(\d{2,3})\s*bpm", p_lower)

        if range_bpm:
            filt.bpm_range = (float(range_bpm.group(1)), float(range_bpm.group(2)))
        elif above_bpm:
            filt.bpm_range = (float(above_bpm.group(1)), 210.0)
        elif single_bpm:
            val = float(single_bpm.group(1))
            filt.bpm_range = (val - 10, val + 15)
        else:
            # Check tempo keywords
            for word, (b_min, b_max) in self.TEMPO_MAP.items():
                if word in p_lower:
                    filt.bpm_range = (b_min, b_max)
                    break

        # Decades
        for dec_key, year_span in self.DECADE_MAP.items():
            if f"anos {dec_key}" in p_lower or f"{dec_key}s" in p_lower:
                filt.year_range = year_span
                break

        # Mood detection
        for mood_key, synonyms in self.MOOD_KEYWORDS.items():
            if any(syn in p_lower for syn in synonyms):
                filt.mood = mood_key
                break

        # Transition mode
        if "transiç" in p_lower or "transic" in p_lower or "harmon" in p_lower or "camelot" in p_lower:
            filt.transition_mode = "harmonic"

        # Genre detection from taxonomy
        for sub, macro in self.genre_engine.TAXONOMY_MAP.items():
            if sub in p_lower and sub not in filt.target_genres:
                filt.target_genres.append(sub)
            if macro.lower() in p_lower and macro.lower() not in filt.target_genres:
                filt.target_genres.append(macro.lower())

        # Excluded artists / genres (e.g. "sem sertanejo", "sem funk", "sem queen")
        sem_matches = re.findall(r"sem\s+([a-zA-Z0-9\s]+?)(?:,|\.|$|e\s|com\s)", p_lower)
        for neg in sem_matches:
            cleaned_neg = neg.strip()
            if len(cleaned_neg) >= 3 and cleaned_neg not in ["músicas lentas", "musicas lentas", "repetir"]:
                filt.excluded_artists.append(cleaned_neg)

        # Tokenize remaining words as keywords
        words = re.findall(r"\w+", p_lower)
        stopwords = {"para", "com", "uma", "playlist", "musicas", "músicas", "faixas", "anos", "pelo", "pela"}
        filt.keywords = [w for w in words if len(w) > 3 and w not in stopwords]

        return filt

    # 3. Candidate Scoring Engine
    def score_track(
        self,
        track: UnifiedTrack,
        criteria: SmartDJFilter,
        weights: Optional[dict[str, float]] = None,
    ) -> ScoredTrack:
        """Stage 5: Multi-parameter scoring with justification builder."""
        w = {
            "bpm": 35.0,
            "genre": 30.0,
            "decade": 25.0,
            "mood": 20.0,
            "keyword": 15.0,
            "energy": 15.0,
        }
        if weights:
            w.update(weights)

        score = 0.0
        reasons: list[str] = []

        # Check exclusions first (hard filter)
        for exc in criteria.excluded_artists:
            if exc in track.artist.lower() or exc in track.title.lower():
                return ScoredTrack(track=track, score=-999.0, reasons=["Artista ou termo excluído pelo filtro"])

        # 1. BPM Alignment
        if criteria.bpm_range and track.bpm:
            min_b, max_b = criteria.bpm_range
            if min_b <= track.bpm <= max_b:
                score += w["bpm"]
                reasons.append(f"Andamento adequado ({int(track.bpm)} BPM)")
            elif abs(track.bpm - min_b) <= 6 or abs(track.bpm - max_b) <= 6:
                score += w["bpm"] * 0.5
                reasons.append(f"Andamento próximo ({int(track.bpm)} BPM)")

        # 2. Decade Alignment
        if criteria.year_range and track.release_year:
            min_y, max_y = criteria.year_range
            if min_y <= track.release_year <= max_y:
                score += w["decade"]
                reasons.append(f"Lançada em {track.release_year} (Época correspondente)")

        # 3. Genre Alignment
        if criteria.target_genres:
            track_genres = [g.lower() for g in track.genres]
            for tg in criteria.target_genres:
                if any(tg in g for g in track_genres) or tg in (track.genres_raw or "").lower():
                    score += w["genre"]
                    reasons.append(f"Gênero identificado: {tg.title()}")
                    break

        # 4. Mood & Energy Alignment
        if criteria.mood:
            keywords_mood = self.MOOD_KEYWORDS.get(criteria.mood, [])
            full_meta = f"{track.title} {track.artist} {track.album or ''} {track.genres_raw}".lower()
            if any(k in full_meta for k in keywords_mood):
                score += w["mood"]
                reasons.append(f"Alinhado com a vibe '{criteria.mood}'")

        # 5. Required artists bonus
        for req in criteria.required_artists:
            if req in track.artist.lower():
                score += 50.0
                reasons.append(f"Artista obrigatório: {track.artist}")

        # 6. Keyword matching
        full_text = f"{track.title} {track.artist} {track.album or ''}".lower()
        matched_kw = [kw for kw in criteria.keywords if kw in full_text]
        if matched_kw:
            score += w["keyword"] * len(matched_kw)
            reasons.append(f"Palavras-chave: {', '.join(matched_kw)}")

        return ScoredTrack(track=track, score=round(score, 2), reasons=reasons)

    # 4. Sequence Organizer
    def organize_sequence(
        self, criteria: SmartDJFilter, scored_tracks: list[ScoredTrack]
    ) -> list[ScoredTrack]:
        """Stage 6: Intelligent ordering respecting DJ Camelot, BPM curve or Energy."""
        if len(scored_tracks) <= 1:
            return scored_tracks

        mode = criteria.transition_mode

        if mode in ("score", "none"):
            return scored_tracks

        if mode == "bpm_progression":
            # Progressively ascending BPM
            with_bpm = [s for s in scored_tracks if s.track.bpm]
            no_bpm = [s for s in scored_tracks if not s.track.bpm]
            return sorted(with_bpm, key=lambda s: s.track.bpm or 0) + no_bpm

        elif mode == "energy_curve":
            # Sort with lowest energy/BPM at start and highest at peak
            return sorted(scored_tracks, key=lambda s: (s.track.bpm or 100))

        elif mode in ("harmonic", "combined"):
            # Use Camelot sorting logic
            tracks_only = [s.track for s in scored_tracks]
            sorted_tracks = self.audio_analyzer.sort_playlist_for_dj(tracks_only)

            # Map back to ScoredTrack order
            track_map = {s.track.id: s for s in scored_tracks}
            result = []
            for t in sorted_tracks:
                if t.id in track_map:
                    result.append(track_map[t.id])
            return result

        return scored_tracks

    # 5. Validator and Deduplicator
    def validate_playlist(
        self, criteria: SmartDJFilter, candidates: list[ScoredTrack]
    ) -> list[ScoredTrack]:
        """Stage 7: Enforce unique artist restriction, max count and total duration constraints."""
        validated: list[ScoredTrack] = []
        seen_artists: set[str] = set()
        accumulated_ms = 0

        for candidate in candidates:
            if candidate.score < 0:
                continue

            art_key = candidate.track.artist.lower().strip()
            if criteria.unique_artists_only and art_key in seen_artists:
                continue

            validated.append(candidate)
            seen_artists.add(art_key)
            accumulated_ms += candidate.track.duration_ms or 180000

            # Target duration check
            if criteria.target_duration_ms and accumulated_ms >= criteria.target_duration_ms:
                break

            # Target count check
            if len(validated) >= criteria.track_count:
                break

        return validated

    # 6. Full Pipeline Entrypoint
    def generate_smart_dj_set(
        self, prompt: str, catalog: list[UnifiedTrack], custom_filter: Optional[SmartDJFilter] = None
    ) -> SmartDJResult:
        """Stage 8: End-to-end execution returning the complete SmartDJResult."""
        criteria = custom_filter or self.parse_prompt_to_filter(prompt)

        # Score catalog
        scored: list[ScoredTrack] = [self.score_track(t, criteria) for t in catalog]

        # Filter out negative scores and sort by highest score first
        eligible = [s for s in scored if s.score > 0]
        eligible.sort(key=lambda s: s.score, reverse=True)

        # If empty, fallback to catalog slice with default score (strictly respecting exclusions)
        if not eligible and catalog:
            non_excluded = [
                t for t in catalog
                if not any(exc.lower() in t.artist.lower() or exc.lower() in t.title.lower() for exc in criteria.excluded_artists)
            ]
            eligible = [
                ScoredTrack(track=t, score=10.0, reasons=["Seleção inicial do acervo"])
                for t in non_excluded[:criteria.track_count]
            ]

        # Validate restrictions (unique artists, exclusions, duration)
        validated = self.validate_playlist(criteria, eligible)

        # Organize transitions
        final_sequence = self.organize_sequence(criteria, validated)

        # Compile results
        tracks_out = [s.track for s in final_sequence]
        reasons_out = {s.track.id or idx: s.justification for idx, s in enumerate(final_sequence)}
        total_ms = sum(t.duration_ms or 0 for t in tracks_out)

        bpms = [t.bpm for t in tracks_out if t.bpm]
        avg_bpm = round(sum(bpms) / len(bpms), 1) if bpms else None

        summary = f"Modo de transição: {criteria.transition_mode.upper()} • {len(tracks_out)} faixas selecionadas"

        return SmartDJResult(
            tracks=tracks_out,
            justifications=reasons_out,
            total_duration_ms=total_ms,
            average_bpm=avg_bpm,
            transition_summary=summary,
        )

    # Backward compatibility method
    def build_playlist(
        self, prompt: str, catalog: list[UnifiedTrack], limit: int = 25
    ) -> list[UnifiedTrack]:
        """Backward-compatible helper returning list of UnifiedTracks."""
        filt = self.parse_prompt_to_filter(prompt)
        filt.track_count = limit
        res = self.generate_smart_dj_set(prompt, catalog, custom_filter=filt)
        return res.tracks
