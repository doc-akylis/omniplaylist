from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional
from sqlmodel import Session, delete, select

from app.core.models import Playlist, PlaylistTrackLink, UnifiedTrack


class PlaylistManagerEngine:
    """Full N:N Playlist Manager: CRUD, persistent ordering, multi-criteria sorting, quality statuses, and metrics."""

    @staticmethod
    def classify_track_status(track: UnifiedTrack) -> list[str]:
        """Return explicit quality & file status flags for a track."""
        statuses: list[str] = []
        has_file = bool(track.local_path and Path(track.local_path).exists())

        if track.is_corrupted:
            statuses.append("CORRUPTED")
        if track.local_path and not has_file:
            statuses.append("MISSING")
        elif not track.local_path:
            if track.is_preview or track.preview_url:
                statuses.append("PREVIEW")
            else:
                statuses.append("MISSING")
        elif track.is_preview:
            statuses.append("PREVIEW")
        else:
            statuses.append("COMPLETE")

        if track.analyzed_at is None or track.quality_analyzed_at is None:
            statuses.append("ANALYSIS_PENDING")
        if track.is_fake_upscale or track.upscale_status in ("LIKELY_UPSCALE", "SUSPECTED_UPSCALE"):
            statuses.append("SUSPECTED_FAKE_UPSCALE")
        if (track.source_classification or "UNKNOWN_SOURCE") == "UNKNOWN_SOURCE":
            statuses.append("UNKNOWN_SOURCE")

        low_quality = bool(
            (track.car_audio_score is not None and track.car_audio_score < 55.0)
            or (track.bitrate_kbps is not None and 0 < track.bitrate_kbps < 160 and (track.codec or "").lower() in {"mp3", "aac", "m4a", "ogg"})
        )
        if low_quality:
            statuses.append("LOW_QUALITY")

        if track.is_preview or "SUSPECTED_FAKE_UPSCALE" in statuses or "LOW_QUALITY" in statuses:
            statuses.append("UPGRADE_AVAILABLE")

        return statuses

    def get_ordered_tracks(self, session: Session, playlist_id: int) -> list[UnifiedTrack]:
        """Return playlist tracks ordered persistently by PlaylistTrackLink.position."""
        stmt = (
            select(UnifiedTrack, PlaylistTrackLink)
            .join(PlaylistTrackLink, UnifiedTrack.id == PlaylistTrackLink.track_id)
            .where(PlaylistTrackLink.playlist_id == playlist_id)
            .order_by(PlaylistTrackLink.position.asc(), UnifiedTrack.id.asc())
        )
        rows = session.exec(stmt).all()
        return [t for t, _ in rows]

    def create_playlist(
        self,
        session: Session,
        name: str,
        description: Optional[str] = None,
        cover_url: Optional[str] = None,
        track_ids: Optional[list[int]] = None,
    ) -> Playlist:
        pl = Playlist(
            name=name.strip(),
            description=description,
            cover_url=cover_url,
            source_provider="local",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(pl)
        session.commit()
        session.refresh(pl)

        if track_ids:
            self.add_tracks(session, pl.id or 0, track_ids)
            session.refresh(pl)
        return pl

    def update_playlist(
        self,
        session: Session,
        playlist_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        cover_url: Optional[str] = None,
    ) -> Optional[Playlist]:
        pl = session.get(Playlist, playlist_id)
        if not pl:
            return None
        if name is not None and name.strip():
            pl.name = name.strip()
        if description is not None:
            pl.description = description
        if cover_url is not None:
            pl.cover_url = cover_url
        pl.updated_at = datetime.now(timezone.utc)
        session.add(pl)
        session.commit()
        session.refresh(pl)
        return pl

    def delete_playlist(self, session: Session, playlist_id: int) -> bool:
        """Delete playlist and its N:N link rows without deleting UnifiedTrack records."""
        pl = session.get(Playlist, playlist_id)
        if not pl:
            return False
        session.exec(delete(PlaylistTrackLink).where(PlaylistTrackLink.playlist_id == playlist_id))
        session.delete(pl)
        session.commit()
        return True

    def duplicate_playlist(
        self, session: Session, playlist_id: int, new_name: Optional[str] = None
    ) -> Optional[Playlist]:
        src = session.get(Playlist, playlist_id)
        if not src:
            return None
        ordered = self.get_ordered_tracks(session, playlist_id)
        dup = self.create_playlist(
            session=session,
            name=new_name or f"{src.name} (Cópia)",
            description=src.description,
            cover_url=src.cover_url,
            track_ids=[t.id for t in ordered if t.id is not None],
        )
        return dup

    def add_tracks(self, session: Session, playlist_id: int, track_ids: list[int]) -> int:
        pl = session.get(Playlist, playlist_id)
        if not pl:
            return 0
        existing_links = session.exec(
            select(PlaylistTrackLink).where(PlaylistTrackLink.playlist_id == playlist_id)
        ).all()
        existing_ids = {lnk.track_id for lnk in existing_links}
        next_pos = max((lnk.position for lnk in existing_links), default=-1) + 1

        added = 0
        for tid in track_ids:
            if tid in existing_ids:
                continue
            if not session.get(UnifiedTrack, tid):
                continue
            session.add(
                PlaylistTrackLink(
                    playlist_id=playlist_id,
                    track_id=tid,
                    position=next_pos,
                    added_at=datetime.now(timezone.utc),
                )
            )
            existing_ids.add(tid)
            next_pos += 1
            added += 1

        if added:
            pl.updated_at = datetime.now(timezone.utc)
            session.add(pl)
            session.commit()
        return added

    def remove_tracks(self, session: Session, playlist_id: int, track_ids: list[int]) -> int:
        pl = session.get(Playlist, playlist_id)
        if not pl or not track_ids:
            return 0
        target_set = set(track_ids)
        links = session.exec(
            select(PlaylistTrackLink)
            .where(PlaylistTrackLink.playlist_id == playlist_id)
            .order_by(PlaylistTrackLink.position.asc())
        ).all()
        removed = 0
        kept: list[PlaylistTrackLink] = []
        for lnk in links:
            if lnk.track_id in target_set:
                session.delete(lnk)
                removed += 1
            else:
                kept.append(lnk)

        for idx, lnk in enumerate(kept):
            lnk.position = idx
            session.add(lnk)

        pl.updated_at = datetime.now(timezone.utc)
        session.add(pl)
        session.commit()
        return removed

    def reorder_tracks(
        self,
        session: Session,
        playlist_id: int,
        ordered_track_ids: list[int],
        save_manual_snapshot: bool = False,
    ) -> list[UnifiedTrack]:
        pl = session.get(Playlist, playlist_id)
        if not pl:
            return []
        links = session.exec(
            select(PlaylistTrackLink)
            .where(PlaylistTrackLink.playlist_id == playlist_id)
            .order_by(PlaylistTrackLink.position.asc())
        ).all()
        if save_manual_snapshot and not pl.original_order_json:
            pl.original_order_json = json.dumps([lnk.track_id for lnk in links])

        by_tid = {lnk.track_id: lnk for lnk in links}
        seen: set[int] = set()
        pos = 0
        for tid in ordered_track_ids:
            if tid in by_tid and tid not in seen:
                by_tid[tid].position = pos
                session.add(by_tid[tid])
                seen.add(tid)
                pos += 1
        # Keep any tracks omitted from ordered_track_ids at the tail
        for lnk in links:
            if lnk.track_id not in seen:
                lnk.position = pos
                session.add(lnk)
                pos += 1

        pl.updated_at = datetime.now(timezone.utc)
        session.add(pl)
        session.commit()
        return self.get_ordered_tracks(session, playlist_id)

    def sort_playlist(
        self,
        session: Session,
        playlist_id: int,
        sort_by: str,
        persist: bool = True,
    ) -> list[UnifiedTrack]:
        tracks = self.get_ordered_tracks(session, playlist_id)
        if not tracks or sort_by == "manual":
            return tracks

        def _camelot_key(t: UnifiedTrack) -> tuple[int, str]:
            code = (t.camelot_code or t.key or "").upper()
            if len(code) >= 2 and code[:-1].isdigit():
                return int(code[:-1]), code[-1]
            return 99, code

        key_funcs = {
            "bpm_asc": lambda t: (t.bpm is None, t.bpm or 0.0),
            "bpm_desc": lambda t: (t.bpm is None, -(t.bpm or 0.0)),
            "energy_asc": lambda t: (t.energy is None, t.energy or 0.0),
            "energy_desc": lambda t: (t.energy is None, -(t.energy or 0.0)),
            "camelot": _camelot_key,
            "artist": lambda t: (t.artist or "").lower(),
            "album": lambda t: (t.album or "zzz").lower(),
            "duration": lambda t: (t.duration_ms is None, t.duration_ms or 0),
            "year": lambda t: (t.release_year is None, t.release_year or 9999),
            "loudness": lambda t: (t.integrated_lufs is None, t.integrated_lufs or -99.0),
            "quality": lambda t: (t.car_audio_score is None, -(t.car_audio_score or 0.0)),
            "file_status": lambda t: self.classify_track_status(t)[0],
        }
        fn = key_funcs.get(sort_by)
        sorted_tracks = sorted(tracks, key=fn) if fn else tracks
        if persist:
            return self.reorder_tracks(
                session,
                playlist_id,
                [t.id for t in sorted_tracks if t.id is not None],
                save_manual_snapshot=True,
            )
        return sorted_tracks

    def compute_playlist_metrics(self, tracks: list[UnifiedTrack]) -> dict[str, Any]:
        """Compute real aggregated playlist metrics explicitly skipping null fields without fabricating data."""
        total = len(tracks)
        total_duration_ms = sum(t.duration_ms or 0 for t in tracks)
        bpms = [t.bpm for t in tracks if t.bpm is not None and t.bpm > 0]
        energies = [t.energy for t in tracks if t.energy is not None]
        lufs_vals = [t.integrated_lufs for t in tracks if t.integrated_lufs is not None]
        quality_scores = [t.car_audio_score for t in tracks if t.car_audio_score is not None]
        camelot_counts = Counter(t.camelot_code for t in tracks if t.camelot_code)

        complete_count = 0
        preview_count = 0
        missing_count = 0
        corrupted_count = 0
        upgrades_available_count = 0
        fake_upscale_count = 0

        for t in tracks:
            st = set(self.classify_track_status(t))
            if "COMPLETE" in st:
                complete_count += 1
            if "PREVIEW" in st:
                preview_count += 1
            if "MISSING" in st:
                missing_count += 1
            if "CORRUPTED" in st:
                corrupted_count += 1
            if "UPGRADE_AVAILABLE" in st:
                upgrades_available_count += 1
            if "SUSPECTED_FAKE_UPSCALE" in st:
                fake_upscale_count += 1

        notes: list[str] = []
        if total > 0 and len(bpms) < total:
            notes.append(f"BPM médio calculado sobre {len(bpms)}/{total} faixas analisadas.")
        if total > 0 and len(lufs_vals) < total:
            notes.append(f"LUFS médio calculado sobre {len(lufs_vals)}/{total} faixas analisadas.")

        return {
            "total_tracks": total,
            "total_duration_ms": total_duration_ms,
            "avg_bpm": round(sum(bpms) / len(bpms), 1) if bpms else None,
            "min_bpm": round(min(bpms), 1) if bpms else None,
            "max_bpm": round(max(bpms), 1) if bpms else None,
            "avg_energy": round(sum(energies) / len(energies), 3) if energies else None,
            "camelot_distribution": dict(camelot_counts),
            "avg_lufs": round(sum(lufs_vals) / len(lufs_vals), 2) if lufs_vals else None,
            "avg_quality_score": round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None,
            "complete_count": complete_count,
            "preview_count": preview_count,
            "missing_count": missing_count,
            "corrupted_count": corrupted_count,
            "upgrades_available_count": upgrades_available_count,
            "fake_upscale_count": fake_upscale_count,
            "metrics_notes": notes,
        }
