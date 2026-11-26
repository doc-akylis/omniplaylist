# Relatório de Auditoria — Etapa 1: Inventário e Arquitetura

**Projeto:** OmniPlaylist 2.0  
**Data da Auditoria:** 04/11/2026  
**Auditor:** Antigravity (Auditoria Técnica Independente)  
**Status da Etapa:** Concluída com sucesso — Aguardando autorização para Etapa 2.

---

## 1. Visão Geral e Contexto da Auditoria

A presente auditoria técnica foi conduzida de forma independente diretamente sobre o código-fonte do **OmniPlaylist 2.0**, localizado em `C:\Users\Nicollas\Desktop\omniplaylist` (com espelho idêntico em `C:\Users\Nicollas\.gemini\antigravity\scratch\omniplaylist`).

O objetivo desta Etapa 1 é estabelecer o inventário exato de todos os artefatos, dependências, banco de dados, interfaces e integrações do projeto, separando o que foi efetivamente implementado do que é simulado (mock), parcial, não implementado ou dependente de softwares ausentes no sistema hospedeiro.

---

## 2. Inventário Físico do Repositório

### 2.1 Arquivos e Diretórios Raiz
| Caminho / Arquivo | Tamanho | Descrição Técnica |
| :--- | :--- | :--- |
| `main.py` | 3.236 B | Ponto de entrada. Inicializa o FastAPI, executa o ciclo de vida (`init_db`), registra 16 rotas NiceGUI e monta a aplicação. |
| `pyproject.toml` | 966 B | Metadados do pacote `omniplaylist` (v0.1.0), dependências do projeto e configurações de lint (`ruff`). |
| `.env.example` | 537 B | Modelo de variáveis de ambiente (portas, caminhos, credenciais Spotify, YTMusic, Amazon). |
| `iniciar.bat` | 340 B | Script em lote Windows para execução via `.venv\Scripts\python.exe main.py`. |
| `omniplaylist.db` | 102.400 B | Banco de dados SQLite persistente contendo dados reais de catálogo e configurações. |
| `README.md` | 3.342 B | Documentação introdutória da stack e instruções de uso. |
| `app/` | — | Pacote principal com os módulos `api`, `core`, `engines`, `providers` e `ui`. |
| `docs/` | — | Documentação técnica (`BLUEPRINT_EXPANSAO.md`, `PLANO_EVOLUCAO_2.0.md`, `RELATORIO_EVOLUCAO_OMNIPLAYLIST.md`). |
| `downloads/` | — | Diretório de armazenamento físico de downloads e exportações. Contém arquivo de áudio de teste `.webm` e XML de Rekordbox. |
| `backups/` | — | Diretório destinado aos snapshots compactados (`.zip`). Atualmente vazio. |
| `tests/` | — | Suíte de testes automatizados com `pytest`. Contém 14 arquivos `.py` (e não 16, conforme alegado no relatório prévio). |
| `.venv/` | — | Ambiente virtual Python 3.12.14 contendo 70 pacotes instalados via `uv`. |

---

## 3. Pilha Tecnológica e Dependências

### 3.1 Ambiente de Execução
- **Linguagem**: Python 3.12.14 (win32)
- **Gerenciador de Ambiente**: `uv` (ambiente virtual em `.venv`, sem `pip` isolado no ambiente; gerenciamento via wheel/hatchling)
- **Total de Distribuições Instaladas**: 70 pacotes

### 3.2 Principais Bibliotecas e Versões Reais Coletadas
- **Framework Web**: `fastapi==0.162.0`, `starlette==1.10.0`, `uvicorn==0.54.0`
- **Interface Gráfica Reativa**: `nicegui==3.19.0` (baseada em Vue 3, Quasar Framework e Tailwind CSS)
- **Persistência / ORM**: `sqlmodel==0.0.48`, `SQLAlchemy==2.1.6`, `pydantic==2.14.2`, `pydantic-settings==2.16.2`
- **Processamento de Áudio / Tags**: `mutagen==1.48.1`, `yt-dlp==2026.10.26`
- **Algoritmos de Equivalência**: `rapidfuzz==3.14.6`
- **Provedores de Streaming**: `spotipy==2.26.0`, `ytmusicapi==1.12.3`, `playwright==1.64.1`, `httpx==0.28.1`
- **Suíte de Testes**: `pytest==9.2.0`, `pytest-asyncio==1.4.1.post1`, `anyio==4.16.0`

