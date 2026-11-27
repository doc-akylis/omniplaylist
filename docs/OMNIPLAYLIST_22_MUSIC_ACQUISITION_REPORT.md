# OMNIPLAYLIST 2.2 — Universal Music Discovery & Automatic Acquisition Engine
## Relatório Técnico Final de Arquitetura, Segurança, Provedores e Verificação

---

## 1. Resumo Executivo

A evolução do **OmniPlaylist 2.1** para o **OmniPlaylist 2.2 — Universal Music Discovery & Automatic Acquisition Engine** transformou o **Download Studio** de um executor orientado a arquivos locais ou URLs manuais em um sistema completo de **descoberta paralela em múltiplas fontes, agrupamento por gravação e versão, comparação técnico-auditável anti-transcode, aquisição automática autorizada com aprovação comercial explícita, endurecimento de segurança e rastreabilidade criptográfica (SHA-256) e de proveniência**.

Toda a baseline da versão 2.0/2.1 (banco SQLite `omniplaylist.db`, motores `TechnicalAnalysisEngine`, `MusicalAnalysisEngine`, `AudioQualityIntelligenceEngine`, `UpgradeEngine`, `DownloadStudioEngine`, `PlaylistManagerEngine`, `DJIntelligenceEngine`, e SPA React Studio Dark) foi integralmente preservada, mantendo **100% dos 79 testes anteriores** passando junto aos **16 novos testes da v2.2** (**95/95 testes aprovados**).

---

## 2. Regra Arquitetural Central: Pesquisar != Baixar

O sistema separa rigorosamente todas as fontes externas em quatro categorias (`ProviderCategory` em `app/sources/base.py`):

1. **`DISCOVERY`**: pesquisa e enriquecimento de catálogos, lançamentos, ISRCs, MBIDs e versões, sem disponibilizar arquivo de áudio completo (ex.: MusicBrainz, Discogs, Spotify Web API).
2. **`PREVIEW_STREAMING`**: catálogo com prévia oficial curta (ex.: AAC/MP3 de 30s no iTunes Search API e Deezer Catalog API), **nunca** tratada como faixa completa nem elegível para aquisição automática.
3. **`AUTHORIZED_DOWNLOAD`**: plataformas e acervos com endpoints oficiais onde o detentor/licença autoriza explicitamente o download do arquivo de áudio (ex.: Internet Archive, Wikimedia Commons, Audius com `is_downloadable/downloadable=true`, Jamendo com `audiodownload_allowed=true`, SoundCloud com `downloadable=true`, Freesound).
4. **`COMMERCIAL_DELIVERY`**: integrações comerciais/B2B licenciadas para entrega paga ou sob contrato (7digital/MassiveMusic, The Rights Foundry, Qobuz Partner), obrigatoriamente bloqueadas em estado **`AWAITING_APPROVAL`** até aprovação explícita do usuário (`approve_and_start_job`).

---

## 3. Matriz Comparativa de Fontes e Capacidades

