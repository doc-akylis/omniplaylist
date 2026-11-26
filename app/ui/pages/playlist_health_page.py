import asyncio
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.playlist_health import HealthReport, PlaylistHealthEngine
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager

health_engine = PlaylistHealthEngine()


def render_playlist_health_page():
    """Render the Playlist Health audit and batch repair center."""
    with main_layout(current_page="playlist_health"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Playlist Health — Auditoria & Reparos").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Identifique faixas com metadados incompletos, capas ausentes, arquivos órfãos e aplique correções em lote."
                ).classes("text-sm text-gray-400")

            ui.button("Executar Diagnóstico", icon="health_and_safety", on_click=lambda: run_audit()).props("color=primary no-caps")

        report_area = ui.column().classes("w-full gap-6")

        def run_audit():
            report_area.clear()
            with report_area:
                ui.spinner(size="lg", color="primary")

            with Session(engine) as session:
                tracks = session.exec(select(UnifiedTrack)).all()

            report: HealthReport = health_engine.audit_tracks(tracks)

            report_area.clear()
            with report_area:
                # Top Score and Batch Fixes Banner
                with ui.row().classes(f"w-full {card_cls} justify-between items-center"):
                    with ui.row().classes("items-center gap-4"):
                        ui.circular_progress(
                            value=report.health_score / 100.0,
                            show_value=True,
                            color="positive" if report.health_score >= 80 else "warning" if report.health_score >= 50 else "negative",
                            size="64px",
                        )
                        with ui.column().classes("gap-0"):
                            ui.label(f"Pontuação de Saúde: {report.health_score}%").classes("text-xl font-bold text-white")
                            ui.label(f"{len(report.issues)} problemas identificados em {report.total_tracks_checked} faixas.").classes(
                                "text-xs text-gray-400"
                            )

                    # Batch Fix Actions
                    with ui.row().classes("gap-2 flex-wrap"):
                        ui.button(
                            "Buscar Capas HD",
                            icon="image",
                            on_click=lambda: run_batch_fix_covers(tracks),
                        ).props("color=primary dense no-caps")

                        ui.button(
                            "Limpar Vínculos Órfãos",
                            icon="link_off",
                            on_click=lambda: run_batch_clear_paths(tracks),
                        ).props("color=secondary dense no-caps")

                # Issues Table
                with ui.column().classes(f"w-full {card_cls} gap-3"):
                    ui.label("Diagnóstico Detalhado por Faixa").classes("text-lg font-bold text-white")

                    if not report.issues:
                        with ui.row().classes("items-center gap-2 text-positive text-sm py-4"):
                            ui.icon("check_circle")
                            ui.label("Parabéns! Sua biblioteca e playlists estão 100% íntegras e completas.")
                    else:
                        for issue in report.issues:
                            with ui.row().classes("w-full items-center justify-between p-3 rounded bg-[#202020] border border-[#2E2E2E]"):
                                with ui.row().classes("items-center gap-3"):
                                    badge_color = "negative" if issue.severity == "error" else "warning" if issue.severity == "warning" else "info"
                                    ui.badge(issue.category.replace("_", " ").upper(), color=badge_color).props("dense")
                                    with ui.column().classes("gap-0"):
                                        ui.label(f"{issue.track_title} — {issue.track_artist}").classes("text-sm font-semibold text-white")
                                        ui.label(issue.description).classes("text-xs text-gray-400")

                                with ui.column().classes("items-end gap-0"):
                                    ui.label(f"Sugestão: {issue.suggested_action}").classes("text-xs text-primary")

        def run_batch_fix_covers(tracks: list[UnifiedTrack]):
            async def _do_fix():
                ui.notify("Iniciando busca em lote de capas HD...", type="info")
                with Session(engine) as session:
                    fixed = await health_engine.fix_missing_covers_batch(tracks, session)
                ui.notify(f"{fixed} capas atualizadas com sucesso!", type="positive")
                run_audit()

            asyncio.create_task(_do_fix())

        def run_batch_clear_paths(tracks: list[UnifiedTrack]):
            with Session(engine) as session:
                cleared = health_engine.remove_broken_paths_batch(tracks, session)
            ui.notify(f"{cleared} caminhos de arquivos inexistentes foram limpos.", type="info")
            run_audit()

        run_audit()
