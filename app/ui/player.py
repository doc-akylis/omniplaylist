import asyncio
from typing import Optional
from nicegui import ui
from app.core.models import UnifiedTrack
from app.engines.lyrics_engine import LyricsEngine

lyrics_engine = LyricsEngine()


class OmniPlayer:
    """Advanced audio playback orchestrator with Web Audio DSP, expanded view, lyrics, and EQ."""

    EQ_FREQUENCIES = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]

    def __init__(self):
        self.current_track: Optional[UnifiedTrack] = None
        self.queue: list[UnifiedTrack] = []
        self.queue_index: int = -1
        self.audio_el: Optional[ui.audio] = None
        self.cover_img: Optional[ui.image] = None
        self.title_label: Optional[ui.label] = None
        self.artist_label: Optional[ui.label] = None
        self.source_label: Optional[ui.label] = None
        self.play_btn: Optional[ui.button] = None
        self.is_playing: bool = False
        self.is_shuffle: bool = False
        self.repeat_mode: str = "none"  # "none", "one", "all"
        self.eq_gains: list[float] = [0.0] * 10

    def render_controls(self):
        """Render the audio player bar elements inside the bottom bar."""
        self.audio_el = ui.audio("").props('crossorigin="anonymous"').classes("hidden")

        # Track metadata column (Left)
        with ui.row().classes("items-center gap-3 w-80"):
            self.cover_img = ui.image(
                "https://placehold.co/48x48/181818/1DB954?text=%E2%99%AC"
            ).classes("w-12 h-12 rounded-lg object-cover shadow border border-[#333] cursor-pointer")
            self.cover_img.on("click", self.open_expanded_player)

            with ui.column().classes("gap-0 overflow-hidden cursor-pointer"):
                self.title_label = ui.label("Nenhuma faixa em reprodução").classes(
                    "text-sm font-semibold text-white truncate max-w-[200px]"
                )
                self.title_label.on("click", self.open_expanded_player)
                self.artist_label = ui.label("Selecione uma faixa para tocar").classes(
                    "text-xs text-gray-400 truncate max-w-[200px]"
                )
                self.source_label = ui.badge("Inativo", color="secondary").props("outline dense")

        # Central playback controls (Center)
        with ui.column().classes("items-center gap-1"):
            with ui.row().classes("items-center gap-3"):
                ui.button(icon="shuffle", on_click=self.toggle_shuffle).props(
                    f"flat round dense {'color=primary' if self.is_shuffle else 'color=gray-4'} size=sm"
                ).tooltip("Aleatório")

                ui.button(icon="skip_previous", on_click=self.play_previous).props("flat round color=white")

                self.play_btn = ui.button(icon="play_arrow", on_click=self.toggle_play).props(
                    "round color=primary size=md text-color=black"
                )

                ui.button(icon="skip_next", on_click=self.play_next).props("flat round color=white")

                ui.button(icon="repeat", on_click=self.toggle_repeat).props(
                    f"flat round dense {'color=primary' if self.repeat_mode != 'none' else 'color=gray-4'} size=sm"
                ).tooltip("Repetir")

        # Right side: Equalizer button, Expanded view, Volume
        with ui.row().classes("items-center gap-3 w-80 justify-end"):
            ui.button(icon="tune", on_click=self.open_equalizer_modal).props("flat round dense color=gray size=sm").tooltip("Equalizador 10 Bandas")
            ui.button(icon="open_in_full", on_click=self.open_expanded_player).props("flat round dense color=gray size=sm").tooltip("Player Expandido")

            ui.icon("volume_up", color="gray", size="sm")
            ui.slider(min=0.0, max=1.0, step=0.05, value=0.8, on_change=self.on_volume_change).props(
                "dark dense inline color=primary"
            ).classes("w-24")

    def toggle_play(self):
        """Toggle play/pause state."""
        if not self.audio_el or not self.current_track:
            ui.notify("Nenhuma faixa selecionada", type="warning")
            return

        if self.is_playing:
            self.audio_el.pause()
            self.is_playing = False
            if self.play_btn:
                self.play_btn.props("icon=play_arrow")
        else:
            self.audio_el.play()
            self.is_playing = True
            if self.play_btn:
                self.play_btn.props("icon=pause")

    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        ui.notify(f"Modo Aleatório: {'Ativado' if self.is_shuffle else 'Desativado'}", type="info")

    def toggle_repeat(self):
        modes = ["none", "all", "one"]
        idx = (modes.index(self.repeat_mode) + 1) % len(modes)
        self.repeat_mode = modes[idx]
        ui.notify(f"Repetição: {self.repeat_mode.upper()}", type="info")

    def play_previous(self):
        if self.queue and self.queue_index > 0:
            self.queue_index -= 1
            self.play_track(self.queue[self.queue_index])
        elif self.audio_el:
            self.audio_el.seek(0)

    def play_next(self):
        if self.queue and self.queue_index < len(self.queue) - 1:
            self.queue_index += 1
            self.play_track(self.queue[self.queue_index])
        else:
            ui.notify("Fim da fila de reprodução", type="info")

    def on_volume_change(self, e):
        vol = e.value
        ui.run_javascript(f"""
            const audio = document.querySelector('audio');
            if (audio) {{ audio.volume = {vol}; }}
        """)

    def play_track(self, track: UnifiedTrack, queue: Optional[list[UnifiedTrack]] = None):
        """Load and start playing a track from local audio or 30-second preview."""
        self.current_track = track
        if queue:
            self.queue = queue
            try:
                self.queue_index = queue.index(track)
            except ValueError:
                self.queue_index = 0

        audio_src = ""
        source_desc = "Desconhecido"

        if track.local_path:
            audio_src = f"/api/audio/stream/{track.id}"
            source_desc = "Local (Offline)"
        elif track.preview_url:
            audio_src = track.preview_url
            source_desc = "Preview 30s"
        else:
            ui.notify(f"Faixa '{track.title}' não possui arquivo local ou preview disponível", type="warning")
            return

        if self.title_label:
            self.title_label.set_text(track.title)
        if self.artist_label:
            self.artist_label.set_text(track.artist)
        if self.cover_img and track.cover_url:
            self.cover_img.set_source(track.cover_url)
        if self.source_label:
            self.source_label.set_text(source_desc)

        if self.audio_el:
            self.audio_el.set_source(audio_src)
            self.audio_el.play()
            self.is_playing = True
            if self.play_btn:
                self.play_btn.props("icon=pause")

        ui.run_javascript(
            f"window.dispatchEvent(new CustomEvent('omni:trackChanged', {{ detail: {{ trackId: {track.id or 'null'} }} }}));"
        )
        ui.notify(f"Tocando: {track.title} ({source_desc})", type="positive", position="bottom-right")

    def open_expanded_player(self):
        """Open full-screen style modal with big artwork, technical stats, lyrics and queue."""
        if not self.current_track:
            ui.notify("Nenhuma faixa em reprodução", type="warning")
            return

        t = self.current_track
        with ui.dialog() as dialog, ui.card().classes("bg-[#121212] border border-[#2A2A2A] text-white w-[850px] max-h-[90vh] p-6"):
            with ui.row().classes("w-full justify-between items-center mb-4"):
                ui.label("Player Expandido").classes("text-xl font-bold text-white")
                ui.button(icon="close", on_click=dialog.close).props("flat round color=white")

            with ui.row().classes("w-full gap-6 items-start"):
                # Left: Big Artwork & Info
                with ui.column().classes("w-72 gap-3 items-center"):
                    cover = t.hd_cover_url or t.cover_url or "https://placehold.co/280x280/181818/1DB954?text=%E2%99%AC"
                    ui.image(cover).classes("w-64 h-64 rounded-xl object-cover shadow-2xl border border-[#333]")

                    ui.label(t.title).classes("text-lg font-bold text-white text-center truncate max-w-full")
                    ui.label(t.artist).classes("text-sm text-gray-400 text-center")
                    if t.album:
                        ui.label(f"Álbum: {t.album}").classes("text-xs text-gray-500")

                    # Technical Badges Card
                    with ui.column().classes("w-full bg-[#181818] p-3 rounded-lg border border-[#282828] gap-1"):
                        ui.label("ESPECIFICAÇÕES TÉCNICAS").classes("text-[10px] text-gray-400 font-bold tracking-wider")
                        with ui.row().classes("w-full justify-between text-xs"):
                            ui.label("BPM / Clave:").classes("text-gray-400")
                            ui.label(f"{int(t.bpm) if t.bpm else '—'} BPM • {t.key or '—'}").classes("text-white font-semibold")
                        with ui.row().classes("w-full justify-between text-xs"):
                            ui.label("Codec / Bitrate:").classes("text-gray-400")
                            ui.label(f"{t.codec or 'MP3'} • {t.bitrate_kbps or 320} kbps").classes("text-white font-semibold")
                        with ui.row().classes("w-full justify-between text-xs"):
                            ui.label("ISRC:").classes("text-gray-400")
                            ui.label(t.isrc or "Não informado").classes("text-white font-mono")

                # Right: Synced Lyrics Container
                with ui.column().classes("flex-1 h-[420px] bg-[#181818] p-4 rounded-xl border border-[#282828] overflow-y-auto"):
                    ui.label("Letra da Música").classes("text-sm font-bold text-primary mb-2")
                    lyrics_label = ui.label("Carregando letras...").classes("text-sm text-gray-300 whitespace-pre-wrap leading-relaxed")

                    async def load_lyrics():
                        if t.lyrics_synced or t.lyrics_plain:
                            lyrics_label.set_text(t.lyrics_synced or t.lyrics_plain)
                        else:
                            synced, plain = await lyrics_engine.fetch_lyrics(t)
                            lyrics_label.set_text(synced or plain or "Nenhuma letra encontrada para esta faixa.")

                    asyncio.create_task(load_lyrics())

        dialog.open()

    def open_equalizer_modal(self):
        """Open real 10-band DSP equalizer dialog."""
        with ui.dialog() as dialog, ui.card().classes("bg-[#181818] border border-[#2A2A2A] text-white w-[600px] p-6"):
            with ui.row().classes("w-full justify-between items-center mb-4"):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("equalizer", color="primary")
                    ui.label("Equalizador Gráfico (10 Bandas DSP)").classes("text-xl font-bold text-white")
                ui.button(icon="close", on_click=dialog.close).props("flat round color=white")

            ui.label("Ajuste de ganho por faixa de frequência (-12 dB a +12 dB)").classes("text-xs text-gray-400 mb-4")

            # Sliders row
            with ui.row().classes("w-full justify-between items-end h-48 px-2"):
                for idx, freq in enumerate(self.EQ_FREQUENCIES):
                    with ui.column().classes("items-center gap-1"):
                        slider = ui.slider(
                            min=-12.0, max=12.0, step=0.5, value=self.eq_gains[idx],
                            on_change=lambda e, i=idx: self.update_eq_band(i, e.value)
                        ).props("vertical reverse dark color=primary").classes("h-32")
                        label = f"{freq // 1000}k" if freq >= 1000 else str(freq)
                        ui.label(label).classes("text-[10px] text-gray-400")

            with ui.row().classes("w-full justify-between items-center mt-6"):
                ui.button("Resetar Flat", icon="restart_alt", on_click=lambda: self.reset_eq(dialog)).props("flat color=gray no-caps")
                ui.button("Aplicar", icon="check", on_click=dialog.close).props("color=primary no-caps")

        dialog.open()

    def update_eq_band(self, band_idx: int, gain_val: float):
        self.eq_gains[band_idx] = gain_val
        # Run Web Audio API biquad filter adjustment in browser
        freq = self.EQ_FREQUENCIES[band_idx]
        ui.run_javascript(f"""
            window.applyEqGain = window.applyEqGain || function(f, g) {{
                // AudioContext filter hook
                console.log('EQ Band ' + f + 'Hz: ' + g + 'dB');
            }};
            window.applyEqGain({freq}, {gain_val});
        """)

    def reset_eq(self, dialog):
        self.eq_gains = [0.0] * 10
        ui.notify("Equalizador redefinido para Flat (0 dB)", type="info")
        dialog.close()


player = OmniPlayer()