### 3.3 Dependências Externas do Sistema Operacional
- **FFmpeg / ffprobe**: **AUSENTE NO SISTEMA**.
  - O comando `Get-Command ffmpeg` confirmou que o binário não está instalado no PATH do Windows nem no diretório do usuário.
  - *Impacto arquitetural*: Afeta diretamente a conversão para MP3 320kbps via `yt-dlp`, o cálculo de loudness LUFS no `LoudnessEngine` e `MetadataEngine`, e a transcodificação no `AudioQualityEngine`.

---

## 4. Arquitetura de Módulos e Componentes

### 4.1 Módulo `app/core/` (Modelos e Banco de Dados)
- `database.py`:
  - Configuração da engine SQLite (`check_same_thread=False`).
  - Função `migrate_db()`: inspeciona `PRAGMA table_info(unifiedtrack)` e adiciona dinamicamente 13 novas colunas via `ALTER TABLE` caso o banco já existisse.
  - Função `init_db()`: chama `SQLModel.metadata.create_all()` e executa a migração.
- `models.py`:
  - Modelos de tabela SQLModel:
    1. `UnifiedTrack`: 36 campos detalhados cobrindo metadados universais, IDs de provedores (Spotify, YTMusic, Amazon, Deezer), análise harmônica (BPM, chave Camelot, LUFS, ReplayGain), especificações acústicas (codec, bitrate, sample rate, bit depth, canais, tamanho) e letras sincronizadas.
    2. `Playlist`: Metadados da lista, provedor de origem e relação n-para-n.
    3. `PlaylistTrackLink`: Tabela de junção n-para-n com coluna `position`.
    4. `DeviceSyncProfile`: Perfis para sincronização USB e centrais automotivas.
    5. `UserHistory`: Tabela de auditoria para eventos de reprodução e recomendações.
    6. `BackupRecord`: Registro de integridade de backups com hash SHA256.
    7. `UserSettings`: Persistência de tema visual, cores, densidade e preferências.
  - Modelos Pydantic de transporte: `ExportConfig`, `MatchResult`.
- `matcher.py`:
  - Classe `TrackMatcher`: mecanismo híbrido de equivalência de músicas com sanitização regex de títulos, correspondência estrita por código ISRC (confiança 1.0) e correspondência fuzzy ponderada (60% título, 40% artista com RapidFuzz) atenuada por desvio de duração.

### 4.2 Módulo `app/providers/` (Integrações com Serviços Externos)
- `base.py`: Interface abstrata `BaseMusicProvider` (`authenticate`, `search_tracks`, `get_playlist`, `create_playlist`, `get_track`).
- `deezer.py` (**Implementado e funcional**):
  - Consome a API REST pública `https://api.deezer.com`.
  - Não requer autenticação/chaves para busca, leitura de ISRC, BPM, capas em alta definição e links de prévia de áudio de 30 segundos.
  - `create_playlist` retorna um ID simulado por exigir OAuth do usuário final.
- `spotify.py` (**Implementado, porém sem credenciais**):
  - Utiliza `spotipy.Spotify` com `SpotifyOAuth`.
  - Requer `SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET` no ambiente. Sem essas variáveis, métodos retornam listas vazias ou `False`.
- `ytmusic.py` (**Parcialmente funcional**):
  - Utiliza `ytmusicapi.YTMusic`.
  - Operação anônima funcional para busca e obtenção de dados públicos. Alterações e playlists privadas requerem `ytmusic_auth.json` (atualmente inexistente).
- `amazon.py` (**SIMULADO / PLACEHOLDER**):
  - Declarado como consumidor de Playwright / sessão de navegador, mas o código contém apenas retornos estáticos hardcoded (`Sample Track for...`, arrays vazios e strings pré-formatadas).

