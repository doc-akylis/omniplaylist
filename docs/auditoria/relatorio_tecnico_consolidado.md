# Relatório Técnico Consolidado de Auditoria — OmniPlaylist 2.0

**Projeto:** OmniPlaylist 2.0  
**Data da Auditoria:** 05/11/2026  
**Auditor Independente:** Antigravity (Auditoria Técnica Independente de Software)  
**Escopo da Auditoria:** Código-fonte integral, banco de dados, motores de áudio, integrações, interface de usuário, segurança da informação e suíte de testes automatizados.

---

## 1. Sumário Geral e Veredito Técnico

O **OmniPlaylist 2.0** é concebido como uma central unificada de gerenciamento de playlists, descoberta musical e estúdio de áudio, integrando múltiplos provedores de streaming (Spotify, YouTube Music, Deezer, Amazon Music), análise acústica harmônica e exportação física para dispositivos automotivos e softwares de DJ.

A presente auditoria técnica independente examinou o código-fonte em cinco etapas exaustivas com testes práticos de execução, sem qualquer alteração aos arquivos originais do projeto.

### Veredito Geral
> [!WARNING]
> **Status de Maturidade: PROTÓTIPO AVANÇADO COM COMPONENTES SIMULADOS E RISCOS CRÍTICOS DE SEGURANÇA.**
> 
> A aplicação possui motores de dados funcionais e um layout visual moderno em NiceGUI/Quasar. Entretanto, **não está pronta para uso em produção nem para distribuição a usuários finais**. Foram comprovados componentes críticos que operam como **placeholders simulados (Mocks)** — em especial o equalizador de 10 bandas e a integração com Amazon Music —, ausência completa de autenticação em rede aberta (`0.0.0.0`), vazamento de segredos no sistema de backup e dependências de sistema operacional ausentes que silenciosamente geram dados acústicos falsos.

---

## 2. Inventário Estrutural e Tecnológico

### 2.1 Métricas de Código e Arquivos
- **Linguagem Principal**: Python 3.12 (interpretador em `.venv/Scripts/python.exe`).
- **Framework Web / Interface**: FastAPI 0.115.4 integrado ao NiceGUI 2.5.0 (baseado em Vue.js / Quasar via WebSocket).
- **Camada de Dados**: SQLite 3 com ORM SQLModel 0.0.22 e SQLAlchemy 2.0.36.
- **Processamento de Áudio e Metadados**: Mutagen 1.47.0, yt-dlp 2024.10.22, Spotipy 2.24.0, ytmusicapi 1.8.2.
- **Total de Arquivos do Projeto**: 34 arquivos Python distribuídos em 4 camadas estruturais:
  - `app/core/`: 3 arquivos (`database.py`, `models.py`, `matcher.py`).
  - `app/engines/`: 13 motores de processamento e sincronização.
  - `app/providers/`: 5 provedores de streaming.
  - `app/ui/`: 13 módulos visuais (layout, player, gerenciador de temas e 14 páginas registradas).
  - Raiz: `main.py`, `app/config.py`.

### 2.2 Dependências Externas de Sistema Operacional
- **FFmpeg / FFprobe**: **AUSENTE NO SISTEMA**. O binário não foi instalado no PATH do Windows. Diversas rotinas acústicas que dependem do FFmpeg falham ou executam caminhos de código alternativos gerando dados falsos ou deixando arquivos temporários `.webm` abandonados no disco.

---

## 3. Matriz Global Definitiva de Conformidade

A classificação técnica obedece estritamente às evidências reais coletadas em tempo de execução:

