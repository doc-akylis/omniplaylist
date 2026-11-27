from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.api.routes import router as api_router
from app.api.v21_routes import download_studio, router as v21_router
from app.api.v22_routes import router as v22_router
from app.config import get_settings
from app.core.database import engine, init_db

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "app" / "ui" / "static"
DIST_DIR = BASE_DIR / "app" / "ui" / "dist"
DIST_ASSETS_DIR = DIST_DIR / "assets"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database and background workers."""
    init_db()
    with Session(engine) as session:
        download_studio.recover_interrupted_jobs(session)
    settings.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    yield


# Initialize FastAPI app
fastapi_app = FastAPI(
    title=f"{settings.APP_NAME} 2.2",
    lifespan=lifespan,
    debug=settings.DEBUG,
)

# Register REST and WebSocket API routes
fastapi_app.include_router(api_router)
fastapi_app.include_router(v21_router)
fastapi_app.include_router(v22_router)

# Mount legacy static JS/assets (AudioWorklet & Web Audio assets)
STATIC_DIR.mkdir(parents=True, exist_ok=True)
fastapi_app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Mount compiled React/Vite assets
DIST_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
fastapi_app.mount("/assets", StaticFiles(directory=str(DIST_ASSETS_DIR)), name="assets")


@fastapi_app.get("/", include_in_schema=False)
@fastapi_app.get("/{full_path:path}", include_in_schema=False)
async def serve_spa(full_path: str = ""):
    """Serve the compiled React SPA (app/ui/dist/index.html) for all frontend routes."""
    if full_path.startswith(("api/", "ws/", "static/", "assets/")):
        raise HTTPException(status_code=404, detail="Not found")

    if full_path:
        candidate = DIST_DIR / full_path
        if candidate.is_file() and DIST_DIR in candidate.resolve().parents:
            return FileResponse(candidate)

    index_file = DIST_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return HTMLResponse(
        "<!doctype html><html><body style='background:#0B0D12;color:#E5E7EB;font-family:sans-serif;padding:2rem'>"
        "<h1>OmniPlaylist 2.0</h1><p>Frontend build not found in <code>app/ui/dist/</code>. "
        "Run <code>npm run build</code> inside <code>frontend/</code>.</p></body></html>"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:fastapi_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
