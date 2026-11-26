from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import Playlist, UnifiedTrack
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme_manager import theme_manager


def render_dashboard_page():
    """Render the configurable home dashboard with quick widgets, recent additions, and playback shortcuts."""
    with main_layout(current_page="dashboard"):
        card_cls = theme_manager.card_style

        # Header Greeting
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Início — OmniPlaylist 2.0").classes("text-3xl font-bold text-white tracking-tight")
                ui.label("Central inteligente de reprodução, curadoria musical e engenharia de áudio.").classes(
                    "text-sm text-gray-400"
                )

            with ui.row().classes("gap-3"):
                ui.button("Smart DJ", icon="auto_awesome", on_click=lambda: ui.navigate.to("/smart-dj")).props("color=primary no-caps")
                ui.button("Buscar Músicas", icon="search", on_click=lambda: ui.navigate.to("/search")).props("color=secondary no-caps")

        # Database queries for widgets
        with Session(engine) as session:
            all_tracks = session.exec(select(UnifiedTrack).order_by(UnifiedTrack.id.desc())).all()
            total_tracks = len(all_tracks)
            recent_tracks = all_tracks[:6]
            offline_tracks = [t for t in all_tracks if t.local_path]
            raw_playlists = session.exec(select(Playlist)).all()
            playlists_data = [
                {"id": p.id, "name": p.name, "count": len(p.tracks)}
                for p in raw_playlists
            ]

        # Quick Stats Overview Row
        with ui.row().classes("w-full gap-4 mb-6"):
            with ui.column().classes(f"{card_cls} flex-1"):
                ui.label("Acervo Total").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(f"{total_tracks} faixas").classes("text-2xl font-bold text-white")

            with ui.column().classes(f"{card_cls} flex-1"):
                ui.label("Playlists Criadas").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(f"{len(playlists_data)} listas").classes("text-2xl font-bold text-primary")

            with ui.column().classes(f"{card_cls} flex-1"):
                ui.label("Músicas Offline").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(f"{len(offline_tracks)} baixadas").classes("text-2xl font-bold text-accent")

            with ui.column().classes(f"{card_cls} flex-1"):
                ui.label("Qualidade Média").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label("320 kbps / FLAC").classes("text-2xl font-bold text-info")

        # Two-column layout: Recent Additions & Quick Tools
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            # Recent Additions
            with ui.column().classes(f"flex-[2] {card_cls} gap-4"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("history", color="primary")
                        ui.label("Adicionadas Recentemente").classes("text-lg font-bold text-white")
                    ui.button("Ver Todas", on_click=lambda: ui.navigate.to("/library")).props("flat dense color=primary no-caps")

                if not recent_tracks:
                    ui.label("Nenhuma música cadastrada ainda.").classes("text-sm text-gray-400 py-4")
                else:
                    for t in recent_tracks:
                        with ui.row().classes("w-full items-center justify-between p-2 rounded-lg bg-[#222] hover:bg-[#282828] transition-colors"):
                            with ui.row().classes("items-center gap-3"):
                                cover = t.cover_url or "https://placehold.co/40x40/181818/1DB954?text=%E2%99%AC"
                                ui.image(cover).classes("w-10 h-10 rounded-md object-cover")
                                with ui.column().classes("gap-0"):
                                    ui.label(t.title).classes("text-sm font-semibold text-white truncate max-w-[280px]")
                                    ui.label(f"{t.artist} • {t.album or 'Single'}").classes("text-xs text-gray-400 truncate max-w-[280px]")

                            with ui.row().classes("items-center gap-2"):
                                if t.bpm:
                                    ui.badge(f"{int(t.bpm)} BPM", color="secondary").props("outline dense")
                                if t.key:
                                    ui.badge(t.key, color="info").props("outline dense")
                                ui.button(
                                    icon="play_arrow",
                                    on_click=lambda trk=t: player.play_track(trk),
                                ).props("flat round dense color=primary")

            # Quick Shortcuts & Playlists
            with ui.column().classes(f"flex-1 {card_cls} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("bolt", color="accent")
                    ui.label("Atalhos Rápidos").classes("text-lg font-bold text-white")

                with ui.column().classes("w-full gap-2"):
                    with ui.button("Gerar Set no Smart DJ", on_click=lambda: ui.navigate.to("/smart-dj")).classes("w-full justify-start").props("flat color=white no-caps align=left"):
                        ui.icon("auto_awesome", color="primary").classes("mr-2")

                    with ui.button("Preparar Set no Modo DJ", on_click=lambda: ui.navigate.to("/dj-mode")).classes("w-full justify-start").props("flat color=white no-caps align=left"):
                        ui.icon("album", color="accent").classes("mr-2")

                    with ui.button("Auditar Biblioteca (Inspector)", on_click=lambda: ui.navigate.to("/audio-inspector")).classes("w-full justify-start").props("flat color=white no-caps align=left"):
                        ui.icon("troubleshoot", color="info").classes("mr-2")

                    with ui.button("Sincronizar Pen Drive (Smart Sync)", on_click=lambda: ui.navigate.to("/smart-sync")).classes("w-full justify-start").props("flat color=white no-caps align=left"):
                        ui.icon("usb", color="warning").classes("mr-2")

                ui.separator().classes("bg-[#2A2A2A]")

                with ui.row().classes("items-center gap-2"):
                    ui.icon("queue_music", color="primary")
                    ui.label("Playlists Salvas").classes("text-sm font-bold text-white")

                if not playlists_data:
                    ui.label("Nenhuma playlist criada ainda.").classes("text-xs text-gray-400")
                else:
                    for pl in playlists_data[:4]:
                        with ui.row().classes("w-full justify-between items-center text-xs py-1"):
                            ui.label(pl["name"]).classes("text-white font-medium truncate max-w-[160px]")
                            ui.badge(f"{pl['count']} faixas", color="secondary").props("dense")
