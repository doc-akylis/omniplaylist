import asyncio
from pathlib import Path
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import ExportConfig, ExportFormat, Playlist, UnifiedTrack
from app.engines.direct_importer import DirectImporter
from app.engines.dj_exporter import DjExporter
from app.engines.exporter import PlaylistExporter
from app.engines.smart_links import SmartLinkEngine
from app.engines.usb_exporter import UsbCarExporter
from app.ui.layout import main_layout
from app.ui.theme import CARD_STYLE

exporter = PlaylistExporter()
dj_exporter = DjExporter()
usb_exporter = UsbCarExporter()
direct_importer = DirectImporter()
smart_links = SmartLinkEngine()


def render_export_hub_page():
    """Render the multi-format export, DJ Rekordbox, USB Car, and Direct URL Import hub."""
    with main_layout(current_page="export"):
        # Header
        with ui.row().classes("w-full justify-between items-center mb-6"):
            with ui.column().classes("gap-1"):
                ui.label("Export & Sync Hub").classes("text-3xl font-bold text-white tracking-tight")
                ui.label(
                    "Exporte em múltiplos formatos, gere arquivos para Rekordbox DJ, Pen Drives de carro e importe por link direto."
                ).classes("text-sm text-gray-400")

        # Top section: 3-column cards
        with ui.row().classes("w-full gap-6 items-start mb-6"):
            # 1. Multi-format Exporter Card
            with ui.column().classes(f"flex-1 {CARD_STYLE} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("file_download", color="primary", size="md")
                    ui.label("Exportador de Arquivos").classes("text-xl font-bold text-white")

                with Session(engine) as session:
                    playlists = session.exec(select(Playlist)).all()
                    pl_options = {0: "Todas as Músicas Salvas", **{p.id: p.name for p in playlists}}

                pl_select = ui.select(
                    pl_options,
                    value=list(pl_options.keys())[0],
                    label="Selecionar Playlist",
                ).props("dark outlined dense")

                fmt_select = ui.select(
                    {
                        ExportFormat.M3U8: ".M3U8 (Extended Playlist)",
                        ExportFormat.CSV: ".CSV (Planilhas)",
                        ExportFormat.JSON: ".JSON (Metadados completos)",
                        ExportFormat.XSPF: ".XSPF (VLC/Universal)",
                    },
                    value=ExportFormat.M3U8,
                    label="Formato de Saída",
                ).props("dark outlined dense")

                ui.button(
                    "Exportar Arquivo",
                    icon="download",
                    on_click=lambda: run_standard_export(pl_select.value, fmt_select.value),
                ).props("color=primary no-caps").classes("w-full mt-2")

            # 2. DJ Rekordbox XML Exporter Card
            with ui.column().classes(f"flex-1 {CARD_STYLE} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("album", color="accent", size="md")
                    ui.label("Pioneer Rekordbox DJ").classes("text-xl font-bold text-white")

                ui.label(
                    "Gera XML oficial compatível com CDJs, Rekordbox, Virtual DJ e Traktor com BPM e Claves Camelot."
                ).classes("text-xs text-gray-400")

                dj_pl_select = ui.select(
                    pl_options,
                    value=list(pl_options.keys())[0],
                    label="Selecionar Playlist",
                ).props("dark outlined dense")

                ui.button(
                    "Gerar XML para Rekordbox",
                    icon="auto_fix_high",
                    on_click=lambda: run_rekordbox_export(dj_pl_select.value),
                ).props("color=accent no-caps text-color=black").classes("w-full mt-2")

            # 3. Car Stereo / FAT32 USB Exporter Card
            with ui.column().classes(f"flex-1 {CARD_STYLE} gap-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("usb", color="info", size="md")
                    ui.label("Som Automotivo (USB)").classes("text-xl font-bold text-white")

                ui.label(
                    "Organiza em pastas [Artista]/[Álbum]/[Faixa].mp3 com sanitização de caracteres ilegais para FAT32."
                ).classes("text-xs text-gray-400")

                usb_path_input = ui.input(
                    label="Caminho do Pen Drive ou Pasta",
                    value="./downloads/usb_car_stereo",
                ).props("dark outlined dense")

                ui.button(
                    "Copiar para Pen Drive",
                    icon="drive_file_move",
                    on_click=lambda: run_usb_export(usb_path_input.value),
                ).props("color=info no-caps").classes("w-full mt-2")

        # Direct Link Public Importer Section
        with ui.column().classes(f"w-full {CARD_STYLE} gap-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("link", color="primary")
                ui.label("Importar Playlist por Link Público (Sem Login / Sem API)").classes(
                    "text-lg font-bold text-white"
                )

            ui.label(
                "Cole qualquer link público de playlist do Spotify, YouTube ou Deezer para clonar as faixas para sua biblioteca."
            ).classes("text-xs text-gray-400")

            with ui.row().classes("w-full items-center gap-3"):
                url_input = ui.input(
                    placeholder="https://open.spotify.com/playlist/... ou https://www.youtube.com/playlist?list=...",
                ).props("dark outlined dense").classes("flex-1")

                ui.button(
                    "Importar Faixas",
                    icon="cloud_download",
                    on_click=lambda: run_direct_import(url_input.value),
                ).props("color=primary no-caps")


def run_standard_export(playlist_id: int, export_format: ExportFormat):
    """Execute standard export and show notification."""
    with Session(engine) as session:
        if playlist_id == 0 or not playlist_id:
            tracks = session.exec(select(UnifiedTrack)).all()
            pl = Playlist(name="Biblioteca Completa")
        else:
            pl = session.get(Playlist, playlist_id)
            if not pl:
                ui.notify("Playlist não encontrada", type="warning")
                return
            tracks = pl.tracks

        config = ExportConfig(playlist_id=pl.id or 0, format=export_format)
        out_file = exporter.export(pl, tracks, config)
        ui.notify(f"Arquivo gerado: {out_file.name}", type="positive")


def run_rekordbox_export(playlist_id: int):
    """Generate Rekordbox XML file."""
    with Session(engine) as session:
        if playlist_id == 0 or not playlist_id:
            tracks = session.exec(select(UnifiedTrack)).all()
            pl = Playlist(name="OmniPlaylist Collection")
        else:
            pl = session.get(Playlist, playlist_id)
            if not pl:
                ui.notify("Playlist não encontrada", type="warning")
                return
            tracks = pl.tracks

        out_path = Path("./downloads") / f"{pl.name}_rekordbox.xml"
        dj_exporter.export_rekordbox_xml(pl, tracks, out_path)
        ui.notify(f"XML Rekordbox gerado em: {out_path.name}", type="positive")


def run_usb_export(target_path_str: str):
    """Copy files to USB destination."""
    with Session(engine) as session:
        tracks = session.exec(select(UnifiedTrack)).all()
        pl = Playlist(name="Car Stereo Selection")
        target_path = Path(target_path_str)
        stats = usb_exporter.export_to_usb(pl, tracks, target_path)
        ui.notify(
            f"Concluído: {stats['copied']} faixas copiadas ({stats['skipped_no_local']} ignoradas sem áudio baixado).",
            type="info",
        )


def run_direct_import(url: str):
    """Import public playlist via direct URL."""
    if not url:
        ui.notify("Insira uma URL válida", type="warning")
        return

    async def _do_import():
        ui.notify("Extraindo metadados da playlist pública...", type="info")
        try:
            pl, tracks = await direct_importer.import_from_url(url)
            if not tracks:
                ui.notify("Nenhuma faixa pôde ser extraída da URL.", type="warning")
                return

            with Session(engine) as session:
                session.add(pl)
                session.commit()
                session.refresh(pl)

                for t in tracks:
                    # Check if exists
                    existing = session.exec(
                        select(UnifiedTrack).where(UnifiedTrack.title == t.title, UnifiedTrack.artist == t.artist)
                    ).first()
                    track_to_link = existing or t
                    if not existing:
                        session.add(t)
                        session.commit()
                        session.refresh(t)

                ui.notify(f"Playlist '{pl.name}' importada com {len(tracks)} faixas!", type="positive")
                ui.navigate.to("/")
        except Exception as e:
            ui.notify(f"Erro ao importar: {e}", type="negative")

    asyncio.create_task(_do_import())
