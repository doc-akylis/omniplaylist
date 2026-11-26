from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import Playlist, PlaylistTrackLink, UnifiedTrack
from app.engines.ai_curator import AICurator
from app.engines.audio_analyzer import AudioAnalyzer
from app.engines.genre_engine import GenreEngine
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme import CARD_STYLE

genre_engine = GenreEngine()
ai_curator = AICurator()
audio_analyzer = AudioAnalyzer()


def render_genre_studio_page():
    """Render the Genre Studio visual playlist generator and AI Prompt DJ."""
    with main_layout(current_page="genres"):
        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Genre Studio & Smart AI DJ").classes("text-3xl font-bold text-white tracking-tight")
                ui.label("Explore a árvore taxonômica ou crie playlists geradas por linguagem natural.").classes(
                    "text-sm text-gray-400"
                )

        # AI Prompt DJ Box
        with ui.column().classes(f"w-full {CARD_STYLE} mb-6 gap-3 border-primary"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("auto_awesome", color="primary", size="md")
                ui.label("Smart DJ — Gerador por Prompt de IA").classes("text-xl font-bold text-white")

            ui.label(
                "Descreva a playlist que deseja (ex: 'rock animado anos 80 com mais de 125 bpm para correr' ou 'synthwave relaxante para programar')."
            ).classes("text-xs text-gray-400")

            with ui.row().classes("w-full items-center gap-3"):
                prompt_input = ui.input(
                    placeholder="Digite seu pedido em linguagem natural...",
                    value="indie rock animado para treino",
                ).props("dark outlined dense").classes("flex-1")

                harmonic_toggle = ui.checkbox("Ordenar por Mix Harmônico DJ (Camelot / BPM)", value=True).props(
                    "dark color=primary"
                )

                ui.button(
                    "Gerar Playlist",
                    icon="bolt",
                    on_click=lambda: generate_ai_playlist(prompt_input.value, harmonic_toggle.value),
                ).props("color=primary no-caps")

        # Two-column layout: Left taxonomy tree, Right recent generated playlists
        with ui.row().classes("w-full gap-6 items-start"):
            # Left: Genre Hierarchy Tree
            with ui.column().classes("flex-[2] gap-4"):
                ui.label("Árvore Taxonômica da Biblioteca").classes("text-lg font-semibold text-white")

                with Session(engine) as session:
                    tracks = session.exec(select(UnifiedTrack)).all()

                tree_data = genre_engine.build_genre_tree(tracks)

                if not tree_data:
                    with ui.column().classes(f"w-full {CARD_STYLE} p-4"):
                        ui.label("Adicione faixas na Biblioteca para visualizar a taxonomia calculada.").classes(
                            "text-sm text-gray-400"
                        )
                else:
                    for parent_genre, data in tree_data.items():
                        count = data["tracks_count"]
                        with ui.expansion(f"{parent_genre} ({count} faixas)", icon="album").classes(
                            "w-full bg-[#181818] rounded-xl border border-[#2A2A2A] text-white"
                        ):
                            with ui.row().classes("gap-2 p-3 flex-wrap"):
                                for subgenre, subtracks in data["subgenres"].items():
                                    ui.chip(
                                        f"{subgenre} ({len(subtracks)})",
                                        icon="label",
                                        selectable=False,
                                        color="secondary",
                                    ).props("dark")

            # Right: Playlists in database
            with ui.column().classes(f"flex-1 {CARD_STYLE} gap-4"):
                ui.label("Playlists Salvas").classes("text-lg font-semibold text-white")

                with Session(engine) as session:
                    playlists = session.exec(select(Playlist)).all()
                    playlists_data = [
                        {"name": pl.name, "source_provider": pl.source_provider, "count": len(pl.tracks)}
                        for pl in playlists
                    ]

                if not playlists_data:
                    ui.label("Nenhuma playlist gerada ainda.").classes("text-sm text-gray-400")
                else:
                    for pl in playlists_data:
                        with ui.column().classes("w-full p-2 bg-[#222] rounded-lg border border-[#333] gap-1"):
                            ui.label(pl["name"]).classes("text-sm font-bold text-white")
                            ui.label(f"Origem: {pl['source_provider']} • {pl['count']} faixas").classes(
                                "text-xs text-gray-400"
                            )


def generate_ai_playlist(prompt_text: str, harmonic_sort: bool):
    """Execute AI curation and save new playlist to database."""
    if not prompt_text:
        ui.notify("Digite um prompt para gerar a playlist", type="warning")
        return

    with Session(engine) as session:
        catalog = session.exec(select(UnifiedTrack)).all()
        if not catalog:
            ui.notify("Sua biblioteca está vazia. Adicione faixas antes de gerar uma playlist.", type="warning")
            return

        selected_tracks = ai_curator.build_playlist(prompt_text, catalog, limit=20)

        if harmonic_sort:
            selected_tracks = audio_analyzer.sort_playlist_for_dj(selected_tracks)

        # Create new Playlist entity
        new_playlist = Playlist(
            name=f"Smart DJ: {prompt_text[:35]}",
            description=f"Gerada via IA por prompt '{prompt_text}' com mixagem harmônica={harmonic_sort}",
            source_provider="ai_curator",
        )
        session.add(new_playlist)
        session.commit()
        session.refresh(new_playlist)

        # Link tracks with position
        for pos, t in enumerate(selected_tracks):
            link = PlaylistTrackLink(playlist_id=new_playlist.id, track_id=t.id, position=pos)
            session.add(link)

        session.commit()

        ui.notify(
            f"Playlist '{new_playlist.name}' criada com {len(selected_tracks)} faixas!",
            type="positive",
        )
        ui.navigate.to("/genres")
