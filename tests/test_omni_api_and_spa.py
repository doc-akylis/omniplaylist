from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.api import routes as api_routes
from app.core.models import UnifiedTrack
from app.engines.lyrics_engine import LyricsEngine
from app.engines.metadata_enrichment import MetadataEnrichmentEngine
from app.providers.acoustid import AcoustIDProvider
from app.providers.deezer import DeezerProvider
from app.providers.itunes import ITunesProvider
from app.providers.lastfm import LastFMProvider
from app.providers.listenbrainz import ListenBrainzProvider
from app.providers.musicbrainz import MusicBrainzProvider
from app.providers.rate_limiter import AsyncRateLimiter
from main import fastapi_app


@pytest.fixture
def isolated_api_client(tmp_path: Path, monkeypatch):
    """Provide isolated FastAPI TestClient using a temporary SQLite DB."""
    db_file = tmp_path / "test_omni_api.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(test_engine)

    with Session(test_engine) as s:
        s.add(
            UnifiedTrack(
                title="Local Groove",
                artist="Local DJ",
                isrc="USLOCAL0001",
                bpm=126.0,
                camelot_code="8A",
                energy=0.8,
            )
        )
        s.commit()

    monkeypatch.setattr(
        api_routes,
        "itunes_provider",
        ITunesProvider(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "results": [
                            {
                                "trackName": "Strobe",
                                "artistName": "deadmau5",
                                "collectionName": "For Lack of a Better Name",
                                "artworkUrl100": "https://it.cdn/100x100bb.jpg",
                                "previewUrl": "https://it.cdn/strobe.m4a",
                                "releaseDate": "2009-09-22T07:00:00Z",
                                "primaryGenreName": "Electronic",
                            }
                        ]
                    },
                )
            )
        ),
    )
    monkeypatch.setattr(
        api_routes,
        "deezer_provider",
        DeezerProvider(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": 99001,
                                "title": "Strobe",
                                "artist": {"name": "deadmau5"},
                                "album": {"title": "For Lack of a Better Name", "cover_xl": "https://dz.cdn/strobe.jpg"},
                                "duration": 637,
                                "isrc": "USUL10900123",
                                "preview": "https://dz.cdn/strobe.mp3",
                            }
                        ]
                    },
                )
            )
        ),
    )
    monkeypatch.setattr(
        api_routes,
        "musicbrainz_provider",
        MusicBrainzProvider(
            rate_limiter=AsyncRateLimiter(0.0),
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"recordings": []})),
        ),
    )
    monkeypatch.setattr(
        api_routes,
        "lyrics_engine",
        LyricsEngine(
            rate_limiter=AsyncRateLimiter(0.0),
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    json=[
                        {
                            "id": 55,
                            "trackName": "Strobe",
                            "artistName": "deadmau5",
                            "syncedLyrics": "[00:05.00] Instrumental",
                            "plainLyrics": "Instrumental",
                        }
                    ],
                )
            ),
        ),
    )
    monkeypatch.setattr(
        api_routes,
        "enrichment_engine",
        MetadataEnrichmentEngine(
            musicbrainz=api_routes.musicbrainz_provider,
            itunes=api_routes.itunes_provider,
            deezer=api_routes.deezer_provider,
            lyrics=api_routes.lyrics_engine,
            acoustid=AcoustIDProvider(api_key=""),
            lastfm=LastFMProvider(api_key=""),
            listenbrainz=ListenBrainzProvider(token=""),
        ),
    )

    app = FastAPI()
    app.include_router(api_routes.router)

    def override_session():
        with Session(test_engine) as s:
            yield s

    app.dependency_overrides[api_routes.get_session] = override_session
    return TestClient(app)


def test_omni_search_and_import_online(isolated_api_client: TestClient):
    res = isolated_api_client.get("/api/search/omni?q=Strobe&mode=all")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 1
    hit = data["results"][0]
    assert hit["title"] == "Strobe"
    assert hit["has_synced_lyrics"] is True
    assert "deezer" in hit["sources"]
    assert "itunes" in hit["sources"]
    assert "lrclib" in hit["sources"]

    imp = isolated_api_client.post("/api/tracks/import-online", json={**hit, "enrich": True})
    assert imp.status_code == 200
    imp_data = imp.json()
    assert imp_data["status"] == "imported"
    assert imp_data["track"]["isrc"] == "USUL10900123"


def test_providers_health_discovery_and_patch(isolated_api_client: TestClient):
    health = isolated_api_client.get("/api/health/providers")
    assert health.status_code == 200
    hdata = health.json()
    assert len(hdata["providers"]) == 8
    active_ids = {p["id"] for p in hdata["providers"] if p["status"] == "active"}
    assert {"musicbrainz", "cover_art_archive", "lrclib", "itunes", "deezer"}.issubset(active_ids)

    disc = isolated_api_client.get("/api/discovery/recommendations?track_id=1")
    assert disc.status_code == 200
    assert disc.json()["seed_track"]["title"] == "Local Groove"

    patch_res = isolated_api_client.patch("/api/tracks/1", json={"key": "Am"})
    assert patch_res.status_code == 200
    assert patch_res.json()["camelot_code"] == "8A"

    dups = isolated_api_client.get("/api/library/duplicates")
    assert dups.status_code == 200
    assert dups.json()["total_tracks"] == 1


def test_spa_serves_built_react_index():
    dist_index = Path(__file__).resolve().parents[1] / "app" / "ui" / "dist" / "index.html"
    assert dist_index.exists()

    client = TestClient(fastapi_app)
    for route in ["/", "/dj-mode", "/audio-inspector", "/search", "/library", "/settings"]:
        r = client.get(route)
        assert r.status_code == 200
        assert "OmniPlaylist 2.0" in r.text
        assert "/assets/" in r.text
