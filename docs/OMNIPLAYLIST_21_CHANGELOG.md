# Changelog — OmniPlaylist 2.1

## [2.1.0] — Audio Intelligence & Playlist Studio

### Adicionado
- **Banco & Migrações (`app/core/models.py`, `app/core/database.py`):**
  - Novas tabelas: `AudioProvenance`, `AudioProcessingHistory`, `DownloadJob`.
  - Novos campos em `UnifiedTrack` para proveniência, corte espectral, status de fake upscale, 4 bandas de energia espectral e Car Audio Intelligence.
  - Novos campos em `Playlist` (`cover_url`, `original_order_json`) e `PlaylistTrackLink` (`added_at`), além de `ExportFormat.M3U`.
  - `migrate_db(target_engine=None)` com suporte seguro e idempotente a bancos existentes.
- **Audio Quality Intelligence (`app/engines/audio_quality_intelligence.py`):**
  - Rastreamento estruturado de proveniência sobrevivendo a conversões/upgrades.
  - Classificação `LOSSLESS_SOURCE` / `LOSSY_SOURCE` / `UNKNOWN_SOURCE`.
  - Detector STFT/Welch de possível fake upscale com níveis de confiança e proteção contra falsos positivos acústicos (`UNKNOWN`).
  - Score Car Audio 0–100 explicável com penalidades e pesos configuráveis sem penalizar baixo subgrave.
  - Quality Dashboard agregado (`GET /api/quality/dashboard`).
- **Download Studio & Upgrade Engine (`app/engines/download_studio.py`, `conversion_engine.py`, `tagging_engine.py`, `upgrade_engine.py`):**
  - Perfis `ORIGINAL`, `FLAC_ARCHIVE`, `WAV_16`, `WAV_24`, `MP3_320`, `AAC_256` reutilizando `_resolve_ffmpeg_binary`.
  - Fila persistente com concorrência controlada, retry/backoff, pause/resume/cancel, tagging multi-formato Mutagen e substituição atômica com backup e rollback.
  - `UpgradeEngine` com decisões explícitas e avisos contra conversões enganosas lossy→lossless.
- **Playlist Manager & Smart Sequencer (`app/engines/playlist_manager.py`, `exporter.py`, `dj_intelligence.py`):**
  - CRUD completo N:N, duplicação, reordenação persistente, 13 modos de ordenação, status de qualidade, métricas reais e exportação M3U/M3U8 com relatório de faltantes.
  - Smart Sequencer com modos `bpm_progression`, `energy_progression`, `harmonic_flow`, `balanced_dj_flow`, `custom`, justificativas reais por transição e restauração da ordem original.
- **DJ Technical Analyzer (`app/engines/dj_intelligence.py`, `frontend/`):**
  - Análise pré-transição Deck A ↔ Deck B (delta BPM, Camelot, delta LUFS, bass overlap, estimativa de pico combinado com ressalva de fase/ganho), EQ Assist não-destrutivo e Comparação A/B de versões.
  - Medidor de Stereo Width estimado (M/S) e alerta de correlação de fase no Spectrum Inspector.
- **API & Frontend React (`app/api/v21_routes.py`, `frontend/src/`):**
  - Endpoints `/api/tracks/{id}/analyze-quality`, `/api/quality/dashboard`, `/api/tracks/compare`, `/api/downloads/*`, `/api/playlists/*`, `/api/dj/transition-analysis`.
  - Novos workspaces integrados: `QualityDashboardView`, `PlaylistsStudioView`, `DownloadStudioView` e componentes `AudioQualityPanel` e `AbComparisonModal`.
