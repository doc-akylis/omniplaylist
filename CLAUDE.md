# CLAUDE.md — OmniPlaylist 2.0 (ECC + FCC)

## 1. Visão Geral e Arquitetura Existente
- **Projeto:** OmniPlaylist 2.0 — Plataforma unificada de gerenciamento de playlists (sincronização, matching via ISRC & RapidFuzz, clusterização por gênero, exportação/download multiplataforma) evoluída com uma estação profissional de análise musical (**DJ Mode 2.0**).
- **Stack Base:**
  - **Linguagem & Ambiente:** Python 3.11+ (`pyproject.toml` PEP 621 / `uv`). Sempre executar scripts, instalações e testes via `.venv\Scripts\python.exe` e `.venv\Scripts\pytest.exe`.
  - **Web & UI:** FastAPI + NiceGUI (Tailwind CSS, componentes Quasar, tema escuro).
  - **Banco & Modelos:** SQLite (`omniplaylist.db`) + SQLModel (Pydantic v2 + SQLAlchemy core) + `pydantic-settings` (`.env`).
  - **Matching & Integrações:** `rapidfuzz` (ISRC primário, similaridade de string secundária), `spotipy` (apenas playlists/catálogo — **não usar para análise técnica**), `ytmusicapi`, Playwright (Amazon Music).
  - **Motor de Mídia:** `yt-dlp`, FFmpeg / `ffprobe`, `mutagen` (tags ID3/FLAC).

## 2. Organização de Diretórios (`app/`)
Respeitar estritamente a separação de responsabilidades já existente no projeto:
- `app/core/`: Modelos de domínio (SQLModel), gerenciamento de sessão do banco, algoritmos de matching (`matcher.py`) e schemas.
- `app/providers/`: Integrações concretas com serviços musicais e APIs de metadados estendendo `BaseMusicProvider` (manter intercambialidade).
- `app/engines/`: Pipelines independentes de processamento (`genre_engine.py`, fila de download, exportadores e **novos motores de análise de áudio FFmpeg / Librosa / Essentia**).
- `app/api/`: Endpoints REST e WebSockets em tempo real para status de fila e telemetria.
- `app/ui/`: Camada de apresentação NiceGUI (páginas, componentes reativos, layout do player, tema escuro e **interface do DJ Mode 2.0**).

## 3. Padrões de Código e Regras Inegociáveis
- **Tipagem Estrita:** Usar type hints modernos do Python (`list[str]`, `dict[str, Any]`, `Optional[T]`, etc.) em todas as funções e métodos.
- **Async First & Não Bloqueante:** Usar `async/await` para I/O de rede, filas de download e handlers do NiceGUI. **Nunca** bloquear o event loop do FastAPI/NiceGUI com análise pesada de áudio; tarefas intensivas de CPU (FFmpeg, Librosa/Essentia) devem rodar em workers/processos em background e persistir no SQLite.
- **Modelos Validados:** Todo payload externo e schema de banco deve usar SQLModel / Pydantic v2.
- **Código Completo:** Nunca gerar placeholders (`# TODO`, `pass`, `...`), funções simuladas ou dados fictícios na UI. Entregar implementações 100% funcionais.
- **Não Duplicar Motores:** Auditar `app/` e `tests/` antes de adicionar bibliotecas ou arquivos para reaproveitar pipelines existentes (FFmpeg, Mutagen, player, modelos SQLModel).
- **Licenciamento:** Priorizar bibliotecas permissivas (Librosa/ISC, Beets/MIT, FFmpeg via subprocesso). Nunca copiar código diretamente de repositórios GPL/AGPL (Mixxx, Essentia, KeyFinder) sem isolamento adequado.
- **Resiliência & Docstrings:** Tratar rate limits, quedas de rede e metadados ausentes sem derrubar o loop principal. Manter docstrings concisas em lógicas complexas (`matcher.py`, `genre_engine.py` e motores de análise).
- **Transparência de Métricas:** Separar explicitamente medições em tempo real (FFT, RMS, picos) de estimativas algorítmicas (energia, danceability, estrutura musical), exibindo confiança e origem dos dados na UI.

