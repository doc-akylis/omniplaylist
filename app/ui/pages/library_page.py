import asyncio
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.downloader import TrackDownloader
from app.engines.lyrics_engine import LyricsEngine
from app.providers.deezer import DeezerProvider
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme import CARD_STYLE

deezer_provider = DeezerProvider()
lyrics_engine = LyricsEngine()
downloader = TrackDownloader()


def render_library_page():
    """Render the unified library page with track browsing, player controls, Deezer import, and lyrics."""
    with main_layout(current_page="library"):
        # Header Section
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Biblioteca Unificada").classes("text-3xl font-bold text-white tracking-tight")
                ui.label("Gerencie, ouça prévias, sincronize letras e localize faixas equivalentes.").classes(
                    "text-sm text-gray-400"
                )

            with ui.row().classes("gap-3"):
                ui.button("Buscar no Deezer", icon="search", on_click=lambda: open_deezer_modal()).props(
                    "color=primary no-caps"
                )
                ui.button("Importar Spotify", icon="podcasts").props("color=secondary no-caps")
                ui.button("Importar YT Music", icon="smart_display").props("color=secondary no-caps")

        # Database Stats Query
        with Session(engine) as session:
            total_tracks = session.exec(select(UnifiedTrack)).all()
            total_count = len(total_tracks)
            matched_count = sum(1 for t in total_tracks if t.isrc)
            downloaded_count = sum(1 for t in total_tracks if t.local_path)

        # Stats Cards
        with ui.row().classes("w-full gap-4 mb-6"):
            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Total de Faixas").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(str(total_count)).classes("text-2xl font-bold text-white")

            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Identificadas com ISRC").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(str(matched_count)).classes("text-2xl font-bold text-primary")

            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Disponíveis Offline").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(str(downloaded_count)).classes("text-2xl font-bold text-accent")

        # Track list container
        ui.label("Músicas Cadastradas").classes("text-xl font-bold text-white mb-2")

        if not total_tracks:
            with ui.column().classes(f"w-full {CARD_STYLE} items-center justify-center p-8 text-center"):
                ui.icon("library_music", size="3rem", color="gray")
                ui.label("Sua biblioteca está vazia").classes("text-lg font-semibold text-white mt-2")
                ui.label("Clique no botão 'Buscar no Deezer' acima para adicionar faixas reais com 1 clique.").classes(
                    "text-sm text-gray-400"
                )
        else:
            with ui.column().classes("w-full gap-2"):
                for track in total_tracks:
                    with ui.row().classes(
                        f"{CARD_STYLE} w-full items-center justify-between py-3 px-4 hover:border-primary"
                    ):
                        # Track metadata
                        with ui.row().classes("items-center gap-3"):
                            cover = track.cover_url or "https://placehold.co/40x40/181818/1DB954?text=%E2%99%AC"
                            ui.image(cover).classes("w-10 h-10 rounded-md object-cover")
                            with ui.column().classes("gap-0"):
                                ui.label(track.title).classes("text-sm font-bold text-white")
                                ui.label(f"{track.artist} {f'• {track.album}' if track.album else ''}").classes(
                                    "text-xs text-gray-400"
                                )

                        # Extra Badges
                        with ui.row().classes("items-center gap-2"):
                            if track.bpm:
                                ui.badge(f"{int(track.bpm)} BPM", color="secondary").props("outline dense")
                            if track.isrc:
                                ui.badge(f"ISRC: {track.isrc}", color="secondary").props("outline dense")
                            if track.local_path:
                                ui.badge("Offline", color="positive").props("dense")

                        # Actions
                        with ui.row().classes("items-center gap-2"):
                            ui.button(
                                icon="play_arrow",
                                on_click=lambda t=track: player.play_track(t),
                            ).props("flat round color=primary").tooltip("Ouvir")

                            ui.button(
                                icon="subtitles",
                                on_click=lambda t=track: show_lyrics_dialog(t),
                            ).props("flat round color=info").tooltip("Ver Letra")

                            ui.button(
                                icon="download",
                                on_click=lambda t=track: start_download(t),
                            ).props("flat round color=gray").tooltip("Baixar MP3 320kbps")


