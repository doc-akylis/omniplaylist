import asyncio
from pathlib import Path
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.audio_quality import AudioQualityEngine, QualityProfile
from app.engines.downloader import TrackDownloader
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager

audio_quality = AudioQualityEngine()
downloader = TrackDownloader()


def render_download_studio_page():
    """Render the Download Studio with audio quality profile management and queue inspection."""
    with main_layout(current_page="download_studio"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Download Studio & Perfis de Áudio").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Gerencie a qualidade real dos downloads com perfis automotivos, DJ lossless e auditoria anti-upscaling."
                ).classes("text-sm text-gray-400")

        # Two-column layout: Left Profiles, Right Download Action
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            # Left: Profiles Selection
            with ui.column().classes(f"flex-1 {card_cls} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("tune", color="primary")
                    ui.label("Perfis Predefinidos de Qualidade").classes("text-lg font-bold text-white")

                profiles = [
                    QualityProfile.CAR_STEREO,
                    QualityProfile.DJ_REKORDBOX,
                    QualityProfile.ARCHIVE_LOSSLESS,
                    QualityProfile.DAILY_USE,
                ]

                selected_profile_name = ui.radio(
                    [p["name"] for p in profiles],
                    value=QualityProfile.CAR_STEREO["name"],
                ).props("dark")

                profile_info_box = ui.column().classes("w-full bg-[#202020] p-3 rounded-lg border border-[#2E2E2E]")

                def update_profile_info():
                    profile_info_box.clear()
                    chosen = next((p for p in profiles if p["name"] == selected_profile_name.value), profiles[0])
                    with profile_info_box:
                        ui.label(f"Formato: {chosen['format'].upper()} • Bitrate: {chosen['bitrate']}").classes("text-xs text-primary font-bold")
                        ui.label(chosen["description"]).classes("text-xs text-gray-300 mt-1")

                selected_profile_name.on("update:model-value", update_profile_info)
                update_profile_info()

            # Right: Download Form
            with ui.column().classes(f"flex-1 {card_cls} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("cloud_download", color="accent")
                    ui.label("Baixar Faixa ou Link").classes("text-lg font-bold text-white")

                search_query_input = ui.input(
                    label="Nome da Música / Artista ou Link do YouTube",
                    placeholder="Ex: Daft Punk - One More Time",
                ).props("dark outlined dense")

                # Quality honesty alert
                with ui.row().classes("w-full p-2 bg-[#251D12] rounded border border-[#6B4B18] items-center gap-2"):
                    ui.icon("warning", color="warning", size="sm")
                    ui.label(
                        "Garantia de Qualidade Real: Se o áudio de origem for inferior a 320k, o sistema registrará a qualidade real e nunca afirmará que uma conversão artificial recupera frequências perdidas."
                    ).classes("text-[11px] text-[#FBBF24] leading-tight")

                start_btn = ui.button("Iniciar Download na Fila", icon="download").props("color=primary no-caps").classes("w-full mt-2")

        # Active Queue Container
        with ui.column().classes(f"w-full {card_cls} gap-3"):
            with ui.row().classes("w-full justify-between items-center"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("hourglass_top", color="info")
                    ui.label("Fila de Processamento de Áudio").classes("text-lg font-bold text-white")
                ui.badge("Monitor Ativo", color="positive").props("outline")

            queue_items_col = ui.column().classes("w-full gap-2")

            def add_to_queue():
                q = search_query_input.value
                if not q:
                    ui.notify("Digite uma música ou link para baixar", type="warning")
                    return

                with queue_items_col:
                    with ui.row().classes("w-full items-center justify-between p-3 rounded bg-[#202020] border border-[#2E2E2E]"):
                        with ui.column().classes("gap-0"):
                            ui.label(q).classes("text-sm font-bold text-white")
                            ui.label(f"Perfil solicitado: {selected_profile_name.value}").classes("text-xs text-primary")

                        with ui.row().classes("items-center gap-3"):
                            ui.spinner(size="sm", color="primary")
                            ui.label("Baixando & Processando...").classes("text-xs text-gray-300")

                async def _run():
                    t = UnifiedTrack(title=q, artist="Download Manual")
                    res = await downloader.download_track(t)
                    if res:
                        ui.notify(f"Download concluído: {q}", type="positive")

                asyncio.create_task(_run())

            start_btn.on("click", add_to_queue)
