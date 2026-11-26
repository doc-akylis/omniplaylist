from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import UnifiedTrack
from app.engines.search_engine import GlobalSearchEngine, SearchQueryCriteria
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme_manager import theme_manager

search_engine = GlobalSearchEngine()


def render_search_page():
    """Render the global multi-criteria search studio."""
    with main_layout(current_page="search"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Busca Avançada — Pesquisa Multi-Critérios").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Localize músicas combinando filtros de BPM, tonalidade Camelot, décadas, codecs, ISRC e provedores."
                ).classes("text-sm text-gray-400")

        # Search Controls Card
        with ui.column().classes(f"w-full {card_cls} mb-6 gap-3"):
            global_q = ui.input(
                placeholder="Busca rápida por qualquer termo (título, artista, álbum, ISRC)..."
            ).props("dark outlined dense clearable").classes("w-full")

            with ui.row().classes("w-full gap-3 flex-wrap"):
                artist_in = ui.input(placeholder="Artista").props("dark outlined dense").classes("flex-1")
                album_in = ui.input(placeholder="Álbum").props("dark outlined dense").classes("flex-1")
                genre_in = ui.input(placeholder="Gênero").props("dark outlined dense").classes("flex-1")
                key_in = ui.input(placeholder="Clave (ex: 8A, Am)").props("dark outlined dense").classes("w-36")

            with ui.row().classes("w-full gap-3 items-center flex-wrap"):
                min_bpm_in = ui.number(placeholder="BPM Mínimo", format="%.0f").props("dark outlined dense").classes("w-36")
                max_bpm_in = ui.number(placeholder="BPM Máximo", format="%.0f").props("dark outlined dense").classes("w-36")
                min_year_in = ui.number(placeholder="Ano Mínimo", format="%d").props("dark outlined dense").classes("w-36")
                max_year_in = ui.number(placeholder="Ano Máximo", format="%d").props("dark outlined dense").classes("w-36")
                offline_cb = ui.checkbox("Apenas arquivos offline", value=False).props("dark color=primary")

            with ui.row().classes("w-full justify-end mt-2"):
                search_btn = ui.button("Pesquisar", icon="search").props("color=primary no-caps")

        # Results Container
        results_container = ui.column().classes("w-full gap-3")

        def run_search():
            results_container.clear()
            with results_container:
                ui.spinner(size="md", color="primary")

            with Session(engine) as session:
                catalog = session.exec(select(UnifiedTrack)).all()

            criteria = SearchQueryCriteria(
                text_query=global_q.value if global_q.value else None,
                artist=artist_in.value if artist_in.value else None,
                album=album_in.value if album_in.value else None,
                genre=genre_in.value if genre_in.value else None,
                min_year=int(min_year_in.value) if min_year_in.value else None,
                max_year=int(max_year_in.value) if max_year_in.value else None,
                min_bpm=float(min_bpm_in.value) if min_bpm_in.value else None,
                max_bpm=float(max_bpm_in.value) if max_bpm_in.value else None,
                key=key_in.value if key_in.value else None,
                only_offline=offline_cb.value,
            )

            matched = search_engine.filter_tracks(catalog, criteria)

            results_container.clear()
            with results_container:
                ui.label(f"{len(matched)} faixas encontradas").classes("text-sm text-gray-400 font-semibold mb-2")

                if not matched:
                    ui.label("Nenhuma música correspondeu a todos os filtros selecionados.").classes("text-sm text-gray-400 py-4")
                    return

                for t in matched:
                    with ui.row().classes(f"w-full {card_cls} items-center justify-between p-3"):
                        with ui.row().classes("items-center gap-3"):
                            cover = t.cover_url or "https://placehold.co/40x40/181818/1DB954?text=%E2%99%AC"
                            ui.image(cover).classes("w-10 h-10 rounded-md object-cover")
                            with ui.column().classes("gap-0"):
                                ui.label(t.title).classes("text-sm font-bold text-white")
                                ui.label(f"{t.artist} • {t.album or '—'} {f'({t.release_year})' if t.release_year else ''}").classes("text-xs text-gray-400")

                        with ui.row().classes("items-center gap-2"):
                            if t.bpm:
                                ui.badge(f"{int(t.bpm)} BPM", color="secondary").props("outline dense")
                            if t.key:
                                ui.badge(t.key, color="info").props("outline dense")
                            if t.local_path:
                                ui.badge("Offline", color="positive").props("dense")

                            ui.button(
                                icon="play_arrow",
                                on_click=lambda trk=t: player.play_track(trk, matched),
                            ).props("flat round color=primary").tooltip("Ouvir")

        search_btn.on("click", run_search)
        run_search()
