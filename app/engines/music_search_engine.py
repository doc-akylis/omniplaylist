"""Parallel multi-source music discovery, rate limiting, version grouping, and TTL search cache."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlmodel import Session, select

from app.core.matcher import TrackMatcher
from app.core.models import MusicSearchSession
from app.engines.source_quality_comparator import SourceQualityComparator
from app.sources.base import (
    GroupedRecording,
    NormalizedTrackResult,
    ProviderAdapter,
)
from app.sources.registry import MusicSourceRegistry


class AsyncRateLimiter:
    """Async minimum-interval rate limiter keyed per provider."""

    def __init__(self, min_intervals_sec: Optional[dict[str, float]] = None):
        self._intervals = min_intervals_sec or {
            "musicbrainz": 1.05,
            "discogs": 1.0,
            "freesound": 0.5,
            "internet_archive": 0.25,
            "wikimedia_commons": 0.25,
        }
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_call: dict[str, float] = {}

    async def wait(self, provider_id: str) -> None:
        interval = self._intervals.get(provider_id, 0.05)
        lock = self._locks.setdefault(provider_id, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            prev = self._last_call.get(provider_id, 0.0)
            wait_sec = interval - (now - prev)
            if wait_sec > 0:
                await asyncio.sleep(wait_sec)
            self._last_call[provider_id] = time.monotonic()


class MusicSearchEngine:
    """Orchestrates parallel discovery across all enabled adapters with isolation, grouping, and comparison."""

    SUPPORTED_SEARCH_TYPES = {
        "track",
        "artist",
        "album",
        "isrc",
        "discography",
        "live",
        "remix",
        "related",
    }

    def __init__(
        self,
        registry: Optional[MusicSourceRegistry] = None,
        matcher: Optional[TrackMatcher] = None,
        comparator: Optional[SourceQualityComparator] = None,
        rate_limiter: Optional[AsyncRateLimiter] = None,
        cache_ttl_sec: int = 300,
        per_provider_timeout_sec: float = 8.0,
        max_retries: int = 1,
    ):
        self.registry = registry or MusicSourceRegistry()
        self.matcher = matcher or TrackMatcher()
        self.comparator = comparator or SourceQualityComparator()
        self.rate_limiter = rate_limiter or AsyncRateLimiter()
        self.cache_ttl_sec = cache_ttl_sec
        self.per_provider_timeout_sec = per_provider_timeout_sec
        self.max_retries = max_retries
        self._mem_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def _build_effective_query(
        self,
        query: str,
        search_type: str,
        artist: Optional[str],
        title: Optional[str],
        album: Optional[str],
        isrc: Optional[str],
    ) -> str:
        st = (search_type or "track").lower()
        if st == "isrc" and isrc:
            return isrc.strip()
        parts: list[str] = []
        if artist:
            parts.append(artist.strip())
        if title:
            parts.append(title.strip())
        if album and st == "album":
            parts.append(album.strip())
        base = " ".join(parts).strip() if parts else (query or "").strip()
        if st == "live" and "live" not in base.lower():
            base = f"{base} live".strip()
        elif st == "remix" and "remix" not in base.lower():
            base = f"{base} remix".strip()
        return base

    async def _query_single_adapter(
        self,
        adapter: ProviderAdapter,
        query: str,
        search_type: str,
        limit: int,
        artist: Optional[str],
        title: Optional[str],
        album: Optional[str],
        isrc: Optional[str],
    ) -> tuple[list[NormalizedTrackResult], dict[str, Any]]:
        pid = adapter.provider_id
        caps = adapter.capabilities()
        started = time.monotonic()

        if caps.requires_auth and not caps.auth_configured:
            return [], {
                "provider_id": pid,
                "provider_name": caps.name,
                "category": caps.category.value,
                "status": "requires_credentials",
                "count": 0,
                "latency_ms": 0.0,
                "error": f"Credenciais pendentes: {', '.join(caps.missing_credentials)}",
            }

        last_err: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                await self.rate_limiter.wait(pid)
                results = await asyncio.wait_for(
                    adapter.search_tracks(
                        query=query,
                        limit=limit,
                        search_type=search_type,
                    ),
                    timeout=self.per_provider_timeout_sec,
                )
                elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
                return results, {
                    "provider_id": pid,
                    "provider_name": caps.name,
                    "category": caps.category.value,
                    "status": "ok",
                    "count": len(results),
                    "latency_ms": elapsed_ms,
                    "error": None,
                }
            except asyncio.TimeoutError:
                last_err = f"Timeout após {self.per_provider_timeout_sec:.1f}s"
                status_label = "timeout"
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_err = f"Falha de transporte: {exc}"
                status_label = "error"
            except Exception as exc:
                # Non-transient / payload errors don't benefit from blind retries
                elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
                return [], {
                    "provider_id": pid,
                    "provider_name": caps.name,
                    "category": caps.category.value,
                    "status": "error",
                    "count": 0,
                    "latency_ms": elapsed_ms,
                    "error": str(exc),
                }
            if attempt < self.max_retries:
                await asyncio.sleep(0.15)

        elapsed_ms = round((time.monotonic() - started) * 1000.0, 1)
        return [], {
            "provider_id": pid,
            "provider_name": caps.name,
            "category": caps.category.value,
            "status": status_label,
            "count": 0,
            "latency_ms": elapsed_ms,
            "error": last_err,
        }

    def _cache_key(
        self,
        effective_query: str,
        search_type: str,
        provider_ids: Optional[list[str]],
        only_downloadable: bool,
    ) -> str:
        pids = ",".join(sorted(provider_ids)) if provider_ids else "ALL"
        return f"{search_type}:{effective_query.lower()}:{pids}:{only_downloadable}"

    async def search(
        self,
        query: str = "",
        session: Optional[Session] = None,
        search_type: str = "track",
        artist: Optional[str] = None,
        title: Optional[str] = None,
        album: Optional[str] = None,
        isrc: Optional[str] = None,
        provider_ids: Optional[list[str]] = None,
        limit_per_provider: int = 10,
        only_downloadable: bool = False,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Run parallel multi-source discovery, group recordings by version, and compare quality."""
        st = search_type if search_type in self.SUPPORTED_SEARCH_TYPES else "track"
        eff_query = self._build_effective_query(query, st, artist, title, album, isrc)
        if not eff_query:
            return {
                "query": "",
                "search_type": st,
                "cached": False,
                "total_raw_results": 0,
                "total_groups": 0,
                "downloadable_groups": 0,
                "provider_statuses": [],
                "groups": [],
            }

        ckey = self._cache_key(eff_query, st, provider_ids, only_downloadable)
        if use_cache and ckey in self._mem_cache:
            exp_ts, payload = self._mem_cache[ckey]
            if time.monotonic() < exp_ts:
                return {**payload, "cached": True}

        adapters = self.registry.get_enabled_adapters(session=session, provider_ids=provider_ids)
        tasks = [
            self._query_single_adapter(
                adapter=ad,
                query=eff_query,
                search_type=st,
                limit=limit_per_provider,
                artist=artist,
                title=title,
                album=album,
                isrc=isrc,
            )
            for ad in adapters
        ]
        gathered = await asyncio.gather(*tasks, return_exceptions=False)

        raw_results: list[NormalizedTrackResult] = []
        provider_statuses: list[dict[str, Any]] = []
        for items, pstatus in gathered:
            raw_results.extend(items)
            provider_statuses.append(pstatus)

        grouped: list[GroupedRecording] = self.matcher.group_recordings(raw_results)
        enriched_groups: list[GroupedRecording] = []
        for grp in grouped:
            comp = self.comparator.compare_group(grp)
            grp.comparison = comp.model_dump(mode="json")
            if only_downloadable and not grp.has_downloadable_source:
                continue
            enriched_groups.append(grp)

        # Rank groups: downloadable sources first, then highest comparison score
        enriched_groups.sort(
            key=lambda g: (
                1 if g.has_free_download else 0,
                1 if g.has_downloadable_source else 0,
                (g.comparison or {}).get("best_authorized", {}).get("total_score", 0.0)
                if (g.comparison or {}).get("best_authorized")
                else 0.0,
                len(g.candidates),
            ),
            reverse=True,
        )

        payload = {
            "query": eff_query,
            "search_type": st,
            "cached": False,
            "total_raw_results": len(raw_results),
            "total_groups": len(enriched_groups),
            "downloadable_groups": sum(1 for g in enriched_groups if g.has_downloadable_source),
            "provider_statuses": provider_statuses,
            "groups": [g.model_dump(mode="json") for g in enriched_groups],
        }

        if use_cache:
            self._mem_cache[ckey] = (time.monotonic() + self.cache_ttl_sec, payload)

        if session is not None:
            now = datetime.now(timezone.utc)
            responded = [s["provider_id"] for s in provider_statuses if s["status"] == "ok"]
            failed = {
                s["provider_id"]: (s["error"] or s["status"])
                for s in provider_statuses
                if s["status"] != "ok"
            }
            rec = MusicSearchSession(
                query=eff_query,
                search_type=st,
                providers_queried_json=json.dumps([s["provider_id"] for s in provider_statuses]),
                providers_responded_json=json.dumps(responded),
                providers_failed_json=json.dumps(failed, ensure_ascii=False),
                downloadable_count=payload["downloadable_groups"],
                total_results=len(raw_results),
                cached_results_json=json.dumps(payload["groups"][:30], ensure_ascii=False),
                expires_at=now + timedelta(seconds=self.cache_ttl_sec),
                created_at=now,
            )
            session.add(rec)
            session.commit()

        return payload

    async def batch_search(
        self,
        queries: list[str],
        session: Optional[Session] = None,
        concurrency: int = 3,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Execute multiple search queries concurrently with bounded concurrency for album/playlist acquisition."""
        sem = asyncio.Semaphore(max(1, concurrency))

        async def _run_one(q: str) -> dict[str, Any]:
            async with sem:
                return await self.search(query=q, session=session, **kwargs)

        return await asyncio.gather(*[_run_one(q) for q in queries])
