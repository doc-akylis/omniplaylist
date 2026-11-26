# Relatório de Auditoria — Etapa 2: Banco de Dados e Testes

**Projeto:** OmniPlaylist 2.0  
**Data da Auditoria:** 04/11/2026  
**Auditor:** Antigravity (Auditoria Técnica Independente)  
**Status da Etapa:** Concluída com sucesso — Aguardando autorização para Etapa 3.

---

## 1. Visão Geral da Etapa

Nesta Etapa 2, a auditoria concentrou-se na análise rigorosa de:
1. **Modelos, integridade relacional, restrições e migrações de banco de dados** no SQLite (`omniplaylist.db` e código em `app/core/`).
2. **Execução real da suíte de testes automatizados** com `pytest`.
3. **Apuração quantitativa exata** de testes coletados, aprovados, reprovados e ignorados.
4. **Auditoria qualitativa dos testes**, identificando testes superficiais, simulados, com falsos positivos ou insuficientes para validar o comportamento real das funcionalidades.

---

## 2. Auditoria de Banco de Dados, Modelos e Migrações

### 2.1 Modelos e Relacionamentos
O sistema define 7 tabelas SQLModel em [`app/core/models.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/models.py):

| Modelo / Tabela | Tipo | Chave Primária | Relações / Foreign Keys | Observação de Auditoria |
| :--- | :--- | :--- | :--- | :--- |
| `UnifiedTrack` | Tabela | `id` (INTEGER) | N:N com `Playlist` via `PlaylistTrackLink` | Possui 36 colunas. Campos acústicos (`energy`, `integrated_lufs`, `codec`) existem na tabela mas raramente são preenchidos por fluxos de entrada. |
| `Playlist` | Tabela | `id` (INTEGER) | N:N com `UnifiedTrack` via `PlaylistTrackLink` | Relacionamento reativo com `UnifiedTrack`. |
| `PlaylistTrackLink` | Tabela (Junção) | Composta (`playlist_id`, `track_id`) | FKs para `playlist.id` e `unifiedtrack.id` | Ação de chave estrangeira definida como `NO ACTION`. Não há `ON DELETE CASCADE`. |
| `DeviceSyncProfile` | Tabela | `id` (INTEGER) | Nenhuma | 0 registros no banco atual. |
| `UserHistory` | Tabela | `id` (INTEGER) | FK para `unifiedtrack.id` | Não possui relação declarada na classe `UnifiedTrack` para carregamento reverso. |
| `BackupRecord` | Tabela | `id` (INTEGER) | Nenhuma | 0 registros no banco atual. |
| `UserSettings` | Tabela | `id` (INTEGER) | Nenhuma | Tabela singleton. 1 registro persistido com tema *"Graphite"*. |

### 2.2 Integridade Relacional e Chaves Estrangeiras (ACHADO CRÍTICO)
- **Desativação de Chaves Estrangeiras no SQLite**:
  - A execução de `PRAGMA foreign_keys;` na conexão do banco retornou **`0`** (desativado).
  - No SQLite, o suporte a chaves estrangeiras é desabilitado por padrão. Para que restrições e integridade referencial sejam impostas, a conexão DEVE executar explicitamente `PRAGMA foreign_keys = ON;`.
  - Em [`app/core/database.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/database.py#L8-L13), a engine é configurada apenas com `connect_args = {"check_same_thread": False}`. Não há listeners do SQLAlchemy (`@event.listens_for(engine, "connect")`) ativando o pragma.
  - **Consequência direta**: O banco de dados opera em tempo de execução **sem qualquer imposição de integridade referencial**.
- **Ausência de Cascata de Deleção (Cascade Delete)**:
  - Nem os modelos SQLModel nem as tabelas no SQLite possuem regras de cascata (`ON DELETE CASCADE`).
  - Se uma faixa for removida de `unifiedtrack`, os registros em `playlisttracklink` e `userhistory` apontando para o `track_id` excluído permanecem órfãos no banco de dados.

### 2.3 Mecanismo de Migrações (`migrate_db`)
O sistema não utiliza ferramentas formais de migração de esquema (como Alembic):
- A função [`migrate_db()`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/database.py#L16-L49) inspeciona colunas existentes em `unifiedtrack` via `PRAGMA table_info(unifiedtrack)` e executa instruções brutas `ALTER TABLE unifiedtrack ADD COLUMN {col_name} {col_type}`.
- **Limitações arquiteturais identificadas**:
  1. Apenas a tabela `unifiedtrack` é verificada. Qualquer evolução de esquema em `playlist`, `userhistory`, `devicesyncprofile` ou `usersettings` é ignorada.
  2. Não há tabela de controle de versões de esquema (ex: `alembic_version`).
  3. Não é possível alterar tipos de colunas, renomear campos, remover colunas obsoletas ou criar novos índices dinamicamente caso a tabela já exista.

---

## 3. Execução dos Testes Automatizados

### 3.1 Comando Executado
```powershell
cd C:\Users\Nicollas\Desktop\omniplaylist
.\.venv\Scripts\pytest.exe -v --durations=0
```

### 3.2 Resultado Real da Execução
```text
============================= test session starts =============================
platform win32 -- Python 3.12.14, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Nicollas\Desktop\omniplaylist
configfile: pyproject.toml
plugins: anyio-4.16.0, asyncio-1.4.1.post1
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 34 items

tests/test_api.py::test_api_tracks_endpoint PASSED                       [  2%]
tests/test_api.py::test_api_playlists_endpoint PASSED                    [  5%]
tests/test_api.py::test_api_playlist_details_404 PASSED                  [  8%]
tests/test_api.py::test_all_ui_pages_render_successfully PASSED          [ 11%]
tests/test_audio_quality.py::test_quality_profiles PASSED                [ 14%]
tests/test_audio_quality.py::test_inspect_missing_file PASSED            [ 17%]
tests/test_audio_quality.py::test_scan_library_quality PASSED            [ 20%]
tests/test_backup_engine.py::test_backup_create_verify_and_restore PASSED [ 23%]
tests/test_database.py::test_sqlite_models_and_relationships PASSED      [ 26%]
tests/test_device_sync.py::test_device_sync_plan_and_execution PASSED    [ 29%]
tests/test_engines.py::test_genre_engine PASSED                          [ 32%]
tests/test_engines.py::test_playlist_exporter PASSED                     [ 35%]
tests/test_engines.py::test_dj_exporter_rekordbox_xml PASSED             [ 38%]
tests/test_engines.py::test_usb_car_exporter PASSED                      [ 41%]
tests/test_engines.py::test_audio_analyzer_camelot PASSED                [ 44%]
tests/test_engines.py::test_ai_curator PASSED                            [ 47%]
tests/test_engines.py::test_deduplicator PASSED                          [ 50%]
tests/test_engines.py::test_analytics_engine PASSED                      [ 52%]
tests/test_engines.py::test_smart_links PASSED                           [ 55%]
tests/test_loudness_engine.py::test_loudness_engine_analysis_fallback PASSED [ 58%]
tests/test_matcher.py::test_isrc_exact_match PASSED                      [ 61%]
tests/test_matcher.py::test_fuzzy_match_similarity PASSED                [ 64%]
tests/test_matcher.py::test_unmatched_different_tracks PASSED            [ 67%]
tests/test_matcher.py::test_find_best_match_from_candidates PASSED       [ 70%]
tests/test_metadata_editor.py::test_metadata_editor_diff_and_apply PASSED [ 73%]
tests/test_music_discovery.py::test_music_discovery_history_and_taste PASSED [ 76%]
tests/test_playlist_health.py::test_playlist_health_audit PASSED         [ 79%]
tests/test_playlist_health.py::test_playlist_health_fix_broken_paths PASSED [ 82%]
tests/test_providers.py::test_deezer_provider_normalization PASSED       [ 85%]
tests/test_providers.py::test_lyrics_engine_lrc_save PASSED              [ 88%]
tests/test_search_engine.py::test_global_search_multi_criteria PASSED    [ 91%]
tests/test_smart_dj.py::test_smart_dj_unique_artists PASSED              [ 94%]
tests/test_smart_dj.py::test_smart_dj_excluded_artists PASSED            [ 97%]
tests/test_smart_dj.py::test_smart_dj_justifications PASSED              [100%]

======================== 34 passed, 1 warning in 7.48s ========================
```

### 3.3 Apuração Estatística dos Resultados
- **Total de Arquivos de Teste no Disco**: **14 arquivos** (e não 16, como informado na documentação anterior).
- **Total de Itens Coletados**: **34 testes**.
- **Aprovados (Passed)**: **34 testes** (100%).
- **Reprovados (Failed)**: **0 testes**.
- **Ignorados / Pulados (Skipped)**: **0 testes**.
- **Alertas (Warnings)**: **1 warning** (`PytestDeprecationWarning` de escopo de loop do `pytest-asyncio` e `StarletteDeprecationWarning` sobre `httpx` no `TestClient`).
- **Tempo Total**: 7,48 segundos.
- **Teste Mais Lento**: `tests/test_api.py::test_all_ui_pages_render_successfully` (1,28 segundos).

---

## 4. Auditoria Qualitativa dos Testes (Superficialidade, Mocks e Lacunas)

Embora 34 testes passem com 100% de sucesso, a auditoria minuciosa do código de cada teste revelou que **grande parte da suíte é superficial, testa constantes estáticas, opera sobre fallbacks simulados ou deixa comportamentos críticos completamente sem teste**.

### 4.1 Testes Simulados, Superficiais ou com Falsos Positivos

1. **`tests/test_loudness_engine.py` (Teste de Fallback Simulado)**:
   - O teste [`test_loudness_engine_analysis_fallback`](file:///C:/Users/Nicollas/Desktop/omniplaylist/tests/test_loudness_engine.py#L7-L15) cria um arquivo de texto arbitrário com a string `"audio bytes"`, invoca o motor e apenas assevera que o resultado não é nulo e o ganho não é nulo.
   - Como o `ffmpeg` não está instalado, o teste apenas valida que o método retorna a estimativa falsa de `-16.0 LUFS`. **A medição real de LUFS e True Peak via filtro EBU R128 NUNCA é testada**.
   - O método `apply_replay_gain_tag` (gravação de ID3) **não possui teste**.

2. **`tests/test_audio_quality.py` (Teste de Dicionários e Arquivo Inexistente)**:
   - `test_quality_profiles`: Assevera apenas chaves de dicionários em memória estáticos (`QualityProfile.CAR_STEREO["format"] == "mp3"`). Não testa nenhuma conversão de áudio.
   - `test_inspect_missing_file`: Passa um nome de arquivo inexistente para testar se marca `is_corrupted = True`.
   - `test_scan_library_quality`: Usa duas faixas fictícias sem arquivos reais.
   - **Resultado**: NENHUM arquivo de áudio real (.mp3, .flac, .wav) é analisado por Mutagen ou FFmpeg nos testes. Transcodificação (`convert_with_profile`) **não possui nenhum teste**.

3. **`tests/test_providers.py` (Provedores Externos sem Teste de Integração)**:
   - `test_deezer_provider_normalization`: Testa unicamente a função de normalização de dicionário `_to_unified_track(dict)`. Nenhuma chamada HTTP à API pública do Deezer é testada.
   - `test_lyrics_engine_lrc_save`: Apenas salva uma string formatada em um arquivo temporário no disco. A busca real de letras via API do LRCLIB (`fetch_lyrics`) e a injeção de tags ID3 `USLT` **não são testadas**.
   - **Spotify, YouTube Music e Amazon Music possuem ZERO testes**.

4. **`tests/test_backup_engine.py` (Restauração Declarada no Nome mas Não Executada)**:
   - O teste se chama `test_backup_create_verify_and_restore`.
   - Ele cria o zip e verifica a integridade. Porém, **a função `restore_backup()` NUNCA é chamada no teste**. O teste termina na linha 31 sem restaurar o banco de dados.

5. **`tests/test_metadata_editor.py` (Gravação Física Desativada no Teste)**:
   - O teste executa `engine.apply_batch_changes(..., update_files_on_disk=False)`.
   - A gravação física em arquivos de áudio via Mutagen foi propositalmente desabilitada no teste. Apenas a alteração dos atributos Python em memória foi testada.

6. **`tests/test_api.py` (Renderização de UI Apenas no Esqueleto HTML)**:
   - `test_all_ui_pages_render_successfully` faz `client.get()` nas 16 rotas NiceGUI e verifica se retornam código 200.
   - O NiceGUI sob o `TestClient` do Starlette retorna apenas o container HTML básico. O motor JavaScript Vue/Quasar do cliente não é executado, nenhum evento de clique é disparado e nenhum componente reativo é testado em profundidade.
   - Além disso, `test_api.py` **conecta diretamente ao banco de dados de produção `omniplaylist.db`**, sem fixture de isolamento para banco em memória.

7. **`tests/test_engines.py`**:
   - `test_smart_links`: Testa apenas a interpolação de strings `get_quick_universal_url`. A chamada à API Odesli (`fetch_platform_links`) não é testada.
   - `test_deduplicator`: Testa o agrupamento por similaridade, mas a operação de mesclagem no banco (`merge_tracks`) não é testada.

---

## 5. Mapeamento de Componentes e Métodos com ZERO Testes

A auditoria identificou módulos e métodos de alta complexidade que **não possuem nenhum teste automatizado**:

| Módulo / Arquivo | Linhas | Funcionalidade Não Testada |
| :--- | :--- | :--- |
| [`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py) | 141 | Fila de downloads, download assíncrono yt-dlp, extração de áudio FFmpeg e injeção de ID3 (`_apply_id3_tags`). |
| [`app/engines/local_scanner.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/local_scanner.py) | 102 | Varredura recursiva de diretórios, extração de metadados de arquivos físicos e indexação no SQLite. |
| [`app/engines/metadata_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/metadata_engine.py) | 103 | Busca de capas HD 1400x1400 no iTunes, cálculo de ReplayGain e aplicação de tags ID3. |
| [`app/engines/direct_importer.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/direct_importer.py) | 188 | Importação por URL pública sem login (Spotify oEmbed/`__NEXT_DATA__`, YouTube flat extraction, Deezer REST). |
| [`app/engines/scheduler_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/scheduler_engine.py) | 71 | Loop assíncrono de agendamento de tarefas em segundo plano. |
| [`app/providers/spotify.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/providers/spotify.py) | 112 | Autenticação Spotipy, busca, leitura e criação de playlists. |
| [`app/providers/ytmusic.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/providers/ytmusic.py) | 112 | Busca anônima, leitura de playlists públicas e criação de playlists via ytmusicapi. |
| [`app/providers/amazon.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/providers/amazon.py) | 56 | Todo o provedor (código é um esqueleto simulado). |
| [`app/core/database.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/database.py) (`migrate_db`) | 34 | Função de migração dinâmica de colunas no SQLite. |
| [`app/ui/player.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/player.py) | 267 | Máquina de estados do reprodutor, fila de reprodução, atalhos e modal expandido. |
| [`app/ui/theme_manager.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/theme_manager.py) | 210 | Troca dinâmica de temas, persistência de preferências no SQLite e aplicação de estilos. |

---

## 6. Síntese dos Achados da Etapa 2

| Item Auditado | Status Técnico Real | Evidência Verificada |
| :--- | :--- | :--- |
| **Integridade de Chaves Estrangeiras** | **Inexistente / Desativada** | `PRAGMA foreign_keys;` retorna `0`. Não há ativação no ciclo de conexão nem regras `ON DELETE CASCADE`. |
| **Migrações de Esquema** | **Parcial e Frágil** | `migrate_db()` cobre exclusivamente a tabela `unifiedtrack`. Não há versionamento formal nem suporte para outras tabelas. |
| **Volume de Testes Executados** | **34 Coletados / 34 Aprovados** | 100% de aprovação técnica sob o comando `pytest -v`. |
| **Profundidade Efetiva da Suíte** | **Baixa a Média** | 7 arquivos de teste testam apenas classes auxiliares em memória ou fallbacks simulados. 6 motores inteiros e todos os provedores privados possuem zero cobertura. |
| **Restauração de Backup** | **Não Testada** | `test_backup_create_verify_and_restore` nunca executa `restore_backup()`. |
| **Processamento de Áudio Real** | **Não Testado** | Nenhum teste executa decodificação, medição acústica ou transcodificação sobre arquivos de áudio reais. |

---

## 7. O que Ainda Não Foi Examinado (Próximas Etapas)

- **Etapa 3**: Auditoria comportamental individualizada dos 6 motores centrais: Smart DJ, Download Studio, Audio Inspector, Playlist Health, Smart Sync e Music Discovery.
- **Etapa 4**: Auditoria comportamental de interface, reprodução de mídia, temas e telas especializadas.
- **Etapa 5**: Auditoria de segurança, integridade de arquivos, injeção em subprocessos e operações no banco de dados.
- **Etapa 6**: Consolidação final e elaboração do resumo executivo.

---

## 8. Conclusão da Etapa 2

A auditoria de banco de dados e testes foi realizada com sucesso sem modificar nenhum arquivo original do projeto.

O relatório técnico desta etapa foi registrado com sucesso em `docs/auditoria/etapa_2_banco_e_testes.md`.

**Aguardando sua autorização para iniciar a ETAPA 3 — Funcionalidades principais.**
