import asyncio
from pathlib import Path
import re
from typing import Optional
import httpx
from mutagen.id3 import ID3, TXXX, ID3NoHeaderError

from app.core.models import UnifiedTrack


class MetadataEngine:
    """HD artwork fetcher and ReplayGain / EBU R128 volume normalizer."""

    ITUNES_API = "https://itunes.apple.com/search"

    def __init__(self, target_lufs: float = -14.0, timeout: float = 8.0):
        self.target_lufs = target_lufs
        self.timeout = timeout

    async def fetch_hd_artwork(self, track: UnifiedTrack) -> Optional[str]:
        """Fetch ultra high-resolution artwork (1400x1400+) via iTunes Public Search API."""
        term = f"{track.artist} {track.title}".strip()
        params = {"term": term, "entity": "song", "limit": 1}

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(self.ITUNES_API, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results", [])
                    if results:
                        art_100 = results[0].get("artworkUrl100")
                        if art_100:
                            # Replace 100x100 thumbnail URL with 1400x1400 ultra high-res
                            hd_url = art_100.replace("100x100bb.jpg", "1400x1400bb.jpg")
                            return hd_url
            except Exception as e:
                print(f"[MetadataEngine] Error fetching HD cover for '{track.title}': {e}")

        return None

    async def calculate_replay_gain(self, file_path: Path) -> Optional[float]:
        """Measure integrated loudness (LUFS) of audio file via FFmpeg EBU R128 filter."""
        if not file_path.exists():
            return None

        cmd = [
            "ffmpeg",
            "-nostats",
            "-i",
            str(file_path),
            "-filter_complex",
            "ebur128=peak=true",
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

            # Extract Integrated loudness: e.g. "I: -16.2 LUFS"
            match = re.search(r"Integrated loudness:\s+I:\s+([-\d.]+)\s+LUFS", output)
            if match:
                measured_lufs = float(match.group(1))
                # Suggested gain in dB = Target LUFS - Measured LUFS
                gain_db = round(self.target_lufs - measured_lufs, 2)
                return gain_db
        except Exception as e:
            print(f"[MetadataEngine] FFmpeg ReplayGain error for {file_path}: {e}")

        return None

    def apply_replay_gain(self, file_path: Path, gain_db: float) -> bool:
        """Write standard REPLAYGAIN_TRACK_GAIN ID3 tags using Mutagen."""
        if not file_path.exists():
            return False

        try:
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()

            tags.delall("TXXX:replaygain_track_gain")
            tags.add(
                TXXX(
                    encoding=3,
                    desc="replaygain_track_gain",
                    text=f"{gain_db:+.2f} dB",
                )
            )
            tags.save(file_path)
            return True
        except Exception as e:
            print(f"[MetadataEngine] Error saving ReplayGain to {file_path}: {e}")
            return False