| Componente / Módulo | Arquivos Principais | Classificação Técnica | Evidência Comportamental Comprovada em Teste |
| :--- | :--- | :--- | :--- |
| **Deezer Provider** | `app/providers/deezer.py` | **Implementada e Funcional** | Busca real na API REST pública; retornou metadados, capas em alta definição e prévias de 30s válidas. |
| **Lyrics Engine** | `app/engines/lyrics_engine.py` | **Implementada e Funcional** | Requisição à API LRCLIB retornou 2.503 caracteres com timestamps sincronizados (`[mm:ss.xx]`); grava `.lrc` no disco. |
| **OmniStats** | `app/engines/analytics_engine.py` | **Implementada e Funcional** | Agregação completa de estatísticas calculadas sobre `omniplaylist.db` (13 faixas, distribuição de gêneros e contadores). |
| **Modo DJ (Rekordbox XML)** | `app/engines/dj_exporter.py` | **Implementada e Funcional** | Gera XML compatível com Rekordbox com curva de BPM e chaves Camelot; validado com `xml.etree.ElementTree`. |
| **Exportação Multi-formato** | `app/engines/exporter.py` | **Implementada e Funcional** | Exportou playlists com sucesso nos formatos M3U8, CSV, JSON e XSPF. |
| **Busca Avançada (Motor)** | `app/engines/search_engine.py` | **Implementada e Funcional** | Filtragem combinada por 11 parâmetros em memória; validada com queries reais de texto e provedores. |
| **Editor de Metadados** | `app/engines/metadata_editor.py` | **Implementada e Funcional** | Aplica atualizações em lote no banco SQLite e grava tags ID3 em arquivos físicos MP3. |
| **Smart Sync** | `app/engines/device_sync.py` | **Implementada e Funcional** | Auditoria de espaço em disco, identificação de arquivos órfãos e cópia atômica com arquivos `.tmp_sync`. |
| **Audio Inspector** | `app/engines/audio_analyzer.py` | **Parcialmente Implementada** | Lê taxas de amostragem e canais com Mutagen em MP3; falha em WebM, classificando incorretamente faixas como corrompidas. |
| **Playlist Health** | `app/engines/playlist_health.py` | **Parcialmente Implementada** | Detecta duplicatas por ISRC e títulos aproximados; escores de qualidade distorcidos por falsos positivos em WebM. |
| **Smart DJ 2.0** | `app/engines/ai_curator.py` | **Parcialmente Implementada** | Algoritmo de transição harmônica inteligente funcional, mas quebra com perda de faixas se `track.id` for nulo. |
| **Music Discovery** | `app/engines/discovery_engine.py` | **Parcialmente Implementada** | Seção "Você Provavelmente Vai Gostar" retorna 0 faixas por falta de tratamento de faixas importadas sem BPM/Tom. |
| **Download Studio** | `app/engines/downloader.py` | **Parcialmente Implementada** | Baixa áudios via yt-dlp em WebM, mas não converte para MP3 320k por ausência do FFmpeg; não salva caminho no banco. |
| **Player Integrado** | `app/ui/player.py` | **Parcialmente Implementada** | Toca áudios locais e Deezer, mas música é interrompida na navegação por recarregamento do DOM; singleton global. |
| **Theme Manager** | `app/ui/theme_manager.py` | **Parcialmente Implementada** | 7 temas persistem no SQLite, mas cores Tailwind fixas no layout anulam o tema claro (*Light Studio*). |
| **Equalizador DSP 10 Bandas** | `app/ui/player.py#L249-L260` | **SIMULADA (MOCK)** | **Sliders apenas executam `console.log` no navegador.** Não existe Web Audio API, nós `BiquadFilterNode` nem efeito no áudio. |
| **Amazon Music Provider** | `app/providers/amazon.py` | **SIMULADA (MOCK)** | **Retorna dicionários estáticos (`"Sample Track for..."`).** Não há automação Playwright nem conexão com Amazon. |
| **Loudness Engine (EBU R128)** | `app/engines/loudness_engine.py` | **SIMULADA (Fallback)** | Devido à ausência do FFmpeg, retorna relatórios com LUFS fixo em `-16.0` sob status "Simulado (FFmpeg ausente)". |
| **Spotify Provider** | `app/providers/spotify.py` | **Não Testada (Sem Credenciais)** | Implementação via Spotipy bem estruturada, porém não testada contra a API real por ausência de chaves válidas. |
| **YouTube Music Provider** | `app/providers/ytmusic.py` | **Parcial (Modo Anônimo)** | Busca pública opera via ytmusicapi; criação de playlists e sincronização de conta não testadas por falta de cookies. |
| **Autenticação e Permissões** | `main.py`, `app/config.py` | **NÃO IMPLEMENTADA** | Não existe camada de login, sessão, controle de usuários ou proteção contra acesso anônimo na rede local. |

