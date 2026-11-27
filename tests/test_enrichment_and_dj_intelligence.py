import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.api import routes as api_routes
from app.core.models import UnifiedTrack
from app.engines.dj_intelligence import DJIntelligenceEngine
from app.engines.lyrics_engine import LyricsEngine
from app.engines.metadata_enrichment import MetadataEnrichmentEngine
from app.providers.acoustid import AcoustIDProvider
from app.providers.deezer import DeezerProvider
from app.providers.itunes import ITunesProvider
from app.providers.lastfm import LastFMProvider
from app.providers.listenbrainz import ListenBrainzProvider
from app.providers.musicbrainz import MusicBrainzProvider
from app.providers.rate_limiter import AsyncRateLimiter


@pytest.fixture
def isolated_session(tmp_path: Path):
    """Create an isolated temporary SQLite database for tests without touching omniplaylist.db."""
    db_file = tmp_path / "test_enrichment_dj.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        yield session, test_engine


@pytest.mark.asyncio
async def test_musicbrainz_rate_limiter_and_user_agent():
    """Verify strict 1 req/s rate limiting and mandatory OmniPlaylist User-Agent header."""
    captured_headers: list[str] = []
    request_times: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_times.append(time.monotonic())
        captured_headers.append(request.headers.get("User-Agent", ""))
        if "musicbrainz.org" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "recordings": [
                        {
                            "id": "mb-rec-123",
                            "title": "One More Time",
                            "isrcs": ["GBDUW0000053"],
                            "first-release-date": "2000-11-13",
                            "artist-credit": [{"name": "Daft Punk"}],
                            "releases": [{"id": "mb-rel-456", "title": "Discovery", "date": "2001"}],
                        }
                    ]
                },
            )
        if "coverartarchive.org" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "images": [
                        {
                            "front": True,
                            "image": "https://coverartarchive.org/release/mb-rel-456/front.jpg",
                            "thumbnails": {
                                "1200": "https://coverartarchive.org/release/mb-rel-456/front-1200.jpg"
                            },
                        }
                    ]
                },
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    limiter = AsyncRateLimiter(min_interval_sec=0.35)
    provider = MusicBrainzProvider(rate_limiter=limiter, transport=transport)

    m1 = await provider.lookup_by_isrc("GBDUW0000053")
    m2 = await provider.search_recording("Daft Punk", "One More Time")

    assert m1 is not None and m1.recording_id == "mb-rec-123"
    assert m1.release_year == 2000
    assert m1.hd_cover_url == "https://coverartarchive.org/release/mb-rel-456/front-1200.jpg"
    assert m2 is not None and m2.recording_id == "mb-rec-123"

    assert all(h == MusicBrainzProvider.USER_AGENT for h in captured_headers)
    # MusicBrainz calls are index 0 and index 2 (index 1 & 3 are Cover Art Archive)
    mb_times = [t for idx, t in enumerate(request_times) if idx in (0, 2)]
    assert mb_times[1] - mb_times[0] >= 0.30


