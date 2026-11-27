# CLAUDE.md — OmniPlaylist 2.2 (Universal Music Discovery & Automatic Acquisition Engine)

## 1. Visão Geral e Arquitetura Atual
- **Projeto:** OmniPlaylist 2.2 — Plataforma unificada de descoberta musical multi-fonte, comparação técnica e aquisição automática autorizada, gerenciamento de playlists, inteligência de qualidade de áudio, sequenciamento inteligente e estação profissional **DJ Mode Pro**.
- **Stack Base:**
  - **Backend & Runtime:** Python 3.12+ (`pyproject.toml` / `uv`). Sempre executar scripts e testes via `.venv\Scripts\python.exe` e `.venv\Scripts\pytest.exe`.
  - **Web & UI:** FastAPI servindo SPA em **React 19 + TypeScript + Vite 8 + Tailwind CSS v4 + Lucide Icons** (`frontend/` compilado em `app/ui/dist/`).
  - **Banco & Modelos:** SQLite (`omniplaylist.db`) + SQLModel + migrações idempotentes (`migrate_db()` em `app/core/database.py`).
  - **Motor de Áudio & DSP:** `FFmpeg`/`ffprobe` (`_resolve_ffmpeg_binary` em `technical_analysis.py`), `librosa`, `scipy`, `numpy`, `mutagen`, Web Audio API + `essentia.js` WASM no navegador.

## 2. Organização de Diretórios (`app/` & `frontend/`)
Respeitar estritamente a separação de responsabilidades e **não duplicar motores existentes**:
- `app/core/`: `models.py` (`UnifiedTrack`, `Playlist`, `PlaylistTrackLink`, `AudioProvenance`, `AudioProcessingHistory`, `DownloadJob`, `MusicProviderConfig`, `MusicSearchSession`, `AcquisitionRecord`, etc.), `database.py` (`init_db`, `migrate_db`, `get_session`), `matcher.py` (ISRC/RapidFuzz + `detect_version_type` e `group_recordings`), `security.py` (SSRF, redirect check, path traversal, magic bytes, SHA-256).
- `app/sources/`: Arquitetura multi-fonte da v2.2 (`base.py` com categorias `DISCOVERY`, `PREVIEW_STREAMING`, `AUTHORIZED_DOWNLOAD`, `COMMERCIAL_DELIVERY`; `registry.py` com 14 adaptadores em `adapters/`).
- `app/providers/`: Provedores legados de catálogo e enriquecimento (`musicbrainz.py`, `itunes.py`, `deezer.py`, `acoustid.py`, `listenbrainz.py`, `lastfm.py`, `spotify.py`, `ytmusic.py`, `amazon.py`, `rate_limiter.py`).
- `app/engines/`:
  - `technical_analysis.py` (`TechnicalAnalysisEngine`, `_resolve_ffmpeg_binary`) — **fonte única de análise FFmpeg/ffprobe**.
  - `musical_analysis.py` (`MusicalAnalysisEngine`) — análise Librosa (BPM, beatgrid, Camelot, seções).
  - `audio_quality_intelligence.py` (`AudioQualityIntelligenceEngine`) — proveniência, origem real (`LOSSLESS_SOURCE`/`LOSSY_SOURCE`/`UNKNOWN_SOURCE`), detector espectral STFT/SciPy de possível fake upscale com confiança, perfil 4 bandas, `car_audio_score` explicável e Quality Dashboard.
  - `source_quality_comparator.py` (`SourceQualityComparator`), `music_search_engine.py` (`MusicSearchEngine`), `acquisition_engine.py` (`AcquisitionEngine`), `conversion_engine.py`, `tagging_engine.py`, `upgrade_engine.py`, `download_studio.py` (`DownloadStudioEngine` com fila persistente única `DownloadJob`, validação binária/SSRF e substituição atômica).
  - `playlist_manager.py` (`PlaylistManagerEngine`) — CRUD N:N, ordenação persistente, status de qualidade e métricas reais; `exporter.py` (`PlaylistExporter` com M3U/M3U8 e relatório de ausentes).
  - `dj_intelligence.py` (`DJIntelligenceEngine`) — recomendação próxima faixa, **Smart Playlist Sequencer** reversível (`SequencerConfig`) e **DJ Technical Analyzer** (`analyze_transition`, `generate_eq_suggestions`, `compare_track_versions`).
  - `metadata_enrichment.py`, `lyrics_engine.py`, `deduplicator.py`, `backup_engine.py`, `metadata_editor.py`, `playlist_health.py`.
- `app/api/`: `routes.py` (endpoints v2.0 + busca omnichannel + WebSocket `/api/ws/progress`), `v21_routes.py` (endpoints v2.1 de Quality Intelligence, Download Studio, Playlist Manager, Smart Sequencer e DJ Analyzer) e `v22_routes.py` (endpoints v2.2 de descoberta paralela `/api/discovery/*`, fontes/credenciais `/api/sources*` e aquisição automática/aprovação `/api/acquisition/*`).
- `frontend/src/`: SPA React Studio Dark (`#0B0D12` / `#12161F` / `#1A202C`) com `audio/djAudioEngine.ts`, 8 workspaces em `views/` e componentes modulares em `components/`.

## 3. Regras Inegociáveis de Engenharia
- **Tipagem & Async First:** Type hints estritos; operações CPU-bound (Librosa, SciPy, FFmpeg) em `asyncio.to_thread()` ou subprocessos assíncronos sem bloquear o event loop.
- **Não Duplicar:** Nunca criar um segundo resolvedor de FFmpeg, segundo motor de análise técnica/musical ou segundo engine de DJ; reutilizar e estender os módulos listados acima.
- **Transparência & Precisão:**
  - Nunca penalizar baixa energia de subgrave no `car_audio_score`.
  - Diferenciar corte abrupto de transcodificação (`LIKELY_UPSCALE`/`SUSPECTED_UPSCALE`) de rolloff acústico natural (`UNKNOWN`).
  - Nunca afirmar clipping combinado absoluto entre decks — tratar como estimativa dependente de fase, ganho e EQ.
  - Não implementar bypass de DRM/paywall; usar fontes autorizadas e reportar limitações de prévias claramente.
- **Segurança de Banco & Testes:** Sempre executar `.venv\Scripts\python.exe -m pytest -v` e `cd frontend; npm run build` após alterações; testes devem usar bancos SQLite isolados em `tmp_path` sem mutar `omniplaylist.db`.
