# OmniPlaylist 2.1 — Auditoria Técnica Inicial & Baseline (Fase 0)

**Data:** 2026-11-27  
**Repositório:** `c:\Users\Nicollas\Desktop\omnimusic`  
**Backup Pré-Migração:** `backups/omniplaylist_backup_20261127_163933.zip` (`14` faixas, `3` playlists, `17` vínculos N:N, SHA-256 verificado).

---

## 1. Arquitetura Real Encontrada (Baseline v2.0)

### Backend (`app/`, `main.py`)
- **Runtime:** Python 3.12 via `.venv\Scripts\python.exe`, FastAPI + Uvicorn + SQLModel + SQLite (`omniplaylist.db`), `asyncio`, `ffmpeg`/`ffprobe` 9.1, `librosa 1.0.1`, `scipy 1.18.1`, `numpy 2.5.5`, `mutagen`, `yt-dlp`.
- **Serving (`main.py`):** Serve a SPA React compilada de `app/ui/dist/index.html`, montando `/assets` e preservando `/static`, `/api/*` e `/api/ws/progress`.
- **Banco de Dados (`omniplaylist.db`):**
  - 7 tabelas existentes: `unifiedtrack` (14 registros, 58 colunas), `playlist` (3 registros, 7 colunas), `playlisttracklink` (17 registros, 3 colunas: `playlist_id`, `track_id`, `position`), `devicesyncprofile`, `userhistory`, `backuprecord`, `usersettings`.
- **Engines Existentes (`app/engines/`):**
  - `technical_analysis.py` (`TechnicalAnalysisEngine`, `_resolve_ffmpeg_binary`): análise single-pass FFmpeg/ffprobe (`ebur128`, `astats`, `silencedetect`).
  - `musical_analysis.py` (`MusicalAnalysisEngine`): análise Librosa/NumPy em `asyncio.to_thread()` (BPM, beatgrid, downbeats, Camelot, seções, energia, danceability).
  - `dj_intelligence.py` (`DJIntelligenceEngine`): compatibilidade Camelot, beatmatching BPM (incluindo half/double-time), pontos `mix_out`/`mix_in` e ranking `recommend_next_tracks`.
  - `metadata_enrichment.py` (`MetadataEnrichmentEngine`): cascata AcoustID -> MusicBrainz + CAA -> iTunes -> Deezer -> LRCLIB -> Last.fm / ListenBrainz.
  - `audio_quality.py` (`AudioQualityEngine`, `QualityProfile`): inspeção básica via Mutagen + conversão simples sem detecção espectral STFT ou proveniência estruturada.
  - `downloader.py` (`TrackDownloader`): fila em memória (`asyncio.Queue`) acoplada ao `yt-dlp` sem persistência em banco, sem pause/resume/cancelamento, sem Upgrade Engine e sem substituição atômica.
  - `exporter.py` (`PlaylistExporter`): exportação M3U8, CSV, JSON, XSPF (sem M3U simples e sem relatório detalhado de arquivos ausentes).
  - `backup_engine.py`, `deduplicator.py`, `metadata_editor.py`, `playlist_health.py`, `local_scanner.py`, `smart_links.py`, `search_engine.py`, `ai_curator.py`, `genre_engine.py`, `analytics_engine.py`, `device_sync.py`, `dj_exporter.py`, `usb_exporter.py`, `loudness_engine.py`, `lyrics_engine.py`, `music_discovery.py`.

### Frontend (`frontend/`)
- React 19 + TypeScript + Vite 8 + Tailwind CSS v4 + Lucide + Essentia.js (`app/ui/dist/`).
- Views implementadas: `DjModeProView` (Decks A/B, RGB waveform, 8 Hot Cues, EQ 3 bandas, Filter, Crossfader, Sync, Pitch, browser), `SpectrumInspectorView` (FFT 8192-pt, Peak Hold, Waterfall, 6-Band, L/R, Phase Correlation), `OmniSearchView`, `LibraryManagerView`, `ProvidersStatusView`.

