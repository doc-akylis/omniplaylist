import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
from typing import Any, Optional
import mutagen
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

from app.core.models import UnifiedTrack


@dataclass
class AudioTechnicalInfo:
    """Detailed technical characteristics extracted from an audio file."""

    file_path: str
    codec: str
    bitrate_kbps: int
    sample_rate_hz: int
    bit_depth: Optional[int]
    channels: int
    duration_sec: float
    file_size_bytes: int
    format_name: str
    is_corrupted: bool = False
    is_truncated: bool = False
    has_clipping: bool = False
    is_upscaling_suspect: bool = False
    codec_extension_mismatch: bool = False
    quality_notes: list[str] = None

    def __post_init__(self):
        if self.quality_notes is None:
            self.quality_notes = []


class QualityProfile:
    """Predefined encoding and format standards for exports and downloads."""

    CAR_STEREO = {
        "name": "Som Automotivo",
        "format": "mp3",
        "codec": "libmp3lame",
        "bitrate": "320k",
        "sample_rate": 44100,
        "cbr": True,
        "fat32_safe": True,
        "embed_cover": True,
        "description": "MP3 320 kbps CBR com compatibilidade universal para centrais automotivas.",
    }

    DJ_REKORDBOX = {
        "name": "DJ / Rekordbox",
        "format": "wav",
        "codec": "pcm_s16le",
        "bitrate": "lossless",
        "sample_rate": 44100,
        "cbr": False,
        "fat32_safe": True,
        "embed_cover": True,
        "description": "Áudio linear PCM sem perdas (WAV 16-bit 44.1kHz) para CDJs e Rekordbox.",
    }

    ARCHIVE_LOSSLESS = {
        "name": "Arquivo Musical (Lossless)",
        "format": "flac",
        "codec": "flac",
        "bitrate": "lossless",
        "sample_rate": 44100,
        "cbr": False,
        "fat32_safe": False,
        "embed_cover": True,
        "description": "FLAC com compressão sem perdas e preservação total de metadados.",
    }

    DAILY_USE = {
        "name": "Uso Cotidiano",
        "format": "mp3",
        "codec": "libmp3lame",
        "bitrate": "192k",
        "sample_rate": 44100,
        "cbr": False,
        "fat32_safe": True,
        "embed_cover": True,
        "description": "MP3 equilibrado de tamanho reduzido para economia de armazenamento.",
    }