| Fonte / Provedor | Categoria | Pesquisa | Download Direto | Formatos Reais | Autenticação / Custo | Limites / Restrições | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Internet Archive Audio** (`internet_archive`) | `AUTHORIZED_DOWNLOAD` | Sim (`advancedsearch.php` + `/metadata/{id}`) | Sim (Acervo público / CC / etree) | FLAC, WAV, MP3 (original e `derivative`), OGG | Sem chave / Gratuito | Respeitar `licenseurl`; arquivos `source=derivative` são diferenciados do original | `IMPLEMENTADO E TESTADO` |
| **Wikimedia Commons** (`wikimedia_commons`) | `AUTHORIZED_DOWNLOAD` | Sim (MediaWiki Action API `filetype:audio`) | Sim (PD / CC0 / CC BY-SA) | FLAC, OGG, WAV, MP3 | Sem chave (exige `User-Agent`) / Gratuito | Atribuição via `extmetadata` | `IMPLEMENTADO E TESTADO` |
| **Audius API v1** (`audius`) | `AUTHORIZED_DOWNLOAD` | Sim (`GET /v1/tracks/search`) | Condicional (`is_downloadable`/`downloadable=true`) | MP3 / Original | Sem chave (`app_name`) / Gratuito | Se `downloadable=false`, classificado estritamente como `STREAMING_ONLY` | `IMPLEMENTADO E TESTADO` |
| **Jamendo API v3.0** (`jamendo`) | `AUTHORIZED_DOWNLOAD` | Sim (`GET /v3.0/tracks/`) | Condicional (`audiodownload_allowed=true` + URL) | MP3, OGG, FLAC | `JAMENDO_CLIENT_ID` opcional / Gratuito pessoal | Licença CC isolada **não** autoriza download (`NOT_DOWNLOADABLE` se `audiodownload_allowed=false`) | `IMPLEMENTADO E TESTADO` |
| **SoundCloud API** (`soundcloud`) | `AUTHORIZED_DOWNLOAD` | Sim (`GET /tracks`) | Condicional (`downloadable=true` + `download_url`) | WAV, FLAC, AIFF, MP3 | `SOUNDCLOUD_CLIENT_ID` opcional | Sem stream-ripping HLS; se `downloadable=false`, marcado como `STREAMING_ONLY` | `IMPLEMENTADO E TESTADO` |
| **Freesound API v2** (`freesound`) | `AUTHORIZED_DOWNLOAD` | Sim (`/apiv2/search/text/`) | Sim (CC / previews HQ; original via OAuth2) | WAV, FLAC, MP3, OGG | `FREESOUND_API_KEY` opcional / Gratuito CC | 60 req/min; orientado a stems/samples/áudio CC | `IMPLEMENTADO E TESTADO` |
| **iTunes Search API** (`itunes`) | `PREVIEW_STREAMING` | Sim | **Não** (apenas prévia 30s) | AAC 256 kbps (30s) | Sem chave / Gratuito | `PREVIEW_ONLY`, `downloadable=False` | `IMPLEMENTADO E TESTADO` |
| **Deezer Catalog API** (`deezer`) | `PREVIEW_STREAMING` | Sim | **Não** (apenas prévia 30s) | MP3 128 kbps (30s) | Sem chave / Gratuito | Termos proíbem download/offline da faixa integral | `IMPLEMENTADO E TESTADO` |
| **MusicBrainz + Cover Art Archive** (`musicbrainz`) | `DISCOVERY` | Sim (WS2 JSON + CAA) | **Não** | Metadados, ISRC, MBID, Capa | Sem chave (`User-Agent` obrigatório, 1 req/s) | Somente descoberta e metadados | `IMPLEMENTADO E TESTADO` |
| **Discogs Database API** (`discogs`) | `DISCOVERY` | Sim (`/database/search`) | **Não** | Metadados de edições/releases | `DISCOGS_TOKEN` opcional / 60 req/min | Catálogo físico/digital; sem arquivo de áudio | `IMPLEMENTADO E TESTADO` |
| **Spotify Web API** (`spotify`) | `DISCOVERY` | Sim (Client Credentials) | **Não** (proibido pelos Termos) | Metadados, ISRC, popularidade | `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` opcionais | Nunca fornece download de áudio | `IMPLEMENTADO E TESTADO` |
| **7digital / MassiveMusic** (`sevendigital`) | `COMMERCIAL_DELIVERY` | Sim (contrato B2B) | Condicional (compra/licença B2B) | FLAC 16/24-bit, MP3 320, AAC | `SEVENDIGITAL_API_KEY` + `SEVENDIGITAL_API_SECRET` | Requer contrato B2B e aprovação explícita antes de cobrança | `IMPLEMENTADO, MAS AGUARDANDO CREDENCIAIS` |
| **The Rights Foundry** (`rights_foundry`) | `COMMERCIAL_DELIVERY` | Sim (contrato B2B) | Condicional (licenciamento pago) | FLAC, WAV, MP3 | `RIGHTS_FOUNDRY_API_KEY` | Requer parceria B2B e aprovação explícita do usuário | `IMPLEMENTADO, MAS AGUARDANDO CREDENCIAIS` |
| **Qobuz Hi-Res Partner** (`qobuz`) | `COMMERCIAL_DELIVERY` | Sim (parceria oficial) | Condicional (`authorized_download_url`) | FLAC 16/24-bit até 192kHz | `QOBUZ_APP_ID` + `QOBUZ_USER_TOKEN` | Sem API pública gratuita; exige parceria e aprovação do usuário | `IMPLEMENTADO, MAS AGUARDANDO CREDENCIAIS` |
| **Apple MusicKit / TIDAL API** | Streaming Comercial | Pesquisa via API | **Não** | AAC / FLAC (streaming DRM) | Developer Program / Partner | Termos proíbem download permanente via API de terceiros (`TIDAL_CLIENT_ID`/`SECRET` previstos para futura descoberta) | `DOCUMENTADO, MAS NÃO INTEGRADO` |
| **Bandcamp / Beatport v4 / FMA / ccMixter** | Catálogo / Loja / CC | APIs restritas a parceiros ou legadas | Indisponível sem parceria formal | — | Contratos comerciais / legado | Não simulados nem submetidos a scraping proibido | `DOCUMENTADO, MAS NÃO INTEGRADO` |

---

## 4. Arquitetura Implementada na Versão 2.2