---

## 2. Divergências entre Documentação v2.0 e Código Real

1. **Testes Baseline:** O relatório anterior citava 65 testes; a execução real antes de qualquer mudança retornou **68 passed in 29.73s** (`0` falhas), devido aos 3 testes adicionados em `tests/test_omni_api_and_spa.py`.
2. **Registros no Banco:** O banco `omniplaylist.db` contém **14** registros em `unifiedtrack` (e não 13), além de 3 playlists e 17 vínculos.
3. **Documentação Desatualizada:** `README.md` e `CLAUDE.md` ainda descreviam a UI em NiceGUI, enquanto `main.py` já serve a SPA React de `app/ui/dist/` (mantendo arquivos legados em `app/ui/pages/` apenas por compatibilidade de testes).
4. **Recursos Ausentes/Incompletos para v2.1:**
   - **Audio Quality Intelligence:** sem tabela de proveniência (`AudioProvenance`) ou histórico (`AudioProcessingHistory`), sem detector espectral STFT/SciPy de possível fake upscale com confiança, sem perfil de energia por 4 bandas espectrais e sem `car_audio_score` explicável.
   - **Download Studio:** `downloader.py` usa fila volátil em memória, sem persistência de jobs (`DownloadJob`), sem `UpgradeEngine`, sem perfis estruturados (`ORIGINAL`, `FLAC_ARCHIVE`, `WAV_16`, `WAV_24`, `MP3_320`, `AAC_256`), sem substituição atômica/rollback e sem UI dedicada.
   - **Playlist Manager & Smart Sequencer:** não há CRUD completo de playlists na API/UI React, nem ordenação persistente multi-critério, métricas consolidadas, exportação M3U com relatório de faltantes, nem sequenciador multi-critério reversível sobre `DJIntelligenceEngine`.
   - **DJ Technical Analyzer:** `DjModeProView` ainda não exibe análise pré-transição (`TransitionAnalysis`: delta LUFS, bass overlap, clipping combinado estimado), `EQAssist` não-destrutivo nem comparação A/B de versões.
   - **Quality Dashboard:** não existe visão agregada da qualidade do acervo com filtros acionáveis.

---

## 3. Baseline de Testes & Build
- **Pytest:** `.venv\Scripts\python.exe -m pytest -q` → **68 passed in 29.73s**, `0 failed`.
- **Frontend Build:** `frontend/` compilado em `app/ui/dist/`.

---

## 4. Plano de Implementação v2.1 & Riscos
1. **Schema & Migrações Idempotentes (`models.py`, `database.py`):** adicionar apenas campos ausentes em `UnifiedTrack`, `Playlist`, `PlaylistTrackLink` e criar tabelas `AudioProvenance`, `AudioProcessingHistory`, `DownloadJob`.
2. **Engines v2.1:** `audio_quality_intelligence.py`, `conversion_engine.py`, `tagging_engine.py`, `upgrade_engine.py`, `download_studio.py`, `playlist_manager.py`, além da expansão de `dj_intelligence.py` e `exporter.py`.
3. **API (`app/api/v21_routes.py`):** endpoints REST integrados ao `ws_manager` e `get_session` existentes.
4. **Frontend (`frontend/src/`):** expandir navegação Studio Dark com `QualityDashboardView`, `PlaylistsStudioView` (Manager + Sequencer), `DownloadStudioView`, `AudioQualityPanel`, `AbComparisonModal`, e integrar `TransitionAnalysis` + `EQAssist` + `StereoWidth` nos painéis existentes.
5. **Riscos Mitigados:**
   - Evitar falsos positivos de fake upscale em faixas acústicas/antigas diferenciando corte abrupto (`brickwall`) de rolloff gradual (`UNKNOWN` quando inconclusivo).
   - Nunca penalizar baixo subgrave no `car_audio_score`.
   - Isolar todos os testes novos em bancos SQLite em `tmp_path` sem tocar `omniplaylist.db`.
