import asyncio
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack, UserSettings
from app.engines.music_discovery import DiscoverySection, MusicDiscoveryEngine
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme_manager import theme_manager

discovery_engine = MusicDiscoveryEngine()


def render_discovery_page():
    """Render the Music Discovery hub with personalized suggestions, deep cuts, and Deezer recommendations."""
    with main_layout(current_page="discovery"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Music Discovery — Descoberta & Recomendações").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Explore faixas semelhantes ao seu gosto musical, resgate raridades do seu acervo e descubra novas músicas."
                ).classes("text-sm text-gray-400")

            ui.button("Atualizar Recomendações", icon="refresh", on_click=lambda: load_feed()).props("color=primary no-caps")

        feed_container = ui.column().classes("w-full gap-6")

        def load_feed():
            feed_container.clear()
            with feed_container:
                ui.spinner(size="lg", color="primary")

            async def _async_load():
                with Session(engine) as session:
                    library_tracks = session.exec(select(UnifiedTrack)).all()
                    sections: list[DiscoverySection] = await discovery_engine.generate_discovery_feed(library_tracks, session)

                feed_container.clear()
                with feed_container:
                    if not sections:
                        with ui.column().classes(f"w-full {card_cls} p-8 items-center text-center"):
                            ui.icon("explore", size="3rem", color="gray")
                            ui.label("Sem dados suficientes para recomendações").classes("text-lg font-bold text-white mt-2")
                            ui.label("Adicione músicas à sua biblioteca na página Biblioteca Unificada para calibrar o motor.").classes("text-sm text-gray-400")
                        return

                    for sec in sections:
                        with ui.column().classes(f"w-full {card_cls} gap-3"):
                            with ui.row().classes("items-center justify-between w-full"):
                                with ui.column().classes("gap-0"):
                                    ui.label(sec.title).classes("text-lg font-bold text-white")
                                    ui.label(sec.description).classes("text-xs text-gray-400")
                                ui.badge(f"{len(sec.tracks)} sugestões", color="primary").props("dense")

                            if not sec.tracks:
                                ui.label("Nenhuma faixa nesta categoria no momento.").classes("text-xs text-gray-500 py-2")
                            else:
                                with ui.row().classes("w-full gap-3 overflow-x-auto pb-2 flex-nowrap"):
                                    for t in sec.tracks:
                                        with ui.column().classes(
                                            "w-44 p-3 rounded-lg bg-[#202020] border border-[#2E2E2E] shrink-0 hover:border-primary transition-all"
                                        ):
                                            cover = t.cover_url or "https://placehold.co/140x140/181818/1DB954?text=%E2%99%AC"
                                            ui.image(cover).classes("w-full h-36 rounded-md object-cover mb-2")

                                            ui.label(t.title).classes("text-sm font-bold text-white truncate max-w-full")
                                            ui.label(t.artist).classes("text-xs text-gray-400 truncate max-w-full mb-2")

                                            with ui.row().classes("w-full justify-between items-center mt-auto"):
                                                ui.button(
                                                    icon="play_arrow",
                                                    on_click=lambda trk=t: player.play_track(trk, sec.tracks),
                                                ).props("flat round dense color=primary").tooltip("Ouvir")

                                                ui.button(
                                                    icon="add",
                                                    on_click=lambda trk=t: add_recommended_track(trk),
                                                ).props("flat round dense color=positive").tooltip("Adicionar à Biblioteca")

                                                if t.id:
                                                    ui.button(
                                                        icon="thumb_down",
                                                        on_click=lambda trk=t: reject_track(trk),
                                                    ).props("flat round dense color=gray").tooltip("Não recomendar mais")

            asyncio.create_task(_async_load())

        def add_recommended_track(track: UnifiedTrack):
            with Session(engine) as session:
                existing = session.exec(select(UnifiedTrack).where(UnifiedTrack.title == track.title, UnifiedTrack.artist == track.artist)).first()
                if not existing:
                    session.add(track)
                    session.commit()
                    discovery_engine.record_event(session, track.id or 0, "added")
                    ui.notify(f"Adicionada: {track.title}", type="positive")
                else:
                    ui.notify(f"'{track.title}' já está na sua biblioteca!", type="info")

        def reject_track(track: UnifiedTrack):
            if track.id:
                with Session(engine) as session:
                    discovery_engine.record_event(session, track.id, "rejected")
                ui.notify(f"'{track.title}' não será mais recomendada.", type="info")
                load_feed()

        load_feed()
