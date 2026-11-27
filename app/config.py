from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "OmniPlaylist"
    APP_ENV: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./omniplaylist.db"
    DOWNLOAD_DIR: Path = Path("./downloads")

    # Spotify credentials
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    SPOTIFY_REDIRECT_URI: str = "http://localhost:8000/callback/spotify"

    # YouTube Music
    YTMUSIC_AUTH_FILE: str = "./ytmusic_auth.json"

    # Amazon Music
    AMAZON_MUSIC_COOKIES_FILE: str = "./amazon_cookies.json"

    # Metadata Enrichment & Discovery (All optional, degrade gracefully)
    ACOUSTID_API_KEY: str = ""
    LISTENBRAINZ_TOKEN: str = ""
    LASTFM_API_KEY: str = ""
    DISCOGS_TOKEN: str = ""

    # Multi-Source Authorized & Commercial Acquisition Providers (v2.2, all optional)
    JAMENDO_CLIENT_ID: str = ""
    SOUNDCLOUD_CLIENT_ID: str = ""
    FREESOUND_API_KEY: str = ""
    TIDAL_CLIENT_ID: str = ""
    TIDAL_CLIENT_SECRET: str = ""
    SEVENDIGITAL_API_KEY: str = ""
    SEVENDIGITAL_API_SECRET: str = ""
    RIGHTS_FOUNDRY_API_KEY: str = ""
    QOBUZ_APP_ID: str = ""
    QOBUZ_USER_TOKEN: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return cached singleton instance of Settings."""
    return Settings()
