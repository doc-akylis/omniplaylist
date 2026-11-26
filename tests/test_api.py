from fastapi.testclient import TestClient
from sqlmodel import Session, select
from main import fastapi_app
from app.core.database import get_session
from app.core.models import Playlist, UnifiedTrack

client = TestClient(fastapi_app)


def test_api_tracks_endpoint():
    response = client.get("/api/tracks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_playlists_endpoint():
    response = client.get("/api/playlists")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_playlist_details_404():
    response = client.get("/api/playlists/999999")
    assert response.status_code == 404


def test_all_ui_pages_render_successfully():
    pages = [
        "/",
        "/library",
        "/search",
        "/smart-dj",
        "/dj-mode",
        "/discovery",
        "/download-studio",
        "/audio-inspector",
        "/genres",
        "/playlist-health",
        "/metadata-editor",
        "/smart-sync",
        "/export",
        "/stats",
        "/backup",
        "/settings",
    ]
    for page in pages:
        res = client.get(page)
        assert res.status_code == 200, f"Page {page} returned status {res.status_code}"
