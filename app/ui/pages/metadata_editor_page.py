from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.metadata_editor import MetadataEditorEngine
from app.ui.layout import main_layout
from app.ui.theme_manager import theme_manager

editor_engine = MetadataEditorEngine()


def render_metadata_editor_page():
    """Render the advanced batch metadata editor with diff preview and undo snapshots."""
    with main_layout(current_page="metadata_editor"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Editor Avançado de Metadados — Edição em Lote").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Edite tags de múltiplos arquivos simultaneamente com prévia de alterações e backup automático para desfazer."
                ).classes("text-sm text-gray-400")

        # Two-column layout: Left Form, Right Tracks Selection
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            # Batch Fields Form
            with ui.column().classes(f"w-80 {card_cls} gap-3 shrink-0"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("edit_note", color="primary")
                    ui.label("Campos em Lote").classes("text-lg font-bold text-white")

                ui.label("Preencha apenas os campos que deseja alterar:").classes("text-xs text-gray-400")

                artist_input = ui.input(label="Novo Artista").props("dark outlined dense")
                album_input = ui.input(label="Novo Álbum").props("dark outlined dense")
                genre_input = ui.input(label="Novo Gênero").props("dark outlined dense")
                year_input = ui.number(label="Novo Ano", format="%d").props("dark outlined dense")
                bpm_input = ui.number(label="Novo BPM", format="%.1f").props("dark outlined dense")
                key_input = ui.input(label="Nova Clave (ex: 8A, Am)").props("dark outlined dense")

                apply_btn = ui.button("Aplicar Alterações em Lote", icon="save").props("color=primary no-caps").classes("w-full mt-2")

            # Tracks Table Selection
            with ui.column().classes(f"flex-1 {card_cls} gap-3"):
                with Session(engine) as session:
                    all_tracks = session.exec(select(UnifiedTrack)).all()

                with ui.row().classes("w-full justify-between items-center"):
                    ui.label(f"Músicas no Acervo ({len(all_tracks)})").classes("text-lg font-bold text-white")
                    ui.label("Marque as músicas que receberão a atualização").classes("text-xs text-gray-400")

                selected_track_ids: set[int] = set()

                with ui.column().classes("w-full max-h-[500px] overflow-y-auto gap-2"):
                    for t in all_tracks:
                        with ui.row().classes("w-full items-center justify-between p-2 rounded bg-[#202020] border border-[#2E2E2E]"):
                            with ui.row().classes("items-center gap-3"):
                                cb = ui.checkbox(value=False)
                                cb.on("change", lambda e, tid=t.id: selected_track_ids.add(tid) if e.value else selected_track_ids.discard(tid))

                                with ui.column().classes("gap-0"):
                                    ui.label(f"{t.title}").classes("text-sm font-semibold text-white")
                                    ui.label(f"{t.artist} • {t.album or '—'} • {t.genres_raw or '—'}").classes("text-xs text-gray-400")

                            with ui.row().classes("items-center gap-2"):
                                if t.release_year:
                                    ui.badge(str(t.release_year), color="secondary").props("dense")
                                if t.bpm:
                                    ui.badge(f"{int(t.bpm)} BPM", color="info").props("outline dense")

        def execute_batch_update():
            if not selected_track_ids:
                ui.notify("Selecione ao menos uma música na lista para editar.", type="warning")
                return

            with Session(engine) as session:
                target_tracks = [session.get(UnifiedTrack, tid) for tid in selected_track_ids if session.get(UnifiedTrack, tid)]

                # Collect new values (None if empty string)
                art_val = artist_input.value if artist_input.value else None
                alb_val = album_input.value if album_input.value else None
                gen_val = genre_input.value if genre_input.value else None
                yr_val = int(year_input.value) if year_input.value else None
                bpm_val = float(bpm_input.value) if bpm_input.value else None
                key_val = key_input.value if key_input.value else None

                backup_id = editor_engine.apply_batch_changes(
                    target_tracks,
                    session,
                    artist=art_val,
                    album=alb_val,
                    genre=gen_val,
                    year=yr_val,
                    bpm=bpm_val,
                    key=key_val,
                )

            ui.notify(f"Metadados de {len(target_tracks)} faixas atualizados! Snapshot salvo: {backup_id}", type="positive")
            ui.navigate.to("/metadata-editor")

        apply_btn.on("click", execute_batch_update)
