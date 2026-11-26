from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from nicegui import app as nicegui_app, ui

from app.api.routes import router as api_router
from app.config import get_settings
from app.core.database import init_db

# Page imports
from app.ui.pages.audio_inspector import render_audio_inspector_page
from app.ui.pages.backup_page import render_backup_page
from app.ui.pages.dashboard import render_dashboard_page
from app.ui.pages.discovery_page import render_discovery_page
from app.ui.pages.dj_mode_page import render_dj_mode_page
from app.ui.pages.download_studio import render_download_studio_page
from app.ui.pages.export_hub import render_export_hub_page
from app.ui.pages.genre_studio import render_genre_studio_page
from app.ui.pages.library_page import render_library_page
from app.ui.pages.metadata_editor_page import render_metadata_editor_page
from app.ui.pages.playlist_health_page import render_playlist_health_page
from app.ui.pages.search_page import render_search_page
from app.ui.pages.settings_page import render_settings_page
from app.ui.pages.smart_dj_page import render_smart_dj_page
from app.ui.pages.smart_sync_page import render_smart_sync_page
from app.ui.pages.stats_page import render_stats_page

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database and background workers."""
    # Startup
    init_db()
    settings.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown logic if needed


# Initialize FastAPI app
fastapi_app = FastAPI(
    title=f"{settings.APP_NAME} 2.0",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# Register REST and WebSocket API routes
fastapi_app.include_router(api_router)

# Mount static JS/assets for DJ Mode 2.0 AudioWorklet & Web Audio engine
STATIC_DIR = Path(__file__).resolve().parent / "app" / "ui" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
fastapi_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Register NiceGUI Pages
@ui.page("/")
def dashboard():
    render_dashboard_page()


@ui.page("/library")
def library():
    render_library_page()


@ui.page("/search")
def search():
    render_search_page()


@ui.page("/smart-dj")
def smart_dj():
    render_smart_dj_page()


@ui.page("/dj-mode")
def dj_mode():
    render_dj_mode_page()


@ui.page("/discovery")
def discovery():
    render_discovery_page()


@ui.page("/genres")
def genres():
    render_genre_studio_page()


@ui.page("/download-studio")
def download_studio():
    render_download_studio_page()


@ui.page("/audio-inspector")
def audio_inspector():
    render_audio_inspector_page()


@ui.page("/playlist-health")
def playlist_health():
    render_playlist_health_page()


@ui.page("/smart-sync")
def smart_sync():
    render_smart_sync_page()


@ui.page("/metadata-editor")
def metadata_editor():
    render_metadata_editor_page()


@ui.page("/export")
def export():
    render_export_hub_page()


@ui.page("/stats")
def stats():
    render_stats_page()


@ui.page("/backup")
def backup():
    render_backup_page()


@ui.page("/settings")
def settings_page():
    render_settings_page()


# Mount NiceGUI to FastAPI
ui.run_with(
    fastapi_app,
    title=f"{settings.APP_NAME} 2.0",
    dark=True,
    favicon="🎵",
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:fastapi_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