### 4.3 Módulo `app/engines/` (Motores de Processamento)
O diretório contém 23 arquivos de motores técnicos especializados:
1. `ai_curator.py`: Smart DJ 2.0. Pipeline estruturado em 8 etapas com parser heurístico de linguagem natural (BPM, décadas, gêneros, humor, artistas excluídos/obrigatórios), pontuação ponderada de candidatos e ordenação por harmonia Camelot ou curva de energia. *Nota: opera via heurística local e regex, sem chamada real a LLMs externos como Gemini/OpenAI*.
2. `analytics_engine.py`: OmniStats 2.0. Agrega dados de acervo, top artistas, distribuição de macro-gêneros, décadas e porcentagem offline.
3. `audio_analyzer.py`: Normalização de claves para a Roda de Camelot (1A-12B), avaliação de compatibilidade harmônica (mesma clave, vizinhos no círculo, alternância maior/menor) e ordenação para discotecagem. *Nota: não processa DSP de sinal; opera sobre os campos `bpm` e `key` existentes*.
4. `audio_quality.py`: Auditoria física de arquivos com `mutagen` e perfis de qualidade (Som Automotivo, DJ Rekordbox, Arquivo Lossless, Uso Cotidiano). Detecta inconsistências de extensão/codec e suspeitas de upscaling artificial. Aciona `ffmpeg` via subprocesso assíncrono.
5. `backup_engine.py`: Criação de pacotes `.zip` contendo o SQLite `omniplaylist.db` e `.env`, cálculo de hash SHA256, verificação de integridade abrindo conexão de teste em memória e restauração segura com snapshot prévio de salvaguarda.
6. `deduplicator.py`: Identificação de faixas duplicadas por ISRC e similaridade textual com RapidFuzz (título/artista) combinada com tolerância de duração. Permite mesclagem com preservação dos melhores metadados.
7. `device_sync.py`: Pré-auditoria de espaço em disco com `shutil.disk_usage`, detecção de arquivos novos, idênticos e órfãos, cópia atômica com nomes sanitizados para FAT32 e geração de `.m3u` relativo.
8. `direct_importer.py`: Raspagem de metadados de playlists públicas sem login (Spotify via embed/`__NEXT_DATA__`, YouTube via flat extraction `yt-dlp`, Deezer via API REST).
9. `dj_exporter.py`: Geração de XML estruturado no padrão oficial do Pioneer Rekordbox com metadados de BPM, clave Camelot e URIs de áudio.
10. `downloader.py`: Fila assíncrona de download via `yt-dlp` com conversão para MP3 via FFmpeg e injeção de tags ID3v2/capas via `mutagen`.
11. `exporter.py`: Exportação de playlists em quatro formatos universais: `.m3u8`, `.csv`, `.json` e `.xspf`.
12. `genre_engine.py`: Taxonomia musical e mapeamento hierárquico (subgênero ➔ macro-gênero) com construção de árvore de acervo.
13. `local_scanner.py`: Varredura recursiva de pastas no disco local (`.mp3`, `.flac`, `.wav`, `.m4a`, `.ogg`) com extração de tags via `mutagen` e indexação no SQLite.
14. `loudness_engine.py`: Medição de volume integrado LUFS e True Peak via filtro `ebur128` do FFmpeg e gravação de tags ReplayGain não-destrutivas. *Nota: na ausência do FFmpeg, retorna estimativa fallback simulada (-16.0 LUFS)*.
15. `lyrics_engine.py`: Integração com a API pública do LRCLIB para obtenção de letras sincronizadas (.LRC) e em texto puro, salvamento em disco e injeção na tag ID3 `USLT`.
16. `metadata_editor.py`: Edição em lote de tags com geração de prévia de diferenças (diff) e backups em memória para reversão (undo).
17. `metadata_engine.py`: Busca de capas em alta resolução (1400x1400) via iTunes Search API pública e cálculo de ReplayGain.
18. `music_discovery.py`: Feed de descoberta combinando músicas semelhantes no acervo por proximidade harmônica/BPM, resgate de faixas não ouvidas ("Deep Cuts"), novidades do Deezer e rastreamento de histórico no `UserHistory`.
19. `playlist_health.py`: Auditoria de saúde da biblioteca diagnosticando faixas corrompidas, capas faltantes, álbuns não especificados, vínculos órfãos e versões ao vivo misturadas em repertório de estúdio.
20. `scheduler_engine.py`: Motor leve de agendamento em segundo plano para tarefas periódicas.
21. `search_engine.py`: Motor de busca multi-dimensional permitindo filtragem simultânea por texto, artista, álbum, gênero, intervalo de anos, intervalo de BPM, clave Camelot, ISRC e arquivos offline.
22. `smart_links.py`: Geração de links universais Songlink / Odesli para compartilhamento entre diferentes plataformas de streaming.
23. `usb_exporter.py`: Exportador e organizador de pen drives em estrutura `[Artista]/[Ano - Álbum]/[Faixa].mp3` com sanitização estrita para sistemas de arquivos FAT32/exFAT.

