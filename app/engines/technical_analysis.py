import asyncio
import json
import os
import re
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlmodel import Session, select

from app.core.models import UnifiedTrack
from app.core.database import get_session
from app.config import get_settings


@dataclass
class FFProbeInfo:
    """Resultado bruto do ffprobe -show_format -show_streams -print_format json"""

    format_name: str
    format_long_name: str
    duration_sec: float
    bitrate_kbps: int
    size_bytes: int
    codec_name: str
    codec_long_name: str
    sample_rate_hz: int
    channels: int
    channel_layout: str
    bit_depth: Optional[int]
    bits_per_raw_sample: Optional[int]
    tags: dict[str, str]


@dataclass
class FFmpegAnalysis:
    """Resultado dos filtros FFmpeg encadeados: ebur128 + astats + silencedetect"""

    # EBU R128 (ebur128 filter)
    integrated_lufs: float
    true_peak_dbfs: float
    momentary_lufs: float
    short_term_lufs: float
    loudness_range_lu: float

    # Estatísticas de amplitude (astats filter)
    rms_level_db: float
    peak_level_db: float
    dynamic_range_db: float
    crest_factor_db: float
    clipping_detected: bool
    clipping_count: int

    # Silêncio (silencedetect filter)
    silence_start_ms: int
    silence_end_ms: int
    silence_duration_ms: int


def _resolve_ffmpeg_binary(binary_name: str) -> str:
    """
    Resolve o caminho completo do binário ffmpeg/ffprobe no Windows.
    Ordem de prioridade:
    1. Variável de ambiente (ex: FFMPEG_PATH, FFPROBE_PATH)
    2. shutil.which (PATH do sistema)
    3. Pasta do projeto raiz (app/engines/ -> app/ -> project_root)
    4. .venv/Scripts/
    5. Locais comuns de instalação Windows (WinGet, Chocolatey, Scoop, manual)
    6. imageio_ffmpeg (se instalado)
    Retorna o nome do binário se não encontrado (deixará o subprocesso falhar com erro claro).
    """
    # 1. Variável de ambiente específica
    env_var = f"{binary_name.upper()}_PATH"
    if env_path := os.environ.get(env_var):
        if Path(env_path).exists():
            return env_path

    # 2. PATH do sistema
    if which_path := shutil.which(binary_name):
        return which_path

    # 3. Pasta do projeto (raiz do repo) - app/engines/technical_analysis.py -> parents[2] = project_root
    project_root = Path(__file__).resolve().parents[2]
    for candidate in [
        project_root / f"{binary_name}.exe",
        project_root / "bin" / f"{binary_name}.exe",
        project_root / "tools" / f"{binary_name}.exe",
    ]:
        if candidate.exists():
            return str(candidate)

    # 4. .venv/Scripts/
    venv_scripts = project_root / ".venv" / "Scripts"
    candidate = venv_scripts / f"{binary_name}.exe"
    if candidate.exists():
        return str(candidate)

    # 5. Locais comuns Windows
    common_paths = [
        # WinGet
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages" / "Gyan.FFmpeg*" / "ffmpeg-*/bin" / f"{binary_name}.exe",
        # Chocolatey
        Path("C:/ProgramData/chocolatey/bin") / f"{binary_name}.exe",
        # Scoop
        Path(os.environ.get("USERPROFILE", "")) / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / f"{binary_name}.exe",
        # Manual C:\ffmpeg
        Path("C:/ffmpeg/bin") / f"{binary_name}.exe",
        # Manual C:\Program Files\ffmpeg
        Path("C:/Program Files/ffmpeg/bin") / f"{binary_name}.exe",
        Path("C:/Program Files (x86)/ffmpeg/bin") / f"{binary_name}.exe",
    ]
    for pattern in common_paths:
        # Handle glob patterns
        if "*" in str(pattern):
            parent = pattern.parent
            if parent.exists():
                for match in parent.glob(pattern.name):
                    if match.exists():
                        return str(match)
        else:
            if pattern.exists():
                return str(pattern)

    # 6. imageio_ffmpeg (fallback se instalado)
    try:
        import imageio_ffmpeg
        if binary_name == "ffmpeg":
            return imageio_ffmpeg.get_ffmpeg_exe()
        # ffprobe não vem com imageio_ffmpeg, mas tenta o mesmo dir
        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
        ffprobe_candidate = ffmpeg_exe.parent / "ffprobe.exe"
        if ffprobe_candidate.exists():
            return str(ffprobe_candidate)
    except Exception:
        pass

    # Fallback: retorna o nome simples (vai falhar no subprocesso com erro claro)
    return binary_name


