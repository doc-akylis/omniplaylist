# OmniPlaylist 2.1 — Relatório de Testes & Build

**Data:** 2026-11-27  
**Comando Backend:** `.venv\Scripts\python.exe -m pytest -v`  
**Comando Frontend:** `cd frontend; npm run build` (`tsc -b && vite build`)

---

## 1. Resumo Quantitativo

| Métrica | Baseline v2.0 | Final v2.1 |
|---|---:|---:|
| Total de Testes Coletados | 68 | **79** |
| Testes Aprovados | 68 | **79** |
| Testes Falhados | 0 | **0** |
| Testes Ignorados (Skipped) | 0 | **0** |
| Novos Testes Adicionados | — | **11** (em 5 suítes dedicadas) |
| Tempo de Execução | 29.73s | 32.80s |
| Build TypeScript + Vite | OK | **OK (exit code 0, 19.52s)** |

---

## 2. Novos Testes Implementados (v2.1)

1. `tests/test_v21_migrations.py` (`1` teste)
   - `test_idempotent_migration_on_v20_db_copy`: executa `init_db()` e `migrate_db()` duas vezes sobre uma cópia isolada do `omniplaylist.db` em `tmp_path`, confirmando preservação exata das 14 faixas, 3 playlists, 17 vínculos e criação das novas tabelas/colunas.
2. `tests/test_audio_quality_intelligence.py` (`3` testes)
   - `test_pcm_lossless_mp3_aac_and_sample_rates`: valida WAV 44.1 kHz, WAV 48 kHz, MP3 128 kbps e AAC 192 kbps via FFmpeg + STFT.
   - `test_fake_upscale_detection_and_acoustic_false_positive_guard`: valida detecção de `fake_flac` transcodificado de MP3 128k (`LIKELY_UPSCALE`/`SUSPECTED_UPSCALE`) e garante que faixa acústica/sem subgrave retorna `UNKNOWN` (sem falso positivo e sem penalidade de subgrave no Car Audio Score).
   - `test_clipping_silence_corrupted_and_provenance_survival`: valida detecção de clipping, silêncio, arquivo corrompido (`POOR`, `car_audio_ready=False`), sobrevivência da proveniência `LOSSY_SOURCE` após conversão para FLAC e endpoint `/api/quality/dashboard`.
3. `tests/test_download_studio.py` (`3` testes)
   - `test_upgrade_engine_decisions`: valida `NO_QUALITY_IMPROVEMENT` (preview e lossy 128→320k com aviso explícito), `UPGRADE_AVAILABLE` (FLAC verificado sobre preview), `DIFFERENT_VERSION` e `SOURCE_UNVERIFIED`.
   - `test_download_studio_profiles_tagging_atomic_replace_and_retry`: valida HTTP 503 + retry com backoff, conversão `FLAC_ARCHIVE`, `MP3_320`, `WAV_24`, `AAC_256`, tagging Mutagen, substituição atômica com backup, limpeza de `.tmp` e persistência de `AudioProvenance` / `AudioProcessingHistory`.
   - `test_download_rollback_on_failure_and_cancellation`: valida preservação do arquivo original em falha de payload corrompido e cancelamento persistente (`CANCELLED`).
4. `tests/test_playlist_manager_and_sequencer.py` (`2` testes)
   - `test_playlist_crud_nn_reorder_sort_metrics_and_export`: valida CRUD, duplicação, relação N:N, reordenação persistente, ordenação `bpm_asc`, métricas reais com notas de campos parciais, exportação M3U com relatório de arquivo ausente e preservação das faixas ao excluir playlist.
   - `test_smart_sequencer_modes_constraints_explainability_and_restore`: valida modos `bpm_progression`, `energy_progression`, `harmonic_flow`, `custom`, `forbidden_track_ids`, justificativas reais, aplicação e restauração da ordem original.
5. `tests/test_dj_technical_analyzer.py` (`2` testes)
   - `test_transition_analysis_eq_assist_and_ab_comparison`: valida `analyze_transition`, `bass_overlap_score`, `combined_clipping_is_estimate`, `generate_eq_suggestions` não-destrutivo e `compare_track_versions`.
   - `test_end_to_end_v21_workflow`: fluxo integrado E2E completo via API + `DownloadStudioEngine` em banco temporário isolado.

---

## 3. Build Frontend (`app/ui/dist/`)

- `index.html`: `0.83 kB`
- `assets/index-CW4Q59XS.css`: `40.47 kB`
- `assets/index-tnKkMpt9.js`: `374.84 kB`
- `assets/essentia.js-3OOxVulq.js`: `2,604.05 kB`
- Diagnóstico TypeScript (`tsc -b`): **0 erros**.
