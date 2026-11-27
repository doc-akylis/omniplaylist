import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any, Optional
import httpx

from app.config import get_settings


@dataclass
class AcoustIDMatch:
    """Acoustic fingerprint identification result."""

    acoustid_id: Optional[str] = None
    musicbrainz_recording_id: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    score: float = 0.0


class AcoustIDProvider:
    """Acoustic fingerprint identification using fpcalc + AcoustID API.

    Degrades gracefully (returns None without error) when ACOUSTID_API_KEY
    is not configured or fpcalc is not installed on the system.
    """

    BASE_URL = "https://api.acoustid.org/v2/lookup"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = api_key if api_key is not None else get_settings().ACOUSTID_API_KEY
        self.timeout = timeout
        self._transport = transport

    def is_available(self) -> bool:
        """Return True if API key is configured and fpcalc binary is present."""
        return bool(self.api_key and self.api_key.strip() and shutil.which("fpcalc"))

    async def compute_fingerprint(self, file_path: Path) -> Optional[tuple[int, str]]:
        """Run fpcalc -json asynchronously to extract (duration_sec, fingerprint)."""
        if not file_path.exists() or not shutil.which("fpcalc"):
            return None

        try:
            proc = await asyncio.create_subprocess_exec(
                "fpcalc",
                "-json",
                str(file_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode != 0:
                return None
            payload = json.loads(stdout.decode("utf-8", errors="ignore"))
            duration = int(round(float(payload.get("duration", 0))))
            fp = payload.get("fingerprint")
            if duration > 0 and fp:
                return duration, fp
        except Exception as e:
            print(f"[AcoustIDProvider] fpcalc error for {file_path}: {e}")
        return None

    async def identify_file(self, file_path: Path) -> Optional[AcoustIDMatch]:
        """Identify an audio file via acoustic fingerprint. Skips gracefully if unconfigured."""
        if not self.is_available() or not file_path.exists():
            return None

        fp_data = await self.compute_fingerprint(file_path)
        if not fp_data:
            return None

        duration, fingerprint = fp_data
        kwargs: dict[str, Any] = {"timeout": self.timeout}
        if self._transport is not None:
            kwargs["transport"] = self._transport

        async with httpx.AsyncClient(**kwargs) as client:
            try:
                resp = await client.get(
                    self.BASE_URL,
                    params={
                        "client": self.api_key,
                        "duration": duration,
                        "fingerprint": fingerprint,
                        "meta": "recordings+compress",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("results") or []
                    if results:
                        best = results[0]
                        recordings = best.get("recordings") or []
                        rec = recordings[0] if recordings else {}
                        artists = rec.get("artists") or []
                        artist_name = artists[0].get("name") if artists else None
                        return AcoustIDMatch(
                            acoustid_id=best.get("id"),
                            musicbrainz_recording_id=rec.get("id"),
                            title=rec.get("title"),
                            artist=artist_name,
                            score=float(best.get("score", 0.0)),
                        )
            except Exception as e:
                print(f"[AcoustIDProvider] Lookup error: {e}")
        return None
