# OmniPlaylist 2.2 — Universal Music Discovery & Automatic Acquisition Engine

Plataforma local unificada de descoberta musical multi-fonte, comparação técnica e aquisição automática autorizada, gerenciamento de playlists, inteligência de qualidade de áudio, sequenciamento harmônico e estação **DJ Mode Pro** em tempo real.

---

## Arquitetura (v2.2)

- **Backend (`main.py`, `app/api/`):** FastAPI + SQLModel + SQLite (`omniplaylist.db`) com migrações idempotentes (`migrate_db()`), WebSocket `/api/ws/progress` e serving da SPA compilada (`app/ui/dist/`).
- **Descoberta Multi-Fonte & Aquisição Automática (`app/sources/`, `app/engines/music_search_engine.py`, `source_quality_comparator.py`, `acquisition_engine.py`):**
  - 14 adaptadores categorizados estritamente em `DISCOVERY` (MusicBrainz, Discogs, Spotify), `PREVIEW_STREAMING` (iTunes, Deezer), `AUTHORIZED_DOWNLOAD` (Internet Archive, Wikimedia Commons, Audius, Jamendo, SoundCloud, Freesound) e `COMMERCIAL_DELIVERY` (7digital/MassiveMusic, The Rights Foundry, Qobuz Partner).
  - Agrupamento por gravação e versão (`TrackMatcher.detect_version_type` + `group_recordings`), comparador anti-transcode, bloqueio comercial (`AWAITING_APPROVAL`) até aprovação do usuário e segurança anti-SSRF/redirect/magic-bytes/SHA-256 (`app/core/security.py`).
- **Frontend (`frontend/`):** React 19 + TypeScript + Vite 8 + Tailwind CSS v4 + Lucide Icons + Web Audio API + `essentia.js` WASM (tema Studio Dark).
  - **DJ Mode Pro:** Decks duplos A/B, waveforms paralelas RGB, 8 Hot Cues por seção, EQ 3 bandas + Filtro HPF/LPF, Sync, Pitch, Crossfader, **Transition Analysis** (BPM, Camelot, delta LUFS, bass overlap, pico combinado estimado) e **EQ Assist** não-destrutivo.
  - **Spectrum & DSP Inspector:** Analisador FFT 8192-pt (Peak Hold, RMS, Waterfall, 6-Band Studio), Stereo Width (M/S estimado), Correlação de Fase, telemetria FFmpeg/Librosa e painel **Audio Quality Intelligence**.
  - **Quality Dashboard:** Visão agregada real do acervo com distribuição de codecs, bitrates, sample rates, Car Audio Score e filtros acionáveis.
  - **Playlists & Smart Flow:** CRUD N:N persistente, métricas reais, exportação M3U/M3U8 com relatório de faltantes e **Smart Sequencer** multi-modo reversível.
  - **Download Studio:** Fila persistente (`DownloadJob`), perfis (`ORIGINAL`, `FLAC_ARCHIVE`, `WAV_16`, `WAV_24`, `MP3_320`, `AAC_256`), **Upgrade Engine**, tagging Mutagen e substituição atômica com backup.
  - **Busca Omnichannel, Biblioteca Beets & Status das 8 APIs:** SQLite, iTunes, Deezer, MusicBrainz + Cover Art Archive, LRCLIB, AcoustID, Last.fm e ListenBrainz.

---

## Pré-requisitos

1. **Python 3.11+** (testado em 3.12 via `.venv`)
2. **Node.js 20+** e `npm` (testado em Node v24.20.0 / npm 11.19.0)
3. **FFmpeg e `ffprobe`** instalados no `PATH`

---

## Setup, Build e Testes

```powershell
# 1. Dependências Python (com uv ou .venv)
uv sync --all-extras

# 2. Build do Frontend React
cd frontend
npm install
npm run build
cd ..

# 3. Rodar a suíte completa de testes
.venv\Scripts\python.exe -m pytest -v

# 4. Iniciar a aplicação
.\iniciar.bat
# ou: .venv\Scripts\python.exe main.py
```

Acesse no navegador: **`http://localhost:8000`**
