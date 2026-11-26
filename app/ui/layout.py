from collections.abc import Generator
from contextlib import contextmanager
from nicegui import ui
from app.ui.player import player
from app.ui.theme import ACTIVE_SIDEBAR_ITEM, SIDEBAR_ITEM, apply_theme


@contextmanager
def main_layout(current_page: str = "dashboard") -> Generator[None, None, None]:
    """Universal layout with grouped sidebar, main content area, and bottom status/player bar."""
    apply_theme()

    def nav_btn(text: str, icon_name: str, target: str, page_key: str):
        is_act = (current_page == page_key)
        cls = ACTIVE_SIDEBAR_ITEM if is_act else SIDEBAR_ITEM
        with ui.link(target=target).classes("w-full no-underline"):
            ui.button(f" {text}", icon=icon_name).classes(cls).props("flat no-caps align=left dense")

    def category_header(title: str):
        ui.label(title).classes("text-[10px] font-bold text-gray-500 uppercase tracking-wider px-3 pt-3 pb-1")

    # Main Grid Container
    with ui.column().classes("w-screen h-screen m-0 p-0 overflow-hidden bg-[#121212] select-none"):
        # Upper Layout: Sidebar + Content Area
        with ui.row().classes("w-full flex-1 overflow-hidden m-0 p-0 gap-0"):
            # Sidebar Navigation (Scrollable navigation menu)
            with ui.column().classes("w-64 h-full bg-[#000000] p-3 flex flex-col justify-between border-r border-[#222222]"):
                with ui.column().classes("w-full overflow-y-auto pr-1 gap-1 flex-1"):
                    # Logo & App Title
                    with ui.link(target="/").classes("no-underline"):
                        with ui.row().classes("items-center gap-2 px-2 py-2 mb-2"):
                            ui.icon("library_music", size="1.8rem", color="primary")
                            ui.label("OmniPlaylist 2.0").classes("text-lg font-bold tracking-tight text-white")

                    # Group 1: PRINCIPAL
                    category_header("Principal")
                    nav_btn("Início", "home", "/", "dashboard")
                    nav_btn("Biblioteca Unificada", "library_books", "/library", "library")
                    nav_btn("Busca Avançada", "search", "/search", "search")

                    # Group 2: CURADORIA & DJ
                    category_header("Curadoria & DJ")
                    nav_btn("Smart DJ 2.0", "auto_awesome", "/smart-dj", "smart_dj")
                    nav_btn("Modo DJ (Camelot)", "album", "/dj-mode", "dj_mode")
                    nav_btn("Music Discovery", "explore", "/discovery", "discovery")
                    nav_btn("Genre Studio", "bubble_chart", "/genres", "genres")

                    # Group 3: ENGENHARIA DE ÁUDIO
                    category_header("Engenharia de Áudio")
                    nav_btn("Download Studio", "cloud_download", "/download-studio", "download_studio")
                    nav_btn("Audio Inspector", "troubleshoot", "/audio-inspector", "audio_inspector")
                    nav_btn("Playlist Health", "health_and_safety", "/playlist-health", "playlist_health")
                    nav_btn("Smart Sync (USB)", "usb", "/smart-sync", "smart_sync")

                    # Group 4: FERRAMENTAS & GESTÃO
                    category_header("Ferramentas & Gestão")
                    nav_btn("Editor de Metadados", "edit_note", "/metadata-editor", "metadata_editor")
                    nav_btn("Export & Sync Hub", "sync_alt", "/export", "export")
                    nav_btn("OmniStats 2.0", "bar_chart", "/stats", "stats")
                    nav_btn("Backups & Restauração", "archive", "/backup", "backup")
                    nav_btn("Configurações & Temas", "settings", "/settings", "settings")

                # Sidebar Bottom: Connected Services Status
                with ui.column().classes("w-full p-2.5 bg-[#121212] rounded-xl border border-[#222222] gap-1 shrink-0 mt-2"):
                    ui.label("Provedores Ativos").classes("text-[10px] font-semibold text-gray-400 uppercase tracking-wider")
                    with ui.row().classes("items-center justify-between text-xs text-gray-300 w-full"):
                        ui.label("Deezer").classes("flex items-center gap-1")
                        ui.badge("Ativo (Livre)", color="positive").props("outline dense")
                    with ui.row().classes("items-center justify-between text-xs text-gray-300 w-full"):
                        ui.label("Spotify").classes("flex items-center gap-1")
                        ui.badge("OAuth", color="positive").props("outline dense")
                    with ui.row().classes("items-center justify-between text-xs text-gray-300 w-full"):
                        ui.label("YT Music").classes("flex items-center gap-1")
                        ui.badge("Pronto", color="info").props("outline dense")

            # Main Page Content Area (Scrollable)
            with ui.column().classes("flex-1 h-full overflow-y-auto p-6 bg-[#121212]"):
                yield

        # Bottom Bar: Real Interactive Audio Player & Status
        with ui.row().classes(
            "w-full h-20 bg-[#181818] border-t border-[#282828] px-6 items-center justify-between z-10 shrink-0"
        ):
            player.render_controls()
