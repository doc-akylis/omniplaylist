import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import librosa
import numpy as np
from sqlmodel import Session, select

from app.core.models import UnifiedTrack
from app.engines.audio_analyzer import AudioAnalyzer

# Krumhansl-Schmuckler (1990) tonal key profiles
_KRUMHANSL_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float64,
)
_KRUMHANSL_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float64,
)
_PITCH_CLASSES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


@dataclass
class BeatgridData:
    """Serialized beatgrid and 4/4 bar downbeat timestamps in seconds."""

    beats_sec: list[float]
    downbeats_sec: list[float]
    time_signature: str
    total_beats: int


@dataclass
class MusicalSection:
    """Estimated structural segment of a track."""

    label: str
    start_sec: float
    end_sec: float
    relative_energy: float
    confidence: float


@dataclass
class MusicalAnalysisResult:
    """Complete Layer-1 musical analysis output (algorithmic estimates)."""

    bpm: float
    bpm_stability: float
    key: str
    camelot_code: str
    key_confidence: float
    energy: float
    danceability: float
    beatgrid: BeatgridData
    sections: list[MusicalSection]
    confidence: float
    is_estimated: bool = True
    estimation_method: str = "librosa_krumhansl_schmuckler"


class MusicalAnalysisEngine:
    """Non-blocking musical analysis engine using librosa + numpy in worker threads."""

    TARGET_SR = 22050

    def __init__(self, max_concurrent: int = 2):
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_audio(self, file_path: Path) -> Optional[MusicalAnalysisResult]:
        """Run CPU-bound librosa extraction in a worker thread without blocking the event loop."""
        if not file_path.exists():
            return None

        async with self._semaphore:
            return await asyncio.to_thread(self._extract_sync, file_path)

    def _extract_sync(self, file_path: Path) -> Optional[MusicalAnalysisResult]:
        """Synchronous CPU-bound feature extraction executed inside a worker thread."""
        try:
            y, sr = librosa.load(str(file_path), sr=self.TARGET_SR, mono=True)
        except Exception as e:
            print(f"[MusicalAnalysis] Failed to load {file_path}: {e}")
            return None

        duration_sec = float(len(y)) / float(sr) if sr > 0 else 0.0
        if y.size == 0 or duration_sec < 0.5:
            return None

        # 1. Onset envelope, BPM, beatgrid & stability
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        bpm, bpm_stability, beatgrid = self._extract_rhythm(onset_env, sr)

        # 2. Key & Camelot mapping via Krumhansl-Schmuckler
        key_name, camelot_code, key_confidence = self._extract_key(y, sr)

        # 3. Algorithmic energy & danceability estimates (0.0 - 1.0)
        rms = librosa.feature.rms(y=y)[0]
        energy = self._estimate_energy(rms, onset_env)
        danceability = self._estimate_danceability(bpm, bpm_stability, onset_env)

        # 4. Structural segmentation
        sections = self._segment_structure(y, sr, rms, duration_sec)

        overall_confidence = round(
            float(np.clip(0.5 * key_confidence + 0.5 * bpm_stability, 0.0, 1.0)),
            3,
        )

        return MusicalAnalysisResult(
            bpm=bpm,
            bpm_stability=bpm_stability,
            key=key_name,
            camelot_code=camelot_code,
            key_confidence=key_confidence,
            energy=energy,
            danceability=danceability,
            beatgrid=beatgrid,
            sections=sections,
            confidence=overall_confidence,
        )

    def _extract_rhythm(
        self, onset_env: np.ndarray, sr: int
    ) -> tuple[float, float, BeatgridData]:
        """Extract average BPM, tempo stability (0-1) and 4/4 beatgrid."""
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_env, sr=sr, units="frames"
        )
        bpm_val = float(np.atleast_1d(tempo)[0]) if np.size(tempo) > 0 else 0.0
        bpm_val = round(bpm_val, 2)

        beat_times = (
            librosa.frames_to_time(beat_frames, sr=sr).tolist()
            if len(beat_frames) > 0
            else []
        )
        beats_sec = [round(float(t), 3) for t in beat_times]

        # Estimate local tempo stability from inter-beat intervals
        if len(beat_times) >= 4:
            ibis = np.diff(np.array(beat_times, dtype=np.float64))
            local_bpms = 60.0 / np.clip(ibis, 1e-4, None)
            mean_bpm = float(np.mean(local_bpms))
            cv = float(np.std(local_bpms)) / max(mean_bpm, 1e-4)
            bpm_stability = round(float(np.clip(1.0 - min(cv, 1.0), 0.0, 1.0)), 3)
        elif len(beat_times) >= 2:
            bpm_stability = 0.6
        else:
            bpm_stability = 0.3

        # Align 4/4 downbeats to strongest onset among the first 4 beats
        downbeats_sec: list[float] = []
        if len(beat_frames) > 0:
            first_bar_len = min(4, len(beat_frames))
            strengths = [
                float(onset_env[min(int(f), len(onset_env) - 1)])
                for f in beat_frames[:first_bar_len]
            ]
            offset = int(np.argmax(strengths))
            downbeats_sec = beats_sec[offset::4]

        beatgrid = BeatgridData(
            beats_sec=beats_sec,
            downbeats_sec=downbeats_sec,
            time_signature="4/4",
            total_beats=len(beats_sec),
        )
        return bpm_val, bpm_stability, beatgrid

    def _extract_key(self, y: np.ndarray, sr: int) -> tuple[str, str, float]:
        """Estimate musical key using chroma_cqt and Krumhansl-Schmuckler profiles."""
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)

        if float(np.sum(chroma_mean)) <= 1e-9:
            return "C", "8B", 0.0

        best_score = -1.0
        second_score = -1.0
        best_key = "C"

        for idx, pitch in enumerate(_PITCH_CLASSES):
            maj_profile = np.roll(_KRUMHANSL_MAJOR, idx)
            min_profile = np.roll(_KRUMHANSL_MINOR, idx)

            for suffix, profile in (("", maj_profile), ("m", min_profile)):
                corr = float(np.corrcoef(chroma_mean, profile)[0, 1])
                if np.isnan(corr):
                    corr = 0.0
                if corr > best_score:
                    second_score = best_score
                    best_score = corr
                    best_key = f"{pitch}{suffix}"
                elif corr > second_score:
                    second_score = corr

        camelot = AudioAnalyzer.normalize_to_camelot(best_key) or "8B"
        margin = max(0.0, best_score - max(second_score, 0.0))
        confidence = round(
            float(np.clip(0.7 * ((best_score + 1.0) / 2.0) + 0.3 * min(margin * 4.0, 1.0), 0.0, 1.0)),
            3,
        )
        return best_key, camelot, confidence

    def _estimate_energy(self, rms: np.ndarray, onset_env: np.ndarray) -> float:
        """Algorithmic energy estimate (0.0-1.0) from RMS amplitude and onset density."""
        rms_mean = float(np.mean(rms)) if rms.size > 0 else 0.0
        rms_norm = float(np.clip(rms_mean / 0.25, 0.0, 1.0))

        onset_mean = float(np.mean(onset_env)) if onset_env.size > 0 else 0.0
        onset_norm = float(np.clip(onset_mean / 4.0, 0.0, 1.0))

        return round(float(np.clip(0.7 * rms_norm + 0.3 * onset_norm, 0.0, 1.0)), 3)

    def _estimate_danceability(
        self, bpm: float, bpm_stability: float, onset_env: np.ndarray
    ) -> float:
        """Algorithmic danceability estimate (0.0-1.0) from tempo, stability and pulse clarity."""
        # Dance-floor sweet spot centered around ~120 BPM
        tempo_score = float(np.exp(-((bpm - 120.0) ** 2) / (2.0 * 35.0**2))) if bpm > 0 else 0.0

        if onset_env.size > 0:
            p95 = float(np.percentile(onset_env, 95))
            mean_val = float(np.mean(onset_env))
            pulse_clarity = float(np.clip((p95 - mean_val) / max(p95, 1e-6), 0.0, 1.0))
        else:
            pulse_clarity = 0.0

        score = 0.45 * bpm_stability + 0.30 * pulse_clarity + 0.25 * tempo_score
        return round(float(np.clip(score, 0.0, 1.0)), 3)

    def _segment_structure(
        self, y: np.ndarray, sr: int, rms: np.ndarray, duration_sec: float
    ) -> list[MusicalSection]:
        """Segment track into structural sections using MFCC novelty boundaries."""
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_diff = np.linalg.norm(np.diff(mfcc, axis=1), axis=0) if mfcc.shape[1] > 1 else np.zeros(1)

        hop_length = 512
        # Smooth novelty curve and pick structural boundaries
        win = max(1, int(round(2.0 * sr / hop_length)))
        kernel = np.ones(win, dtype=np.float64) / float(win)
        novelty = np.convolve(mfcc_diff, kernel, mode="same") if mfcc_diff.size >= win else mfcc_diff

        min_seg_sec = min(8.0, max(1.5, duration_sec / 4.0))
        min_seg_frames = max(1, int(round(min_seg_sec * sr / hop_length)))

        boundaries_sec: list[float] = [0.0]
        if novelty.size > min_seg_frames * 2:
            threshold = float(np.mean(novelty) + 0.75 * np.std(novelty))
            peaks = librosa.util.peak_pick(
                novelty,
                pre_max=min_seg_frames,
                post_max=min_seg_frames,
                pre_avg=min_seg_frames,
                post_avg=min_seg_frames,
                delta=max(threshold * 0.15, 1e-4),
                wait=min_seg_frames,
            )
            for p in peaks:
                t = float(librosa.frames_to_time(int(p), sr=sr, hop_length=hop_length))
                if min_seg_sec <= t <= duration_sec - min_seg_sec:
                    boundaries_sec.append(round(t, 2))
        boundaries_sec.append(round(duration_sec, 2))

        # Compute per-segment relative energy and label heuristically
        rms_max = max(float(np.percentile(rms, 95)) if rms.size > 0 else 1.0, 1e-6)
        rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)

        sections: list[MusicalSection] = []
        total_segs = len(boundaries_sec) - 1
        for i in range(total_segs):
            start_t = boundaries_sec[i]
            end_t = boundaries_sec[i + 1]
            mask = (rms_times >= start_t) & (rms_times <= end_t)
            seg_rms = float(np.mean(rms[mask])) if np.any(mask) else float(np.mean(rms))
            rel_energy = round(float(np.clip(seg_rms / rms_max, 0.0, 1.0)), 3)

            if i == 0 and total_segs > 1 and rel_energy < 0.75:
                label = "intro"
            elif i == total_segs - 1 and total_segs > 1 and rel_energy < 0.75:
                label = "outro"
            elif rel_energy >= 0.72:
                label = "chorus"
            elif rel_energy <= 0.42:
                label = "breakdown"
            else:
                label = "verse"

            sections.append(
                MusicalSection(
                    label=label,
                    start_sec=start_t,
                    end_sec=end_t,
                    relative_energy=rel_energy,
                    confidence=0.65,
                )
            )

        return sections

    async def analyze_and_persist(
        self, track: UnifiedTrack, session: Session, force: bool = False
    ) -> bool:
        """Analyze a track's local audio file and persist musical metrics to SQLite."""
        if not track.local_path:
            return False

        file_path = Path(track.local_path)
        if not file_path.exists():
            return False

        if track.musical_analyzed_at is not None and not force:
            return False

        result = await self.analyze_audio(file_path)
        if result is None:
            return False

        track.bpm = result.bpm
        track.key = result.camelot_code
        track.camelot_code = result.camelot_code
        track.bpm_stability = result.bpm_stability
        track.energy = result.energy
        track.danceability = result.danceability
        track.beatgrid_json = json.dumps(asdict(result.beatgrid))
        track.sections_json = json.dumps([asdict(s) for s in result.sections])
        track.musical_analysis_confidence = result.confidence
        track.musical_analyzed_at = datetime.now(timezone.utc)
        track.updated_at = datetime.now(timezone.utc)

        session.add(track)
        session.commit()
        session.refresh(track)
        return True

    async def analyze_library(
        self,
        session_factory: Callable[[], Session],
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
        force: bool = False,
        batch_size: int = 20,
    ) -> dict[str, int]:
        """Process all tracks with local_path in controlled async batches."""
        stats = {"analyzed": 0, "skipped": 0, "errors": 0}

        with session_factory() as session:
            track_ids = session.exec(
                select(UnifiedTrack.id).where(UnifiedTrack.local_path.is_not(None))
            ).all()

        total = len(track_ids)
        for i in range(0, total, batch_size):
            batch_ids = track_ids[i : i + batch_size]

            async def process_track(track_id: int) -> str:
                try:
                    with session_factory() as session:
                        track = session.get(UnifiedTrack, track_id)
                        if track:
                            ok = await self.analyze_and_persist(track, session, force=force)
                            return "analyzed" if ok else "skipped"
                        return "skipped"
                except Exception as e:
                    print(f"[MusicalAnalysis] Error analyzing track {track_id}: {e}")
                    return "error"

            results = await asyncio.gather(
                *(process_track(tid) for tid in batch_ids if tid is not None),
                return_exceptions=True,
            )

            for r in results:
                if isinstance(r, Exception) or r == "error":
                    stats["errors"] += 1
                elif r == "analyzed":
                    stats["analyzed"] += 1
                else:
                    stats["skipped"] += 1

            if progress_callback:
                progress_callback(min(i + batch_size, total), total, "Analisando musicalmente...")

        return stats