### 4.1 Camada de Adaptadores & Registro (`app/sources/`)
- `app/sources/base.py`: define `ProviderCategory`, `PermissionStatus`, `FormatOption`, `DownloadPermission`, `ProviderCapabilities`, `NormalizedTrackResult`, `GroupedRecording` e a classe abstrata `ProviderAdapter`.
- `app/sources/registry.py`: `MusicSourceRegistry` gerencia os 14 adaptadores, configurações não-secretas em `MusicProviderConfig` (habilitação/desabilitação e prioridade) e health checks sob demanda (`run_health_check`).
- `app/sources/adapters/`: adaptadores assíncronos independentes em `internet_archive.py`, `wikimedia_commons.py`, `audius.py`, `jamendo.py`, `soundcloud.py`, `freesound.py`, `catalog_adapters.py` e `commercial_adapters.py`.

### 4.2 Equivalência e Separação de Versões (`app/core/matcher.py`)
- `TrackMatcher.detect_version_type(title, album=None)` classifica versões em `original`, `live`, `remix`, `extended`, `radio_edit`, `remaster`, `acoustic`, `instrumental`, `demo`, `rerecording`, `clean`, `explicit`.
- `TrackMatcher.group_recordings(results)` agrupa candidatos equivalentes via ISRC, MBID ou similaridade RapidFuzz + tolerância de duração ($\pm 8\text{s}$) **exigindo igualdade exata de `version_type`**, impedindo que versões *Live*, *Remix* ou *Extended Mix* sejam misturadas à faixa original.

### 4.3 Comparador Técnico & Anti-Transcode (`app/engines/source_quality_comparator.py`)
- `SourceQualityComparator` avalia separadamente **Identidade**, **Qualidade Técnica** e **Confiabilidade/Autorização**, aplicando o gate obrigatório `is_candidate_downloadable`.
- Candidatos marcados com `suspected_transcode=True` ou `origin_classification="SUSPECTED_TRANSCODE"` sofrem penalização de `-48` pontos (`ComparatorWeights.transcode_penalty`), garantindo que **FLAC Lossless verificado > MP3 320 original > FLAC suspeito de transcodificação lossy**, além de apontar separadamente `best_authorized`, `best_free`, `best_commercial` e `best_quality_overall`.

### 4.4 Busca Paralela com Isolamento de Falhas & Cache (`app/engines/music_search_engine.py`)
- `MusicSearchEngine` consulta todos os adaptadores habilitados em paralelo via `asyncio.gather` com `asyncio.wait_for` individual, `AsyncRateLimiter` por provedor, retry controlado para erros transitórios, cache TTL em memória e auditoria persistida em `MusicSearchSession`.
- Falhas ou timeouts em um subconjunto de provedores são isolados em `provider_statuses` sem abortar os resultados das demais fontes.

### 4.5 Aquisição Automática, Aprovação Comercial & Fila Única (`app/engines/acquisition_engine.py` + `download_studio.py`)
- `AcquisitionEngine` suporta os modos `ASK_BEFORE_PAID`, `AUTO_BEST_SOURCE`, `FREE_AUTHORIZED_ONLY` e `MANUAL_SOURCE_SELECTION`.
- Fontes gratuitas autorizadas (`ALLOWED_FREE`) seguem para o `DownloadStudioEngine` único (validação `ffprobe`, conversão FFmpeg por perfil, tagging Mutagen, substituição atômica com backup, `AudioQualityIntelligenceEngine` com análise espectral STFT/SciPy e atualização do Quality Dashboard).
- Fontes comerciais (`ALLOWED_COMMERCIAL_REQUIRES_APPROVAL` ou `requires_payment=True`) ficam obrigatoriamente retidas em estado **`AWAITING_APPROVAL`**, bloqueadas inclusive contra execução direta em `DownloadStudioEngine.run_job`, até aprovação explícita via `approve_and_start_job` / `POST /api/acquisition/jobs/{job_id}/approve`.
- Cada decisão gera registro auditável em `AcquisitionRecord`.

### 4.6 Segurança & Proveniência Estruturada (`app/core/security.py` + `download_studio.py`)
- **Anti-SSRF (`validate_external_url`)**: bloqueia `localhost`, `.local`, `.internal`, `169.254.169.254`, `metadata.google.internal`, faixas privadas/loopback/link-local (IP literal e resolução DNS), além de validar **cada salto de redirecionamento HTTP manualmente** (`follow_redirects=False`, limite de 5 hops) em `AuthorizedSourceProvider.acquire`.
- **Anti-Path Traversal (`safe_join_path`)**: garante que arquivos de staging, saída e backup permaneçam estritamente dentro dos diretórios configurados.
- **Assinatura Binária & Limite (`validate_audio_magic_bytes`, `MAX_DOWNLOAD_BYTES`)**: inspeciona magic bytes reais (`fLaC`, `RIFF/WAVE`, `FORM/AIFF`, `OggS`, `ID3`/ADTS, `ftyp`, `Opus`) para rejeitar HTML, JSON, XML e executáveis, impondo limite de 250 MB.
- **Integridade & Proveniência (`compute_sha256`, `AudioProvenance`)**: calcula SHA-256 real do arquivo final e persiste separadamente `declared_metadata_json`, `extracted_metadata_json`, `inferences_json`, `license_info`, `source_item_id` e `verification_status`.
- **Higiene de Credenciais**: chaves opcionais são gravadas exclusivamente em `.env` local (`POST /api/sources/credentials` com whitelist `ALLOWED_ENV_CREDENTIAL_KEYS`), jamais no SQLite nem expostas em respostas da API.