---

## 4. Avaliação da Cobertura de Testes Automatizados

### 4.1 Resultados da Execução
A suíte oficial de testes foi executada diretamente via `pytest` com o interpretador virtual do projeto:
- **Testes Coletados**: 34 testes unitários.
- **Aprovados**: 34 testes (100% de aprovação aparente).
- **Reprovados**: 0.
- **Tempo de Execução**: 2.76 segundos.

### 4.2 Análise Qualitativa e Fragilidades dos Testes
Apesar do índice de 100% de aprovação, a auditoria qualitativa revelou que a suíte é **superficial, excessivamente focada em testes sintéticos e possui enormes zonas cegas**:

1. **Testes Baseados em Fallbacks e Mocks**:
   - Em `test_audio_analyzer.py`, o teste `test_analyze_track_metadata_fallback` apenas valida que o método retorna valores zerados padrão quando o arquivo não existe.
   - Em `test_loudness_engine.py`, o teste `test_analyze_loudness_fallback` passa justamente porque o motor mascara a ausência do FFmpeg retornando o valor simulado `-16.0 LUFS`.
   - Em `test_audio_quality.py`, o teste assenta um dicionário de perfis estáticos sem acionar nenhuma conversão de áudio.
2. **Motores com ZERO Cobertura de Testes (Cobertura Nula)**:
   - `app/engines/downloader.py` (Download via yt-dlp e FFmpeg) — 0 testes.
   - `app/engines/backup_engine.py` (Criação de backup ZIP e restauração) — 0 testes.
   - `app/engines/metadata_editor.py` (Edição em lote e snapshots de undo) — 0 testes.
   - `app/engines/usb_exporter.py` (Sanitização FAT32 e exportação automotiva) — 0 testes.
   - `app/engines/device_sync.py` (Smart Sync e cálculo diferencial de armazenamento) — 0 testes.
   - `app/engines/lyrics_engine.py` (Integração LRCLIB e sincronização de letras) — 0 testes de rede.
3. **Provedores Privados com ZERO Testes**:
   - `app/providers/spotify.py` — 0 testes.
   - `app/providers/ytmusic.py` — 0 testes.
   - `app/providers/amazon.py` — 0 testes.
4. **Interface e Player com ZERO Testes**:
   - Nenhuma página NiceGUI, nenhum componente Quasar e nenhum método do `OmniPlayer` possui testes de renderização ou de ciclo de vida.

---

## 5. Principais Problemas Técnicos e Achados Críticos