class TechnicalAnalysisEngine:
    """Pipeline unificado de análise técnica via FFmpeg/ffprobe - Single Pass."""

    def __init__(
        self,
        target_lufs: float = -14.0,
        silence_threshold_db: float = -50.0,
        max_concurrent: int = 3,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
    ):
        self.target_lufs = target_lufs
        self.silence_threshold_db = silence_threshold_db
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._settings = get_settings()

        # Resolve binários (permite override via parâmetro para testes)
        self.ffmpeg_cmd = ffmpeg_path or _resolve_ffmpeg_binary("ffmpeg")
        self.ffprobe_cmd = ffprobe_path or _resolve_ffmpeg_binary("ffprobe")

        # Log resolved paths for debugging
        if self.ffmpeg_cmd != "ffmpeg":
            print(f"[TechnicalAnalysis] Using ffmpeg: {self.ffmpeg_cmd}")
        if self.ffprobe_cmd != "ffprobe":
            print(f"[TechnicalAnalysis] Using ffprobe: {self.ffprobe_cmd}")

    # --- FFprobe: inspeção técnica rápida e precisa ---
    async def probe_file(self, file_path: Path) -> Optional[FFProbeInfo]:
        """Executa ffprobe -show_format -show_streams -print_format json"""
        if not file_path.exists():
            return None

        cmd = [
            self.ffprobe_cmd,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(file_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                err_msg = stderr.decode("utf-8", errors="ignore")
                print(f"[TechnicalAnalysis] ffprobe failed for {file_path}: {err_msg[:200]}")
                return None

            data = json.loads(stdout.decode("utf-8", errors="ignore"))

            # Encontrar stream de áudio principal
            audio_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_stream = stream
                    break

            if not audio_stream:
                return None

            format_info = data.get("format", {})

            # Bit depth: tentar bits_per_raw_sample, depois bits_per_sample
            bit_depth = audio_stream.get("bits_per_raw_sample")
            if bit_depth is None:
                bit_depth = audio_stream.get("bits_per_sample")
            if bit_depth is not None:
                bit_depth = int(bit_depth)

            bits_per_raw_sample = audio_stream.get("bits_per_raw_sample")
            if bits_per_raw_sample is not None:
                bits_per_raw_sample = int(bits_per_raw_sample)

            return FFProbeInfo(
                format_name=format_info.get("format_name", ""),
                format_long_name=format_info.get("format_long_name", ""),
                duration_sec=float(format_info.get("duration", 0.0)),
                bitrate_kbps=int(format_info.get("bit_rate", 0)) // 1000
                if format_info.get("bit_rate")
                else 0,
                size_bytes=int(format_info.get("size", 0)),
                codec_name=audio_stream.get("codec_name", ""),
                codec_long_name=audio_stream.get("codec_long_name", ""),
                sample_rate_hz=int(audio_stream.get("sample_rate", 0)),
                channels=int(audio_stream.get("channels", 0)),
                channel_layout=audio_stream.get("channel_layout", ""),
                bit_depth=bit_depth,
                bits_per_raw_sample=bits_per_raw_sample,
                tags=format_info.get("tags", {}),
            )

        except Exception as e:
            print(f"[TechnicalAnalysis] ffprobe error for {file_path}: {e}")
            return None

    # --- FFmpeg Single Pass: análise completa em uma única decodificação ---
    async def analyze_audio(self, file_path: Path) -> Optional[FFmpegAnalysis]:
        """
        Executa pipeline único com filtros encadeados:
        -af "ebur128=peak=true,astats=measure_perchannel=none:metadata=1:reset=1,silencedetect=n=-50dB:d=0.5"
        Parseia stderr com os resumos de ebur128, astats e silencedetect.
        """
        if not file_path.exists():
            return None

        # Filtros encadeados em série - uma única passada de I/O
        filter_chain = (
            "ebur128=peak=true,"
            "astats=measure_perchannel=none:metadata=1:reset=1,"
            f"silencedetect=n={self.silence_threshold_db}dB:d=0.5"
        )

        cmd = [
            self.ffmpeg_cmd,
            "-nostats",
            "-i",
            str(file_path),
            "-af",
            filter_chain,
            "-f",
            "null",
            "-",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            output = stderr.decode("utf-8", errors="ignore")

            if proc.returncode != 0:
                print(
                    f"[TechnicalAnalysis] FFmpeg analysis failed (rc={proc.returncode}) "
                    f"for {file_path}: {output[-500:]}"
                )
                return None

            # Parsear stderr unificado
            result = self._parse_combined_output(output)
            if "integrated_lufs" not in result and "rms_level_db" not in result:
                print(
                    f"[TechnicalAnalysis] Could not parse FFmpeg metrics for {file_path}: "
                    f"{output[-500:]}"
                )
                return None

            return FFmpegAnalysis(
                integrated_lufs=result.get("integrated_lufs", 0.0),
                true_peak_dbfs=result.get("true_peak_dbfs", 0.0),
                momentary_lufs=result.get("momentary_lufs", result.get("integrated_lufs", 0.0)),
                short_term_lufs=result.get("short_term_lufs", result.get("integrated_lufs", 0.0)),
                loudness_range_lu=result.get("loudness_range_lu", 0.0),
                rms_level_db=result.get("rms_level_db", 0.0),
                peak_level_db=result.get("peak_level_db", 0.0),
                dynamic_range_db=result.get("dynamic_range_db", 0.0),
                crest_factor_db=result.get("crest_factor_db", 0.0),
                clipping_detected=result.get("clipping_detected", False),
                clipping_count=result.get("clipping_count", 0),
                silence_start_ms=result.get("silence_start_ms", 0),
                silence_end_ms=result.get("silence_end_ms", 0),
                silence_duration_ms=result.get("silence_duration_ms", 0),
            )

        except FileNotFoundError:
            print(f"[TechnicalAnalysis] FFmpeg binary not found at: {self.ffmpeg_cmd}")
            return None
        except Exception as e:
            print(f"[TechnicalAnalysis] Single-pass analysis error for {file_path}: {e}")
            return None

    def _parse_combined_output(self, output: str) -> dict[str, Any]:
        """Parseia stderr do FFmpeg 9.1 com filtros encadeados (ebur128, astats, silencedetect)."""
        result: dict[str, Any] = {}

        # --- EBU R128 ---
        # Summary block no FFmpeg 9.1 é indentado em múltiplas linhas após "Summary:"
        num = r"-?\d+(?:\.\d+)?"

        m = re.search(rf"Integrated loudness:\s*I:\s*({num})\s+LUFS", output)
        if m:
            result["integrated_lufs"] = float(m.group(1))

        m = re.search(rf"Loudness range:\s*LRA:\s*({num})\s+LU", output)
        if m:
            result["loudness_range_lu"] = float(m.group(1))

        m = re.search(rf"True peak:\s*(?:Peak:\s*)?({num})\s+dBFS", output)
        if m:
            result["true_peak_dbfs"] = float(m.group(1))

        # Momentary (M) e Short-term (S)
        m = re.search(rf"Momentary loudness:\s*M:\s*({num})\s+LUFS", output)
        if m:
            result["momentary_lufs"] = float(m.group(1))
        else:
            m_vals = [
                float(val)
                for val in re.findall(rf"Parsed_ebur128_\d+.*?\bM:\s*({num})", output)
            ]
            valid_m = [v for v in m_vals if v > -120.0]
            if valid_m:
                result["momentary_lufs"] = valid_m[-1]
            elif m_vals:
                result["momentary_lufs"] = m_vals[-1]

        m = re.search(rf"Short-term loudness:\s*S:\s*({num})\s+LUFS", output)
        if m:
            result["short_term_lufs"] = float(m.group(1))
        else:
            s_vals = [
                float(val)
                for val in re.findall(rf"Parsed_ebur128_\d+.*?\bS:\s*({num})", output)
            ]
            valid_s = [v for v in s_vals if v > -120.0]
            if valid_s:
                result["short_term_lufs"] = valid_s[-1]
            elif s_vals:
                result["short_term_lufs"] = s_vals[-1]

        # --- ASTATS ---
        m = re.search(rf"RMS level(?:\s+dB)?:\s*({num})(?:\s+dB)?", output)
        if m:
            result["rms_level_db"] = float(m.group(1))

        m = re.search(rf"Peak level(?:\s+dB)?:\s*({num})(?:\s+dB)?", output)
        if m:
            result["peak_level_db"] = float(m.group(1))

        # Clipping: formato explícito ou detecção real via Peak level dB >= 0 / Peak count no FFmpeg 9.1
        m = re.search(r"Clipping:\s*(\d+)", output)
        if m:
            result["clipping_count"] = int(m.group(1))
        else:
            peak_db = result.get("peak_level_db")
            true_peak = result.get("true_peak_dbfs")
            is_full_scale = (peak_db is not None and peak_db >= -0.01) or (
                true_peak is not None and true_peak >= 0.0
            )
            if is_full_scale:
                m_peak_cnt = re.search(r"(?:Abs )?Peak count:\s*(\d+(?:\.\d+)?)", output)
                count = int(float(m_peak_cnt.group(1))) if m_peak_cnt else 1
                result["clipping_count"] = max(count, 1)
            else:
                result["clipping_count"] = 0

        # Derived: Dynamic Range e Crest Factor
        if "rms_level_db" in result and "peak_level_db" in result:
            result["dynamic_range_db"] = round(result["peak_level_db"] - result["rms_level_db"], 2)
            result["crest_factor_db"] = round(result["peak_level_db"] - result["rms_level_db"], 2)

        result["clipping_detected"] = result.get("clipping_count", 0) > 0

        # --- SILENCEDETECT ---
        silence_starts = [
            float(m.group(1)) * 1000
            for m in re.finditer(rf"silencedetect.*?silence_start:\s*({num})", output)
        ]
        silence_ends = [
            float(m.group(1)) * 1000
            for m in re.finditer(rf"silencedetect.*?silence_end:\s*({num})", output)
        ]
        silence_durations = [
            float(m.group(1)) * 1000
            for m in re.finditer(rf"silencedetect.*?silence_duration:\s*({num})", output)
        ]

        if silence_starts:
            result["silence_start_ms"] = int(silence_starts[0])
        if silence_ends:
            result["silence_end_ms"] = int(silence_ends[-1])
        if silence_durations:
            result["silence_duration_ms"] = int(sum(silence_durations))

        return result

    # --- Pipeline completo: probe + analyze + persist ---
    async def analyze_and_persist(
        self, track: UnifiedTrack, session: Session, force: bool = False
    ) -> bool:
        """Analisa arquivo local e persiste resultados no UnifiedTrack"""
        if not track.local_path:
            return False

        file_path = Path(track.local_path)
        if not file_path.exists():
            track.is_corrupted = True
            track.quality_warning = "Arquivo local não encontrado"
            session.add(track)
            session.commit()
            return False

        # Pular se já analisado e não forçado
        if track.analyzed_at is not None and not force:
            return False

        async with self._semaphore:
            # 1. FFprobe para info técnica (codec, bitrate, sample rate, etc.)
            probe_info = await self.probe_file(file_path)

            # 2. FFmpeg single-pass para loudness, dinâmica, silêncio
            analysis = await self.analyze_audio(file_path)

            if probe_info:
                track.codec = probe_info.codec_name
                track.bitrate_kbps = probe_info.bitrate_kbps
                track.sample_rate_hz = probe_info.sample_rate_hz
                track.bit_depth = probe_info.bit_depth
                track.channels = probe_info.channels
                track.file_size_bytes = probe_info.size_bytes
                track.duration_ms = int(probe_info.duration_sec * 1000)
            else:
                track.is_corrupted = True
                track.quality_warning = "Falha ao inspecionar com ffprobe (arquivo corrompido ou formato não suportado)"

            if analysis:
                track.integrated_lufs = round(analysis.integrated_lufs, 2)
                track.true_peak_dbfs = round(analysis.true_peak_dbfs, 2)
                track.momentary_lufs = round(analysis.momentary_lufs, 2)
                track.short_term_lufs = round(analysis.short_term_lufs, 2)
                track.loudness_range_lu = round(analysis.loudness_range_lu, 2)
                track.dynamic_range_db = round(analysis.dynamic_range_db, 2)
                track.crest_factor_db = round(analysis.crest_factor_db, 2)
                track.silence_start_ms = analysis.silence_start_ms
                track.silence_end_ms = analysis.silence_end_ms
                track.clipping_count = analysis.clipping_count

                # ReplayGain baseado no target LUFS
                track.replay_gain = round(self.target_lufs - analysis.integrated_lufs, 2)

                # Quality warning se clipping detectado
                if analysis.clipping_detected:
                    track.quality_warning = (
                        f"Clipping detectado ({analysis.clipping_count} samples)"
                    )
                elif track.quality_warning and "Clipping" in str(track.quality_warning):
                    track.quality_warning = None
            else:
                track.is_corrupted = True
                track.quality_warning = "Falha na análise de áudio via FFmpeg"

            track.analysis_version = 1
            track.analyzed_at = datetime.now(timezone.utc)
            track.updated_at = datetime.now(timezone.utc)

            session.add(track)
            session.commit()
            session.refresh(track)

            return True

    # --- Batch para biblioteca inteira ---
    async def analyze_library(
        self,
        session_factory: Callable[[], Session],
        progress_callback: Optional[Callable[[int, int, str], Any]] = None,
        force: bool = False,
        batch_size: int = 50,
    ) -> dict[str, int]:
        """Processa todos os tracks com local_path em lotes assíncronos"""
        stats = {"analyzed": 0, "skipped": 0, "errors": 0}

        # Buscar IDs dos tracks para processar (sessão curta)
        with session_factory() as session:
            track_ids = session.exec(
                select(UnifiedTrack.id).where(UnifiedTrack.local_path.is_not(None))
            ).all()

        total = len(track_ids)

        # Processar em lotes
        for i in range(0, total, batch_size):
            batch_ids = track_ids[i : i + batch_size]

            # Criar tasks para processamento paralelo (limitado pelo semáforo)
            async def process_track(track_id: int):
                try:
                    # Sessão curta e isolada por track
                    with session_factory() as session:
                        track = session.get(UnifiedTrack, track_id)
                        if track:
                            result = await self.analyze_and_persist(track, session, force)
                            if result:
                                return "analyzed"
                            else:
                                return "skipped"
                except Exception as e:
                    print(f"[TechnicalAnalysis] Error analyzing track {track_id}: {e}")
                    return "error"

            tasks = [process_track(tid) for tid in batch_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, Exception):
                    stats["errors"] += 1
                elif r == "analyzed":
                    stats["analyzed"] += 1
                else:
                    stats["skipped"] += 1

            if progress_callback:
                progress_callback(min(i + batch_size, total), total, "Analisando...")

        return stats