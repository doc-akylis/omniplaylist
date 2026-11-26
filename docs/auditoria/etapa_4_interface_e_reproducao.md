# Relatório de Auditoria — Etapa 4: Interface e Reprodução

**Projeto:** OmniPlaylist 2.0  
**Data da Auditoria:** 04/11/2026  
**Auditor:** Antigravity (Auditoria Técnica Independente)  
**Status da Etapa:** Concluída com sucesso — Aguardando autorização para Etapa 5.

---

## 1. Visão Geral da Etapa

Nesta Etapa 4, a auditoria concentrou-se na análise comportamental e técnica dos componentes visuais, de reprodução e de interação do **OmniPlaylist 2.0**:
1. **Theme Manager** ([`app/ui/theme_manager.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/theme_manager.py), [`app/ui/theme.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/theme.py), [`app/ui/pages/settings_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/settings_page.py))
2. **Player** ([`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py), [`app/ui/layout.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/layout.py), [`app/api/routes.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py))
3. **Equalizador Gráfico DSP de 10 Bandas** ([`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py))
4. **Letras Sincronizadas (.LRC)** ([`app/engines/lyrics_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/lyrics_engine.py), [`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py), [`app/ui/pages/library_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/library_page.py))
5. **OmniStats** ([`app/engines/analytics_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/analytics_engine.py), [`app/ui/pages/stats_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/stats_page.py))
6. **Modo DJ (DJ Mode)** ([`app/ui/pages/dj_mode_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/dj_mode_page.py), [`app/engines/audio_analyzer.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_analyzer.py), [`app/engines/dj_exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/dj_exporter.py))
7. **Busca Avançada (Advanced Search)** ([`app/engines/search_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/search_engine.py), [`app/ui/pages/search_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/search_page.py))

---

## 2. Auditoria Detalhada dos 7 Componentes

### 2.1 Theme Manager (Gerenciador de Temas)
- **Arquivos**: [`app/ui/theme_manager.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/theme_manager.py), [`app/ui/theme.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/theme.py), [`app/ui/pages/settings_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/settings_page.py).
- **Classificação Técnica**: **Implementada / Inconsistência com Classes Tailwind Estáticas**.
- **Comportamento Verificado**:
  - Disponibiliza 7 paletas completas: *Omni Green*, *Midnight Blue*, *Purple Neon*, *Crimson*, *AMOLED Black*, *Graphite* e *Light Studio*.
  - Persiste a seleção na tabela `UserSettings` do SQLite e recarrega na inicialização.
  - Injeta variáveis CSS no cabeçalho HTML e aplica `ui.colors()` para cores Quasar.
- **Problemas e Divergências Encontrados**:
  1. *Conflito com Cores Hardcoded no Layout*:
     - Em [`app/ui/layout.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/layout.py#L23-L27), as colunas principais possuem classes estáticas `bg-[#121212]` e `bg-[#000000]`.
     - Na área de conteúdo principal (linha 77), a classe é fixada como `bg-[#121212]`.
     - Caso o usuário selecione o tema claro (*Light Studio*, onde `dark = "#F8FAFC"`), a tela continua forçada em fundo cinza-escuro/preto.
  2. *Uso de Constante Estática em Vez de Propriedade Dinâmica*:
     - O arquivo `theme.py` define `CARD_STYLE = "bg-[#181818] ... border border-[#2A2A2A]"`.
     - Várias páginas (`dashboard.py`, `export_hub.py`, `genre_studio.py`, `stats_page.py`, `library_page.py`) importam `CARD_STYLE` estático em vez de consumir `theme_manager.card_style`, tornando os cartões imunes à troca de temas nessas páginas.

---

### 2.2 Player (Reprodutor Integrado)
- **Arquivos**: [`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py), [`app/ui/layout.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/layout.py), [`app/api/routes.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py).
- **Classificação Técnica**: **Parcialmente Funcional / Arquitetura Singleton Global com Interrupção na Navegação**.
- **Comportamento Verificado**:
  - Reproduz tanto arquivos locais via endpoint `/api/audio/stream/{track_id}` quanto amostras de 30 segundos da CDN pública do Deezer.
  - Controles centrais (play/pause, anterior, próximo, aleatório, repetição) atualizam o estado da fila em memória.
  - Modal do Player Expandido (`open_expanded_player`) renderiza capa grande em alta definição, especificações técnicas (BPM, Tom, Codec, Bitrate, ISRC) e área de letras.
- **Problemas e Divergências Encontrados**:
  1. *Interrupção de Áudio ao Trocar de Página*:
     - A aplicação não adota Single Page Application (SPA) para roteamento de conteúdo. As páginas são registradas via decoradores `@ui.page("/")`, `@ui.page("/library")`, etc.
     - Quando o usuário clica em qualquer link da sidebar, o navegador realiza recarregamento da página, destruindo o elemento HTML `<audio>` e **interrompendo a música imediatamente**.
  2. *Singleton Global sem Isolamento de Sessão*:
     - O reprodutor é uma única instância global no processo Python (`player = OmniPlayer()`).
     - Se múltiplos usuários ou abas acessarem a aplicação, eles compartilham o mesmo estado de fila (`self.queue`) e faixa atual (`self.current_track`), e as referências aos elementos visuais (`self.audio_el`, `self.cover_img`) são sobrescritas pela última página renderizada.
  3. *MIME Type Estático no Endpoint de Streaming*:
     - O endpoint `/api/audio/stream/{track_id}` força `media_type="audio/mpeg"` no `FileResponse`, mesmo quando o arquivo local for `.flac`, `.wav` ou `.ogg`.

---

### 2.3 Equalizador Gráfico DSP de 10 Bandas (ACHADO CRÍTICO)
- **Arquivo**: [`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py#L221-L265).
- **Classificação Técnica**: **SIMULADO / PLACEHOLDER (MOCK)**.
- **Comportamento Verificado**:
  - A interface gráfica do diálogo abre perfeitamente, exibindo 10 controles deslizantes verticais com frequências de 31 Hz a 16 kHz e escala de ganho de -12 dB a +12 dB.
  - Possui botões de reset ("Flat") e confirmação.
- **Evidência Irrefutável de Simulação**:
  - Ao inspecionar o método [`update_eq_band`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py#L249-L260), constatou-se que o código JavaScript executado é unicamente:
    ```javascript
    window.applyEqGain = window.applyEqGain || function(f, g) {
        // AudioContext filter hook
        console.log('EQ Band ' + f + 'Hz: ' + g + 'dB');
    };
    window.applyEqGain(freq, gain_val);
    ```
  - **Fato Técnico**: Não existe `AudioContext`, não há criação de nós `BiquadFilterNode`, não há captura de stream com `MediaElementAudioSourceNode` e não há conexão com o áudio que está tocando.
  - Mover os controles deslizantes apenas gera mensagens no console do navegador (`console.log`), sem produzir qualquer efeito acústico no áudio reproduzido.
  - A declaração no relatório anterior de que *"O equalizador gráfico de 10 bandas se comunica com o Web Audio API no navegador"* é falsa.

---

### 2.4 Letras Sincronizadas (.LRC)
- **Arquivos**: [`app/engines/lyrics_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/lyrics_engine.py), [`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py#L206-L218), [`app/api/routes.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py#L109-L132).
- **Classificação Técnica**: **Implementada na Busca e Salvamento / Incompleta na Reprodução Visual**.
- **Comportamento Verificado**:
  - Integração real com a API pública aberta do **LRCLIB** (`https://lrclib.net/api`).
  - **Comprovação em teste real**: A consulta para *"Bohemian Rhapsody"* do *Queen* recuperou com sucesso 2.503 caracteres contendo marcações de tempo precisas (ex: `[00:00.15] Is this the real life?`).
  - Os métodos `save_lrc_file` (gravação de arquivo `.lrc` no disco) e `embed_lyrics_to_audio` (incorporação na tag ID3 `USLT` com Mutagen) estão implementados.
- **Problemas e Divergências Encontrados**:
  1. *Ausência de Sincronização Dinâmica na Interface*:
     - Tanto no Player Expandido quanto no diálogo da Biblioteca, o conteúdo de `lyrics_synced` é simplesmente jogado como texto corrido dentro de um `ui.label` estático.
     - As marcações de tempo aparecem brutas na tela (ex: `[00:07.13] Caught in a landslide...`).
     - Não há rotina de leitura de `currentTime` do player, rolagem automática ou destaque de linha no estilo karaokê durante a execução do áudio.

---

### 2.5 OmniStats (Painel Analítico)
- **Arquivos**: [`app/engines/analytics_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/analytics_engine.py), [`app/ui/pages/stats_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/stats_page.py).
- **Classificação Técnica**: **Implementada e Funcional**.
- **Comportamento Verificado**:
  - O motor `AnalyticsEngine` agrega estatísticas reais do banco SQLite: total de faixas, tempo total de reprodução, ranking de artistas mais presentes com `Counter`, distribuição de gêneros com taxonomia hierárquica, distribuição de décadas, porcentagem de músicas offline e BPM médio.
  - **Comprovação em teste com o banco real**:
    ```text
    total_tracks: 13
    total_duration_minutes: 40.5
    top_artists: [('Link do Zap', 5), ('Mc Hariel', 2), ('chard la plaga', 2), ('Felix Zaltaio', 2), ('Lukão Mec', 1)]
    decade_distribution: {'Desconhecida': 13}
    offline_percentage: 0.0
    average_bpm: 0.0
    ```
  - A interface em `stats_page.py` trata ausência de dados adequadamente, renderizando barras de progresso proporcionais para gêneros e cartões modernos para décadas.

---

### 2.6 Modo DJ (DJ Mode)
- **Arquivos**: [`app/ui/pages/dj_mode_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/dj_mode_page.py), [`app/engines/audio_analyzer.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_analyzer.py), [`app/engines/dj_exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/dj_exporter.py).
- **Classificação Técnica**: **Implementada e Funcional (como ferramenta de preparação e exportação)**.
- **Comportamento Verificado**:
  - Permite carregar qualquer playlist ou todo o acervo.
  - Executa reordenação por curva gradual de BPM respeitando a compatibilidade harmônica da Roda de Camelot via `AudioAnalyzer.sort_playlist_for_dj`.
  - Exibe indicadores visuais por faixa: borda verde para transições compatíveis (mesmo tom, vizinho imediato +/- 1 ou chave relativa maior/menor) e amarela para divergência tonal.
  - **Exportação Rekordbox XML**: Gerou XML estruturado com sucesso, validado pelo parser `xml.etree.ElementTree` com schema `<DJ_PLAYLISTS Version="1.0.0">`, atributos de `AverageBpm` e `Tonality`.
- **Limitações Identificadas**:
  - Não executa mixagem contínua de áudio nem detecção de beatgrids (atua exclusivamente como planejador e exportador de sets).

---

### 2.7 Busca Avançada (Advanced Search)
- **Arquivos**: [`app/engines/search_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/search_engine.py), [`app/ui/pages/search_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/search_page.py).
- **Classificação Técnica**: **Implementada e Funcional (no motor) / Parcialmente Exposta na Interface**.
- **Comportamento Verificado**:
  - O motor `GlobalSearchEngine` aplica 11 critérios combinados (texto geral, artista, álbum, gênero, intervalo de anos, intervalo de BPM, chave Camelot, ISRC, arquivos offline, codec e provedor).
  - **Comprovação com o banco real**:
    - Busca textual `"Link do Zap"` retornou exatamente 5 faixas.
    - Filtro por provedor `provider="deezer"` retornou exatamente 13 faixas.
    - Filtro por `only_offline=True` retornou 0 faixas (compatível com a ausência de downloads locais).
- **Problema de Interface Encontrado**:
  - A interface visual em `search_page.py` oferece campos para texto, artista, álbum, gênero, chave, BPM, anos e offline, mas **não expõe os filtros de codec, bitrate mínimo nem provedor**, subutilizando a capacidade implementada no motor.

---

## 3. Matriz de Avaliação dos Componentes da Etapa 4

| Componente | Estado de Implementação | Comportamento Real Comprovado | Testes Automatizados | Principais Riscos / Inconsistências |
| :--- | :--- | :--- | :--- | :--- |
| **Theme Manager** | Implementada | Troca de temas e persistência em banco | Zero testes diretos | Cores hardcoded no layout e cartões imunes à troca de tema claro. |
| **Player** | Parcialmente Funcional | Toca prévias de 30s Deezer e áudios locais | Zero testes | Música interrompida na navegação de páginas; singleton global compartilhado. |
| **Equalizador DSP** | **SIMULADO (MOCK)** | Sliders renderizam visualmente | Zero testes | Apenas emite `console.log` no navegador. Não há filtros Web Audio API reais. |
| **Letras Sincronizadas** | Parcial (busca OK, UI estática) | API do LRCLIB retorna letras com timestamps | 1 teste unitário de arquivo | Letras despejadas como texto estático com colchetes; sem sincronismo visual. |
| **OmniStats** | Implementada e Funcional | Agregação completa de acervo e estatísticas | 1 teste unitário | Decadas/gêneros aparecem desconhecidos se metadados não forem preenchidos. |
| **Modo DJ** | Implementada e Funcional | Sequenciamento Camelot e Rekordbox XML | 2 testes unitários | Ferramenta puramente de planejamento e exportação XML (sem DSP). |
| **Advanced Search** | Funcional (motor completo) | 11 filtros combinados com precisão | 1 teste unitário | Filtros de codec e provedor omitidos no formulário da página. |

---

## 4. O que Ainda Não Foi Examinado (Próximas Etapas)

- **Etapa 5**: Auditoria de segurança e integridade (operações de arquivos locais, execução de subprocessos FFmpeg/yt-dlp, injeção de parâmetros, segurança de conexões e autenticação).
- **Etapa 6**: Consolidação final e relatório executivo com matriz conclusiva de conformidade.

---

## 5. Conclusão da Etapa 4

A auditoria de interface, reprodução e ferramentas interativas foi finalizada sem qualquer modificação aos arquivos originais do projeto.

O relatório parcial desta etapa foi registrado com sucesso em `docs/auditoria/etapa_4_interface_e_reproducao.md`.

**Aguardando sua autorização para iniciar a ETAPA 5 — Segurança e integridade.**
