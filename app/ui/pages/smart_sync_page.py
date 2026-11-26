from pathlib import Path
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import Playlist, UnifiedTrack
from app.engines.device_sync import DeviceSyncEngine, SyncPlanPreview
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager

sync_engine = DeviceSyncEngine()


def render_smart_sync_page():
    """Render the Smart Sync device manager with pre-flight storage audit and safe sync execution."""
    with main_layout(current_page="smart_sync"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Smart Sync — Sincronização Inteligente de Dispositivos").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Sincronize pen drives, centrais automotivas e players portáteis com auditoria prévia de espaço e segurança FAT32."
                ).classes("text-sm text-gray-400")

        # Two-column layout: Left Settings, Right Storage Preview
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            # Configuration Card
            with ui.column().classes(f"flex-1 {card_cls} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("usb", color="primary")
                    ui.label("Configuração do Dispositivo").classes("text-lg font-bold text-white")

                with Session(engine) as session:
                    playlists = session.exec(select(Playlist)).all()
                    pl_options = {0: "Todas as Músicas Salvas", **{p.id: p.name for p in playlists}}

                pl_select = ui.select(pl_options, value=list(pl_options.keys())[0], label="Playlist a Sincronizar").props("dark outlined dense")

                target_dir_input = ui.input(
                    label="Diretório de Destino / Letra do Pen Drive",
                    value="./downloads/usb_device_test",
                ).props("dark outlined dense")

                profile_select = ui.select(
                    ["Som Automotivo (FAT32 Naming)", "DJ / Rekordbox", "Biblioteca Portátil", "Pasta Simples"],
                    value="Som Automotivo (FAT32 Naming)",
                    label="Perfil de Sincronização",
                ).props("dark outlined dense")

                delete_orphans_cb = ui.checkbox("Excluir arquivos do dispositivo que não estão na playlist", value=False).props("dark color=negative")

                plan_btn = ui.button("Gerar Prévia de Sincronização", icon="calculate").props("color=primary no-caps").classes("w-full mt-2")

            # Preview Summary Card
            preview_card = ui.column().classes(f"flex-1 {card_cls} gap-4")

            current_plan: list[SyncPlanPreview] = []

            def calculate_plan():
                current_plan.clear()
                target_path = Path(target_dir_input.value)

                with Session(engine) as session:
                    if pl_select.value == 0:
                        tracks = session.exec(select(UnifiedTrack)).all()
                        p_name = "Biblioteca Completa"
                    else:
                        pl = session.get(Playlist, pl_select.value)
                        tracks = pl.tracks if pl else []
                        p_name = pl.name if pl else "Playlist"

                plan = sync_engine.generate_sync_plan(tracks, target_path)
                current_plan.append(plan)

                preview_card.clear()
                with preview_card:
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("analytics", color="accent")
                        ui.label("Prévia da Operação & Espaço").classes("text-lg font-bold text-white")

                    # Stats Row
                    with ui.row().classes("w-full gap-2 text-xs"):
                        mb_needed = round(plan.total_bytes_needed / (1024 * 1024), 1)
                        mb_available = round(plan.available_bytes_on_device / (1024 * 1024), 1)

                        with ui.column().classes("flex-1 p-2 bg-[#202020] rounded border border-[#333]"):
                            ui.label("Novos a Copiar").classes("text-gray-400")
                            ui.label(f"{plan.new_to_copy_count} faixas ({mb_needed} MB)").classes("text-white font-bold")

                        with ui.column().classes("flex-1 p-2 bg-[#202020] rounded border border-[#333]"):
                            ui.label("Já Sincronizados").classes("text-gray-400")
                            ui.label(f"{plan.already_synced_count} faixas").classes("text-positive font-bold")

                        with ui.column().classes("flex-1 p-2 bg-[#202020] rounded border border-[#333]"):
                            ui.label("Espaço Disponível").classes("text-gray-400")
                            ui.label(f"{mb_available} MB").classes("text-info font-bold")

                    if not plan.has_sufficient_space:
                        ui.label("ALERTA: Espaço insuficiente no dispositivo de destino!").classes("text-xs text-negative font-bold")

                    ui.label(f"Arquivos extras/órfãos encontrados no dispositivo: {plan.orphan_files_count}").classes("text-xs text-gray-400")

                    ui.button(
                        f"Executar Sincronização ({plan.new_to_copy_count} arquivos)",
                        icon="sync",
                        on_click=lambda: run_execution(plan, p_name),
                    ).props("color=accent no-caps text-color=black").classes("w-full mt-2")

            def run_execution(plan: SyncPlanPreview, p_name: str):
                stats = sync_engine.execute_sync(plan, playlist_name=p_name, delete_orphans=delete_orphans_cb.value)
                ui.notify(
                    f"Sincronização concluída com sucesso! {stats['copied']} copiados, {stats['skipped']} mantidos, {stats['deleted_orphans']} excluídos.",
                    type="positive",
                )
                calculate_plan()

            plan_btn.on("click", calculate_plan)
            calculate_plan()