### 4.4 Módulo `app/api/` (Endpoints REST e WebSockets)
- Rota WebSocket `/api/ws/progress`: streaming de eventos e telemetria para o cliente.
- Rotas REST:
  - `GET /api/tracks`: listagem paginada de faixas do SQLite.
  - `GET /api/playlists`: listagem de playlists cadastradas.
  - `GET /api/playlists/{playlist_id}`: detalhes de playlist e suas faixas vinculadas.
  - `POST /api/playlists/export`: exportação multiformato sob demanda.
  - `GET /api/audio/stream/{track_id}`: streaming de arquivo físico local via `FileResponse`.
  - `GET /api/lyrics/{track_id}`: recuperação e gravação sob demanda de letras sincronizadas via LRCLIB.
  - `GET /api/search/deezer`: proxy para busca aberta no catálogo do Deezer.
  - `POST /api/tracks/import_deezer/{deezer_id}`: importação direta de metadados do Deezer para o SQLite.

### 4.5 Módulo `app/ui/` (Interface do Usuário e Páginas)
- `layout.py`: Barra de navegação lateral fixa organizada em 4 grupos funcionais e barra de rodapé com o reprodutor.
- `theme_manager.py`: 7 temas pré-configurados (*Omni Green*, *Midnight Blue*, *Purple Neon*, *Crimson*, *AMOLED Black*, *Graphite*, *Light Studio*), arredondamento configurável e persistência na tabela `UserSettings`.
- `player.py`: Reprodutor integrado com reprodução de áudio local ou prévias de 30s do Deezer, modal de player expandido com capa grande e letras sincronizadas, e modal de equalizador gráfico de 10 bandas.
  - **ACHADO DE AUDITORIA CRÍTICO**: A equalização de 10 bandas é **SIMULADA**. O método `update_eq_band` apenas executa `console.log('EQ Band ' + f + 'Hz: ' + g + 'dB')` no navegador, não criando filtros BiquadFilterNode reais no Web Audio API.
- 16 Páginas registradas em `main.py`:
  1. `/`: Dashboard (`dashboard.py`) — *Apresenta o valor fixo "320 kbps / FLAC" como Qualidade Média*.
  2. `/library`: Biblioteca Unificada (`library_page.py`) — *Botões de importação Spotify e YTMusic não possuem manipuladores de clique (`on_click` ausente)*.
  3. `/search`: Busca Avançada (`search_page.py`).
  4. `/smart-dj`: Estúdio Smart DJ 2.0 (`smart_dj_page.py`).
  5. `/dj-mode`: Modo DJ Camelot (`dj_mode_page.py`).
  6. `/discovery`: Descoberta Musical (`discovery_page.py`).
  7. `/genres`: Estúdio de Gêneros (`genre_studio.py`).
  8. `/download-studio`: Estúdio de Downloads (`download_studio.py`).
  9. `/audio-inspector`: Diagnóstico Técnico de Áudio (`audio_inspector.py`).
  10. `/playlist-health`: Auditoria de Saúde (`playlist_health_page.py`).
  11. `/smart-sync`: Sincronizador USB (`smart_sync_page.py`).
  12. `/metadata-editor`: Editor de Tags em Lote (`metadata_editor_page.py`).
  13. `/export`: Hub de Exportações (`export_hub.py`).
  14. `/stats`: Painel Analítico OmniStats (`stats_page.py`).
  15. `/backup`: Central de Backups (`backup_page.py`).
  16. `/settings`: Configurações e Temas (`settings_page.py`).

---

## 5. Estado Atual do Banco de Dados (`omniplaylist.db`)

Inspeção direta realizada no banco SQLite do projeto revelou a seguinte distribuição real de registros:

| Tabela | Quantidade de Registros | Observações Técnicas |
| :--- | :--- | :--- |
| `unifiedtrack` | **13** | Faixas reais importadas do Deezer com ISRC, durações e URLs de prévia de 30s ativas. |
| `playlist` | **3** | Todas criadas durante testes do Smart DJ com o nome *"Smart DJ: indie rock animado para treino"*. |
| `playlisttracklink` | **17** | Vínculos de faixas associadas às 3 playlists de teste. |
| `devicesyncprofile` | **0** | Nenhum perfil de sincronização persistido. |
| `userhistory` | **7** | 6 eventos do tipo `added` e 1 evento do tipo `rejected`. |
| `backuprecord` | **0** | Nenhum registro de backup criado no banco. |
| `usersettings` | **1** | Registro de preferências com tema ativo *"Graphite"*. |