def show_lyrics_dialog(track: UnifiedTrack):
    """Open an interactive dialog displaying synced or plain lyrics."""
    with ui.dialog() as dialog, ui.card().classes("bg-[#181818] border border-[#2A2A2A] text-white w-[500px] max-h-[80vh]"):
        ui.label(f"Letra: {track.title}").classes("text-lg font-bold text-primary")
        ui.label(f"Artista: {track.artist}").classes("text-xs text-gray-400 mb-3")

        spinner = ui.spinner(size="md", color="primary")
        lyrics_container = ui.column().classes("w-full max-h-[50vh] overflow-y-auto whitespace-pre-wrap text-sm text-gray-300")

        async def load_lyrics():
            if not track.lyrics_synced and not track.lyrics_plain:
                synced, plain = await lyrics_engine.fetch_lyrics(track)
                with Session(engine) as session:
                    db_t = session.get(UnifiedTrack, track.id)
                    if db_t:
                        db_t.lyrics_synced = synced
                        db_t.lyrics_plain = plain
                        session.add(db_t)
                        session.commit()
                track.lyrics_synced = synced
                track.lyrics_plain = plain

            spinner.set_visibility(False)
            content = track.lyrics_synced or track.lyrics_plain or "Letra não encontrada para esta faixa."
            with lyrics_container:
                ui.label(content).classes("text-sm leading-relaxed")

        asyncio.create_task(load_lyrics())

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Fechar", on_click=dialog.close).props("flat color=white")

    dialog.open()


def start_download(track: UnifiedTrack):
    """Enqueue a track for MP3 download."""
    async def _download():
        ui.notify(f"Iniciando download de '{track.title}'...", type="info")
        path = await downloader.download_track(track)
        if path:
            with Session(engine) as session:
                db_t = session.get(UnifiedTrack, track.id)
                if db_t:
                    db_t.local_path = str(path)
                    session.add(db_t)
                    session.commit()
            ui.notify(f"Download concluído: {track.title}", type="positive")
            # If lyrics exist, save .lrc alongside
            if track.lyrics_synced:
                lyrics_engine.save_lrc_file(track)

    asyncio.create_task(_download())


def open_deezer_modal():
    """Modal to search and import tracks from Deezer instantly with 1-click."""
    with ui.dialog() as dialog, ui.card().classes("bg-[#181818] border border-[#2A2A2A] text-white w-[650px]"):
        ui.label("Buscar e Importar do Deezer").classes("text-xl font-bold text-primary")
        ui.label("Busca pública rápida com ISRC real e prévia de áudio de 30 segundos.").classes("text-xs text-gray-400 mb-2")

        with ui.row().classes("w-full items-center gap-2"):
            search_input = ui.input(placeholder="Nome da música ou artista...").props("dark outlined dense").classes("flex-1")
            results_column = ui.column().classes("w-full max-h-[50vh] overflow-y-auto mt-2 gap-2")

            async def do_search():
                q = search_input.value
                if not q:
                    return
                results_column.clear()
                with results_column:
                    ui.spinner(color="primary")

                tracks = await deezer_provider.search_tracks(q, limit=10)
                results_column.clear()

                if not tracks:
                    with results_column:
                        ui.label("Nenhum resultado encontrado.").classes("text-sm text-gray-400")
                    return

                with results_column:
                    for t in tracks:
                        with ui.row().classes("w-full items-center justify-between p-2 rounded-lg bg-[#222] hover:bg-[#282828]"):
                            with ui.row().classes("items-center gap-3"):
                                if t.cover_url:
                                    ui.image(t.cover_url).classes("w-8 h-8 rounded")
                                with ui.column().classes("gap-0"):
                                    ui.label(t.title).classes("text-sm font-semibold text-white")
                                    ui.label(t.artist).classes("text-xs text-gray-400")

                            with ui.row().classes("items-center gap-2"):
                                if t.preview_url:
                                    ui.button(
                                        icon="play_arrow",
                                        on_click=lambda trk=t: player.play_track(trk),
                                    ).props("flat round dense color=primary").tooltip("Ouvir prévia 30s")

                                ui.button(
                                    "Adicionar",
                                    icon="add",
                                    on_click=lambda trk=t: import_to_db(trk, dialog),
                                ).props("color=primary dense no-caps")

            search_input.on("keydown.enter", do_search)
            ui.button("Buscar", icon="search", on_click=do_search).props("color=primary dense no-caps")

        with ui.row().classes("w-full justify-end mt-4"):
            ui.button("Fechar", on_click=dialog.close).props("flat color=white")

    dialog.open()


def import_to_db(track: UnifiedTrack, dialog):
    """Save Deezer track into SQLite."""
    with Session(engine) as session:
        # Check duplicate
        exists = session.exec(select(UnifiedTrack).where(UnifiedTrack.title == track.title, UnifiedTrack.artist == track.artist)).first()
        if not exists:
            session.add(track)
            session.commit()
            ui.notify(f"Adicionada: {track.title} - {track.artist}", type="positive")
        else:
            ui.notify(f"'{track.title}' já está na sua biblioteca!", type="info")

    dialog.close()
    ui.navigate.to("/")
