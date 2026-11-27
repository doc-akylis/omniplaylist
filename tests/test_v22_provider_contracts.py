"""Contract tests for all OmniPlaylist 2.2 multi-source adapters across all 4 provider categories."""

from __future__ import annotations

import httpx
import pytest

from app.sources.adapters.audius import AudiusAdapter
from app.sources.adapters.catalog_adapters import (
    DeezerDiscoveryAdapter,
    DiscogsDiscoveryAdapter,
    ITunesDiscoveryAdapter,
    MusicBrainzDiscoveryAdapter,
    SpotifyDiscoveryAdapter,
)
from app.sources.adapters.commercial_adapters import (
    QobuzPartnerAdapter,
    SevenDigitalMassiveMusicAdapter,
    TheRightsFoundryAdapter,
)
from app.sources.adapters.freesound import FreesoundAdapter
from app.sources.adapters.internet_archive import InternetArchiveAdapter
from app.sources.adapters.jamendo import JamendoAdapter
from app.sources.adapters.soundcloud import SoundCloudAdapter
from app.sources.adapters.wikimedia_commons import WikimediaCommonsAdapter
from app.sources.base import PermissionStatus, ProviderCategory
from app.sources.registry import MusicSourceRegistry


def test_registry_has_all_14_adapters_with_strict_categories():
    reg = MusicSourceRegistry()
    caps = {a.provider_id: a.capabilities() for a in reg._adapters.values()}
    assert len(caps) == 14

    assert caps["internet_archive"].category == ProviderCategory.AUTHORIZED_DOWNLOAD
    assert caps["wikimedia_commons"].category == ProviderCategory.AUTHORIZED_DOWNLOAD
    assert caps["audius"].category == ProviderCategory.AUTHORIZED_DOWNLOAD
    assert caps["jamendo"].category == ProviderCategory.AUTHORIZED_DOWNLOAD
    assert caps["soundcloud"].category == ProviderCategory.AUTHORIZED_DOWNLOAD
    assert caps["freesound"].category == ProviderCategory.AUTHORIZED_DOWNLOAD

    assert caps["itunes"].category == ProviderCategory.PREVIEW_STREAMING
    assert caps["deezer"].category == ProviderCategory.PREVIEW_STREAMING
    assert caps["spotify"].category == ProviderCategory.DISCOVERY
    assert caps["musicbrainz"].category == ProviderCategory.DISCOVERY
    assert caps["discogs"].category == ProviderCategory.DISCOVERY

    assert caps["sevendigital"].category == ProviderCategory.COMMERCIAL_DELIVERY
    assert caps["rights_foundry"].category == ProviderCategory.COMMERCIAL_DELIVERY
    assert caps["qobuz"].category == ProviderCategory.COMMERCIAL_DELIVERY


@pytest.mark.asyncio
async def test_internet_archive_lossless_and_derivative_contract():
    def handler(req: httpx.Request) -> httpx.Response:
        if "advancedsearch.php" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "response": {
                        "docs": [
                            {
                                "identifier": "gd1977-05-08.flac16",
                                "title": "Scarlet Begonias (Live at Barton Hall)",
                                "creator": "Grateful Dead",
                                "year": "1977",
                                "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/",
                            }
                        ]
                    }
                },
            )
        if "/metadata/gd1977-05-08.flac16" in str(req.url):
            return httpx.Response(
                200,
                json={
                    "metadata": {"album": "Cornell 1977"},
                    "files": [
                        {"name": "gd77_track01.mp3", "format": "VBR MP3", "source": "derivative", "bitrate": "192"},
                        {"name": "gd77_track01.flac", "format": "Flac", "source": "original", "size": "45000000"},
                    ],
                },
            )
        return httpx.Response(404)

    adapter = InternetArchiveAdapter(transport=httpx.MockTransport(handler))
    res = await adapter.search_tracks("Scarlet Begonias", limit=5)
    assert len(res) == 1
    item = res[0]
    assert item.category == ProviderCategory.AUTHORIZED_DOWNLOAD
    assert item.version_type == "live"
    assert item.permission.status == PermissionStatus.ALLOWED_FREE
    assert item.permission.downloadable is True
    assert item.declared_codec == "flac"
    assert item.origin_classification == "LOSSLESS_SOURCE"
    assert item.download_url.endswith("/gd77_track01.flac")