### 5.1 O Equalizador Gráfico DSP de 10 Bandas é 100% Fictício (Mock)
- **Localização**: [`app/ui/player.py#L249-L260`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py#L249-L260)
- **Descrição Técnica**: A interface gráfica apresenta um modal completo com 10 faders verticais graduados de 31 Hz a 16 kHz com ganhos de -12 dB a +12 dB. No entanto, o manipulador de eventos JavaScript invocado pelo NiceGUI resume-se a:
  ```javascript
  window.applyEqGain = window.applyEqGain || function(f, g) {
      console.log('EQ Band ' + f + 'Hz: ' + g + 'dB');
  };
  ```
  **Não existe Web Audio API**, não há instanciamento de `AudioContext`, não há filtros `BiquadFilterNode` e não há conexão com o elemento HTML `<audio>`. Os controles deslizantes apenas poluem o console do desenvolvedor no navegador, sem produzir qualquer efeito sonoro real.

### 5.2 O Provedor Amazon Music é 100% Mock
- **Localização**: [`app/providers/amazon.py#L27-L56`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/providers/amazon.py#L27-L56)
- **Descrição Técnica**: Não há código de automação headless Playwright, nem requisições à Amazon. A busca retorna uma lista com uma faixa falsa estática (`"Sample Track for '{query}'"`), e os demais métodos retornam listas vazias ou strings prefixadas.

### 5.3 Ausência do Binário FFmpeg e Quebra em Cascata no Áudio
- **Localização**: Variáveis de ambiente do Windows / PATH
- **Impacto Sistêmico**:
  - O `yt-dlp` baixa o áudio do YouTube no formato Opus dentro de contêiner `.webm`. A pós-conversão para MP3 320k falha silenciosamente, abandonando arquivos `.webm` brutos no disco sem vincular à faixa no SQLite.
  - O Mutagen falha ao inspecionar contêineres `.webm`, acionando a flag `is_corrupted = True` e gerando falsos positivos graves de corrupção na biblioteca.
  - O `LoudnessEngine` devolve medições de ganho de volume fictícias (-16.0 LUFS fixo).
  - O `AudioQualityEngine.convert_with_profile` falha em todas as conversões de bitrate e formato para veículos e DJs.

### 5.4 Vulnerabilidade de Exposição Arbitrária de Arquivos (Path Traversal / CWE-22)
- **Localização**: [`app/api/routes.py#L92-L106`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py#L92-L106)
- **Descrição Técnica**: O endpoint `/api/audio/stream/{track_id}` obtém o valor da coluna `local_path` e devolve um `FileResponse(path=file_path)` diretamente, sem verificar se `file_path.resolve()` está contido no diretório autorizado (`DOWNLOAD_DIR`). Caso um registro aponte para um arquivo sensível do sistema operacional (ex: credenciais, chaves ou logs), o arquivo é baixado integralmente via streaming.

### 5.5 Servidor Exposto sem Autenticação em Rede Aberta (`0.0.0.0`)
- **Localização**: [`app/config.py#L18`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/config.py#L18) e [`main.py#L145`](file:///C:/Users/Nicollas/Desktop/omniplaylist/main.py#L145)
- **Descrição Técnica**: A aplicação sobe vinculada a `0.0.0.0:8000` sem nenhuma tela de login, sessão, token ou HTTP Basic Auth. Qualquer dispositivo conectado na mesma rede local tem acesso total e irrestrito ao acervo, podendo apagar dados, iniciar downloads, alterar metadados e acionar a restauração do banco SQLite.

### 5.6 Exposição de Credenciais no Sistema de Backup
- **Localização**: [`app/engines/backup_engine.py#L43-L46`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/backup_engine.py#L43-L46)
- **Descrição Técnica**: O arquivo ZIP de backup empacota automaticamente o arquivo `.env`. Se o usuário possuir credenciais como `SPOTIFY_CLIENT_SECRET` configuradas, esses segredos serão gravados no arquivo ZIP. Se o arquivo de backup for compartilhado ou sincronizado em nuvem não segura, as chaves privadas são expostas.

### 5.7 Injeção de Fórmulas em CSV (CWE-1236) e Injeção CRLF em M3U
- **Localização**: [`app/engines/exporter.py#L35-L64`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py#L35-L64)
- **Descrição Técnica**: Na exportação CSV, células que iniciam com `=`, `+`, `-`, `@` não são sanitizadas, permitindo execução de código DDE caso a planilha seja aberta no Excel. Na exportação M3U8, quebras de linha (`\n`, `\r`) em títulos e nomes de artistas não são filtradas, permitindo injeção de comandos de protocolo M3U.

### 5.8 Bug de Colapso Harmônico no Smart DJ 2.0
- **Localização**: [`app/engines/ai_curator.py#L302`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/ai_curator.py#L302)
- **Descrição Técnica**: A ordenação harmônica indexa faixas pelo seu identificador: `{s.track.id: s for s in scored}`. Se faixas em memória não estiverem persistidas no banco (`id=None`), todas as entradas colapsam na mesma chave `None`, resultando na perda de quase todas as faixas e retenção de duplicatas da última música avaliada.

### 5.9 Quebra de Reprodução Contínua na Navegação
- **Localização**: [`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py), [`main.py#L52-L130`](file:///C:/Users/Nicollas/Desktop/omniplaylist/main.py#L52-L130)
- **Descrição Técnica**: As páginas são registradas com `@ui.page()`, o que provoca recarregamento do DOM a cada navegação de menu pelo usuário. Isso destrói o elemento `<audio>` no navegador e interrompe imediatamente a reprodução de música.

### 5.10 Botões Mortos na Interface
- **Localização**: [`app/ui/pages/library_page.py#L79-L84`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/library_page.py#L79-L84)
- **Descrição Técnica**: Os botões visíveis de `"Importar Spotify"` e `"Importar YT Music"` não possuem manipulador de eventos `on_click` associado, sendo completamente inoperantes para o usuário.

---

## 6. Recomendações e Roadmap de Remediação Arquitetural

### Prioridade P0: Segurança e Estabilidade Crítica (Imediato)
1. **Confinamento de Rede**: Alterar `HOST` padrão em `app/config.py` de `0.0.0.0` para `127.0.0.1` até que uma camada robusta de autenticação/sessão seja introduzida.
2. **Correção de Path Traversal**: Validar em `/api/audio/stream/{track_id}` que `Path(track.local_path).resolve()` seja filho estrito de `settings.DOWNLOAD_DIR.resolve()`.
3. **Criação de `.gitignore`**: Adicionar imediatamente arquivo `.gitignore` ignorando `.env`, `.cache`, `*.db`, `*.db-*`, `ytmusic_auth.json`, `amazon_cookies.json` e `backups/`.
4. **Isolamento de Segredos no Backup**: Remover imediatamente o empacotamento de `.env` do método `create_backup` em `backup_engine.py`.
5. **Instalação e Validação do FFmpeg**: Integrar o binário `ffmpeg` ao PATH do ambiente ou embutir binários portáteis no projeto com rotina de checagem na inicialização (`shutil.which("ffmpeg")`).

### Prioridade P1: Correções de Funcionalidades e Motores (Curto Prazo)
1. **Implementação Real do Web Audio API**: Substituir o stub de `console.log` no equalizador de 10 bandas por uma cadeia real de filtros `BiquadFilterNode` conectados ao elemento `<audio>`.
2. **Correção do Smart DJ**: Refatorar `ai_curator.py` para usar índices baseados em ISRC ou índices de lista enumerados (`enumerate`), impedindo o colapso de faixas com `id=None`.
3. **Correção do Audio Inspector**: Adequar o inspetor para tratar arquivos `.webm` e formatos não-MP3 sem acusar falsos positivos de corrupção.
4. **Resolução de Caminhos URI**: Adicionar `.resolve()` antes de chamar `.as_uri()` em `exporter.py` e `dj_exporter.py` para compatibilidade com caminhos relativos.
5. **Ativação de Chaves Estrangeiras e WAL no SQLite**: Adicionar listener de conexão para executar `PRAGMA foreign_keys = ON;` e `PRAGMA journal_mode = WAL;`.

### Prioridade P2: Interface e Experiência do Usuário (Médio Prazo)
1. **Arquitetura de Áudio Persistente (SPA)**: Estruturar as rotas do NiceGUI dentro de uma casca SPA de página única (conteúdo dinâmico em containers), mantendo o rodapé do player imutável para não interromper o áudio.
2. **Sincronismo Dinâmico de Letras**: Conectar o evento `on_time_update` do player ao leitor de `.lrc` para realizar rolagem automática e destaque de texto estilo karaokê.
3. **Substituição de Classes Tailwind Hardcoded**: Ajustar `layout.py` e `theme.py` para consumir variáveis CSS dinâmicas baseadas no `theme_manager`, permitindo que temas claros funcionem corretamente.
4. **Ativação dos Botões de Importação**: Implementar os diálogos e rotinas reais de importação nos botões da Biblioteca.