class AudioQualityEngine:
    """Engine for deep audio inspection, quality profile conversion, and integrity checking."""

    FFMPEG_CMD = "ffmpeg"
    FFPROBE_CMD = "ffprobe"

    def inspect_file(self, file_path: Path) -> AudioTechnicalInfo:
        """Inspect physical file using Mutagen and system headers."""
        if not file_path.exists():
            return AudioTechnicalInfo(
                file_path=str(file_path),
                codec="missing",
                bitrate_kbps=0,
                sample_rate_hz=0,
                bit_depth=None,
                channels=0,
                duration_sec=0.0,
                file_size_bytes=0,
                format_name="none",
                is_corrupted=True,
                quality_notes=["Arquivo não existe no disco."],
            )

        file_size = file_path.stat().st_size
        notes = []
        ext = file_path.suffix.lower().lstrip(".")

        # Initial fallback values
        codec = ext
        bitrate_kbps = 0
        sample_rate_hz = 44100
        channels = 2
        duration_sec = 0.0
        bit_depth = None
        is_corrupted = False

        try:
            audio = mutagen.File(str(file_path))
            if audio is None or audio.info is None:
                is_corrupted = True
                notes.append("Cabeçalho de áudio inválido ou corrompido.")
            else:
                info = audio.info
                duration_sec = getattr(info, "length", 0.0)
                sample_rate_hz = getattr(info, "sample_rate", 44100)
                channels = getattr(info, "channels", 2)

                # Bitrate calculation
                raw_bitrate = getattr(info, "bitrate", None)
                if raw_bitrate:
                    bitrate_kbps = int(raw_bitrate / 1000)
                elif duration_sec > 0 and file_size > 0:
                    bitrate_kbps = int((file_size * 8) / (duration_sec * 1000))

                # Bit depth if lossless
                bit_depth = getattr(info, "bits_per_sample", None)

                # Codec detection
                if isinstance(audio, MP3):
                    codec = "mp3"
                elif isinstance(audio, FLAC):
                    codec = "flac"
                    bit_depth = bit_depth or 16
                elif "wav" in ext:
                    codec = "pcm"
                    bit_depth = bit_depth or 16
        except Exception as e:
            is_corrupted = True
            notes.append(f"Erro ao analisar tags: {e}")

        # Check mismatch between extension and detected codec
        mismatch = False
        if ext in ["flac", "wav"] and codec == "mp3":
            mismatch = True
            notes.append(f"Extensão .{ext} não coincide com o conteúdo codificado ({codec}).")

        # Suspected artificial upscaling heuristic
        is_upscaling_suspect = False
        if codec in ["flac", "wav"] and bitrate_kbps < 400 and file_size > 1000:
            is_upscaling_suspect = True
            notes.append("Suspeita de upscaling artificial: bitrate excessivamente baixo para formato lossless.")

        # Low bitrate warning
        if 0 < bitrate_kbps < 128:
            notes.append(f"Qualidade baixa de origem ({bitrate_kbps} kbps).")

        return AudioTechnicalInfo(
            file_path=str(file_path),
            codec=codec,
            bitrate_kbps=bitrate_kbps,
            sample_rate_hz=sample_rate_hz,
            bit_depth=bit_depth,
            channels=channels,
            duration_sec=round(duration_sec, 2),
            file_size_bytes=file_size,
            format_name=ext.upper(),
            is_corrupted=is_corrupted,
            codec_extension_mismatch=mismatch,
            is_upscaling_suspect=is_upscaling_suspect,
            quality_notes=notes,
        )

    async def convert_with_profile(
        self,
        src_file: Path,
        dest_dir: Path,
        profile: dict[str, Any],
        track_meta: Optional[UnifiedTrack] = None,
    ) -> tuple[Optional[Path], list[str]]:
        """Convert audio file adhering strictly to a quality profile without claiming fake quality improvement."""
        warnings: list[str] = []
        if not src_file.exists():
            return None, ["Arquivo de origem não existe."]

        # Inspect origin first
        origin_info = self.inspect_file(src_file)

        # Anti-fake upscaling warning
        target_fmt = profile["format"]
        target_bitrate = profile.get("bitrate", "320k")

        if origin_info.bitrate_kbps and origin_info.bitrate_kbps < 192 and target_bitrate == "320k":
            warnings.append(
                f"Aviso de Qualidade: A origem possui apenas {origin_info.bitrate_kbps} kbps. "
                "A conversão para 320 kbps preserva compatibilidade, mas NÃO recupera informações perdidas na gravação original."
            )

        if origin_info.codec == "mp3" and target_fmt in ["wav", "flac"]:
            warnings.append(
                "Aviso Lossless: Converter de MP3 comprimido para WAV/FLAC não torna o áudio Lossless real."
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        filename_base = src_file.stem
        if profile.get("fat32_safe"):
            filename_base = re.sub(r'[\\/:*?"<>|]', "", filename_base)[:64].strip()

        dest_file = dest_dir / f"{filename_base}.{target_fmt}"

        # Build FFmpeg command
        cmd = [self.FFMPEG_CMD, "-y", "-i", str(src_file)]

        if target_fmt == "mp3":
            cmd.extend(["-codec:a", "libmp3lame"])
            if profile.get("cbr"):
                cmd.extend(["-b:a", target_bitrate])
            else:
                cmd.extend(["-q:a", "2"])
        elif target_fmt == "flac":
            cmd.extend(["-codec:a", "flac", "-compression_level", "8"])
        elif target_fmt == "wav":
            cmd.extend(["-codec:a", "pcm_s16le"])

        cmd.extend(["-ar", str(profile.get("sample_rate", 44100)), str(dest_file)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0 and dest_file.exists():
                return dest_file, warnings
            else:
                err_msg = stderr.decode("utf-8", errors="ignore")
                return None, [f"Erro na conversão FFmpeg: {err_msg[:200]}"]
        except FileNotFoundError:
            # If FFmpeg binary is missing, copy original if format matches or return clear notice
            if src_file.suffix.lower() == f".{target_fmt}":
                shutil.copy2(src_file, dest_file)
                warnings.append("FFmpeg ausente: arquivo copiado em formato original sem re-encoding.")
                return dest_file, warnings
            return None, ["Binário do FFmpeg não encontrado no PATH para conversão."]
        except Exception as e:
            return None, [f"Exceção no processamento: {e}"]

    def scan_library_quality(self, tracks: list[UnifiedTrack]) -> dict[str, Any]:
        """Perform library-wide technical audit for Audio Inspector."""
        report = {
            "total_analyzed": len(tracks),
            "valid_files": 0,
            "corrupted_files": 0,
            "suspect_files": 0,
            "codec_distribution": {},
            "bitrate_distribution": {"Baixo (<128k)": 0, "Médio (128k-256k)": 0, "Alto (320k)": 0, "Lossless": 0},
            "issues": [],
        }

        for t in tracks:
            if not t.local_path:
                continue

            info = self.inspect_file(Path(t.local_path))
            codec = info.codec.upper()
            report["codec_distribution"][codec] = report["codec_distribution"].get(codec, 0) + 1

            if info.is_corrupted:
                report["corrupted_files"] += 1
                report["issues"].append({
                    "track_id": t.id,
                    "title": t.title,
                    "artist": t.artist,
                    "type": "Corrompido",
                    "details": "; ".join(info.quality_notes),
                })
            else:
                report["valid_files"] += 1

            if info.is_upscaling_suspect or info.codec_extension_mismatch:
                report["suspect_files"] += 1
                report["issues"].append({
                    "track_id": t.id,
                    "title": t.title,
                    "artist": t.artist,
                    "type": "Suspeito",
                    "details": "; ".join(info.quality_notes),
                })

            # Bitrate distribution
            if info.codec in ["flac", "pcm", "wav"]:
                report["bitrate_distribution"]["Lossless"] += 1
            elif info.bitrate_kbps >= 300:
                report["bitrate_distribution"]["Alto (320k)"] += 1
            elif info.bitrate_kbps >= 128:
                report["bitrate_distribution"]["Médio (128k-256k)"] += 1
            elif info.bitrate_kbps > 0:
                report["bitrate_distribution"]["Baixo (<128k)"] += 1

        return report