@pytest.mark.asyncio
async def test_wikimedia_commons_contract():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "query": {
                    "pages": {
                        "12345": {
                            "title": "File:Beethoven Symphony 5.ogg",
                            "imageinfo": [
                                {
                                    "url": "https://upload.wikimedia.org/wikipedia/commons/b/be/Beethoven5.ogg",
                                    "mime": "audio/ogg",
                                    "size": 5400000,
                                    "extmetadata": {
                                        "ObjectName": {"value": "Symphony No. 5"},
                                        "Artist": {"value": "<b>Skidmore Orchestra</b>"},
                                        "LicenseShortName": {"value": "CC BY-SA 3.0"},
                                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/3.0/"},
                                    },
                                }
                            ],
                        }
                    }
                }
            },
        )

    adapter = WikimediaCommonsAdapter(transport=httpx.MockTransport(handler))
    res = await adapter.search_tracks("Beethoven 5", limit=5)
    assert len(res) == 1
    assert res[0].artist == "Skidmore Orchestra"
    assert res[0].permission.status == PermissionStatus.ALLOWED_FREE
    assert res[0].permission.downloadable is True
    assert res[0].license_info == "CC BY-SA 3.0"


@pytest.mark.asyncio
async def test_audius_downloadable_vs_streaming_only_contract():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "track-dl",
                        "title": "Synthwave Sunset",
                        "user": {"name": "Neon Producer"},
                        "is_downloadable": True,
                        "download_url": "https://discoveryprovider.audius.co/v1/tracks/track-dl/download",
                        "duration": 210,
                        "genre": "Electronic",
                    },
                    {
                        "id": "track-stream",
                        "title": "Locked Single",
                        "user": {"name": "Major Indie"},
                        "is_downloadable": False,
                        "duration": 180,
                    },
                ]
            },
        )

    adapter = AudiusAdapter(transport=httpx.MockTransport(handler))
    res = await adapter.search_tracks("Synthwave", limit=5)
    assert len(res) == 2
    assert res[0].permission.downloadable is True
    assert res[0].permission.status == PermissionStatus.ALLOWED_FREE
    assert res[1].permission.downloadable is False
    assert res[1].permission.status == PermissionStatus.STREAMING_ONLY
    assert res[1].download_url is None


@pytest.mark.asyncio
async def test_jamendo_cc_license_without_audiodownload_allowed_is_not_downloadable():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "901",
                        "name": "CC Stream Only",
                        "artist_name": "Indie Band",
                        "audiodownload_allowed": False,
                        "audiodownload": "",
                        "audio": "https://mp3l.jamendo.com/?trackid=901",
                        "license_ccurl": "https://creativecommons.org/licenses/by-nc-nd/3.0/",
                        "duration": 200,
                    },
                    {
                        "id": "902",
                        "name": "CC Download Open",
                        "artist_name": "Open Artist",
                        "audiodownload_allowed": True,
                        "audiodownload": "https://prod-1.storage.jamendo.com/download/track/902/mp32/",
                        "audio": "https://mp3l.jamendo.com/?trackid=902",
                        "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                        "duration": 205,
                    },
                ]
            },
        )

    adapter = JamendoAdapter(client_id="demo-client", transport=httpx.MockTransport(handler))
    res = await adapter.search_tracks("Indie", limit=5)
    assert len(res) == 2
    assert res[0].permission.downloadable is False
    assert res[0].permission.status == PermissionStatus.NOT_DOWNLOADABLE
    assert res[1].permission.downloadable is True
    assert res[1].permission.status == PermissionStatus.ALLOWED_FREE


@pytest.mark.asyncio
async def test_soundcloud_and_freesound_contracts():
    def sc_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": 77,
                    "title": "Deep House (Extended Mix)",
                    "user": {"username": "ClubDJ"},
                    "downloadable": True,
                    "download_url": "https://api.soundcloud.com/tracks/77/download",
                    "original_format": "wav",
                    "duration": 360000,
                },
                {
                    "id": 78,
                    "title": "Stream Only ID",
                    "user": {"username": "ClubDJ"},
                    "downloadable": False,
                    "stream_url": "https://api.soundcloud.com/tracks/78/stream",
                    "duration": 180000,
                },
            ],
        )

    sc = SoundCloudAdapter(client_id="sc-key", transport=httpx.MockTransport(sc_handler))
    sc_res = await sc.search_tracks("Deep House", limit=5)
    assert len(sc_res) == 2
    assert sc_res[0].version_type == "extended"
    assert sc_res[0].permission.downloadable is True
    assert sc_res[1].permission.downloadable is False
    assert sc_res[1].download_url is None

    def fs_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 500,
                        "name": "Analog Pad C2",
                        "username": "SynthLab",
                        "duration": 12.5,
                        "type": "wav",
                        "samplerate": 48000,
                        "bitdepth": 24,
                        "license": "https://creativecommons.org/publicdomain/zero/1.0/",
                        "previews": {"preview-hq-mp3": "https://cdn.freesound.org/previews/500-hq.mp3"},
                    }
                ]
            },
        )

    fs = FreesoundAdapter(api_key="fs-key", transport=httpx.MockTransport(fs_handler))
    fs_res = await fs.search_tracks("Analog Pad", limit=5)
    assert len(fs_res) == 1
    assert fs_res[0].permission.status == PermissionStatus.ALLOWED_FREE
    assert fs_res[0].download_url == "https://cdn.freesound.org/previews/500-hq.mp3"


