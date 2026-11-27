import json
from pathlib import Path
from typing import Optional
from nicegui import ui
from sqlmodel import Session, select

from app.core.database import engine
from app.core.models import Playlist, UnifiedTrack
from app.engines.audio_analyzer import AudioAnalyzer
from app.engines.dj_exporter import DjExporter
from app.engines.dj_intelligence import DJIntelligenceEngine
from app.engines.metadata_enrichment import MetadataEnrichmentEngine
from app.engines.musical_analysis import MusicalAnalysisEngine
from app.engines.technical_analysis import TechnicalAnalysisEngine
from app.ui.layout import main_layout
from app.ui.player import player
from app.ui.theme_manager import theme_manager

analyzer = AudioAnalyzer()
dj_exporter = DjExporter()
tech_engine = TechnicalAnalysisEngine()
musical_engine = MusicalAnalysisEngine()
enrichment_engine = MetadataEnrichmentEngine()
dj_intelligence = DJIntelligenceEngine()

SIX_BAND_META = [
    ("sub_bass", "Subgrave", "20–60 Hz", "#22c55e"),
    ("bass", "Grave", "60–250 Hz", "#10b981"),
    ("low_mid", "Médio-grave", "250–500 Hz", "#06b6d4"),
    ("mid", "Médio", "500 Hz–2 kHz", "#3b82f6"),
    ("high_mid", "Médio-agudo", "2–6 kHz", "#a855f7"),
    ("high", "Agudo", "6–20 kHz", "#ec4899"),
]