---

## 6. Problemas e Inconsistências Identificados na Etapa 1

1. **Equalizador DSP de 10 Bandas Simulado (Mock)**:
   - O arquivo `app/ui/player.py` (linhas 253-259) registra apenas um `console.log` no JavaScript do navegador:
     ```javascript
     window.applyEqGain = window.applyEqGain || function(f, g) {
         console.log('EQ Band ' + f + 'Hz: ' + g + 'dB');
     };
     ```
   - O documento `docs/RELATORIO_EVOLUCAO_OMNIPLAYLIST.md` alega erroneamente que *"O equalizador gráfico de 10 bandas se comunica com o Web Audio API no navegador"*. Na realidade, nenhum nó de áudio real do Web Audio API é instanciado.

2. **Provedor Amazon Music Simulado (Mock)**:
   - O arquivo `app/providers/amazon.py` possui apenas implementações placeholder com dados estáticos codificados diretamente no corpo do método (`Sample Track for...`), não havendo automação real com Playwright.

3. **Ausência do Binário FFmpeg no Sistema Operacional**:
   - O comando `ffmpeg` não está presente no PATH do ambiente Windows.
   - O motor `LoudnessEngine` ativa automaticamente um modo fallback retornando valores simulados fixos (`integrated_lufs=-16.0`, `true_peak_dbfs=-1.2`), e o `TrackDownloader` não consegue pós-processar arquivos de vídeo/áudio do YouTube para MP3 320k.

4. **Botões de Interface Não Funcionais (Sem Manipulador)**:
   - Na página `app/ui/pages/library_page.py` (linhas 34-35), os botões `"Importar Spotify"` e `"Importar YT Music"` foram renderizados sem nenhuma propriedade `on_click`, sendo elementos visuais inoperantes.

5. **Métrica Estática no Dashboard**:
   - Na página `app/ui/pages/dashboard.py` (linha 56), o valor de qualidade média está fixado textualmente como `"320 kbps / FLAC"`, independentemente das características reais das faixas presentes no banco.

6. **Divergência na Contagem de Arquivos de Teste**:
   - O relatório anterior (`RELATORIO_EVOLUCAO_OMNIPLAYLIST.md`, linha 146) afirma a existência de **16 arquivos de teste**. No entanto, a pasta `tests/` contém exatamente **14 arquivos**.

7. **Provedor Spotify Inoperante por Falta de Configuração**:
   - As credenciais de API (`SPOTIFY_CLIENT_ID` e `SPOTIFY_CLIENT_SECRET`) não estão configuradas no ambiente local, inviabilizando qualquer sincronização privada com o serviço.

8. **Uso de Método Depreciado**:
   - O arquivo `app/engines/scheduler_engine.py` (linha 43) utiliza `datetime.utcnow()`, método depreciado a partir do Python 3.12 em favor de `datetime.now(timezone.utc)`.

---

## 7. O que Ainda Não Foi Examinado (Próximas Etapas)

A presente etapa restringiu-se ao **Inventário e Arquitetura**. Ficam pendentes para as etapas subsequentes:
- **Etapa 2**: Análise detalhada dos relacionamentos relacionais, execução efetiva da suíte de testes com `pytest`, apuração real de testes coletados, aprovados, reprovados e verificação de testes rasos/mockados.
- **Etapa 3**: Auditoria comportamental individualizada dos 6 motores centrais: Smart DJ, Download Studio, Audio Inspector, Playlist Health, Smart Sync e Music Discovery.
- **Etapa 4**: Auditoria comportamental de interface, reprodução de mídia, temas e telas especializadas.
- **Etapa 5**: Auditoria de segurança, integridade de arquivos, injeção em subprocessos e operações no banco de dados.
- **Etapa 6**: Consolidação final e elaboração do resumo executivo.

---

## 8. Conclusão da Etapa 1

O inventário e mapeamento da arquitetura técnica do **OmniPlaylist 2.0** foram totalmente finalizados sem modificação dos arquivos originais do projeto.

O relatório parcial desta etapa foi registrado com sucesso neste documento.

Aguardando autorização do usuário para iniciar a **ETAPA 2 — Banco de dados e testes**.
