# 🚀 OmniPlaylist 2.0 — Plano de Evolução e Auditoria

## 1. Diagnóstico da Auditoria Inicial
- **Ambiente**: Python 3.12 no `.venv`, 64 pacotes instalados.
- **Suíte de Testes Original**: 19 testes passando (`pytest` 9.2.0).
- **Banco de Dados**: SQLite com SQLModel (`UnifiedTrack`, `Playlist`, `PlaylistTrackLink`).
- **Estado dos Motores**: Módulos básicos funcionais; necessidade de expansão de modelos para suportar inspeção de áudio, perfis de qualidade, auditoria de integridade, histórico de usuário e temas.

## 2. Roteiro de Execução em Fases

| Fase | Escopo | Arquivos Chave |
| :--- | :--- | :--- |
| **Fase 1** | Modelos & Schema SQLModel 2.0 | `app/core/models.py`, `app/core/database.py` |
| **Fase 2** | Smart DJ 2.0 (Curadoria & 8 Estágios) | `app/engines/ai_curator.py`, `app/ui/pages/smart_dj_page.py` |
| **Fase 3** | Download Studio (Perfis & Qualidade Real) | `app/engines/audio_quality.py`, `app/ui/pages/download_studio.py` |
| **Fase 4** | Audio Inspector (Inspeção Profunda da Biblioteca) | `app/ui/pages/audio_inspector.py` |
| **Fase 5** | Playlist Health (Auditoria & Correção em Lote) | `app/engines/playlist_health.py`, `app/ui/pages/playlist_health_page.py` |
| **Fase 6** | Smart Sync (Sincronização Segura de Dispositivos) | `app/engines/device_sync.py`, `app/ui/pages/smart_sync_page.py` |
| **Fase 7** | Music Discovery & Histórico | `app/engines/music_discovery.py`, `app/ui/pages/discovery_page.py` |
| **Fase 8** | OmniStats 2.0 (Analytics Avançado) | `app/engines/analytics_engine.py`, `app/ui/pages/stats_page.py` |
| **Fase 9** | Personalização Visual & Gerenciador de Temas | `app/ui/theme_manager.py`, `app/ui/pages/settings_page.py` |
| **Fase 10** | Dashboard Personalizável (Início) | `app/ui/pages/dashboard.py` |
| **Fase 11** | Player Avançado (Mini, Expandido, DSP EQ 10 bandas) | `app/ui/player.py`, `app/ui/layout.py` |
| **Fase 12** | Editor Avançado de Metadados em Lote | `app/engines/metadata_editor.py`, `app/ui/pages/metadata_editor_page.py` |
| **Fase 13** | Backup, Integridade & Histórico | `app/engines/backup_engine.py`, `app/ui/pages/backup_page.py` |
| **Fase 14** | Equalização & Normalização EBU R128 | `app/engines/loudness_engine.py` |
| **Fase 15** | Modo DJ (Preparação Profissional de Sets) | `app/ui/pages/dj_mode_page.py` |
| **Fase 16** | Busca Avançada Global | `app/engines/search_engine.py`, `app/ui/pages/search_page.py` |
| **Fase 17** | Navegação Global & Acabamento UI | `app/ui/layout.py`, `main.py` |
| **Fase 18** | Bateria de Testes Automatizados & Relatório Final | `tests/`, `docs/RELATORIO_EVOLUCAO_OMNIPLAYLIST.md` |
