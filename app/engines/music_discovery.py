from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from sqlmodel import Session, select

from app.core.models import UnifiedTrack, UserHistory
from app.engines.audio_analyzer import AudioAnalyzer
from app.engines.genre_engine import GenreEngine
from app.providers.deezer import DeezerProvider


@dataclass
class DiscoverySection:
    """Grouped recommendation category."""

    title: str
    description: str
    tracks: list[UnifiedTrack] = field(default_factory=list)


class MusicDiscoveryEngine:
    """Intelligent recommendation and music discovery engine."""

    def __init__(self):
        self.genre_engine = GenreEngine()
        self.audio_analyzer = AudioAnalyzer()
        self.deezer_provider = DeezerProvider()

    def record_event(
        self,
        session: Session,
        track_id: int,
        event_type: str,  # "played", "recommended", "added", "rejected"
        notes: Optional[str] = None,
    ) -> None:
        """Register a user interaction event in history for recommendation training."""
        entry = UserHistory(
            track_id=track_id,
            event_type=event_type,
            notes=notes,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(entry)
        session.commit()

    def get_rejected_track_ids(self, session: Session) -> set[int]:
        """Fetch IDs of tracks previously rejected by user."""
        rejected = session.exec(
            select(UserHistory.track_id).where(UserHistory.event_type == "rejected")
        ).all()
        return {tid for tid in rejected if tid}

    def get_user_taste_profile(self, library_tracks: list[UnifiedTrack], session: Session) -> dict[str, Any]:
        """Aggregate played and added tracks to compute user's core taste."""
        top_artists = Counter(t.artist for t in library_tracks).most_common(5)
        top_genres = Counter(
            self.genre_engine.get_parent_genre(g) for t in library_tracks for g in t.genres
        ).most_common(5)

        bpms = [t.bpm for t in library_tracks if t.bpm]
        avg_bpm = round(sum(bpms) / len(bpms), 1) if bpms else 120.0

        return {
            "favorite_artists": [a for a, _ in top_artists],
            "favorite_genres": [g for g, _ in top_genres],
            "preferred_bpm": avg_bpm,
        }

    def find_similar_tracks_in_library(
        self, reference_track: UnifiedTrack, catalog: list[UnifiedTrack], limit: int = 10
    ) -> list[UnifiedTrack]:
        """Find library songs harmonically and acoustically close to reference track."""
        similar = []
        for t in catalog:
            if t.id == reference_track.id:
                continue

            score = 0.0
            # Same artist
            if t.artist.lower() == reference_track.artist.lower():
                score += 30.0

            # Harmonic compatibility
            if reference_track.key and t.key:
                if self.audio_analyzer.are_keys_compatible(reference_track.key, t.key):
                    score += 25.0

            # BPM proximity
            if reference_track.bpm and t.bpm:
                if abs(reference_track.bpm - t.bpm) <= 6.0:
                    score += 20.0

            # Shared genres
            if any(g in reference_track.genres for g in t.genres):
                score += 20.0

            if score > 0:
                similar.append((score, t))

        similar.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in similar[:limit]]

    def get_deep_cuts(self, library_tracks: list[UnifiedTrack], limit: int = 10) -> list[UnifiedTrack]:
        """Uncover rarely played or newly added gems in the library."""
        # Sort by lowest play_count
        unplayed = [t for t in library_tracks if (t.play_count or 0) == 0]
        if len(unplayed) >= limit:
            return unplayed[:limit]

        sorted_tracks = sorted(library_tracks, key=lambda t: t.play_count or 0)
        return sorted_tracks[:limit]

    async def get_external_recommendations(
        self, seed_artists: list[str], limit: int = 15
    ) -> list[UnifiedTrack]:
        """Fetch fresh external suggestions from Deezer without requiring authentication."""
        results: list[UnifiedTrack] = []
        seen_titles = set()

        for artist in seed_artists[:3]:
            try:
                tracks = await self.deezer_provider.search_tracks(f"{artist} radio", limit=limit // 2)
                for t in tracks:
                    if t.title.lower() not in seen_titles:
                        results.append(t)
                        seen_titles.add(t.title.lower())
            except Exception as e:
                print(f"[MusicDiscovery] External fetch notice: {e}")

        return results[:limit]

    async def generate_discovery_feed(
        self, library_tracks: list[UnifiedTrack], session: Session
    ) -> list[DiscoverySection]:
        """Compile a multi-section discovery hub for the UI."""
        sections: list[DiscoverySection] = []
        rejected_ids = self.get_rejected_track_ids(session)
        clean_library = [t for t in library_tracks if t.id not in rejected_ids]

        taste = self.get_user_taste_profile(clean_library, session)

        # Section 1: "Você Provavelmente Vai Gostar" (Personalized)
        if clean_library:
            ref = clean_library[0]
            recommended = self.find_similar_tracks_in_library(ref, clean_library, limit=8)
            sections.append(
                DiscoverySection(
                    title="Você Provavelmente Vai Gostar",
                    description=f"Baseado no seu gosto por {taste['favorite_artists'][:2]} e {taste['favorite_genres'][:2]}.",
                    tracks=recommended,
                )
            )

        # Section 2: "Deep Cuts do Seu Acervo" (Faixas esquecidas)
        deep_cuts = self.get_deep_cuts(clean_library, limit=8)
        if deep_cuts:
            sections.append(
                DiscoverySection(
                    title="Baús do Acervo (Deep Cuts)",
                    description="Músicas na sua biblioteca que você ainda ouviu pouco.",
                    tracks=deep_cuts,
                )
            )

        # Section 3: "Descobertas Externas" (Fresh recommendations via Deezer)
        if taste["favorite_artists"]:
            external = await self.get_external_recommendations(taste["favorite_artists"], limit=8)
            if external:
                sections.append(
                    DiscoverySection(
                        title="Novidades & Descobertas no Deezer",
                        description="Faixas relacionadas aos seus artistas favoritos disponíveis para prévia e adição.",
                        tracks=external,
                    )
                )

        return sections