## 4. Arquitetura do DJ Mode 2.0 (3 Camadas)
Toda evolução do DJ Mode deve seguir esta separação:
1. **Camada 1 — Análise Prévia (`app/engines/` + SQLite):**
   - **FFmpeg / ffprobe:** Decodificação, codec, formato, bitrate real/estimado, sample rate, bit depth, canais, loudness EBU R128 (LUFS integrado/momentâneo), True Peak, Crest Factor, Dynamic Range, ReplayGain e detecção de clipping/silêncio.
   - **Análise Musical (Librosa / Essentia conforme compatibilidade no Windows):** BPM médio/variação, beatgrid, onset, tonalidade, notação Camelot, energia por bandas, danceability e estimativa de seções (intro, verso, refrão, breakdown, outro).
   - **Persistência:** Salvar todos os resultados no `omniplaylist.db` para nunca recalcular faixas já analisadas.
2. **Camada 2 — Análise em Tempo Real (`app/ui/` — Browser Web Audio API + AudioWorklet):**
   - Capturar o áudio **efetivamente reproduzido** pelo player (nunca simular valores a partir do arquivo estático).
   - Calcular via `AudioWorklet` + FFT: espectro de frequências, espectrograma, medidor de pico/RMS e divisão nas 6 bandas:
     - Subgrave: `20–60 Hz`
     - Grave: `60–250 Hz`
     - Médio-grave: `250–500 Hz`
     - Médio: `500 Hz–2 kHz`
     - Médio-agudo: `2–6 kHz`
     - Agudo: `6–20 kHz`
3. **Camada 3 — Inteligência DJ (`app/core/` & `app/engines/`):**
   - Compatibilidade harmônica (Camelot), alinhamento de compassos/beatmatching, detecção de pontos de transição e recomendação de próxima faixa.

## 5. Provedores de Metadados e Letras (`app/providers/`)
- **Não usar Spotify** para análise técnica de áudio.
- **Ordem de Prioridade e Fallbacks:**
  1. **MusicBrainz + Cover Art Archive** (sem chave; respeitar rate limit estrito de **1 req/s** e enviar header `User-Agent` identificando o OmniPlaylist): ISRC, gravações, artistas, álbuns e capas.
  2. **iTunes Search API & Deezer API** (sem chave): fallback de busca de catálogo, capas e prévias.
  3. **LRCLIB** (sem chave; respeitar rate limit): letras normais e sincronizadas (`.lrc`).
  4. **AcoustID** (chave gratuita via `.env`): identificação por impressão digital acústica.
  5. **ListenBrainz & Last.fm** (token/chave gratuita via `.env`): estatísticas, tags, artistas semelhantes e recomendações.

## 6. Interface do DJ Mode 2.0 (`app/ui/` — 4 Áreas)
- **A. Leitor Principal:** Waveform com cursor sincronizado, BPM atual/médio, beatgrid/compassos, tempo decorrido/restante, estrutura da faixa e indicador de sincronização rítmica.
- **B. Analisador de Frequências:** 6 bandas (20 Hz a 20 kHz), espectro, espectrograma e medidores Peak/RMS.
- **C. Análise Técnica:** Codec, bitrate, sample rate, bit depth, canais, LUFS (integrado/momentâneo), True Peak, Crest Factor, Dynamic Range, ReplayGain e alertas de clipping/compressão com perda.
- **D. Análise Musical:** Tonalidade, Camelot, energia, danceability, intensidade por seção, variação de BPM e compatibilidade harmônica com a próxima faixa.

## 7. Fluxo de Execução com ECC + FCC
1. **Ordem de Implementação:**
   - **Passo 1:** Auditoria de `app/`, `main.py`, `omniplaylist.db` e `tests/` + Pipeline técnico via **FFmpeg** em `app/engines/` com persistência no SQLite.
   - **Passo 2:** Motor de análise musical prévia (**Librosa** / **Essentia**) em `app/engines/` + persistência (BPM, beatgrid, Camelot, seções).
   - **Passo 3:** Leitor em tempo real em `app/ui/` via **Web Audio API + AudioWorklet** (6 bandas, FFT, RMS, Peak) acoplado ao stream real do player.
   - **Passo 4:** Provedores de enriquecimento em `app/providers/` (**MusicBrainz + Cover Art Archive + iTunes/Deezer** com rate limiter) e letras (**LRCLIB**).
   - **Passo 5:** Inteligência DJ e descoberta (**ListenBrainz + Last.fm**, compatibilidade Camelot e recomendação de transição).
2. **Protocolo no Claude Code:**
   - Usar `/plan` antes de iniciar cada passo acima.
   - Rodar `.venv\Scripts\pytest.exe` e invocar `code-reviewer` após cada entrega.
   - Usar `/compact` entre etapas para manter o contexto enxuto no `fcc-server`.