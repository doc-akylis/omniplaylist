from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Optional
from rapidfuzz import fuzz
from sqlmodel import Session, select

from app.core.models import Playlist, PlaylistTrackLink, UnifiedTrack
from app.engines.deduplicator import Deduplicator
from app.engines.metadata_engine import MetadataEngine


@dataclass
class HealthIssue:
    """A detected anomaly or quality problem in a playlist or library track."""

    track_id: int
    track_title: str
    track_artist: str
    category: str  # "duplicate", "broken_file", "missing_cover", "missing_album", "live_mixed", "suspicious_duration", "unmatched"
    severity: str  # "warning", "error", "info"
    description: str
    suggested_action: str


@dataclass
class HealthReport:
    """Aggregated health evaluation of a playlist or the entire library."""

    total_tracks_checked: int
    health_score: float  # 0.0 to 100.0%
    issues: list[HealthIssue] = field(default_factory=list)
    category_summary: dict[str, int] = field(default_factory=dict)


class PlaylistHealthEngine:
    """Audits playlists for dead links, metadata gaps, duplicates, and incongruities."""

    LIVE_REGEX = re.compile(r"[\(\[\{].*?(live|ao vivo|en vivo).*?[\)\]\}]", re.IGNORECASE)

    def __init__(self):
        self.metadata_engine = MetadataEngine()
        self.deduplicator = Deduplicator()
        self.audit_log: list[dict[str, Any]] = []

    def audit_tracks(self, tracks: list[UnifiedTrack]) -> HealthReport:
        """Run complete diagnostic check on a list of tracks."""
        issues: list[HealthIssue] = []
        total = len(tracks)

        if total == 0:
            return HealthReport(total_tracks_checked=0, health_score=100.0)

        # 1. Check duplicates
        dup_groups = self.deduplicator.find_duplicate_groups(tracks)
        for grp in dup_groups:
            cand_names = ", ".join(f"#{c.id} {c.title}" for c in grp["candidates"])
            issues.append(
                HealthIssue(
                    track_id=grp["primary"].id or 0,
                    track_title=grp["primary"].title,
                    track_artist=grp["primary"].artist,
                    category="duplicate",
                    severity="warning",
                    description=f"Possível duplicata encontrada com: {cand_names}",
                    suggested_action="Mesclar ou remover duplicatas",
                )
            )

        # 2. Check individual track anomalies
        live_tracks = []
        studio_tracks = []

        for t in tracks:
            t_id = t.id or 0

            # Missing cover art
            if not t.cover_url and not t.hd_cover_url:
                issues.append(
                    HealthIssue(
                        track_id=t_id,
                        track_title=t.title,
                        track_artist=t.artist,
                        category="missing_cover",
                        severity="info",
                        description="Faixa não possui capa de álbum cadastrada.",
                        suggested_action="Buscar capa em alta definição via iTunes/Deezer",
                    )
                )

            # Missing album
            if not t.album or t.album.strip() in ["", "—", "Unknown Album", "Unknown"]:
                issues.append(
                    HealthIssue(
                        track_id=t_id,
                        track_title=t.title,
                        track_artist=t.artist,
                        category="missing_album",
                        severity="info",
                        description="Álbum não especificado.",
                        suggested_action="Identificar álbum oficial via catálogo",
                    )
                )

            # Broken local file
            if t.local_path and not Path(t.local_path).exists():
                issues.append(
                    HealthIssue(
                        track_id=t_id,
                        track_title=t.title,
                        track_artist=t.artist,
                        category="broken_file",
                        severity="error",
                        description=f"Arquivo local não encontrado no disco: {t.local_path}",
                        suggested_action="Rebaixar áudio ou remover vínculo local",
                    )
                )

            # Suspicious duration (< 30 seconds or > 20 minutes)
            if t.duration_ms:
                dur_sec = t.duration_ms / 1000
                if dur_sec < 30:
                    issues.append(
                        HealthIssue(
                            track_id=t_id,
                            track_title=t.title,
                            track_artist=t.artist,
                            category="suspicious_duration",
                            severity="warning",
                            description=f"Duração muito curta ({int(dur_sec)}s). Possível vinheta ou áudio incompleto.",
                            suggested_action="Verificar se a faixa está completa",
                        )
                    )
                elif dur_sec > 1200:
                    issues.append(
                        HealthIssue(
                            track_id=t_id,
                            track_title=t.title,
                            track_artist=t.artist,
                            category="suspicious_duration",
                            severity="info",
                            description=f"Duração incomum ({int(dur_sec / 60)} min). Possível set ou gravação contínua.",
                            suggested_action="Verificar se é faixa individual",
                        )
                    )

            # Provider match check
            if not t.isrc and not t.spotify_id and not t.ytmusic_id and not t.deezer_id:
                issues.append(
                    HealthIssue(
                        track_id=t_id,
                        track_title=t.title,
                        track_artist=t.artist,
                        category="unmatched",
                        severity="info",
                        description="Faixa não vinculada a nenhum provedor oficial de streaming.",
                        suggested_action="Localizar correspondência via ISRC ou Deezer",
                    )
                )

            # Detect Live vs Studio
            if self.LIVE_REGEX.search(t.title):
                live_tracks.append(t)
            else:
                studio_tracks.append(t)

        # 3. Check live versions mixed with studio
        if live_tracks and studio_tracks and len(live_tracks) <= len(studio_tracks) * 0.3:
            for lt in live_tracks:
                issues.append(
                    HealthIssue(
                        track_id=lt.id or 0,
                        track_title=lt.title,
                        track_artist=lt.artist,
                        category="live_mixed",
                        severity="info",
                        description="Versão ao vivo misturada em playlist predominantemente de estúdio.",
                        suggested_action="Substituir por versão de estúdio equivalente",
                    )
                )

        # Compute summary
        cat_counts: dict[str, int] = {}
        for iss in issues:
            cat_counts[iss.category] = cat_counts.get(iss.category, 0) + 1

        # Calculate health score: start 100, deduct for errors/warnings
        penalty = 0.0
        for iss in issues:
            if iss.severity == "error":
                penalty += 15.0
            elif iss.severity == "warning":
                penalty += 8.0
            else:
                penalty += 2.0

        health_score = max(0.0, min(100.0, round(100.0 - (penalty / max(1, total)) * 10, 1)))

        return HealthReport(
            total_tracks_checked=total,
            health_score=health_score,
            issues=issues,
            category_summary=cat_counts,
        )

    async def fix_missing_covers_batch(self, tracks: list[UnifiedTrack], session: Session) -> int:
        """Fetch HD artwork for tracks missing covers."""
        fixed_count = 0
        for t in tracks:
            if not t.cover_url and not t.hd_cover_url:
                hd_url = await self.metadata_engine.fetch_hd_artwork(t)
                if hd_url:
                    t.hd_cover_url = hd_url
                    t.cover_url = hd_url
                    session.add(t)
                    fixed_count += 1
                    self.audit_log.append({
                        "action": "fix_cover",
                        "track_id": t.id,
                        "title": t.title,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
        if fixed_count > 0:
            session.commit()
        return fixed_count

    def remove_broken_paths_batch(self, tracks: list[UnifiedTrack], session: Session) -> int:
        """Clear local_path on tracks whose audio file is missing on disk."""
        cleared_count = 0
        for t in tracks:
            if t.local_path and not Path(t.local_path).exists():
                self.audit_log.append({
                    "action": "clear_broken_path",
                    "track_id": t.id,
                    "old_path": t.local_path,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                t.local_path = None
                session.add(t)
                cleared_count += 1
        if cleared_count > 0:
            session.commit()
        return cleared_count