@pytest.mark.asyncio
async def test_enrichment_cascade_fallback_and_persistence(isolated_session):
    """Verify MusicBrainz miss falls back to iTunes + Deezer + LRCLIB and persists to SQLite."""
    session, _ = isolated_session
    track = UnifiedTrack(title="Midnight City", artist="M83", duration_ms=243000)
    session.add(track)
    session.commit()
    session.refresh(track)

    def mb_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"recordings": []})

    def itunes_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "trackName": "Midnight City",
                        "artistName": "M83",
                        "collectionName": "Hurry Up, We're Dreaming",
                        "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/100x100bb.jpg",
                        "previewUrl": "https://audio-ssl.itunes.apple.com/preview.m4a",
                        "releaseDate": "2011-10-18T07:00:00Z",
                        "primaryGenreName": "Electronic",
                    }
                ]
            },
        )

    def deezer_handler(request: httpx.Request) -> httpx.Response:
        if "/search" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": 14450001,
                            "title": "Midnight City",
                            "artist": {"name": "M83"},
                            "album": {"title": "Hurry Up, We're Dreaming", "cover_xl": "https://dz.cdn/xl.jpg"},
                            "duration": 243,
                            "preview": "https://dz.cdn/prev.mp3",
                        }
                    ]
                },
            )
        if "/track/14450001" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "id": 14450001,
                    "isrc": "FR10S1100123",
                    "title": "Midnight City",
                    "artist": {"name": "M83"},
                    "album": {"title": "Hurry Up, We're Dreaming", "cover_xl": "https://dz.cdn/xl.jpg"},
                    "duration": 243,
                    "release_date": "2011-10-18",
                    "preview": "https://dz.cdn/prev.mp3",
                },
            )
        return httpx.Response(404)

    def lrclib_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "syncedLyrics": "[00:10.00] Waiting in a car\n[00:14.00] Waiting for a ride in the dark",
                "plainLyrics": "Waiting in a car\nWaiting for a ride in the dark",
            },
        )

    engine_enrich = MetadataEnrichmentEngine(
        musicbrainz=MusicBrainzProvider(
            rate_limiter=AsyncRateLimiter(0.0),
            transport=httpx.MockTransport(mb_handler),
        ),
        itunes=ITunesProvider(transport=httpx.MockTransport(itunes_handler)),
        deezer=DeezerProvider(transport=httpx.MockTransport(deezer_handler)),
        lyrics=LyricsEngine(
            rate_limiter=AsyncRateLimiter(0.0),
            transport=httpx.MockTransport(lrclib_handler),
        ),
        acoustid=AcoustIDProvider(api_key=""),
        lastfm=LastFMProvider(api_key=""),
        listenbrainz=ListenBrainzProvider(token=""),
    )

    result = await engine_enrich.enrich_track(track, session, force=True)
    assert result["enriched"] is True
    assert "itunes" in result["sources_used"]
    assert "deezer" in result["sources_used"]
    assert "lrclib" in result["sources_used"]

    assert track.hd_cover_url == "https://is1-ssl.mzstatic.com/image/thumb/1400x1400bb.jpg"
    assert track.isrc == "FR10S1100123"
    assert track.release_year == 2011
    assert track.lyrics_synced is not None and "[00:10.00]" in track.lyrics_synced
    assert track.lyrics_plain is not None
    assert track.metadata_enriched_at is not None


@pytest.mark.asyncio
async def test_optional_providers_degrade_gracefully_without_keys(tmp_path: Path):
    """AcoustID, ListenBrainz, and Last.fm must return empty/None cleanly when keys are unset."""
    acoustid = AcoustIDProvider(api_key="")
    listenbrainz = ListenBrainzProvider(token="")
    lastfm = LastFMProvider(api_key="")

    dummy_file = tmp_path / "dummy.mp3"
    dummy_file.write_bytes(b"fake")

    assert acoustid.is_available() is False
    assert await acoustid.identify_file(dummy_file) is None
    assert listenbrainz.is_configured() is False
    assert await listenbrainz.get_similar_recordings("mb-123") == []
    assert lastfm.is_configured() is False
    assert await lastfm.get_track_tags("Artist", "Title") == []
    assert await lastfm.get_similar_tracks("Artist", "Title") == []