@pytest.mark.asyncio
async def test_catalog_and_preview_adapters_never_mark_downloadable():
    # Mock empty Spotify token + search
    def sp_handler(req: httpx.Request) -> httpx.Response:
        if "api/token" in str(req.url):
            return httpx.Response(200, json={"access_token": "tok"})
        return httpx.Response(
            200,
            json={
                "tracks": {
                    "items": [
                        {
                            "id": "sp1",
                            "name": "Midnight City",
                            "artists": [{"name": "M83"}],
                            "album": {"name": "Hurry Up, We're Dreaming", "images": [{"url": "https://i.scdn.co/1.jpg"}]},
                            "external_ids": {"isrc": "FR10S1100123"},
                            "duration_ms": 243000,
                            "preview_url": None,
                        }
                    ]
                }
            },
        )

    sp = SpotifyDiscoveryAdapter(client_id="cid", client_secret="sec", transport=httpx.MockTransport(sp_handler))
    sp_res = await sp.search_tracks("Midnight City", limit=3)
    assert len(sp_res) == 1
    assert sp_res[0].category == ProviderCategory.DISCOVERY
    assert sp_res[0].permission.downloadable is False
    assert sp_res[0].download_url is None

    # Discogs
    def dg_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 999,
                        "title": "Daft Punk - Discovery",
                        "year": "2001",
                        "genre": ["Electronic"],
                        "cover_image": "https://img.discogs.com/dp.jpg",
                    }
                ]
            },
        )

    dg = DiscogsDiscoveryAdapter(token="dg-tok", transport=httpx.MockTransport(dg_handler))
    dg_res = await dg.search_tracks("Discovery", limit=3)
    assert len(dg_res) == 1
    assert dg_res[0].category == ProviderCategory.DISCOVERY
    assert dg_res[0].permission.downloadable is False

    # MusicBrainz / iTunes / Deezer capabilities check
    assert ITunesDiscoveryAdapter().capabilities().category == ProviderCategory.PREVIEW_STREAMING
    assert DeezerDiscoveryAdapter().capabilities().supports_download is False
    assert MusicBrainzDiscoveryAdapter().capabilities().supports_download is False


@pytest.mark.asyncio
async def test_commercial_adapters_require_credentials_or_explicit_approval():
    # Unconfigured commercial adapters must explicitly state REQUIRES_CREDENTIALS
    sd_unconf = SevenDigitalMassiveMusicAdapter(api_key="", api_secret="")
    assert sd_unconf.capabilities().auth_configured is False
    assert (await sd_unconf.health_check())["status"] == "requires_credentials"
    assert await sd_unconf.search_tracks("Test") == []

    # Configured Qobuz Partner with mock catalog response
    def qobuz_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "tracks": {
                    "items": [
                        {
                            "id": "qb-88",
                            "title": "Get Lucky",
                            "performer": {"name": "Daft Punk"},
                            "album": {"title": "RAM", "image": {"large": "https://static.qobuz.com/cover.jpg"}},
                            "isrc": "USQX91300108",
                            "duration": 369,
                            "maximum_bit_depth": 24,
                            "maximum_sampling_rate": 88.2,
                            "hires_streamable": True,
                            "authorized_download_url": "https://partner-dl.qobuz.com/track/88.flac",
                        }
                    ]
                }
            },
        )

    qb = QobuzPartnerAdapter(
        app_id="q-app",
        user_token="q-tok",
        transport=httpx.MockTransport(qobuz_handler),
    )
    res = await qb.search_tracks("Get Lucky", limit=3)
    assert len(res) == 1
    assert res[0].category == ProviderCategory.COMMERCIAL_DELIVERY
    assert res[0].permission.status == PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL
    assert res[0].permission.downloadable is True
    assert res[0].requires_payment is True
    assert res[0].declared_bit_depth == 24
    assert res[0].declared_sample_rate_hz == 88200

    # Configured 7digital
    def sd_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "searchResults": {
                    "searchResult": [
                        {
                            "track": {
                                "id": 1234,
                                "title": "Get Lucky",
                                "artist": {"name": "Daft Punk"},
                                "price": {"formattedPrice": "$1.99"},
                                "isrc": "USQX91300108",
                                "download_url": "https://dl.7digital.com/track/1234.flac",
                            }
                        }
                    ]
                }
            },
        )

    sd = SevenDigitalMassiveMusicAdapter(
        api_key="k",
        api_secret="s",
        transport=httpx.MockTransport(sd_handler),
    )
    sd_res = await sd.search_tracks("Get Lucky", limit=3)
    assert len(sd_res) == 1
    assert sd_res[0].permission.status == PermissionStatus.ALLOWED_COMMERCIAL_REQUIRES_APPROVAL
    assert sd_res[0].estimated_cost_label == "$1.99"

    # Unconfigured Rights Foundry
    rf = TheRightsFoundryAdapter(api_key="")
    assert rf.capabilities().auth_configured is False
