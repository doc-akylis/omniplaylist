# Relatório de Auditoria — Etapa 3: Funcionalidades Principais

**Projeto:** OmniPlaylist 2.0  
**Data da Auditoria:** 04/11/2026  
**Auditor:** Antigravity (Auditoria Técnica Independente)  
**Status da Etapa:** Concluída com sucesso — Aguardando autorização para Etapa 4.

---

## 1. Visão Geral da Etapa

Nesta Etapa 3, a auditoria realizou a avaliação técnica e comportamental individualizada dos **6 motores centrais** do OmniPlaylist 2.0:
1. **Smart DJ 2.0** ([`app/engines/ai_curator.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/ai_curator.py))
2. **Download Studio** ([`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py), [`app/engines/audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_quality.py))
3. **Audio Inspector** ([`app/engines/audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_quality.py))
4. **Playlist Health** ([`app/engines/playlist_health.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/playlist_health.py))
5. **Smart Sync** ([`app/engines/device_sync.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/device_sync.py))
6. **Music Discovery** ([`app/engines/music_discovery.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/music_discovery.py))

Seguindo o critério central da auditoria, nenhuma funcionalidade foi considerada funcional apenas pela existência de arquivos ou classes; cada módulo foi submetido a execução de código real, testes com dados do banco e verificação de condições de contorno e dependências de ambiente.

---

## 2. Auditoria Individual das 6 Funcionalidades

### 2.1 Smart DJ 2.0
- **Arquivos**: [`app/engines/ai_curator.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/ai_curator.py), [`app/ui/pages/smart_dj_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/smart_dj_page.py), [`tests/test_smart_dj.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/tests/test_smart_dj.py).
- **Classificação Técnica**: **Implementada Heuristicamente / Parcialmente Funcional**.
- **Comportamento Verificado**:
  - O motor decompõe pedidos em linguagem natural através de regex e dicionários de sinônimos (`TEMPO_MAP`, `DECADE_MAP`, `MOOD_KEYWORDS`).
  - O cálculo ponderado de relevância pontua alinhamento de BPM (+35), gênero taxonômico (+30), década (+25), humor (+20) e palavras-chave (+15 por termo).
  - Gera justificativas textuais legíveis para cada faixa selecionada.
  - As restrições de artistas únicos (`unique_artists_only`) e exclusões explícitas (`excluded_artists`) operam corretamente na validação.
- **Divergências e Problemas Encontrados**:
  1. *Ausência de LLM*: O `BLUEPRINT_EXPANSAO.md` alega "interpretador baseado em LLM (Gemini API)". Na realidade, o código não contém nenhuma chamada a LLM nem SDK do Gemini; opera exclusivamente via casamento heurístico de padrões e regex.
  2. *Bug de Duplicação Harmônica com Faixas em Memória (id=None)*:
     - No método `organize_sequence` (linha 302), a ordenação harmônica indexa candidatos com `track_map = {s.track.id: s for s in scored_tracks}`.
     - Quando testado com faixas que ainda não possuem chave primária persistida (`id=None`), todas as faixas colapsam na mesma chave `None`.
     - **Comprovação em teste real**: A execução de `curator.generate_smart_dj_set('animada com transicao harmonica', [t1, t2])` com faixas com `id=None` gerou a lista `['Track 2', 'Track 2']`, perdendo faixas legítimas e duplicando instâncias.

---

### 2.2 Download Studio
- **Arquivos**: [`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py), [`app/engines/audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_quality.py), [`app/ui/pages/download_studio.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/download_studio.py).
- **Classificação Técnica**: **Parcialmente Implementada / Bloqueada por Dependência Externa**.
- **Comportamento Verificado**:
  - Os 4 perfis de qualidade (`CAR_STEREO`, `DJ_REKORDBOX`, `ARCHIVE_LOSSLESS`, `DAILY_USE`) estão bem especificados no código.
  - A interface gráfica NiceGUI renderiza o seletor de perfis e a fila de processamento.
- **Divergências e Problemas Encontrados**:
  1. *Dependência Quebrada do FFmpeg*: O binário `ffmpeg` não está instalado no PATH do Windows.
  2. *Falha de Pós-Processamento no `yt-dlp`*: O `TrackDownloader` define o pós-processador `FFmpegExtractAudio` para MP3 320k. Na ausência do executável, o download do áudio não converte para `.mp3`.
  3. *Evidência Físico-Comportamental*: O arquivo real presente em `downloads\Download Manual - daft punk.webm` (5 MB) permaneceu como `.webm` porque o pós-processamento falhou. Como `downloader.download_track` verifica se `final_mp3.exists()`, a rotina falha silenciosamente e retorna `None`, não atualizando o `local_path` da faixa no banco.
  4. *Zero Cobertura de Testes*: Nem o `TrackDownloader` nem a rotina `convert_with_profile` possuem testes automatizados.

---

### 2.3 Audio Inspector
- **Arquivos**: [`app/engines/audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_quality.py), [`app/ui/pages/audio_inspector.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/audio_inspector.py), [`tests/test_audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/tests/test_audio_quality.py).
- **Classificação Técnica**: **Parcialmente Implementada / Falsos Positivos em Formatos WebM**.
- **Comportamento Verificado**:
  - Inspeciona arquivos físicos utilizando a biblioteca `mutagen`, extraindo codec, bitrate, sample rate, bit depth e canais para MP3, FLAC e WAV.
  - Possui heurísticas para sinalizar discrepâncias de extensão e bitrates excessivamente baixos (<400 kbps) em arquivos rotulados como Lossless.
- **Divergências e Problemas Encontrados**:
  1. *Falso Positivo de Corrupção em Arquivos WebM*:
     - Submetemos o arquivo real baixado pelo `yt-dlp` (`downloads/Download Manual - daft punk.webm`) ao `AudioQualityEngine().inspect_file()`.
     - **Resultado obtido**:
       ```text
       Codec: webm | Bitrate: 0 | Sample Rate: 44100 | Corrupted: True
       Notes: ['Cabeçalho de áudio inválido ou corrompido.']
       ```
     - O Mutagen nativo não reconhece contêineres Matroska/WebM sem bibliotecas adicionais, classificando erroneamente áudios baixados do YouTube como "corrompidos".
  2. *Inoperância em Bibliotecas Baseadas em Nuvem*:
     - O método `scan_library_quality` descarta qualquer faixa sem `local_path` (`if not t.local_path: continue`).
     - Executado sobre o banco real atual (13 faixas Deezer com prévias de streaming), o relatório retornou: `total_analyzed: 13, valid_files: 0, corrupted_files: 0, suspect_files: 0`.

---

### 2.4 Playlist Health
- **Arquivos**: [`app/engines/playlist_health.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/playlist_health.py), [`app/ui/pages/playlist_health_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/playlist_health_page.py), [`tests/test_playlist_health.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/tests/test_playlist_health.py).
- **Classificação Técnica**: **Implementada e Funcional (em regras de acervo) / Parcial em correções externas**.
- **Comportamento Verificado**:
  - Diagnosticou com sucesso anomalias em 7 categorias: duplicatas, arquivos com caminho físico quebrado, capas faltantes, álbuns não preenchidos, durações suspeitas (<30s ou >20min), faixas sem vínculo com provedores e versões ao vivo misturadas em repertório de estúdio.
  - **Comprovação com o banco de dados real**: A execução do motor sobre as 13 faixas da biblioteca identificou pontuação de saúde de **96.9%** e sinalizou corretamente 2 faixas com versões ao vivo misturadas (*"A Dança (Ao Vivo)"* e *"Vida Louca, Bela e Curta (Ao Vivo)"*).
  - O método de reparo em lote `remove_broken_paths_batch` limpa os campos `local_path` inválidos com sucesso.
- **Divergências e Problemas Encontrados**:
  1. *Reparo de Capas Não Testado*: `fix_missing_covers_batch` realiza consultas assíncronas à API do iTunes, mas não possui testes automatizados nem isolamento contra timeouts ou indisponibilidade de rede.
  2. *Falso negativo de duplicata sem duração*: Se duas versões idênticas tiverem o campo `duration_ms` nulo, a correspondência fuzzy pode ser ignorada dependendo do threshold.

---

### 2.5 Smart Sync
- **Arquivos**: [`app/engines/device_sync.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/device_sync.py), [`app/ui/pages/smart_sync_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/smart_sync_page.py), [`tests/test_device_sync.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/tests/test_device_sync.py).
- **Classificação Técnica**: **Implementada e Funcional (para arquivos locais)**.
- **Comportamento Verificado**:
  - `generate_sync_plan` audita o diretório do dispositivo, calcula o espaço livre via `shutil.disk_usage`, identifica arquivos que já foram sincronizados por tamanho e mapeia arquivos novos e órfãos.
  - `execute_sync` realiza cópia atômica com arquivo temporário (`.tmp_sync`) antes da substituição final, evitando arquivos corrompidos em caso de desconexão do pen drive durante a gravação.
  - Gera playlists `.m3u` com caminhos relativos sanitizados para sistemas de arquivos FAT32/exFAT.
- **Divergências e Problemas Encontrados**:
  1. *Descarte Silencioso de Faixas em Nuvem*: Músicas que não possuem arquivo físico local (`local_path`) são descartadas do plano sem alerta explícito ao usuário na tela de sincronização.
  2. *Resíduo de Pastas Vazias*: A opção `delete_orphans` exclui os arquivos órfãos, mas não remove as pastas vazias (`[Artista]/[Álbum]`) que continuam ocupando a árvore do dispositivo.

---

### 2.6 Music Discovery
- **Arquivos**: [`app/engines/music_discovery.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/music_discovery.py), [`app/ui/pages/discovery_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/discovery_page.py), [`tests/test_music_discovery.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/tests/test_music_discovery.py).
- **Classificação Técnica**: **Parcialmente Implementada / Heurística Frágil**.
- **Comportamento Verificado**:
  - Integração funcional com `UserHistory` para auditoria de eventos (`played`, `recommended`, `added`, `rejected`).
  - Faixas marcadas como rejeitadas são excluídas com sucesso de todas as seções recomendadas.
  - A busca externa no Deezer (`get_external_recommendations`) consulta a API aberta com sucesso e retorna faixas reais com links de prévia de áudio de 30 segundos.
  - A seção "Baús do Acervo (Deep Cuts)" resgata faixas não tocadas (`play_count == 0`).
- **Divergências e Problemas Encontrados**:
  1. *Heurística Fixa na Primeira Faixa do Acervo*:
     - A Seção 1 ("Você Provavelmente Vai Gostar") define estaticamente `ref = clean_library[0]` (linha 145), ignorando histórico de escuta recente ou artistas prediletos.
  2. *Falha de Geração de Seção Vazia (0 Faixas)*:
     - O método `find_similar_tracks_in_library` requer pontuação > 0 baseada em mesmo artista (+30), clave Camelot compatível (+25), BPM próximo (+20) ou gênero comum (+20).
     - Quando a faixa inicial `clean_library[0]` não possui BPM ou Clave preenchidos, **a pontuação de todas as outras faixas resulta em 0**.
     - **Comprovação com o banco de dados real**: A execução do motor gerou:
       ```text
       Total sections generated: 3
         Section: Você Provavelmente Vai Gostar (0 tracks)
         Section: Baús do Acervo (Deep Cuts) (8 tracks)
         Section: Novidades & Descobertas no Deezer (7 tracks)
       ```
     - A principal seção da interface é entregue vazia ao usuário devido a essa fragilidade.
  3. *Zero Testes do Feed Principal*: O método assíncrono `generate_discovery_feed` não possui testes automatizados.

---

## 3. Matriz de Avaliação das Funcionalidades Principais

| Funcionalidade | Estado de Implementação | Comportamento Real Comprovado | Testes Automatizados | Principais Riscos / Gargalos |
| :--- | :--- | :--- | :--- | :--- |
| **Smart DJ 2.0** | Parcialmente Funcional | Heurística regex e pontuação funcionando | 3 testes unitários | Bug de duplicação harmônica com faixas `id=None`; ausência de LLM. |
| **Download Studio** | Bloqueada | UI renderiza; perfis declarados | Zero testes | Falha de extração para MP3 por ausência de FFmpeg; deixa arquivos `.webm`. |
| **Audio Inspector** | Parcial | Análise Mutagen funcional para MP3/FLAC/WAV | 3 testes superficiais | Falso positivo de corrupção em WebM; inoperante sem arquivos locais. |
| **Playlist Health** | Funcional (regras de acervo) | Detecta anomalias reais e calcula score de saúde | 2 testes unitários | Busca de capas HD não testada; depende de APIs externas. |
| **Smart Sync** | Funcional (arquivos locais) | Cópia atômica, M3U relativo e auditoria de disco | 1 teste unitário | Ignora faixas sem arquivo local; deixa pastas órfãs. |
| **Music Discovery** | Parcial | Deezer API externa e Deep Cuts funcionando | 1 teste unitário | Seção "Você Vai Gostar" gerada vazia (0 faixas); heurística fixa em `library[0]`. |

---

## 4. O que Ainda Não Foi Examinado (Próximas Etapas)

- **Etapa 4**: Interface e reprodução (Theme Manager, Player, equalizador DSP, letras sincronizadas, OmniStats, DJ Mode, Advanced Search).
- **Etapa 5**: Auditoria de segurança e integridade (operações de arquivos, sanitização de subprocessos, injeções SQL e backups).
- **Etapa 6**: Consolidação final e relatório executivo.

---

## 5. Conclusão da Etapa 3

A auditoria técnica e comportamental individualizada das 6 funcionalidades principais do **OmniPlaylist 2.0** foi concluída sem qualquer modificação aos arquivos originais do projeto.

O relatório parcial desta etapa foi registrado com sucesso em `docs/auditoria/etapa_3_funcionalidades_principais.md`.

**Aguardando sua autorização para iniciar a ETAPA 4 — Interface e reprodução.**