def test_dj_intelligence_camelot_bpm_and_transition_points():
    """Verify Camelot wheel scoring, half/double-time BPM matching, and beatgrid-snapped transitions."""
    dj = DJIntelligenceEngine()

    # Camelot compatibility
    assert dj.camelot_compatibility("8A", "8A")[0] == 1.0
    assert dj.camelot_compatibility("8A", "8B")[0] == 0.9
    assert dj.camelot_compatibility("12A", "1A")[0] == 0.85
    assert dj.camelot_compatibility("8A", "3B")[0] < 0.3

    # BPM compatibility (direct, adjustable, half-time, double-time)
    s_direct, d_direct, rel_direct = dj.bpm_compatibility(128.0, 130.0)
    assert rel_direct == "direct"
    assert abs(d_direct - 1.56) < 0.1
    assert s_direct >= 0.95

    s_half, _, rel_half = dj.bpm_compatibility(140.0, 70.0)
    assert rel_half == "double_time"
    assert s_half >= 0.85

    s_dbl, _, rel_dbl = dj.bpm_compatibility(70.0, 140.0)
    assert rel_dbl == "half_time"
    assert s_dbl >= 0.85

    # Transition points with sections & beatgrid downbeats
    curr = UnifiedTrack(
        id=1,
        title="Current",
        artist="DJ A",
        bpm=126.0,
        camelot_code="8A",
        energy=0.8,
        duration_ms=240000,
        genres_raw="house, tech house",
        sections_json=json.dumps([
            {"label": "intro", "start_sec": 0.0, "end_sec": 32.0},
            {"label": "outro", "start_sec": 191.4, "end_sec": 240.0},
        ]),
        beatgrid_json=json.dumps({"downbeats_sec": [0.0, 32.0, 192.0, 224.0]}),
    )
    cand_best = UnifiedTrack(
        id=2,
        title="Best Next",
        artist="DJ B",
        bpm=128.0,
        camelot_code="9A",
        energy=0.82,
        duration_ms=210000,
        genres_raw="tech house",
        sections_json=json.dumps([
            {"label": "intro", "start_sec": 1.8, "end_sec": 30.0},
            {"label": "verse", "start_sec": 30.0, "end_sec": 90.0},
        ]),
        beatgrid_json=json.dumps({"downbeats_sec": [2.0, 30.0]}),
    )
    cand_poor = UnifiedTrack(
        id=3,
        title="Poor Match",
        artist="DJ C",
        bpm=92.0,
        camelot_code="3B",
        energy=0.25,
        duration_ms=180000,
        genres_raw="ambient",
    )

    recs = dj.recommend_next_tracks(curr, [curr, cand_poor, cand_best], limit=5)
    assert len(recs) == 2
    assert recs[0]["track_id"] == 2
    assert recs[0]["score"] > recs[1]["score"]
    assert recs[0]["transition_points"]["mix_out_sec"] == 192.0
    assert recs[0]["transition_points"]["mix_in_sec"] == 2.0


def test_api_enrich_and_next_recommendations_endpoints(isolated_session, monkeypatch):
    """Verify /api/tracks/{id}/enrich and /api/tracks/{id}/next-recommendations against isolated DB."""
    session, test_engine = isolated_session
    t1 = UnifiedTrack(title="Track One", artist="Artist A", bpm=124.0, camelot_code="8A", energy=0.75)
    t2 = UnifiedTrack(title="Track Two", artist="Artist B", bpm=125.0, camelot_code="8B", energy=0.78)
    session.add(t1)
    session.add(t2)
    session.commit()
    session.refresh(t1)
    session.refresh(t2)

    mock_enrich = MetadataEnrichmentEngine(
        musicbrainz=MusicBrainzProvider(
            rate_limiter=AsyncRateLimiter(0.0),
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"recordings": []})),
        ),
        itunes=ITunesProvider(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "artworkUrl100": "https://example.com/100x100bb.jpg",
                                "previewUrl": "https://example.com/prev.m4a",
                                "releaseDate": "2022-05-01T00:00:00Z",
                            }
                        ]
                    },
                )
            )
        ),
        deezer=DeezerProvider(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"data": []}))
        ),
        lyrics=LyricsEngine(
            rate_limiter=AsyncRateLimiter(0.0),
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"plainLyrics": "La la la"})
            ),
        ),
        acoustid=AcoustIDProvider(api_key=""),
        lastfm=LastFMProvider(api_key=""),
        listenbrainz=ListenBrainzProvider(token=""),
    )
    monkeypatch.setattr(api_routes, "enrichment_engine", mock_enrich)

    app = FastAPI()
    app.include_router(api_routes.router)

    def override_get_session():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[api_routes.get_session] = override_get_session
    client = TestClient(app)

    enrich_resp = client.post(f"/api/tracks/{t1.id}/enrich")
    assert enrich_resp.status_code == 200
    enrich_data = enrich_resp.json()
    assert enrich_data["enriched"] is True
    assert enrich_data["hd_cover_url"] == "https://example.com/1400x1400bb.jpg"
    assert enrich_data["has_plain_lyrics"] is True

    rec_resp = client.get(f"/api/tracks/{t1.id}/next-recommendations")
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["track_id"] == t1.id
    assert len(rec_data["recommendations"]) == 1
    assert rec_data["recommendations"][0]["track_id"] == t2.id
    assert rec_data["recommendations"][0]["is_harmonic_compatible"] is True