---

## 5. Banco de Dados, Endpoints REST e Interface React

- **Banco de Dados (`omniplaylist.db`):** migrado de forma idempotente mantendo 13 tabelas intactas (`unifiedtrack`, `playlist`, `playlisttracklink`, `devicesyncprofile`, `userhistory`, `backuprecord`, `usersettings`, `audioprovenance`, `downloadjob`, `audioprocessinghistory`, `musicproviderconfig`, `musicsearchsession`, `acquisitionrecord`), preservando integralmente os dados reais (**14 faixas, 3 playlists, 17 vínculos**), com backup prévio verificado em `backups/omniplaylist_backup_20261127_172312.zip`.
- **Novos Endpoints (`app/api/v22_routes.py`):**
  - `GET /api/sources`, `PATCH /api/sources/{provider_id}`, `POST /api/sources/{provider_id}/health-check`, `POST /api/sources/credentials`
  - `POST /api/discovery/search`, `POST /api/discovery/search/batch`
  - `POST /api/acquisition/auto`, `POST /api/acquisition/batch`, `POST /api/acquisition/jobs/{job_id}/approve`, `GET /api/acquisition/records`
- **Frontend React (`frontend/src/views/DownloadStudioView.tsx`):** evoluído para 3 abas integradas (*Descoberta & Aquisição*, *Fontes & Credenciais (.env)* e *URL / Local Manual*), exibindo agrupamento por versão, comparação de scores e risco de transcode, player de prévia 30s, fila persistente com botão **Aprovar Aquisição Comercial** para jobs `AWAITING_APPROVAL`, SHA-256 e painel de histórico de decisão/proveniência.

---

## 6. Resultados Reais de Build e Testes Executados

1. **Build do Frontend (`cd frontend; npm run build`):**
   - `tsc -b && vite build` concluído com código de saída `0` (`✓ 2177 modules transformed`, saída gerada em `app/ui/dist/index.html`).
2. **Suíte Completa de Testes (`.venv\Scripts\python.exe -m pytest -v`):**
   - **95 passed in 38.00s** (0 falhas, 0 erros, 0 skips):
     - Todos os **79 testes anteriores** das versões 2.0 e 2.1 aprovados sem regressão.
     - **6 testes de contrato** em `tests/test_v22_provider_contracts.py` validando payloads representativos dos 14 adaptadores e regras de download vs catálogo/prévia/B2B.
     - **10 testes funcionais, de segurança e E2E** em `tests/test_v22_discovery_acquisition.py` cobrindo SSRF direto e por redirecionamento, path traversal, rejeição de HTML/EXE por magic bytes, separação de versões no agrupamento, ranking anti-transcode no comparador, isolamento de falhas parciais e cache TTL, aquisição gratuita E2E até biblioteca/Quality Dashboard com `file_sha256` e proveniência, bloqueio e aprovação explícita de aquisição comercial e rotas FastAPI/higiene de credenciais com banco isolado em `tmp_path`.
3. **Verificação do Banco de Produção (`omniplaylist.db`):**
   - `13` tabelas presentes; contagens reais preservadas (`unifiedtrack: 14`, `playlist: 3`, `playlisttracklink: 17`).

---

## 7. Limitações Atuais e Próximos Passos

- **Credenciais Comerciais B2B e Opcionais:** Os adaptadores `sevendigital`, `rights_foundry` e `qobuz` (além de `jamendo`, `soundcloud`, `freesound`, `discogs` e `spotify`) foram validados com testes de contrato simulando payloads oficiais; uso em produção contra esses provedores depende da inserção das respectivas credenciais/contratos no `.env`.
- **Serviços Restritos a Parceiros:** Serviços como Bandcamp, Beatport v4, Apple MusicKit e TIDAL não possuem API pública aberta de download irrestrito; permanecem documentados sem bypass ou simulação.
- **Próximos Passos Sugeridos:**
  1. Conectar credenciais reais no painel *Fontes & Credenciais (.env)* e executar testes de integração ao vivo por provedor.
  2. Adicionar aquisição automática em lote diretamente a partir de playlists importadas com faixas ausentes (`missing_files` / *Missing Tracks Resolver*).
  3. Incorporar suporte a dumps locais offline do MusicBrainz/Discogs caso deseje busca em catálogo massivo sem latência de rede.
