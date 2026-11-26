# Relatório de Auditoria — Etapa 5: Segurança e Integridade

**Projeto:** OmniPlaylist 2.0  
**Data da Auditoria:** 05/11/2026  
**Auditor:** Antigravity (Auditoria Técnica Independente)  
**Status da Etapa:** Concluída com sucesso — Aguardando autorização para Etapa 6 (Consolidação Final).

---

## 1. Visão Geral da Etapa

A presente **Etapa 5** realizou uma auditoria técnica de segurança da informação, integridade de dados e resiliência arquitetural do **OmniPlaylist 2.0**, cobrindo 7 domínios críticos:

1. **Backups e Restauração de Dados** ([`app/engines/backup_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/backup_engine.py), [`app/ui/pages/backup_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/backup_page.py))
2. **Operações com Arquivos e Path Traversal** ([`app/api/routes.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py), [`app/engines/exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py), [`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py), [`app/engines/usb_exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/usb_exporter.py), [`app/engines/device_sync.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/device_sync.py))
3. **Execução de Subprocessos e Injeção de Comandos** ([`app/engines/audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_quality.py), [`app/engines/loudness_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/loudness_engine.py), [`app/engines/metadata_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/metadata_engine.py))
4. **Banco de Dados e Injeção de SQL** ([`app/core/database.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/database.py), [`app/engines/search_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/search_engine.py))
5. **Autenticação, Controle de Acesso e Gestão de Segredos** ([`main.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/main.py), [`app/config.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/config.py), `.env.example`, `.gitignore`)
6. **Integridade de Formatos e Injeção de Metadados (M3U / CSV / XML / SSRF)**
7. **Provedores Externos e Segurança de Rede** ([`app/providers/`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/providers/), [`app/engines/lyrics_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/lyrics_engine.py))

---

## 2. Auditoria Detalhada dos 7 Domínios

### 2.1 Backups e Restauração de Dados
- **Arquivos Auditados**: [`app/engines/backup_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/backup_engine.py), [`app/ui/pages/backup_page.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/ui/pages/backup_page.py).
- **Classificação Técnica**: **Implementada com Riscos de Integridade Concorrente e Exposição de Segredos**.
- **Comportamento Verificado**:
  - Geração de backup ZIP comprovada em execução real (`omniplaylist_backup_20261105_183455.zip`, 10.177 bytes).
  - Cálculo de hash SHA256 funcional (`4d97c52ac7f475dd35e4251ac5db78c881ea462e7037e501262f804591930112`) e persistência do registro na tabela `BackupRecord`.
  - Verificação prévia de integridade antes da restauração (`verify_backup_integrity`) confirmou a presença do arquivo e leitura de faixas.
- **Vulnerabilidades e Problemas de Engenharia Encontrados**:
  1. *Exposição de Credenciais no Arquivo ZIP (Vulnerabilidade de Confidencialidade)*:
     - No método `create_backup` (linhas 43-46), se o arquivo `.env` existir, ele é empacotado no ZIP:
       ```python
       env_file = Path(".env")
       if env_file.exists():
           zip_out.write(env_file, arcname=".env")
       ```
     - Arquivos `.env` contêm segredos corporativos e chaves privadas (`SPOTIFY_CLIENT_SECRET`). Ao compartilhar ou exportar backups de playlists, credenciais sensíveis vazam no arquivo compactado. Além disso, o método `restore_backup` sequer restaura o `.env`, empacotando-o inutilmente.
  2. *Cópia Crua de Banco SQLite em Execução (Risco de Inconsistência / Snapshot Corrompido)*:
     - A rotina de backup lê o arquivo `omniplaylist.db` diretamente do disco enquanto a aplicação e o pool de conexões do SQLAlchemy mantêm transações abertas. Em SQLite, transações em andamento ou registros pendentes no arquivo WAL (`-wal`) não são sincronizados de forma atômica dessa forma.
     - A prática segura exige o uso da API nativa `sqlite3.Connection.backup()` ou comando explícito `PRAGMA wal_checkpoint(TRUNCATE);`.
  3. *Verificação de Integridade Superficial*:
     - `verify_backup_integrity` executa unicamente `cursor.execute("SELECT count(*) FROM unifiedtrack")`. Essa instrução lê apenas o cabeçalho/primeira página da tabela principal. Não executa `PRAGMA integrity_check;`, deixando de detectar páginas de índices corrompidas, tabelas filhas corrompidas ou freelists inconsistentes.
  4. *Sobrescrita com Conexões Ativas e Resíduos no Disco*:
     - `restore_backup` cria uma cópia `omniplaylist.db.before_restore_HHMMSS` que permanece acumulando no diretório raiz sem política de descarte.
     - A restauração substitui o arquivo físico sem chamar `engine.dispose()`. Conexões ativas no pool do SQLAlchemy continuam apontando para descritores de arquivo antigos.
     - Caso o SQLite estivesse operando em WAL mode, os arquivos `omniplaylist.db-wal` e `omniplaylist.db-shm` não são limpos, fazendo com que o SQLite aplique o log WAL defasado sobre a base recém-restaurada, corrompendo a base.

---

### 2.2 Operações com Arquivos e Path Traversal
- **Arquivos Auditados**: [`app/api/routes.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py), [`app/engines/exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py), [`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py), [`app/engines/usb_exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/usb_exporter.py), [`app/engines/device_sync.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/device_sync.py).
- **Vulnerabilidades e Problemas de Engenharia Encontrados**:
  1. *Leitura Arbitrária de Arquivos no Endpoint de Streaming (CWE-22 / CWE-73)*:
     - Em [`app/api/routes.py#L92-L106`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py#L92-L106):
       ```python
       @router.get("/audio/stream/{track_id}")
       def stream_audio(track_id: int, session: Session = Depends(get_session)):
           ...
           file_path = Path(track.local_path)
           return FileResponse(path=file_path, media_type="audio/mpeg", filename=file_path.name)
       ```
     - Não há validação para garantir que `file_path.resolve()` esteja confinado dentro de `DOWNLOAD_DIR`. Se um registro tiver seu campo `local_path` apontando para qualquer arquivo do sistema operacional (ex: chaves SSH, arquivos de configuração ou bancos de dados), o endpoint `/api/audio/stream/{track_id}` fará a leitura e transmissão do arquivo arbitrário pela rede.
  2. *Escrita Arbitrária de Diretórios no Endpoint de Exportação*:
     - Em [`app/api/routes.py#L77-L90`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/api/routes.py#L77-L90) e [`app/engines/exporter.py#L19-L20`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py#L19-L20):
       ```python
       target_dir = Path(config.output_directory) if config.output_directory else self.default_output_dir
       target_dir.mkdir(parents=True, exist_ok=True)
       ```
     - O parâmetro `output_directory` é recebido sem sanitização ou restrição de escopo. Um chamador pode instruir a aplicação a criar diretórios e gravar arquivos fora do escopo do projeto em qualquer caminho com privilégios de gravação do usuário do sistema operacional.
  3. *Falha de Quebra em Caminhos Relativos (`Path.as_uri()`)*:
     - Em [`app/engines/exporter.py#L95`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py#L95) e [`app/engines/dj_exporter.py#L28`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/dj_exporter.py#L28), o código invoca diretamente `Path(t.local_path).as_uri()`.
     - **Comprovação em teste real**: `Path("./downloads/song.mp3").as_uri()` lança imediatamente `ValueError: relative path can't be expressed as a file URI`.
     - Como a configuração padrão de downloads é relativa (`./downloads`), a tentativa de exportar playlists com faixas locais para XSPF ou Rekordbox XML resulta em exceção não tratada e falha na exportação. O correto é chamar `Path(t.local_path).resolve().as_uri()`.
  4. *Sanitização Incompleta de Nomes de Arquivos no Windows / FAT32*:
     - No [`downloader.py#L77`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py#L77), apenas `/` e `\` são substituídos por `_`. Caracteres reservados pelo Windows como `:`, `*`, `?`, `"`, `<`, `>`, `|` não são removidos. Músicas com títulos contendo `:` causam erro no sistema de arquivos NTFS (`OSError: [Errno 22] Invalid argument`) ou acionam streams alternativos de dados (ADS).
     - Nomes reservados de dispositivo do DOS/Windows (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) não são filtrados em nenhum módulo de exportação ou download.
  5. *Risco de Destruição Acidental de Arquivos no SmartSync*:
     - No motor [`device_sync.py#L163-L172`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/device_sync.py#L163-L172), caso o usuário acione a sincronização com `delete_orphans=True` e aponte para um diretório comum (ex: pasta de Documentos, Músicas pessoais ou raiz de disco), todo e qualquer arquivo de extensão `.mp3`, `.flac`, `.wav`, etc., que não conste na playlist em sincronização é apagado permanentemente (`unlink`) sem envio para lixeira.

---

### 2.3 Execução de Subprocessos e Injeção de Comandos
- **Arquivos Auditados**: [`app/engines/audio_quality.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/audio_quality.py), [`app/engines/loudness_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/loudness_engine.py), [`app/engines/metadata_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/metadata_engine.py), [`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py).
- **Classificação Técnica**: **Boa Conformidade contra Command Injection / Fragilidade no Tratamento de Dependências Ausentes**.
- **Comportamento Verificado**:
  - Todas as chamadas a processos externos utilizam a API nativa assíncrona `asyncio.create_subprocess_exec` passando listas tipadas de argumentos (`*cmd`).
  - **Zero uso de `shell=True`** ou concatenação insegura de comandos em strings. Vetores clássicos de injeção de comandos via ponto-e-vírgula (`;`), pipes (`|`), `&&` ou crases em títulos e nomes de artistas são completamente neutralizados pela camada do sistema operacional.
  - O motor de download [`downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py) utiliza o pacote Python `yt_dlp.YoutubeDL` diretamente como biblioteca em um executor assíncrono em vez de chamar o binário CLI do yt-dlp via shell.
- **Problemas Encontrados**:
  - *Mascaramento de Falhas e Dados Falsos*: Como o `ffmpeg` não se encontra no PATH do sistema Windows, `loudness_engine.py` captura a falha e retorna medições com `status="Simulado (FFmpeg ausente)"` e LUFS fixo em `-16.0`, induzindo o usuário a acreditar que uma análise acústica real ocorreu. Em `metadata_engine.py#L75`, a exceção é descartada e silenciada via `print`.

---

### 2.4 Banco de Dados e Injeção de SQL
- **Arquivos Auditados**: [`app/core/database.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/database.py), [`app/engines/search_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/search_engine.py).
- **Classificação Técnica**: **Seguro contra SQL Injection / Inseguro em Integridade Relacional e Concorrência**.
- **Comportamento Verificado**:
  - As operações CRUD utilizam estritamente o ORM SQLModel/SQLAlchemy com parâmetros vinculados (`bind parameters`), eliminando vulnerabilidades de SQL Injection tradicional.
  - A rotina de migração [`migrate_db`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/core/database.py#L16-L49) executa `ALTER TABLE unifiedtrack ADD COLUMN ...`, porém os nomes e tipos das colunas são iterados a partir de um dicionário imutável e estático interno, sem recepção de dados do usuário.
  - O motor de busca [`GlobalSearchEngine`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/search_engine.py) opera filtrando objetos carregados na memória do processo Python, não gerando queries SQL dinâmicas vulneráveis.
- **Problemas Encontrados**:
  - *Chaves Estrangeiras Desativadas por Padrão*: O SQLite por definição inicializa conexões com chaves estrangeiras desligadas (`PRAGMA foreign_keys = 0`). O arquivo `database.py` não registra um hook `@event.listens_for(engine, "connect")` para emitir `PRAGMA foreign_keys = ON;`. A integridade referencial entre playlists e faixas depende exclusivamente do código Python.
  - *Ausência de WAL Mode*: O banco opera em modo journal rollback padrão. Em cenários concorrentes (múltiplas requisições FastAPI, conexões WebSocket e renderização NiceGUI em paralelo), o SQLite sofre frequentes exceções de bloqueio de escrita (`sqlite3.OperationalError: database is locked`).

---

### 2.5 Autenticação, Controle de Acesso e Gestão de Segredos
- **Arquivos Auditados**: [`main.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/main.py), [`app/config.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/config.py), `.env.example`.
- **Classificação Técnica**: **CRÍTICO: Ausência Total de Autenticação e Autorização**.
- **Problemas Encontrados**:
  1. *Servidor Exposto em `0.0.0.0` sem Autenticação (Achado Crítico)*:
     - Em [`app/config.py#L18`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/config.py#L18) e [`main.py#L145`](file:///C:/Users/Nicollas/Desktop/omniplaylist/main.py#L145), a aplicação é vinculada por padrão a `HOST = "0.0.0.0"`.
     - **Não existe nenhuma camada de autenticação, login, senha, token de API ou proteção de sessão**.
     - Qualquer dispositivo ou usuário na mesma rede local (Wi-Fi corporativo, doméstico ou rede compartilhada) que acessar o IP da máquina na porta 8000 ganha controle irrestrito sobre a aplicação: pode apagar históricos, restaurar backups (sobrescrevendo o banco), iniciar downloads arbitrários, visualizar metadados e acionar comandos.
  2. *Ausência de Arquivo `.gitignore` na Raiz do Projeto*:
     - **Não existe arquivo `.gitignore` no repositório**.
     - Como consequência, ao inicializar um controle de versão (`git init`), arquivos altamente sensíveis serão incluídos acidentalmente no commit:
       - O arquivo `.cache` gerado pelo Spotipy (contendo o token de acesso e refresh token do Spotify em texto claro).
       - Arquivos de credenciais locais: `ytmusic_auth.json` e `amazon_cookies.json`.
       - O arquivo `.env` contendo `SPOTIFY_CLIENT_SECRET`.
       - O próprio banco de dados de produção `omniplaylist.db`.
  3. *Armazenamento de Credenciais em Texto Claro*:
     - As integrações com YouTube Music (`YTMUSIC_AUTH_FILE`) e Amazon Music (`AMAZON_MUSIC_COOKIES_FILE`) operam sobre arquivos JSON em texto claro no disco, sem nenhuma camada de encriptação em repouso (como DPAPI no Windows ou SecretStorage no Linux).

---

### 2.6 Integridade de Formatos e Injeção de Metadados
- **Arquivos Auditados**: [`app/engines/exporter.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py), [`app/engines/downloader.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py).
- **Problemas Encontrados**:
  1. *Injeção de Metadados em Arquivos M3U / CRLF Injection*:
     - Em [`app/engines/exporter.py#L35-L44`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py#L35-L44):
       ```python
       lines.append(f"#EXTINF:{duration_sec},{t.artist} - {t.title}")
       lines.append(t.local_path or f"https://www.youtube.com/watch?v={t.ytmusic_id or ''}")
       ```
     - Os campos `t.artist` e `t.title` não têm caracteres de controle ou quebras de linha (`\r`, `\n`) filtrados. Uma faixa com quebra de linha no título permite que um atacante injete diretivas adicionais do protocolo M3U ou referências a executáveis locais maliciosos que serão abertos por reprodutores como VLC.
  2. *Injeção de Fórmulas em CSV (CSV Formula Injection — CWE-1236)*:
     - Em [`app/engines/exporter.py#L46-L63`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/exporter.py#L46-L63), as faixas são escritas em CSV utilizando `csv.writer`. O módulo `csv` padrão do Python não previne injeção de fórmulas.
     - Se o título ou artista de uma música iniciar com caracteres especiais como `=`, `@`, `+`, `-`, `|`, quando o usuário abrir a planilha no Microsoft Excel ou LibreOffice Calc, o aplicativo executará a expressão como uma fórmula ou comando DDE. Nenhuma sanitização de prefixo (como escape com apóstrofo `'`) é executada.
  3. *Potencial de SSRF em Download de Capas de Áudio*:
     - Em [`app/engines/downloader.py#L47-L50`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/downloader.py#L47-L50):
       ```python
       if track.cover_url:
           with httpx.Client(timeout=10) as client:
               resp = client.get(track.cover_url)
       ```
     - O cliente HTTP faz a requisição diretamente para qualquer URL informada em `track.cover_url`, sem validar se o esquema é HTTPS ou se o endereço pertence a provedores legítimos. Caso um metadado malicioso aponte para um IP de infraestrutura interna ou metadados de nuvem (`http://169.254.169.254/`), o servidor fará a requisição interna.

---

### 2.7 Provedores Externos e Segurança de Rede
- **Arquivos Auditados**: [`app/providers/deezer.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/providers/deezer.py), [`app/engines/lyrics_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/lyrics_engine.py), [`app/engines/metadata_engine.py`](file:///C:/Users/Nicollas/Desktop/omniplaylist/app/engines/metadata_engine.py).
- **Classificação Técnica**: **Implementada com Boas Práticas de TLS e Timeouts**.
- **Comportamento Verificado**:
  - Todas as chamadas para as APIs abertas do Deezer (`api.deezer.com`), LRCLIB (`lrclib.net`) e iTunes (`itunes.apple.com`) são realizadas estritamente sobre HTTPS criptografado.
  - A verificação de certificados SSL/TLS é mantida ativa (nenhum uso de `verify=False`).
  - Todas as instâncias de clientes HTTP (`httpx.AsyncClient`) definem timeouts explícitos (entre 8.0s e 10.0s), prevenindo o travamento indefinido de workers em cenários de degradação de rede externa.

---

## 3. Matriz de Avaliação dos Domínios de Segurança (Etapa 5)

| Domínio de Segurança | Estado Técnico | Nível de Risco | Vulnerabilidades e Fragilidades Identificadas |
| :--- | :--- | :--- | :--- |
| **Backups & Restauração** | Implementada / Inconsistente | **Alto** | Exposição do arquivo `.env` com segredos no ZIP; cópia crua de banco sem `sqlite3.backup`; integridade superficial; resíduos de arquivos cópia na raiz. |
| **Operações com Arquivos** | Parcial / Vulnerável | **Alto** | Leitura de arquivos arbitrários via `/api/audio/stream/{track_id}`; `Path.as_uri()` quebra com caminhos relativos; sanitização incompleta de nomes no Windows; `SmartSync` apaga órfãos permanentemente. |
| **Subprocessos** | Implementada e Segura | **Baixo** | Uso correto de `create_subprocess_exec` sem shell; risco restrito a mascaramento de relatórios quando `ffmpeg` inexiste. |
| **Banco de Dados & SQL** | Implementada e Segura | **Médio** | Consultas parametrizadas (zero SQL Injection); ausência de `PRAGMA foreign_keys = ON;` e falta de WAL mode no SQLite. |
| **Autenticação & Controle** | **NÃO IMPLEMENTADA** | **CRÍTICO** | Bind padrão em `0.0.0.0` sem autenticação; ausência de `.gitignore` (risco de commit de chaves e banco); segredos e tokens salvos em texto claro. |
| **Integridade de Formatos** | Parcial / Frágil | **Médio** | Injeção CRLF em arquivos M3U; Injeção de Fórmulas em exportação CSV (CWE-1236); risco de SSRF no download de capas. |
| **Provedores Externos** | Implementada e Segura | **Baixo** | Conexões HTTPS com validação TLS ativa e timeouts bem definidos (8-10s); Amazon Provider permanece simulado. |

---

## 4. O que Ainda Não Foi Examinado (Próxima Etapa)

- **ETAPA 6 — Consolidação**:
  - Consolidação final de todas as evidências técnicas coletadas nas Etapas 1 a 5.
  - Produção do **Relatório Técnico Consolidado de Auditoria** e do **Resumo Executivo para Tomada de Decisão**.
  - Matriz global definitiva de conformidade por funcionalidade (Implementada, Parcial, Simulada, Não Implementada, Não Testada).
  - Roadmap técnico de remediação arquitetural, segurança e estabilidade.

---

## 5. Conclusão da Etapa 5

A auditoria de segurança, integridade, subprocessos, arquivos e autenticação foi finalizada com sucesso. Nenhuma linha de código original, banco de dados ou dependência do projeto foi alterada.

O relatório desta etapa encontra-se devidamente salvo em [`docs/auditoria/etapa_5_seguranca_e_integridade.md`](file:///C:/Users/Nicollas/Desktop/omniplaylist/docs/auditoria/etapa_5_seguranca_e_integridade.md).

**Aguardando sua autorização para iniciar a ETAPA 6 — Consolidação.**
