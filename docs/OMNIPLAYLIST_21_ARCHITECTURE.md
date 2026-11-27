# OmniPlaylist 2.1 — Arquitetura Técnica

## 1. Visão em Camadas

1. **Camada de Domínio & Persistência (`app/core/`)**
   - `UnifiedTrack`: metadados multiplataforma, análise técnica FFmpeg (`codec`, `bitrate_kbps`, `sample_rate_hz`, `bit_depth`, `integrated_lufs`, `true_peak_dbfs`, `dynamic_range_db`, `crest_factor_db`, `clipping_count`, etc.), análise musical Librosa (`bpm`, `camelot_code`, `beatgrid_json`, `sections_json`) e colunas v2.1 (`is_preview`, `source_classification`, `spectral_cutoff_hz`, `upscale_status`, `upscale_confidence`, `is_fake_upscale`, `sub_bass_energy`, `mid_bass_energy`, `midrange_energy`, `high_freq_energy`, `car_audio_score`, `car_audio_status`, `car_audio_ready`, `quality_intelligence_json`, `quality_analyzed_at`).
   - `Playlist` (`cover_url`, `original_order_json`) e `PlaylistTrackLink` (relação N:N com `position` e `added_at`).
   - `AudioProvenance`: rastreia origem real de aquisição, codec/bitrate originais, classificação (`LOSSLESS_SOURCE`, `LOSSY_SOURCE`, `UNKNOWN_SOURCE`), container atual e evidências.
   - `AudioProcessingHistory`: trilha imutável de operações (`acquire`, `convert`, `upgrade_replace`, `quality_analyze`), codecs de origem/destino, flags `was_lossy_to_lossless` e avisos.
   - `DownloadJob`: fila persistente com estados (`PENDING`, `QUEUED`, `DOWNLOADING`, `VALIDATING`, `CONVERTING`, `TAGGING`, `ANALYZING`, `COMPLETED`, `FAILED`, `CANCELLED`, `PAUSED`), progresso, velocidade, ETA, tentativas e decisão do `UpgradeEngine`.

2. **Camada de Motores (`app/engines/`)**
   - `AudioQualityIntelligenceEngine`: orquestra `TechnicalAnalysisEngine` (FFmpeg/ffprobe) + STFT/Welch (`scipy.signal.welch` + `librosa.load`) em `asyncio.to_thread()` + `CarAudioWeights` explicável + `AudioProvenance`.
   - `DownloadStudioEngine` + `ConversionEngine` + `TaggingEngine` + `UpgradeEngine`: pipeline concorrente (`asyncio.Semaphore`), retry com backoff exponencial, staging em `downloads/.tmp/`, validação dupla `ffprobe`, backup pré-substituição em `backups/replaced_audio/`, `os.replace()` atômico e recuperação pós-restart (`recover_interrupted_jobs`).
   - `PlaylistManagerEngine` + `PlaylistExporter`: CRUD N:N, ordenação persistente multi-critério, classificação de status por faixa, métricas agregadas reais e exportação M3U/M3U8 com relatório de arquivos ausentes.
   - `DJIntelligenceEngine`: além de `recommend_next_tracks`, inclui **Smart Playlist Sequencer** (`SequencerConfig`, otimização global + 2-opt, justificativas baseadas em dados, snapshot/restauração de ordem) e **DJ Technical Analyzer** (`analyze_transition`, `generate_eq_suggestions`, `compare_track_versions`).

3. **Camada API (`app/api/routes.py` & `app/api/v21_routes.py`)**
   - Endpoints REST unificados sob `/api/*` e WebSocket `/api/ws/progress` para eventos de análise em lote e progresso em tempo real dos jobs do Download Studio.

4. **Camada de Apresentação (`frontend/src/` -> `app/ui/dist/`)**
   - SPA React + TypeScript + Tailwind Studio Dark com `DualDeckAudioEngine` (Web Audio API) e 8 workspaces integrados na barra lateral única.
