import asyncio
from pathlib import Path
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.audio_quality import AudioQualityEngine
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager

inspector_engine = AudioQualityEngine()


def render_audio_inspector_page():
    """Render the Audio Inspector technical library diagnostics dashboard."""
    with main_layout(current_page="audio_inspector"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Audio Inspector — Análise Técnica da Biblioteca").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Auditoria profunda de integridade, codecs reais, bitrates, clipping e detecção de upscaling artificial."
                ).classes("text-sm text-gray-400")

            with ui.row().classes("gap-2"):
                run_scan_btn = ui.button("Executar Varredura Básica", icon="troubleshoot").props("color=primary no-caps")
                run_tech_analysis_btn = ui.button(
                    "Análise Técnica FFmpeg (Completa)", icon="analytics"
                ).props("color=accent no-caps text-color=black")

        # Progress area for technical analysis
        progress_area = ui.column().classes("w-full gap-3")
        progress_bar = ui.linear_progress(value=0, show_value=False).props("color=primary").classes("w-full hidden")
        progress_label = ui.label("").classes("text-sm text-gray-400 hidden")

        # Container for inspection results
        results_area = ui.column().classes("w-full gap-6")

        async def run_tech_analysis():
            """Run full FFmpeg/ffprobe technical analysis on all local tracks."""
            progress_area.clear()
            results_area.clear()

            # Show progress UI
            progress_bar.props(remove="hidden")
            progress_label.props(remove="hidden")
            progress_bar.value = 0
            progress_label.set_text("Iniciando análise técnica...")

            with progress_area:
                ui.spinner(size="lg", color="accent")
                ui.label("Analisando biblioteca com FFmpeg/ffprobe (single-pass)...").classes("text-sm text-gray-400")

            # Call API endpoint
            from app.api.routes import tech_engine, ws_manager

            def progress_cb(current: int, total: int, msg: str):
                pct = current / total if total > 0 else 0
                progress_bar.value = pct
                progress_label.set_text(f"{msg} ({current}/{total})")

            stats = await tech_engine.analyze_library(
                session_factory=lambda: Session(engine),
                progress_callback=progress_cb,
                force=False,
            )

            progress_bar.props(add="hidden")
            progress_label.props(add="hidden")

            # Show results
            with progress_area:
                ui.label("Análise técnica concluída!").classes("text-sm text-positive")
                with ui.row().classes("gap-4 text-sm"):
                    ui.badge(f"Analisados: {stats['analyzed']}", color="positive")
                    ui.badge(f"Pulados: {stats['skipped']}", color="warning")
                    ui.badge(f"Erros: {stats['errors']}", color="negative" if stats['errors'] > 0 else "secondary")

            # Re-run basic inspection to show updated data
            run_inspection()

        def run_inspection():
            results_area.clear()
            with results_area:
                ui.spinner(size="lg", color="primary")

            with Session(engine) as session:
                tracks = session.exec(select(UnifiedTrack)).all()

            report = inspector_engine.scan_library_quality(tracks)

            # Also compute advanced stats from persisted technical analysis
            advanced_stats = compute_advanced_stats(tracks)

            results_area.clear()
            with results_area:
                # Top Stat Badges - Basic
                with ui.row().classes("w-full gap-4"):
                    with ui.column().classes(f"{card_cls} flex-1"):
                        ui.label("Arquivos Analisados").classes("text-xs text-gray-400 uppercase font-semibold")
                        ui.label(str(report["total_analyzed"])).classes("text-2xl font-bold text-white")

                    with ui.column().classes(f"{card_cls} flex-1"):
                        ui.label("Arquivos Íntegros").classes("text-xs text-gray-400 uppercase font-semibold")
                        ui.label(str(report["valid_files"])).classes("text-2xl font-bold text-positive")

                    with ui.column().classes(f"{card_cls} flex-1"):
                        ui.label("Arquivos Suspeitos (Upscale/Inconsistência)").classes("text-xs text-gray-400 uppercase font-semibold")
                        ui.label(str(report["suspect_files"])).classes("text-2xl font-bold text-warning")

                    with ui.column().classes(f"{card_cls} flex-1"):
                        ui.label("Arquivos Corrompidos / Falhas").classes("text-xs text-gray-400 uppercase font-semibold")
                        ui.label(str(report["corrupted_files"])).classes("text-2xl font-bold text-negative")

                # Advanced Technical Analysis Stats
                if advanced_stats["tracks_with_analysis"] > 0:
                    with ui.row().classes("w-full gap-4 mt-4"):
                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("Com Análise Técnica FFmpeg").classes("text-xs text-gray-400 uppercase font-semibold")
                            ui.label(str(advanced_stats["tracks_with_analysis"])).classes("text-2xl font-bold text-primary")

                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("True Peak Médio (dBFS)").classes("text-xs text-gray-400 uppercase font-semibold")
                            color = "positive" if advanced_stats["avg_true_peak"] <= -1.0 else "warning"
                            ui.label(f"{advanced_stats['avg_true_peak']:.1f}").classes(f"text-2xl font-bold text-{color}")

                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("Dynamic Range Médio (dB)").classes("text-xs text-gray-400 uppercase font-semibold")
                            color = "positive" if advanced_stats["avg_dynamic_range"] >= 8 else "warning"
                            ui.label(f"{advanced_stats['avg_dynamic_range']:.1f}").classes(f"text-2xl font-bold text-{color}")

                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("Crest Factor Médio (dB)").classes("text-xs text-gray-400 uppercase font-semibold")
                            ui.label(f"{advanced_stats['avg_crest_factor']:.1f}").classes("text-2xl font-bold text-white")

                    with ui.row().classes("w-full gap-4"):
                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("LRA Médio (LU)").classes("text-xs text-gray-400 uppercase font-semibold")
                            ui.label(f"{advanced_stats['avg_lra']:.1f}").classes("text-2xl font-bold text-white")

                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("Faixas com Clipping").classes("text-xs text-gray-400 uppercase font-semibold")
                            color = "negative" if advanced_stats["clipping_tracks"] > 0 else "positive"
                            ui.label(str(advanced_stats["clipping_tracks"])).classes(f"text-2xl font-bold text-{color}")

                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("Silêncio Inicial Médio (ms)").classes("text-xs text-gray-400 uppercase font-semibold")
                            ui.label(f"{advanced_stats['avg_silence_start']:.0f}").classes("text-2xl font-bold text-white")

                        with ui.column().classes(f"{card_cls} flex-1"):
                            ui.label("LUFS Integrado Médio").classes("text-xs text-gray-400 uppercase font-semibold")
                            ui.label(f"{advanced_stats['avg_integrated_lufs']:.1f}").classes("text-2xl font-bold text-white")

                # Codec & Bitrate Distributions Row
                with ui.row().classes("w-full gap-6 items-start"):
                    # Codec breakdown
                    with ui.column().classes(f"flex-1 {card_cls} gap-3"):
                        ui.label("Distribuição Real por Codec").classes("text-sm font-bold text-white")
                        if not report["codec_distribution"]:
                            ui.label("Nenhum arquivo local identificado.").classes("text-xs text-gray-400")
                        else:
                            for c_name, c_count in report["codec_distribution"].items():
                                with ui.row().classes("w-full justify-between text-xs py-1 border-b border-[#2A2A2A]"):
                                    ui.label(c_name).classes("text-white font-medium")
                                    ui.badge(f"{c_count} faixas", color="secondary").props("dense")

                    # Bitrate breakdown
                    with ui.column().classes(f"flex-1 {card_cls} gap-3"):
                        ui.label("Distribuição por Qualidade de Bitrate").classes("text-sm font-bold text-white")
                        for b_label, b_count in report["bitrate_distribution"].items():
                            with ui.row().classes("w-full justify-between text-xs py-1 border-b border-[#2A2A2A]"):
                                ui.label(b_label).classes("text-white font-medium")
                                ui.badge(f"{b_count} faixas", color="primary" if "320" in b_label or "Lossless" in b_label else "secondary").props("dense")

                # Actionable Issues List
                with ui.column().classes(f"w-full {card_cls} gap-3"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("report_problem", color="warning")
                        ui.label("Arquivos que Requerem Atenção").classes("text-lg font-bold text-white")

                    if not report["issues"]:
                        with ui.row().classes("items-center gap-2 text-positive text-sm py-4"):
                            ui.icon("verified")
                            ui.label("Excelente! Nenhum arquivo corrompido ou inconsistente detectado na biblioteca.")
                    else:
                        for issue in report["issues"]:
                            with ui.row().classes("w-full items-center justify-between p-3 rounded bg-[#202020] border border-[#2E2E2E]"):
                                with ui.column().classes("gap-0"):
                                    ui.label(f"{issue['title']} — {issue['artist']}").classes("text-sm font-bold text-white")
                                    ui.label(issue["details"]).classes("text-xs text-gray-400")

                                ui.badge(issue["type"], color="negative" if issue["type"] == "Corrompido" else "warning").props("dense")

        def compute_advanced_stats(tracks: list[UnifiedTrack]) -> dict:
            """Compute advanced statistics from persisted technical analysis data."""
            tracks_with_analysis = [t for t in tracks if t.analyzed_at is not None]
            count = len(tracks_with_analysis)

            if count == 0:
                return {
                    "tracks_with_analysis": 0,
                    "avg_true_peak": 0.0,
                    "avg_dynamic_range": 0.0,
                    "avg_crest_factor": 0.0,
                    "avg_lra": 0.0,
                    "clipping_tracks": 0,
                    "avg_silence_start": 0.0,
                    "avg_integrated_lufs": 0.0,
                }

            true_peaks = [t.true_peak_dbfs for t in tracks_with_analysis if t.true_peak_dbfs is not None]
            dyn_ranges = [t.dynamic_range_db for t in tracks_with_analysis if t.dynamic_range_db is not None]
            crest_factors = [t.crest_factor_db for t in tracks_with_analysis if t.crest_factor_db is not None]
            lras = [t.loudness_range_lu for t in tracks_with_analysis if t.loudness_range_lu is not None]
            silence_starts = [t.silence_start_ms for t in tracks_with_analysis if t.silence_start_ms is not None]
            integrated_lufs = [t.integrated_lufs for t in tracks_with_analysis if t.integrated_lufs is not None]
            clipping_tracks = sum(1 for t in tracks_with_analysis if t.clipping_count and t.clipping_count > 0)

            return {
                "tracks_with_analysis": count,
                "avg_true_peak": sum(true_peaks) / len(true_peaks) if true_peaks else 0.0,
                "avg_dynamic_range": sum(dyn_ranges) / len(dyn_ranges) if dyn_ranges else 0.0,
                "avg_crest_factor": sum(crest_factors) / len(crest_factors) if crest_factors else 0.0,
                "avg_lra": sum(lras) / len(lras) if lras else 0.0,
                "clipping_tracks": clipping_tracks,
                "avg_silence_start": sum(silence_starts) / len(silence_starts) if silence_starts else 0.0,
                "avg_integrated_lufs": sum(integrated_lufs) / len(integrated_lufs) if integrated_lufs else 0.0,
            }

        run_scan_btn.on("click", run_inspection)
        run_tech_analysis_btn.on("click", run_tech_analysis)
        # Run basic inspection automatically on open
        run_inspection()