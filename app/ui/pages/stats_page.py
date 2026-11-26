from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.analytics_engine import AnalyticsEngine
from app.ui.layout import main_layout
from app.ui.theme import CARD_STYLE

analytics = AnalyticsEngine()


def render_stats_page():
    """Render the OmniStats analytics and personal wrapped dashboard."""
    with main_layout(current_page="stats"):
        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("OmniStats — Análise da Biblioteca").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label("Estatísticas completas, décadas musicais, distribuição de gêneros e métricas de acervo.").classes(
                    "text-sm text-gray-400"
                )

        # Fetch all tracks from SQLite
        with Session(engine) as session:
            tracks = session.exec(select(UnifiedTrack)).all()

        stats = analytics.generate_stats(tracks)

        # Overview Stats Top Row
        with ui.row().classes("w-full gap-4 mb-6"):
            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Acervo Total").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(f"{stats['total_tracks']} faixas").classes("text-2xl font-bold text-white")

            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Tempo de Reprodução").classes("text-xs text-gray-400 uppercase font-semibold")
                hours = round(stats["total_duration_minutes"] / 60, 1)
                ui.label(f"{hours} horas").classes("text-2xl font-bold text-primary")

            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Média de Andamento").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(f"{stats['average_bpm']} BPM").classes("text-2xl font-bold text-info")

            with ui.column().classes(f"{CARD_STYLE} flex-1"):
                ui.label("Cobertura Offline").classes("text-xs text-gray-400 uppercase font-semibold")
                ui.label(f"{stats['offline_percentage']}%").classes("text-2xl font-bold text-accent")

        # Two-column layout: Top Artists & Genre Distribution
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            # Top Artists Card
            with ui.column().classes(f"flex-1 {CARD_STYLE} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("star", color="primary")
                    ui.label("Artistas Mais Frequentes").classes("text-lg font-bold text-white")

                if not stats["top_artists"]:
                    ui.label("Nenhum artista registrado ainda.").classes("text-sm text-gray-400")
                else:
                    for rank, (artist, count) in enumerate(stats["top_artists"], 1):
                        with ui.row().classes("w-full items-center justify-between py-1 border-b border-[#252525]"):
                            with ui.row().classes("items-center gap-2"):
                                ui.badge(str(rank), color="primary").props("dense")
                                ui.label(artist).classes("text-sm font-semibold text-white")
                            ui.label(f"{count} faixas").classes("text-xs text-gray-400")

            # Genre Distribution Card
            with ui.column().classes(f"flex-1 {CARD_STYLE} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("category", color="accent")
                    ui.label("Distribuição por Macro-Gênero").classes("text-lg font-bold text-white")

                if not stats["genre_distribution"]:
                    ui.label("Gêneros ainda não classificados.").classes("text-sm text-gray-400")
                else:
                    max_genre_val = max(stats["genre_distribution"].values()) if stats["genre_distribution"] else 1
                    for genre, count in stats["genre_distribution"].items():
                        with ui.column().classes("w-full gap-1"):
                            with ui.row().classes("w-full justify-between text-xs"):
                                ui.label(genre).classes("text-white font-medium")
                                ui.label(f"{count}").classes("text-gray-400")
                            ui.linear_progress(
                                value=count / max_genre_val,
                                show_value=False,
                                color="accent",
                            ).props("rounded size=6px")

        # Decades Distribution Row
        with ui.column().classes(f"w-full {CARD_STYLE} gap-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("history", color="info")
                ui.label("Linha do Tempo das Músicas (Décadas)").classes("text-lg font-bold text-white")

            with ui.row().classes("w-full gap-4 flex-wrap mt-2"):
                for decade, count in sorted(stats["decade_distribution"].items()):
                    with ui.column().classes("items-center p-3 rounded-lg bg-[#222] min-w-[90px] border border-[#333]"):
                        ui.label(decade).classes("text-sm font-bold text-white")
                        ui.label(f"{count} músicas").classes("text-xs text-primary")