def render_dj_mode_page():
    """Render the DJ Mode 2.0 station with 4 analysis areas and harmonic set sequencing."""
    ui.add_body_html('<script src="/static/js/dj_realtime_engine.js"></script>')

    with main_layout(current_page="dj_mode"):
        card_cls = theme_manager.card_style

        # Header
        with ui.row().classes("w-full justify-between items-center mb-4"):
            with ui.column().classes("gap-1"):
                ui.label("DJ Mode 2.0 — Estação de Análise & Mixagem").classes(
                    "text-3xl font-bold text-white tracking-tight"
                )
                ui.label(
                    "Telemetria em tempo real (Web Audio + AudioWorklet), análise técnica FFmpeg e inteligência musical Librosa."
                ).classes("text-sm text-gray-400")

        # ==================== ÁREA A: LEITOR PRINCIPAL ====================
        with ui.column().classes(f"w-full {card_cls} mb-4 gap-3 border border-[#2A2A2A]"):
            with ui.row().classes("w-full justify-between items-center flex-wrap gap-2"):
                with ui.row().classes("items-center gap-3"):
                    ui.html(
                        '<div id="dj-beat-pulse" class="w-3.5 h-3.5 rounded-full bg-primary transition-transform duration-75" style="opacity:0.25;"></div>'
                    )
                    active_title_lbl = ui.label("Nenhuma faixa selecionada no deck").classes(
                        "text-lg font-bold text-white"
                    )
                    ui.badge("Área A • Leitor Principal", color="primary").props("outline dense")

                with ui.row().classes("items-center gap-3"):
                    ui.html('<span id="dj-current-section" class="px-2 py-0.5 rounded bg-[#222] text-xs font-bold text-accent">—</span>')
                    ui.html('<span id="dj-time-display" class="font-mono text-sm text-white">00:00 / -00:00</span>')
                    analyze_tech_btn = ui.button("Analisar Técnico", icon="graphic_eq").props("dense outline color=info no-caps")
                    analyze_music_btn = ui.button("Analisar Musical", icon="music_note").props("dense outline color=accent no-caps")
                    enrich_btn = ui.button("Enriquecer Metadados/Letras", icon="auto_awesome").props("dense outline color=positive no-caps")

            ui.html(
                '<canvas id="dj-waveform-canvas" width="1100" height="120" '
                'class="w-full h-[120px] rounded-lg border border-[#2A2A2A] cursor-pointer bg-[#111317]"></canvas>'
            )

        # ==================== ÁREAS B, C e D ====================
        with ui.row().classes("w-full gap-4 mb-6 items-stretch flex-wrap lg:flex-nowrap"):
            # ÁREA B: Analisador de Frequências (Tempo Real)
            with ui.column().classes(f"flex-1 min-w-[320px] {card_cls} gap-3"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Área B • Analisador de Frequências").classes("text-sm font-bold text-white")
                    ui.badge("Tempo Real • Web Audio + AudioWorklet", color="positive").props("dense")

                ui.html(
                    '<canvas id="dj-spectrum-canvas" width="480" height="110" '
                    'class="w-full h-[110px] rounded border border-[#282828] bg-[#111317]"></canvas>'
                )
                ui.html(
                    '<canvas id="dj-spectrogram-canvas" width="480" height="80" '
                    'class="w-full h-[80px] rounded border border-[#282828] bg-[#111317]"></canvas>'
                )

                # 6 Bandas exatas
                with ui.column().classes("w-full gap-1"):
                    for key, label, freq_range, color in SIX_BAND_META:
                        ui.html(
                            f'<div class="flex items-center gap-2 text-[11px]">'
                            f'<span class="w-24 text-gray-300">{label}</span>'
                            f'<span class="w-20 text-gray-500 font-mono">{freq_range}</span>'
                            f'<div class="flex-1 h-2 bg-[#222] rounded overflow-hidden">'
                            f'<div id="dj-band-bar-{key}" style="width:0%;background:{color};" class="h-full transition-all duration-75"></div>'
                            f'</div>'
                            f'<span id="dj-band-val-{key}" class="w-9 text-right text-gray-400 font-mono">0%</span>'
                            f'</div>'
                        )

                # Medidores Peak / RMS ao vivo
                ui.html(
                    '<div class="w-full pt-2 border-t border-[#2A2A2A] flex flex-col gap-1 text-xs">'
                    '<div class="flex justify-between"><span class="text-gray-400">RMS Ao Vivo</span><span id="dj-rms-val" class="font-mono text-white">-96.0 dBFS</span></div>'
                    '<div class="w-full h-2 bg-[#222] rounded overflow-hidden"><div id="dj-rms-bar" style="width:0%;background:#1DB954;" class="h-full"></div></div>'
                    '<div class="flex justify-between mt-1"><span class="text-gray-400">Peak Ao Vivo</span><span id="dj-peak-val" class="font-mono text-white">-96.0 dBFS</span></div>'
                    '<div class="w-full h-2 bg-[#222] rounded overflow-hidden"><div id="dj-peak-bar" style="width:0%;background:#f59e0b;" class="h-full"></div></div>'
                    '<div class="flex justify-between mt-1"><span class="text-gray-400">Clipping Stream</span><span id="dj-clip-indicator" class="font-bold text-positive">SEM CLIPPING</span></div>'
                    '</div>'
                )

            # ÁREA C: Análise Técnica (FFmpeg / ffprobe)
            tech_panel = ui.column().classes(f"flex-1 min-w-[280px] {card_cls} gap-2")

            # ÁREA D: Análise Musical (Librosa)
            music_panel = ui.column().classes(f"flex-1 min-w-[280px] {card_cls} gap-2")

        def render_tech_panel(track: Optional[UnifiedTrack]):
            tech_panel.clear()
            with tech_panel:
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Área C • Análise Técnica").classes("text-sm font-bold text-white")
                    ui.badge("Análise Prévia • FFmpeg/ffprobe", color="info").props("dense")

                if not track:
                    ui.label("Selecione ou toque uma faixa para ver as métricas técnicas.").classes("text-xs text-gray-400 py-4")
                    return

                rows = [
                    ("Codec / Bitrate", f"{track.codec or '—'} • {track.bitrate_kbps or '—'} kbps"),
                    ("Sample Rate / Depth", f"{track.sample_rate_hz or '—'} Hz • {track.bit_depth or '—'} bit ({track.channels or '—'} ch)"),
                    ("LUFS Integrado", f"{track.integrated_lufs:.1f} LUFS" if track.integrated_lufs is not None else "Pendente"),
                    ("LUFS Momentâneo / S", f"{track.momentary_lufs or '—'} / {track.short_term_lufs or '—'} LUFS"),
                    ("Loudness Range (LRA)", f"{track.loudness_range_lu:.1f} LU" if track.loudness_range_lu is not None else "—"),
                    ("True Peak", f"{track.true_peak_dbfs:.1f} dBFS" if track.true_peak_dbfs is not None else "—"),
                    ("Dynamic Range / Crest", f"{track.dynamic_range_db or '—'} / {track.crest_factor_db or '—'} dB"),
                    ("ReplayGain", f"{track.replay_gain:+.2f} dB" if track.replay_gain is not None else "—"),
                    ("Clipping Detectado", f"{track.clipping_count or 0} samples"),
                ]
                for k, v in rows:
                    with ui.row().classes("w-full justify-between text-xs py-1 border-b border-[#252525]"):
                        ui.label(k).classes("text-gray-400")
                        ui.label(v).classes("text-white font-mono")

                if track.quality_warning:
                    ui.badge(track.quality_warning, color="warning").classes("mt-2").props("outline")

        def render_music_panel(track: Optional[UnifiedTrack]):
            music_panel.clear()
            with music_panel:
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Área D • Análise Musical").classes("text-sm font-bold text-white")
                    conf_pct = int((track.musical_analysis_confidence or 0) * 100) if track and track.musical_analysis_confidence is not None else 0
                    ui.badge(f"Estimativa Algorítmica • {conf_pct}% conf.", color="accent").props("dense text-color=black")

                if not track:
                    ui.label("Selecione ou toque uma faixa para ver BPM, Camelot e seções.").classes("text-xs text-gray-400 py-4")
                    return

                rows = [
                    ("BPM Médio", f"{track.bpm:.1f} BPM" if track.bpm else "Pendente"),
                    ("Estabilidade BPM", f"{int((track.bpm_stability or 0) * 100)}%" if track.bpm_stability is not None else "—"),
                    ("Tonalidade / Camelot", f"{track.key or '—'} / {track.camelot_code or '—'}"),
                    ("Energia (est.)", f"{int((track.energy or 0) * 100)}%" if track.energy is not None else "—"),
                    ("Danceability (est.)", f"{int((track.danceability or 0) * 100)}%" if track.danceability is not None else "—"),
                ]
                for k, v in rows:
                    with ui.row().classes("w-full justify-between text-xs py-1 border-b border-[#252525]"):
                        ui.label(k).classes("text-gray-400")
                        ui.label(v).classes("text-white font-mono")

                ui.label("Seções Musicais Estimadas").classes("text-xs font-semibold text-gray-300 mt-2")
                try:
                    sections = json.loads(track.sections_json) if track.sections_json else []
                except Exception:
                    sections = []

                if not sections:
                    ui.label("Nenhuma segmentação estrutural disponível.").classes("text-xs text-gray-500")
                else:
                    for sec in sections[:6]:
                        with ui.row().classes("w-full justify-between text-[11px] py-0.5"):
                            ui.badge(sec.get("label", "section").upper(), color="secondary").props("dense")
                            ui.label(f"{sec.get('start_sec', 0):.1f}s – {sec.get('end_sec', 0):.1f}s").classes("text-gray-400 font-mono")
                            ui.label(f"E: {int(sec.get('relative_energy', 0) * 100)}%").classes("text-primary font-mono")

                # Capa HD & Metadados Enriquecidos
                cover_src = track.hd_cover_url or track.cover_url
                if cover_src or track.isrc or track.release_year:
                    with ui.row().classes("w-full items-center gap-3 mt-2 pt-2 border-t border-[#252525]"):
                        if cover_src:
                            ui.image(cover_src).classes("w-12 h-12 rounded-md object-cover")
                        with ui.column().classes("gap-0"):
                            if track.release_year:
                                ui.label(f"Ano: {track.release_year}").classes("text-[11px] text-gray-300")
                            if track.isrc:
                                ui.label(f"ISRC: {track.isrc}").classes("text-[11px] text-gray-400 font-mono")
                            if track.lastfm_tags:
                                ui.label(f"Tags: {track.lastfm_tags[:48]}").classes("text-[10px] text-gray-500")

                # Compatibilidade Harmônica & Sugestão de Próxima Faixa
                ui.label("Sugestão de Próxima Faixa (Camada 3)").classes("text-xs font-semibold text-gray-300 mt-2 pt-2 border-t border-[#252525]")
                catalog_for_recs = current_set_tracks if current_set_tracks else []
                if not catalog_for_recs:
                    with Session(engine) as session:
                        catalog_for_recs = session.exec(select(UnifiedTrack)).all()
                recs = dj_intelligence.recommend_next_tracks(track, catalog_for_recs, limit=3)
                if not recs:
                    ui.label("Nenhuma outra faixa na biblioteca para sugerir transição.").classes("text-[11px] text-gray-500")
                else:
                    for rec in recs:
                        t_pts = rec["transition_points"]
                        delta_sign = "+" if rec["bpm_delta_pct"] > 0 else ""
                        rel_tag = f" ({rec['bpm_relation']})" if rec["bpm_relation"] not in ("direct", "unknown") else ""
                        with ui.row().classes("w-full items-center justify-between bg-[#1c1f26] rounded px-2 py-1.5 mt-1"):
                            with ui.column().classes("gap-0 max-w-[190px]"):
                                ui.label(f"{rec['title']} — {rec['artist']}").classes("text-[11px] font-semibold text-white truncate")
                                ui.label(
                                    f"{rec['camelot_code'] or '—'} • {delta_sign}{rec['bpm_delta_pct']:.1f}% BPM{rel_tag} • "
                                    f"Out {t_pts['mix_out_sec']:.0f}s → In {t_pts['mix_in_sec']:.0f}s"
                                ).classes("text-[10px] text-gray-400 font-mono")
                            with ui.row().classes("items-center gap-1"):
                                ui.badge(f"{int(rec['score'] * 100)}%", color="positive" if rec["is_harmonic_compatible"] else "warning").props("dense")
                                ui.button(
                                    icon="play_arrow",
                                    on_click=lambda next_trk=rec["track"]: play_and_sync(next_trk, catalog_for_recs),
                                ).props("flat round dense size=xs color=primary").tooltip("Carregar & Tocar Próxima Faixa")

                # Letra Sincronizada / Normal
                lyrics_text = track.lyrics_synced or track.lyrics_plain
                if lyrics_text:
                    with ui.expansion("Letra Sincronizada (.LRC)" if track.lyrics_synced else "Letra", icon="lyrics").classes("w-full text-xs text-gray-300 mt-1"):
                        preview_lines = "\n".join(lyrics_text.splitlines()[:12])
                        ui.label(preview_lines).classes("text-[11px] font-mono text-gray-400 whitespace-pre-wrap")

        def sync_deck_to_track(track: Optional[UnifiedTrack]):
            render_tech_panel(track)
            render_music_panel(track)
            if not track:
                return
            active_title_lbl.set_text(f"{track.title} — {track.artist}")
            profile_payload = json.dumps(
                {
                    "id": track.id,
                    "duration_ms": track.duration_ms,
                    "beatgrid_json": track.beatgrid_json,
                    "sections_json": track.sections_json,
                }
            )
            ui.run_javascript(
                f"if (window.OmniDjRealtime) {{ window.OmniDjRealtime.setTrackProfile({profile_payload}); window.OmniDjRealtime.start(); }}"
            )

        async def run_track_technical():
            trk = player.current_track
            if not trk or not trk.id:
                ui.notify("Toque uma faixa primeiro para analisar.", type="warning")
                return
            ui.notify("Executando análise técnica FFmpeg...", type="info")
            with Session(engine) as session:
                db_trk = session.get(UnifiedTrack, trk.id)
                if db_trk:
                    await tech_engine.analyze_and_persist(db_trk, session, force=True)
                    player.current_track = db_trk
                    sync_deck_to_track(db_trk)
                    ui.notify("Análise técnica concluída!", type="positive")

        async def run_track_musical():
            trk = player.current_track
            if not trk or not trk.id:
                ui.notify("Toque uma faixa primeiro para analisar.", type="warning")
                return
            ui.notify("Executando análise musical Librosa...", type="info")
            with Session(engine) as session:
                db_trk = session.get(UnifiedTrack, trk.id)
                if db_trk:
                    await musical_engine.analyze_and_persist(db_trk, session, force=True)
                    player.current_track = db_trk
                    sync_deck_to_track(db_trk)
                    ui.notify("Análise musical concluída!", type="positive")

        async def run_track_enrich():
            trk = player.current_track
            if not trk or not trk.id:
                ui.notify("Toque uma faixa primeiro para enriquecer.", type="warning")
                return
            ui.notify("Enriquecendo metadados, capa HD e letras...", type="info")
            with Session(engine) as session:
                db_trk = session.get(UnifiedTrack, trk.id)
                if db_trk:
                    res = await enrichment_engine.enrich_track(db_trk, session, force=True)
                    player.current_track = db_trk
                    sync_deck_to_track(db_trk)
                    sources = ", ".join(res.get("sources_used", [])) or "nenhuma nova fonte"
                    ui.notify(f"Metadados enriquecidos ({sources})!", type="positive")

        analyze_tech_btn.on("click", run_track_technical)
        analyze_music_btn.on("click", run_track_musical)
        enrich_btn.on("click", run_track_enrich)

        # ==================== CONTROLES DO SET & TABELA HARMÔNICA ====================
        with ui.row().classes(f"w-full {card_cls} justify-between items-center mb-4"):
            with Session(engine) as session:
                playlists = session.exec(select(Playlist)).all()
                pl_options = {0: "Todas as Músicas da Biblioteca", **{p.id: p.name for p in playlists}}

            with ui.row().classes("items-center gap-4 flex-1"):
                pl_select = ui.select(pl_options, value=list(pl_options.keys())[0], label="Selecionar Lista para o Set").props(
                    "dark outlined dense"
                ).classes("w-64")
                load_btn = ui.button("Carregar Set", icon="folder_open").props("color=primary dense no-caps")

            with ui.row().classes("gap-2"):
                sort_camelot_btn = ui.button("Reordenar Mix Harmônico (Camelot)", icon="auto_fix_high").props("color=accent dense no-caps text-color=black")
                export_rekordbox_btn = ui.button("Exportar Rekordbox XML", icon="download").props("color=secondary dense no-caps")

        set_container = ui.column().classes("w-full gap-3")
        current_set_tracks: list[UnifiedTrack] = []

        def play_and_sync(trk: UnifiedTrack, tracks_list: list[UnifiedTrack]):
            player.play_track(trk, tracks_list)
            sync_deck_to_track(trk)

        def load_current_set(do_harmonic_sort: bool = False):
            nonlocal current_set_tracks
            set_container.clear()
            with set_container:
                ui.spinner(size="md", color="primary")

            with Session(engine) as session:
                if pl_select.value == 0:
                    tracks = session.exec(select(UnifiedTrack)).all()
                else:
                    pl = session.get(Playlist, pl_select.value)
                    tracks = pl.tracks if pl else []

            if do_harmonic_sort:
                tracks = analyzer.sort_playlist_for_dj(tracks)

            current_set_tracks = tracks
            render_set_table(current_set_tracks)

        def render_set_table(tracks: list[UnifiedTrack]):
            set_container.clear()
            with set_container:
                if not tracks:
                    ui.label("Nenhuma faixa carregada no set.").classes("text-sm text-gray-400 py-4")
                    return

                total_sec = sum((t.duration_ms or 0) // 1000 for t in tracks)
                with ui.row().classes("w-full justify-between items-center px-2 text-xs text-gray-400"):
                    ui.label(f"Total de Faixas: {len(tracks)} • Duração Total: {total_sec // 60} minutos").classes("font-semibold text-white")
                    ui.label("Indicador Harmônico: Verde = Transição Suave | Amarelo = Quebra de Clave")

                for i in range(len(tracks)):
                    curr_t = tracks[i]
                    next_t = tracks[i + 1] if i + 1 < len(tracks) else None

                    is_compatible = False
                    trans_text = "Fim do Set"
                    if next_t:
                        is_compatible = analyzer.are_keys_compatible(curr_t.camelot_code or curr_t.key, next_t.camelot_code or next_t.key)
                        trans_text = (
                            "Transição Harmônica Compatível"
                            if is_compatible
                            else f"Divergência Tonal ({curr_t.camelot_code or curr_t.key or '—'} ➔ {next_t.camelot_code or next_t.key or '—'})"
                        )

                    with ui.row().classes(f"w-full {card_cls} items-center justify-between p-3 border-l-4 {'border-l-positive' if is_compatible or not next_t else 'border-l-warning'}"):
                        with ui.row().classes("items-center gap-3"):
                            ui.badge(f"{i + 1:02d}", color="secondary").props("dense")
                            cover = curr_t.cover_url or "https://placehold.co/40x40/181818/1DB954?text=%E2%99%AC"
                            ui.image(cover).classes("w-10 h-10 rounded-md object-cover")

                            with ui.column().classes("gap-0 max-w-[320px]"):
                                ui.label(curr_t.title).classes("text-sm font-bold text-white truncate")
                                ui.label(f"{curr_t.artist} {f'• {curr_t.album}' if curr_t.album else ''}").classes("text-xs text-gray-400 truncate")

                        with ui.row().classes("items-center gap-3"):
                            bpm_str = f"{int(curr_t.bpm)} BPM" if curr_t.bpm else "BPM Pendente"
                            ui.badge(bpm_str, color="secondary").props("outline dense")
                            key_str = curr_t.camelot_code or curr_t.key or "S/ Clave"
                            ui.badge(key_str, color="primary" if (curr_t.camelot_code or curr_t.key) else "gray").props("dense")

                            if next_t:
                                ui.icon("arrow_forward", color="gray", size="xs")
                                ui.badge(trans_text, color="positive" if is_compatible else "warning").props("outline dense")

                        with ui.row().classes("items-center gap-2"):
                            ui.button(
                                icon="play_arrow",
                                on_click=lambda trk=curr_t: play_and_sync(trk, tracks),
                            ).props("flat round color=primary").tooltip("Ouvir e Analisar no Deck")

        def export_set_to_rekordbox():
            if not current_set_tracks:
                ui.notify("Carregue uma lista antes de exportar.", type="warning")
                return

            out_file = Path("./downloads") / "OmniPlaylist_DJ_Set_Rekordbox.xml"
            pl = Playlist(name="OmniPlaylist Live Set")
            dj_exporter.export_rekordbox_xml(pl, current_set_tracks, out_file)
            ui.notify(f"Arquivo exportado com sucesso em: {out_file.name}", type="positive")

        load_btn.on("click", lambda: load_current_set(False))
        sort_camelot_btn.on("click", lambda: load_current_set(True))
        export_rekordbox_btn.on("click", export_set_to_rekordbox)

        sync_deck_to_track(player.current_track)
        load_current_set(False)
        ui.run_javascript("if (window.OmniDjRealtime) { window.OmniDjRealtime.start(); }")
