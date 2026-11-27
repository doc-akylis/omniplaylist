import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any, Optional

from app.engines.technical_analysis import _resolve_ffmpeg_binary

LOSSY_EXTS = {"mp3", "aac", "m4a", "ogg", "opus", "wma"}
LOSSLESS_EXTS = {"flac", "wav", "aiff", "alac"}

AUDIO_PROFILES: dict[str, dict[str, Any]] = {
    "ORIGINAL": {
        "id": "ORIGINAL",
        "name": "Original / Best Available",
        "format": None,
        "codec": None,
        "bitrate": None,
        "sample_rate": None,
        "lossy": None,
        "description": "Preserva exatamente a fonte disponível sem recodificação.",
    },
    "FLAC_ARCHIVE": {
        "id": "FLAC_ARCHIVE",
        "name": "FLAC Archive",
        "format": "flac",
        "codec": "flac",
        "bitrate": "lossless",
        "sample_rate": None,
        "lossy": False,
        "description": "FLAC sem perdas preservando sample rate original; não converte lossy em lossless real.",
    },
    "WAV_16": {
        "id": "WAV_16",
        "name": "WAV PCM 16-bit",
        "format": "wav",
        "codec": "pcm_s16le",
        "bitrate": "lossless",
        "sample_rate": None,
        "lossy": False,
        "description": "WAV PCM 16-bit padrão CDJ/Rekordbox.",
    },
    "WAV_24": {
        "id": "WAV_24",
        "name": "WAV PCM 24-bit",
        "format": "wav",
        "codec": "pcm_s24le",
        "bitrate": "lossless",
        "sample_rate": None,
        "lossy": False,
        "description": "WAV PCM 24-bit de estúdio preservando o sample rate original.",
    },
    "MP3_320": {
        "id": "MP3_320",
        "name": "MP3 320 kbps CBR",
        "format": "mp3",
        "codec": "libmp3lame",
        "bitrate": "320k",
        "sample_rate": 44100,
        "lossy": True,
        "description": "MP3 320 kbps CBR com máxima compatibilidade universal.",
    },
    "AAC_256": {
        "id": "AAC_256",
        "name": "AAC 256 kbps",
        "format": "m4a",
        "codec": "aac",
        "bitrate": "256k",
        "sample_rate": 44100,
        "lossy": True,
        "description": "AAC 256 kbps de alta eficiência.",
    },
}


@dataclass
class ConversionResult:
    """Result of an asynchronous FFmpeg profile conversion."""

    success: bool
    output_path: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)
    was_lossy_to_lossless: bool = False
    error: Optional[str] = None


class ConversionEngine:
    """Non-blocking FFmpeg audio converter reusing _resolve_ffmpeg_binary from technical_analysis."""

    def __init__(self, ffmpeg_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or _resolve_ffmpeg_binary("ffmpeg")

    @staticmethod
    def get_profile(profile_id: str) -> dict[str, Any]:
        key = (profile_id or "ORIGINAL").strip().upper()
        return AUDIO_PROFILES.get(key, AUDIO_PROFILES["ORIGINAL"])

    async def convert_file(
        self,
        src_path: Path,
        dest_dir: Path,
        profile_id: str = "ORIGINAL",
        output_stem: Optional[str] = None,
        target_sample_rate_hz: Optional[int] = None,
        source_bitrate_kbps: Optional[int] = None,
        timeout_sec: float = 300.0,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> ConversionResult:
        """Convert audio safely into dest_dir using FFmpeg with timeout and cancellation support."""
        if not src_path.exists():
            return ConversionResult(success=False, error="Arquivo de origem não encontrado.")

        profile = self.get_profile(profile_id)
        warnings: list[str] = []
        src_ext = src_path.suffix.lstrip(".").lower()
        src_is_lossy = src_ext in LOSSY_EXTS
        stem = output_stem or src_path.stem
        dest_dir.mkdir(parents=True, exist_ok=True)

        if profile["id"] == "ORIGINAL":
            dest_path = dest_dir / f"{stem}.{src_ext or 'bin'}"
            if src_path.resolve() != dest_path.resolve():
                await asyncio.to_thread(shutil.copy2, src_path, dest_path)
            return ConversionResult(success=True, output_path=dest_path, warnings=warnings)

        target_fmt = profile["format"]
        target_codec = profile["codec"]
        dest_path = dest_dir / f"{stem}.{target_fmt}"
        was_lossy_to_lossless = bool(src_is_lossy and profile["lossy"] is False)

        if was_lossy_to_lossless:
            warnings.append(
                f"Aviso Lossy→Lossless: converter {src_ext.upper()} em {target_fmt.upper()} não recupera áudio perdido nem cria qualidade lossless real."
            )
        if profile["lossy"] is True:
            if not src_is_lossy:
                warnings.append(
                    f"Conversão com perdas: áudio de origem será comprimido para {profile['name']}."
                )
            elif source_bitrate_kbps and profile["id"] == "MP3_320" and source_bitrate_kbps < 256:
                warnings.append(
                    f"Origem possui {source_bitrate_kbps} kbps; converter para 320 kbps não restaura qualidade original."
                )

        cmd = [self.ffmpeg_path, "-y", "-i", str(src_path), "-vn", "-codec:a", target_codec]
        if profile["bitrate"] and profile["bitrate"] != "lossless":
            cmd.extend(["-b:a", str(profile["bitrate"])])
        if target_codec == "flac":
            cmd.extend(["-compression_level", "8"])

        sr = target_sample_rate_hz or profile.get("sample_rate")
        if sr:
            cmd.extend(["-ar", str(int(sr))])

        cmd.append(str(dest_path))

        proc: Optional[asyncio.subprocess.Process] = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            if cancel_event is not None:
                comm_task = asyncio.create_task(proc.communicate())
                cancel_task = asyncio.create_task(cancel_event.wait())
                done, pending = await asyncio.wait(
                    {comm_task, cancel_task},
                    timeout=timeout_sec,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for p in pending:
                    p.cancel()
                if cancel_task in done and cancel_event.is_set():
                    proc.kill()
                    await proc.wait()
                    if dest_path.exists():
                        dest_path.unlink(missing_ok=True)
                    return ConversionResult(success=False, error="Conversão cancelada pelo usuário.")
                if not done:
                    proc.kill()
                    await proc.wait()
                    if dest_path.exists():
                        dest_path.unlink(missing_ok=True)
                    return ConversionResult(success=False, error="Timeout na conversão FFmpeg.")
                _, stderr = await comm_task
            else:
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)

            if proc.returncode == 0 and dest_path.exists() and dest_path.stat().st_size > 0:
                return ConversionResult(
                    success=True,
                    output_path=dest_path,
                    warnings=warnings,
                    was_lossy_to_lossless=was_lossy_to_lossless,
                )

            err_txt = stderr.decode("utf-8", errors="ignore")[:300] if stderr else "Código de saída inválido"
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            return ConversionResult(success=False, error=f"FFmpeg falhou: {err_txt}", warnings=warnings)

        except asyncio.TimeoutError:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            return ConversionResult(success=False, error="Timeout na conversão FFmpeg.")
        except Exception as e:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            if dest_path.exists():
                dest_path.unlink(missing_ok=True)
            return ConversionResult(success=False, error=f"Erro ao executar FFmpeg: {e}")
