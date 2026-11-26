# OmniPlaylist 2.0 (DJ Mode 2.0)

Plataforma unificada de gerenciamento de playlists, sincronização multiplataforma (Spotify, YouTube Music, Amazon Music, Deezer), análise técnica e musical de áudio e estação **DJ Mode 2.0** em tempo real.

---

## Arquitetura do Projeto

- **Camada Web & UI (`main.py`, `app/ui/`, `app/api/`):** FastAPI + NiceGUI (Tailwind CSS / Quasar dark theme) com endpoints REST/WebSocket e motor **Web Audio API + AudioWorklet** (`app/ui/static/js/`) para espectro de 6 bandas, espectrograma waterfall, waveform interativa e medidores Peak/RMS ao vivo.
- **Domínio & Persistência (`app/core/`):** SQLite + SQLModel (`UnifiedTrack`, `Playlist`), migrações idempotentes (`migrate_db`) e matching via ISRC + RapidFuzz (`matcher.py`).
- **Motores de Processamento (`app/engines/`):**
  - `technical_analysis.py`: Pipeline single-pass via **FFmpeg / ffprobe** (codec, bitrate, sample rate, bit depth, EBU R128 LUFS, True Peak, Dynamic Range, Crest Factor, ReplayGain, clipping e silêncio).
  - `musical_analysis.py`: Análise musical assíncrona em worker threads via **Librosa + NumPy** (BPM, estabilidade de tempo, beatgrid 4/4, tonalidade Krumhansl-Schmuckler, notação Camelot, energia, danceability e segmentação estrutural).
  - `local_scanner.py`, `downloader.py`, `exporter.py`, `dj_exporter.py`, `genre_engine.py`.
- **Provedores (`app/providers/`):** Integrações intercambiáveis estendendo `BaseMusicProvider`.

---

## Pré-requisitos do Sistema

1. **Python 3.11+** (testado em Python 3.12)
2. **`uv`** (gerenciador de pacotes e ambientes virtuais — recomendado) ou `pip`
3. **FFmpeg e `ffprobe`** instalados e disponíveis no `PATH` do sistema:
   - **Windows (WinGet):** `winget install Gyan.FFmpeg`
   - **Linux (Ubuntu/Debian):** `sudo apt update && sudo apt install -y ffmpeg`
   - **macOS (Homebrew):** `brew install ffmpeg`

---

## Setup em Outra Máquina (Windows ou Linux)

### 1. Clonar o repositório
```bash
git clone https://github.com/doc-akylis/omniplaylist.git
cd omniplaylist
```

### 2. Configurar variáveis de ambiente
```bash
# Linux / macOS / Git Bash
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```
*(Edite o `.env` apenas se for utilizar credenciais do Spotify, YouTube Music ou Amazon Music.)*

### 3. Instalar dependências
Com `uv` (recomendado — usa `uv.lock` para reprodutibilidade exata):
```bash
uv sync --all-extras
```

Ou com `pip` tradicional:
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Rodar a suíte de testes
```bash
# Windows
.venv\Scripts\python.exe -m pytest -v

# Linux / macOS
.venv/bin/python -m pytest -v
```

### 5. Iniciar a aplicação
```bash
# Windows
.venv\Scripts\python.exe main.py

# Linux / macOS
.venv/bin/python main.py
```
Acesse no navegador: **`http://localhost:8000`**
