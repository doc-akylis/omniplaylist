import asyncio
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import Playlist, PlaylistTrackLink, UnifiedTrack
from app.engines.ai_curator import AICurator, SmartDJFilter, SmartDJResult
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme_manager import theme_manager

curator = AICurator()


def render_smart_dj_page():
    """Render the dedicated Smart DJ 2.0 interactive curation studio."""
    with main_layout(current_page="smart_dj"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Smart DJ 2.0 — Curadoria por Inteligência Musical").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Descreva o set desejado em linguagem natural com transições harmônicas Camelot e regras acústicas."
                ).classes("text-sm text-gray-400")

        # Prompt & Criteria Input Card
        with ui.column().classes(f"w-full {card_cls} mb-6 gap-4 border-primary"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("auto_awesome", color="primary", size="md")
                ui.label("Descreva a Playlist ou Set Musical").classes("text-xl font-bold text-white")

            prompt_input = ui.textarea(
                label="Prompt em Linguagem Natural",
                placeholder="Exemplo: Rock animado anos 80 para treinar com mais de 125 bpm, sem repetir artistas e com transição harmônica.",
                value="synthwave e eletronica animada anos 80 para dirigir",
            ).props("dark outlined rows=2").classes("w-full")

            # Advanced expandable settings
            with ui.expansion("Filtros Avançados & Parâmetros Opcionais", icon="tune").classes("w-full text-white bg-[#202020] rounded-lg"):
                with ui.row().classes("w-full gap-4 p-3 flex-wrap"):
                    count_slider = ui.slider(min=5, max=50, value=20).props("label color=primary inline").classes("w-48")
                    ui.label("Quantidade de Músicas").classes("text-xs text-gray-400 self-center")

                    transition_select = ui.select(
                        {
                            "combined": "Combinada (BPM + Harmônica Camelot)",
                            "harmonic": "Harmônica Estrita (Camelot)",
                            "bpm_progression": "Progressão Gradual de BPM",
                            "score": "Apenas Relevância de Pontuação",
                        },
                        value="combined",
                        label="Modo de Transição",
                    ).props("dark outlined dense").classes("w-64")

                    unique_artists_cb = ui.checkbox("Sem repetir artistas (um por faixa)", value=False).props("dark color=primary")

            with ui.row().classes("w-full justify-end gap-3 mt-2"):
                generate_btn = ui.button("Gerar Set com Smart DJ", icon="bolt").props("color=primary no-caps")

        # Results Container
        results_container = ui.column().classes("w-full gap-4")

        # Session state for generated tracks
        generated_set: list[UnifiedTrack] = []
        set_reasons: dict[int, str] = {}

        def do_generate():
            nonlocal generated_set, set_reasons
            p_text = prompt_input.value
            if not p_text:
                ui.notify("Por favor, digite uma descrição para a playlist.", type="warning")
                return

            results_container.clear()
            with results_container:
                ui.spinner(size="lg", color="primary")

            with Session(engine) as session:
                catalog = session.exec(select(UnifiedTrack)).all()

            if not catalog:
                results_container.clear()
                with results_container:
                    ui.notify("Sua biblioteca está vazia. Adicione músicas antes de gerar sets.", type="warning")
                return

            filt = curator.parse_prompt_to_filter(p_text)
            filt.track_count = int(count_slider.value)
            filt.transition_mode = transition_select.value
            if unique_artists_cb.value:
                filt.unique_artists_only = True

            result: SmartDJResult = curator.generate_smart_dj_set(p_text, catalog, custom_filter=filt)
            generated_set = result.tracks
            set_reasons = result.justifications

            render_results(result)

        def render_results(result: SmartDJResult):
            results_container.clear()
            with results_container:
                # Results Header Banner
                with ui.row().classes(f"w-full {card_cls} justify-between items-center py-3"):
                    with ui.row().classes("items-center gap-3"):
                        ui.icon("check_circle", color="positive", size="md")
                        with ui.column().classes("gap-0"):
                            ui.label(f"Set Gerado: {len(result.tracks)} faixas selecionadas").classes("text-lg font-bold text-white")
                            dur_min = round(result.total_duration_ms / 60000, 1)
                            ui.label(f"Duração estimada: {dur_min} min • Média: {result.average_bpm or '—'} BPM • {result.transition_summary}").classes(
                                "text-xs text-gray-400"
                            )

                    with ui.row().classes("gap-2"):
                        ui.button("Regenerar", icon="refresh", on_click=do_generate).props("flat color=white no-caps")
                        ui.button("Salvar na Biblioteca", icon="save", on_click=save_generated_playlist).props("color=primary no-caps")

                # Track List Items
                for idx, t in enumerate(result.tracks, 1):
                    reason = result.justifications.get(t.id or idx, "Compatibilidade com os critérios do prompt")
                    with ui.row().classes(f"w-full {card_cls} items-center justify-between p-3 hover:border-primary transition-all"):
                        # Order number & Cover
                        with ui.row().classes("items-center gap-3"):
                            ui.badge(str(idx), color="secondary").props("dense")
                            cover = t.cover_url or "https://placehold.co/40x40/181818/1DB954?text=%E2%99%AC"
                            ui.image(cover).classes("w-10 h-10 rounded-md object-cover")

                            with ui.column().classes("gap-0 max-w-[320px]"):
                                ui.label(t.title).classes("text-sm font-bold text-white truncate")
                                ui.label(f"{t.artist} {f'• {t.album}' if t.album else ''}").classes("text-xs text-gray-400 truncate")
                                ui.label(f"💡 {reason}").classes("text-[11px] text-primary truncate")

                        # Badges
                        with ui.row().classes("items-center gap-2"):
                            if t.bpm:
                                ui.badge(f"{int(t.bpm)} BPM", color="secondary").props("outline dense")
                            if t.key:
                                ui.badge(t.key, color="info").props("outline dense")
                            if t.local_path:
                                ui.badge("Offline", color="positive").props("dense")

                        # Actions
                        with ui.row().classes("items-center gap-2"):
                            ui.button(
                                icon="play_arrow",
                                on_click=lambda trk=t: player.play_track(trk, result.tracks),
                            ).props("flat round color=primary").tooltip("Tocar")

                            ui.button(
                                icon="delete",
                                on_click=lambda trk=t: remove_track_from_set(trk, result),
                            ).props("flat round color=negative").tooltip("Remover deste set")

        def remove_track_from_set(track_to_remove: UnifiedTrack, result: SmartDJResult):
            result.tracks = [t for t in result.tracks if t.id != track_to_remove.id]
            render_results(result)
            ui.notify(f"Faixa '{track_to_remove.title}' removida do set.", type="info")

        def save_generated_playlist():
            if not generated_set:
                ui.notify("Nenhuma faixa para salvar.", type="warning")
                return

            p_title = f"Smart DJ: {prompt_input.value[:30]}"
            with Session(engine) as session:
                new_pl = Playlist(
                    name=p_title,
                    description=f"Gerada pelo Smart DJ 2.0 via prompt: '{prompt_input.value}'",
                    source_provider="smart_dj_2",
                )
                session.add(new_pl)
                session.commit()
                session.refresh(new_pl)

                for pos, t in enumerate(generated_set):
                    link = PlaylistTrackLink(playlist_id=new_pl.id, track_id=t.id, position=pos)
                    session.add(link)
                session.commit()

            ui.notify(f"Playlist '{p_title}' salva com sucesso na sua biblioteca!", type="positive")

        generate_btn.on("click", do_generate)
