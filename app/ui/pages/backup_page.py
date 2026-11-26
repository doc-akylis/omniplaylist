from pathlib import Path
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import BackupRecord
from app.engines.backup_engine import BackupEngine
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager

backup_engine = BackupEngine()


def render_backup_page():
    """Render the Backup, Integrity Verification and Disaster Recovery hub."""
    with main_layout(current_page="backup"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Backup & Recuperação — Proteção de Dados").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Gere snapshots compactados do banco de dados SQLite com hash SHA256, verifique integridade e restaure com segurança."
                ).classes("text-sm text-gray-400")

            ui.button("Criar Novo Backup Agora", icon="archive", on_click=lambda: run_create_backup()).props("color=primary no-caps")

        backups_container = ui.column().classes("w-full gap-4")

        def load_backups_list():
            backups_container.clear()
            with backups_container:
                with Session(engine) as session:
                    records = session.exec(select(BackupRecord).order_by(BackupRecord.id.desc())).all()

                if not records:
                    with ui.column().classes(f"w-full {card_cls} p-8 items-center text-center"):
                        ui.icon("folder_zip", size="3rem", color="gray")
                        ui.label("Nenhum backup registrado").classes("text-lg font-bold text-white mt-2")
                        ui.label("Clique no botão acima para gerar uma cópia compactada da sua biblioteca.").classes("text-sm text-gray-400")
                    return

                with ui.column().classes(f"w-full {card_cls} gap-3"):
                    ui.label("Histórico de Backups Disponíveis").classes("text-lg font-bold text-white")

                    for rec in records:
                        with ui.row().classes("w-full items-center justify-between p-3 rounded bg-[#202020] border border-[#2E2E2E]"):
                            with ui.row().classes("items-center gap-3"):
                                ui.icon("inventory_2", color="primary")
                                with ui.column().classes("gap-0"):
                                    ui.label(rec.filename).classes("text-sm font-bold text-white")
                                    size_kb = round(rec.file_size_bytes / 1024, 1)
                                    ui.label(
                                        f"Tamanho: {size_kb} KB • Faixas: {rec.track_count} • SHA256: {rec.checksum_sha256[:12]}..."
                                    ).classes("text-xs text-gray-400 font-mono")

                            with ui.row().classes("items-center gap-2"):
                                ui.button(
                                    "Verificar Integridade",
                                    icon="verified",
                                    on_click=lambda r=rec: run_verify(r),
                                ).props("flat dense color=info no-caps")

                                ui.button(
                                    "Restaurar",
                                    icon="restore",
                                    on_click=lambda r=rec: run_restore(r),
                                ).props("color=negative dense no-caps")

        def run_create_backup():
            with Session(engine) as session:
                rec = backup_engine.create_backup(session)
            ui.notify(f"Backup criado com sucesso: {rec.filename}", type="positive")
            load_backups_list()

        def run_verify(rec: BackupRecord):
            valid, msg = backup_engine.verify_backup_integrity(Path(rec.file_path))
            ui.notify(msg, type="positive" if valid else "negative")

        def run_restore(rec: BackupRecord):
            with ui.dialog() as confirm_dialog, ui.card().classes("bg-[#181818] border border-[#333] text-white p-6"):
                ui.label("Confirmar Restauração").classes("text-lg font-bold text-negative")
                ui.label(
                    f"Atenção: A restauração substituirá a base de dados atual pelo backup '{rec.filename}'. "
                    "Uma cópia de segurança do estado atual será feita automaticamente antes da restauração."
                ).classes("text-sm text-gray-300 mb-4")

                with ui.row().classes("w-full justify-end gap-3"):
                    ui.button("Cancelar", on_click=confirm_dialog.close).props("flat color=white")
                    ui.button("Sim, Restaurar", color="negative", on_click=lambda: do_restore(rec, confirm_dialog)).props("no-caps")
            confirm_dialog.open()

        def do_restore(rec: BackupRecord, dialog):
            dialog.close()
            success, msg = backup_engine.restore_backup(Path(rec.file_path))
            ui.notify(msg, type="positive" if success else "negative")
            load_backups_list()

        load_backups_list()
