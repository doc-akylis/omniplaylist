import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Compass,
  DownloadCloud,
  KeyRound,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Volume2,
  XCircle,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type {
  AcquisitionRecordItem,
  AudioProfile,
  CandidateScoreBreakdown,
  CandidateSourcePayload,
  DiscoverySearchResponse,
  DownloadJob,
  GroupedRecording,
  MusicSourceInfo,
  UnifiedTrack,
  UpgradeCheckResult,
} from '../types/music';

interface DownloadStudioViewProps {
  tracks: UnifiedTrack[];
  wsLastEvent: Record<string, unknown> | null;
  onRefreshTracks: () => void;
}

const JOB_STATUS_COLOR: Record<string, string> = {
  COMPLETED: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  DOWNLOADING: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
  CONVERTING: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  ANALYZING: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  PAUSED: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  AWAITING_APPROVAL: 'bg-amber-500/25 text-amber-200 border-amber-400/60',
  FAILED: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
  CANCELLED: 'bg-slate-600/20 text-slate-400 border-slate-600/40',
  QUEUED: 'bg-slate-700/30 text-slate-200 border-slate-600',
};

const PERMISSION_BADGE: Record<string, string> = {
  ALLOWED_FREE: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  ALLOWED_COMMERCIAL_REQUIRES_APPROVAL: 'bg-amber-500/20 text-amber-200 border-amber-400/50',
  PREVIEW_ONLY: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  STREAMING_ONLY: 'bg-slate-600/30 text-slate-300 border-slate-500/40',
  REQUIRES_CREDENTIALS: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  NOT_DOWNLOADABLE: 'bg-slate-700/40 text-slate-400 border-slate-600/40',
  UNAVAILABLE: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
};

const CATEGORY_LABEL: Record<string, string> = {
  AUTHORIZED_DOWNLOAD: 'Download Autorizado',
  COMMERCIAL_DELIVERY: 'Entrega Comercial B2B',
  PREVIEW_STREAMING: 'Catálogo & Prévia 30s',
  DISCOVERY: 'Descoberta & Metadados',
};

export const DownloadStudioView: React.FC<DownloadStudioViewProps> = ({
  tracks,
  wsLastEvent,
  onRefreshTracks,
}) => {
  const [activeTab, setActiveTab] = useState<'discovery' | 'providers' | 'manual'>('discovery');

  // Common Studio State
  const [profiles, setProfiles] = useState<AudioProfile[]>([]);
  const [jobs, setJobs] = useState<DownloadJob[]>([]);
  const [records, setRecords] = useState<AcquisitionRecordItem[]>([]);
  const [sources, setSources] = useState<MusicSourceInfo[]>([]);
  const [credentialKeys, setCredentialKeys] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Tab 1: Discovery & Automatic Acquisition
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState('track');
  const [onlyDownloadable, setOnlyDownloadable] = useState(false);
  const [acqMode, setAcqMode] = useState<string>('ASK_BEFORE_PAID');
  const [acqProfile, setAcqProfile] = useState<string>('ORIGINAL');
  const [discoveryRes, setDiscoveryRes] = useState<DiscoverySearchResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [playingPreviewUrl, setPlayingPreviewUrl] = useState<string | null>(null);

  // Tab 2: Credentials (.env only, write-only form)
  const [credInputs, setCredInputs] = useState<Record<string, string>>({});
  const [healthResults, setHealthResults] = useState<Record<string, string>>({});

  // Tab 3: Manual URL / Local Conversion (v2.1 preserved)
  const [selectedTrackId, setSelectedTrackId] = useState<string>('');
  const [profile, setProfile] = useState<string>('FLAC_ARCHIVE');
  const [targetSr, setTargetSr] = useState<string>('');
  const [sourceUrl, setSourceUrl] = useState<string>('');
  const [localSourcePath, setLocalSourcePath] = useState<string>('');
  const [title, setTitle] = useState<string>('');
  const [artist, setArtist] = useState<string>('');
  const [codec, setCodec] = useState<string>('flac');
  const [bitrateKbps, setBitrateKbps] = useState<string>('');
  const [originCls, setOriginCls] = useState<string>('LOSSLESS_SOURCE');
  const [isPreview, setIsPreview] = useState<boolean>(false);
  const [allowOverride, setAllowOverride] = useState<boolean>(false);
  const [upgradeCheck, setUpgradeCheck] = useState<UpgradeCheckResult | null>(null);

  const loadData = async () => {
    const [pRes, jRes, sRes, rRes] = await Promise.all([
      apiClient.getAudioProfiles(),
      apiClient.getDownloadJobs(),
      apiClient.getMusicSources(),
      apiClient.getAcquisitionRecords(25),
    ]);
    setProfiles(pRes.profiles || []);
    setJobs(jRes.jobs || []);
    setSources(sRes.providers || []);
    setCredentialKeys(sRes.credential_keys || []);
    setRecords(rRes.records || []);
  };

  useEffect(() => {
    void loadData();
  }, []);

  useEffect(() => {
    if (wsLastEvent?.type === 'download_job_update') {
      void apiClient.getDownloadJobs().then((res) => setJobs(res.jobs || []));
      void apiClient.getAcquisitionRecords(25).then((res) => setRecords(res.records || []));
      const jobObj = wsLastEvent.job as { status?: string } | undefined;
      if (jobObj?.status === 'COMPLETED') {
        onRefreshTracks();
      }
    }
  }, [wsLastEvent, onRefreshTracks]);

  const runDiscoverySearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setSearching(true);
    setFeedback(null);
    try {
      const res = await apiClient.discoverySearch({
        query: searchQuery.trim(),
        search_type: searchType,
        only_downloadable: onlyDownloadable,
        limit_per_provider: 8,
      });
      setDiscoveryRes(res);
    } catch (err) {
      setFeedback(`Erro na pesquisa multi-fonte: ${(err as Error).message}`);
    } finally {
      setSearching(false);
    }
  };

  const triggerGroupAcquisition = async (
    group: GroupedRecording,
    preferredProviderId?: string,
    preferredSourceItemId?: string,
  ) => {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await apiClient.acquireAuto({
        query: `${group.artist} ${group.title}`,
        mode: preferredProviderId ? 'MANUAL_SOURCE_SELECTION' : acqMode,
        profile: acqProfile,
        preferred_provider_id: preferredProviderId || null,
        preferred_source_item_id: preferredSourceItemId || null,
        group_payload: group as unknown as Record<string, unknown>,
      });
      setFeedback(
        res.job
          ? `Job #${res.job.id}: ${res.status} — ${res.reason}`
          : `${res.status}: ${res.reason}`,
      );
      await loadData();
    } catch (err) {
      setFeedback(`Erro ao adquirir faixa: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const approveCommercialJob = async (jobId: number) => {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await apiClient.approveAcquisitionJob(jobId);
      setFeedback(`Job comercial #${res.job.id} aprovado e iniciado!`);
      await loadData();
    } catch (err) {
      setFeedback(`Erro ao aprovar job: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const toggleSource = async (providerId: string, enabled: boolean) => {
    await apiClient.updateMusicSource(providerId, { enabled });
    await loadData();
  };

  const testSourceConnection = async (providerId: string) => {
    setHealthResults((prev) => ({ ...prev, [providerId]: 'Testando...' }));
    try {
      const res = await apiClient.healthCheckMusicSource(providerId);
      setHealthResults((prev) => ({
        ...prev,
        [providerId]: `${res.status.toUpperCase()} (${res.latency_ms ?? 0}ms): ${res.detail}`,
      }));
      await loadData();
    } catch (err) {
      setHealthResults((prev) => ({
        ...prev,
        [providerId]: `ERRO: ${(err as Error).message}`,
      }));
    }
  };

  const handleSaveCredentials = async (e: React.FormEvent) => {
    e.preventDefault();
    const nonEmpty: Record<string, string> = {};
    for (const [k, v] of Object.entries(credInputs)) {
      if (v.trim()) nonEmpty[k] = v.trim();
    }
    if (Object.keys(nonEmpty).length === 0) {
      setFeedback('Preencha ao menos uma chave para salvar no arquivo .env.');
      return;
    }
    setBusy(true);
    try {
      const res = await apiClient.saveSourceCredentials(nonEmpty);
      setSources(res.providers || []);
      setCredInputs({});
      setFeedback(`Credenciais atualizadas com segurança no .env: ${res.updated_keys.join(', ')}`);
    } catch (err) {
      setFeedback(`Erro ao salvar credenciais: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleSelectTrack = (tidStr: string) => {
    setSelectedTrackId(tidStr);
    const t = tracks.find((x) => String(x.id) === tidStr);
    if (t) {
      setTitle(t.title);
      setArtist(t.artist);
      if (t.local_path && !localSourcePath) {
        setLocalSourcePath(t.local_path);
      }
    }
  };

  const buildManualCandidate = (): CandidateSourcePayload => ({
    provider: localSourcePath ? 'local_conversion' : 'authorized_url',
    source_url: sourceUrl.trim() || null,
    local_source_path: localSourcePath.trim() || null,
    title: title.trim() || 'Faixa Sem Título',
    artist: artist.trim() || 'Artista Desconhecido',
    codec: codec.trim() || null,
    bitrate_kbps: bitrateKbps ? Number(bitrateKbps) : null,
    is_preview: isPreview,
    origin_classification: originCls,
    verified_source: true,
  });

  const runUpgradeCheck = async () => {
    setBusy(true);
    setFeedback(null);
    try {
      const res = await apiClient.checkUpgrade(
        selectedTrackId ? Number(selectedTrackId) : null,
        buildManualCandidate(),
        profile,
      );
      setUpgradeCheck(res);
    } catch (err) {
      setFeedback(`Erro ao avaliar upgrade: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const handleManualEnqueue = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      const job = await apiClient.enqueueDownloadJob({
        track_id: selectedTrackId ? Number(selectedTrackId) : null,
        candidate: buildManualCandidate(),
        profile,
        target_sample_rate_hz: targetSr ? Number(targetSr) : null,
        allow_downgrade_or_same: allowOverride,
      });
      setFeedback(`Job manual #${job.id} criado (${job.status} • ${job.upgrade_decision || ''})`);
      await loadData();
    } catch (err) {
      setFeedback(`Erro ao enfileirar: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  };

  const jobAction = async (id: number, action: 'cancel' | 'pause' | 'resume' | 'retry') => {
    if (action === 'cancel') await apiClient.cancelDownloadJob(id);
    else if (action === 'pause') await apiClient.pauseDownloadJob(id);
    else if (action === 'resume') await apiClient.resumeDownloadJob(id);
    else await apiClient.retryDownloadJob(id);
    await loadData();
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Header & Tabs */}
      <div className="studio-panel p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <DownloadCloud className="w-5 h-5 text-cyan-400" />
          <div>
            <h1 className="text-sm font-bold text-white uppercase tracking-wide">
              Download Studio 2.2 — Universal Discovery & Automatic Acquisition
            </h1>
            <p className="text-[11px] text-slate-400">
              Pesquisa paralela em múltiplas fontes, comparação anti-transcode, aquisição autorizada e validação Audio Quality Intelligence.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            onClick={() => setActiveTab('discovery')}
            className={`px-3 py-1.5 rounded text-xs font-semibold inline-flex items-center gap-1.5 border ${
              activeTab === 'discovery'
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                : 'bg-[#0B0D12] text-slate-300 border-[#242C3D]'
            }`}
          >
            <Compass className="w-3.5 h-3.5" /> Descoberta & Aquisição
          </button>
          <button
            onClick={() => setActiveTab('providers')}
            className={`px-3 py-1.5 rounded text-xs font-semibold inline-flex items-center gap-1.5 border ${
              activeTab === 'providers'
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                : 'bg-[#0B0D12] text-slate-300 border-[#242C3D]'
            }`}
          >
            <Settings2 className="w-3.5 h-3.5" /> Fontes & Credenciais ({sources.length})
          </button>
          <button
            onClick={() => setActiveTab('manual')}
            className={`px-3 py-1.5 rounded text-xs font-semibold inline-flex items-center gap-1.5 border ${
              activeTab === 'manual'
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                : 'bg-[#0B0D12] text-slate-300 border-[#242C3D]'
            }`}
          >
            <DownloadCloud className="w-3.5 h-3.5" /> URL / Local Manual
          </button>
          <button
            onClick={loadData}
            className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-slate-300 hover:text-white inline-flex items-center gap-1"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {feedback && (
        <div className="text-xs font-mono-tech text-cyan-200 bg-[#101521] border border-cyan-500/40 rounded px-3 py-2 flex items-center justify-between">
          <span>{feedback}</span>
          <button onClick={() => setFeedback(null)} className="text-slate-400 hover:text-white">
            ×
          </button>
        </div>
      )}

      {/* TAB 1: DISCOVERY & AUTOMATIC ACQUISITION */}
      {activeTab === 'discovery' && (
        <div className="space-y-3">
          <form onSubmit={runDiscoverySearch} className="studio-panel p-4 space-y-3 text-xs">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-2">
              <div className="lg:col-span-5 relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-2.5 top-2" />
                <input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Pesquise faixa, artista, álbum, ISRC, remix ou ao vivo (sem URL manual)..."
                  className="w-full pl-8 pr-3 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
                />
              </div>
              <select
                value={searchType}
                onChange={(e) => setSearchType(e.target.value)}
                className="lg:col-span-2 px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              >
                <option value="track">Faixa</option>
                <option value="artist">Artista</option>
                <option value="album">Álbum</option>
                <option value="isrc">ISRC</option>
                <option value="live">Ao Vivo / Live</option>
                <option value="remix">Remix / Rework</option>
              </select>
              <select
                value={acqMode}
                onChange={(e) => setAcqMode(e.target.value)}
                className="lg:col-span-2 px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
                title="Política de seleção automática"
              >
                <option value="ASK_BEFORE_PAID">Perguntar antes de pago</option>
                <option value="AUTO_BEST_SOURCE">Melhor fonte autorizada</option>
                <option value="FREE_AUTHORIZED_ONLY">Apenas gratuito autorizado</option>
              </select>
              <select
                value={acqProfile}
                onChange={(e) => setAcqProfile(e.target.value)}
                className="lg:col-span-2 px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              >
                <option value="ORIGINAL">Preservar Original</option>
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button
                type="submit"
                disabled={searching}
                className="lg:col-span-1 py-1.5 px-3 rounded font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 inline-flex items-center justify-center gap-1"
              >
                {searching ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
                Buscar
              </button>
            </div>
            <label className="inline-flex items-center gap-2 text-[11px] text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={onlyDownloadable}
                onChange={(e) => setOnlyDownloadable(e.target.checked)}
              />
              Mostrar apenas gravações com download autorizado direto (ocultar fontes apenas catálogo/prévia)
            </label>
          </form>

          {playingPreviewUrl && (
            <div className="studio-panel p-2.5 flex items-center justify-between gap-3">
              <div className="flex items-center gap-2 text-xs text-sky-300 font-mono-tech">
                <Volume2 className="w-4 h-4" /> Ouvindo prévia oficial de catálogo (30s):
              </div>
              <audio src={playingPreviewUrl} controls autoPlay className="h-8 flex-1 max-w-md" />
              <button
                onClick={() => setPlayingPreviewUrl(null)}
                className="text-xs px-2 py-1 rounded bg-[#0B0D12] border border-[#242C3D] text-slate-300"
              >
                Fechar
              </button>
            </div>
          )}

          {discoveryRes && (
            <div className="space-y-3">
              {/* Provider health strip */}
              <div className="studio-panel p-3 flex flex-wrap items-center gap-2 text-[11px] font-mono-tech">
                <span className="text-slate-400">
                  {discoveryRes.total_groups} gravações agrupadas ({discoveryRes.downloadable_groups} com download autorizado) •{' '}
                  {discoveryRes.total_raw_results} resultados brutos:
                </span>
                {discoveryRes.provider_statuses.map((ps) => (
                  <span
                    key={ps.provider_id}
                    className={`px-2 py-0.5 rounded border ${
                      ps.status === 'ok'
                        ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                        : ps.status === 'requires_credentials'
                        ? 'bg-purple-500/10 text-purple-300 border-purple-500/30'
                        : 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                    }`}
                    title={ps.error || `${ps.latency_ms}ms`}
                  >
                    {ps.provider_name}: {ps.status === 'ok' ? `${ps.count}` : ps.status}
                  </span>
                ))}
              </div>

              {/* Grouped recordings */}
              {discoveryRes.groups.length === 0 ? (
                <div className="studio-panel p-6 text-center text-xs text-slate-400">
                  Nenhuma gravação encontrada com os filtros atuais. Desmarque "apenas download autorizado" para explorar todo o catálogo global.
                </div>
              ) : (
                <div className="space-y-3">
                  {discoveryRes.groups.map((grp) => {
                    const comp = grp.comparison;
                    const best = comp?.best_authorized;
                    return (
                      <div key={grp.group_key} className="studio-panel p-4 space-y-3">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div className="flex items-start gap-3">
                            {grp.cover_url ? (
                              <img
                                src={grp.cover_url}
                                alt={grp.title}
                                className="w-12 h-12 rounded object-cover border border-[#242C3D]"
                              />
                            ) : (
                              <div className="w-12 h-12 rounded bg-[#0B0D12] border border-[#242C3D] flex items-center justify-center text-slate-500 text-[10px]">
                                CAPA
                              </div>
                            )}
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="text-sm font-bold text-white">{grp.title}</h3>
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech uppercase bg-[#151A25] border border-[#242C3D] text-cyan-300">
                                  {grp.version_type}
                                </span>
                                {grp.has_free_download && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                                    DOWNLOAD GRATUITO AUTORIZADO
                                  </span>
                                )}
                                {!grp.has_free_download && grp.has_commercial_download && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech bg-amber-500/20 text-amber-200 border border-amber-400/50">
                                    ENTREGA COMERCIAL (REQUER APROVAÇÃO)
                                  </span>
                                )}
                                {!grp.has_downloadable_source && (
                                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech bg-slate-700/40 text-slate-300 border border-slate-600/40">
                                    APENAS CATÁLOGO / PRÉVIA
                                  </span>
                                )}
                              </div>
                              <div className="text-xs text-slate-300">
                                {grp.artist} {grp.album ? `• ${grp.album}` : ''}
                                {grp.duration_ms ? ` • ${Math.round(grp.duration_ms / 1000)}s` : ''}
                                {grp.isrc ? ` • ISRC ${grp.isrc}` : ''}
                              </div>
                              {comp && (
                                <div className="text-[11px] font-mono-tech text-slate-400 mt-1">
                                  {comp.selection_reason}
                                </div>
                              )}
                            </div>
                          </div>

                          {grp.has_downloadable_source && (
                            <button
                              disabled={busy}
                              onClick={() => triggerGroupAcquisition(grp)}
                              className="px-3 py-1.5 rounded text-xs font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 inline-flex items-center gap-1.5"
                            >
                              <Sparkles className="w-3.5 h-3.5" />
                              {best?.requires_payment ? 'Solicitar Aprovação Comercial' : 'Adquirir Melhor Fonte'}
                            </button>
                          )}
                        </div>

                        {/* Candidates comparison table */}
                        {comp && comp.ranked_candidates.length > 0 && (
                          <div className="overflow-x-auto border border-[#1E2634] rounded">
                            <table className="w-full text-left text-[11px]">
                              <thead className="bg-[#0B0D12] text-slate-400 font-mono-tech uppercase text-[10px]">
                                <tr>
                                  <th className="px-2.5 py-1.5">Fonte / Categoria</th>
                                  <th className="px-2.5 py-1.5">Permissão</th>
                                  <th className="px-2.5 py-1.5">Técnico / Transcode</th>
                                  <th className="px-2.5 py-1.5">Score</th>
                                  <th className="px-2.5 py-1.5">Ação</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-[#1E2634]">
                                {comp.ranked_candidates.map((cand: CandidateScoreBreakdown, idx: number) => (
                                  <tr key={`${cand.provider_id}-${cand.source_item_id}-${idx}`} className="bg-[#0F131C]/70">
                                    <td className="px-2.5 py-2">
                                      <div className="font-semibold text-white">{cand.provider_name}</div>
                                      <div className="text-[10px] text-slate-400">{CATEGORY_LABEL[cand.category] || cand.category}</div>
                                    </td>
                                    <td className="px-2.5 py-2">
                                      <span
                                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono-tech border ${
                                          PERMISSION_BADGE[cand.permission_status] || 'border-slate-600 text-slate-300'
                                        }`}
                                      >
                                        {cand.permission_status}
                                      </span>
                                      {cand.license_info && (
                                        <div className="text-[10px] text-slate-400 mt-0.5 truncate max-w-[180px]" title={cand.license_info}>
                                          {cand.license_info}
                                        </div>
                                      )}
                                    </td>
                                    <td className="px-2.5 py-2 font-mono-tech">
                                      <div className="text-slate-200">
                                        {cand.declared_codec ? cand.declared_codec.toUpperCase() : 'N/A'}
                                        {cand.declared_bitrate_kbps ? ` • ${cand.declared_bitrate_kbps} kbps` : ''}
                                      </div>
                                      {cand.suspected_transcode && (
                                        <div className="text-amber-300 text-[10px] inline-flex items-center gap-1">
                                          <AlertTriangle className="w-3 h-3" /> Suspeita de transcode
                                        </div>
                                      )}
                                    </td>
                                    <td className="px-2.5 py-2 font-mono-tech">
                                      <span className="font-bold text-cyan-300">{cand.total_score}</span>
                                      <span className="text-[10px] text-slate-400 block">
                                        T:{cand.technical_score} • C:{cand.reliability_score}
                                      </span>
                                    </td>
                                    <td className="px-2.5 py-2">
                                      <div className="flex items-center gap-1.5">
                                        {cand.preview_url && (
                                          <button
                                            type="button"
                                            onClick={() => setPlayingPreviewUrl(cand.preview_url || null)}
                                            className="px-2 py-1 rounded bg-[#151A25] border border-[#242C3D] text-sky-300 hover:border-sky-400 inline-flex items-center gap-1"
                                          >
                                            <Volume2 className="w-3 h-3" /> Prévia
                                          </button>
                                        )}
                                        {cand.downloadable && (
                                          <button
                                            type="button"
                                            disabled={busy}
                                            onClick={() =>
                                              triggerGroupAcquisition(grp, cand.provider_id, cand.source_item_id)
                                            }
                                            className="px-2 py-1 rounded bg-emerald-500/20 border border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/30"
                                          >
                                            {cand.requires_payment ? 'Aprovar/Comprar' : 'Baixar Esta'}
                                          </button>
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* TAB 2: PROVIDERS & CREDENTIALS */}
      {activeTab === 'providers' && (
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
          <div className="xl:col-span-8 studio-panel p-4 space-y-3">
            <div className="text-xs font-bold text-white uppercase tracking-wide">
              Fontes Musicais Registradas ({sources.length})
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
              {sources.map((src) => (
                <div key={src.provider_id} className="bg-[#0B0D12] border border-[#1E2634] rounded p-3 space-y-2 text-xs">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <div className="font-bold text-white">{src.name}</div>
                      <div className="text-[10px] font-mono-tech text-cyan-300">
                        {CATEGORY_LABEL[src.category] || src.category}
                      </div>
                    </div>
                    <label className="inline-flex items-center gap-1.5 text-[11px] cursor-pointer">
                      <input
                        type="checkbox"
                        checked={src.enabled}
                        onChange={(e) => toggleSource(src.provider_id, e.target.checked)}
                      />
                      Ativo
                    </label>
                  </div>

                  <div className="text-[11px] text-slate-400">{src.restrictions}</div>
                  <div className="flex flex-wrap gap-1.5 text-[10px] font-mono-tech">
                    <span className="px-1.5 py-0.5 rounded bg-[#151A25] border border-[#242C3D] text-slate-300">
                      {src.cost_info}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded border ${
                        src.auth_configured
                          ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                      }`}
                    >
                      {src.requires_auth
                        ? src.auth_configured
                          ? 'Credenciais OK'
                          : `Falta: ${src.missing_credentials.join(', ')}`
                        : 'Sem Chave'}
                    </span>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] font-mono-tech text-slate-500">
                      {src.last_health_status ? `Último check: ${src.last_health_status}` : src.rate_limit_info}
                    </span>
                    <button
                      type="button"
                      onClick={() => testSourceConnection(src.provider_id)}
                      className="px-2 py-1 rounded text-[10px] font-mono-tech bg-[#151A25] border border-[#242C3D] text-cyan-300 hover:border-cyan-400 inline-flex items-center gap-1"
                    >
                      <Activity className="w-3 h-3" /> Testar
                    </button>
                  </div>
                  {healthResults[src.provider_id] && (
                    <div className="text-[10px] font-mono-tech text-cyan-200 bg-[#131824] rounded px-2 py-1">
                      {healthResults[src.provider_id]}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          <form onSubmit={handleSaveCredentials} className="xl:col-span-4 studio-panel p-4 space-y-2.5 text-xs">
            <div className="flex items-center gap-2 text-xs font-bold text-white uppercase tracking-wide">
              <KeyRound className="w-4 h-4 text-amber-400" /> Credenciais Opcionais (.env)
            </div>
            <p className="text-[11px] text-slate-400">
              Tokens são gravados exclusivamente no arquivo <code className="text-cyan-300">.env</code> local e nunca no banco SQLite ou retornados em texto claro.
            </p>
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
              {credentialKeys.map((k) => (
                <label key={k} className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono-tech text-slate-400">{k}</span>
                  <input
                    type="password"
                    autoComplete="off"
                    value={credInputs[k] || ''}
                    onChange={(e) => setCredInputs((prev) => ({ ...prev, [k]: e.target.value }))}
                    placeholder="Inserir ou atualizar token (oculto)"
                    className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech"
                  />
                </label>
              ))}
            </div>
            <button
              type="submit"
              disabled={busy}
              className="w-full py-2 rounded font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400"
            >
              Salvar Credenciais no .env
            </button>
          </form>
        </div>
      )}

      {/* TAB 3: MANUAL URL / LOCAL CONVERSION (v2.1 preserved) */}
      {activeTab === 'manual' && (
        <form onSubmit={handleManualEnqueue} className="studio-panel p-4 flex flex-col gap-3 text-xs">
          <div className="text-xs font-bold text-white uppercase tracking-wide">
            Conversão Local / URL Autorizada Manual / Upgrade Engine
          </div>

          <label className="flex flex-col gap-1">
            <span className="text-[10px] font-mono-tech text-slate-400">FAIXA ALVO NA BIBLIOTECA (OPCIONAL)</span>
            <select
              value={selectedTrackId}
              onChange={(e) => handleSelectTrack(e.target.value)}
              className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
            >
              <option value="">Nova faixa independente</option>
              {tracks.map((t) => (
                <option key={t.id} value={t.id}>
                  #{t.id} • {t.title} — {t.artist} ({t.codec || 'sem arquivo'})
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">TÍTULO</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">ARTISTA</span>
              <input
                value={artist}
                onChange={(e) => setArtist(e.target.value)}
                required
                className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              />
            </label>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">URL AUTORIZADA (HTTP/HTTPS)</span>
              <input
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder="https://... (deixe vazio se usar arquivo local)"
                className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">CAMINHO LOCAL DE ORIGEM</span>
              <input
                value={localSourcePath}
                onChange={(e) => setLocalSourcePath(e.target.value)}
                placeholder="C:\...\arquivo.flac"
                className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech"
              />
            </label>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">PERFIL DE SAÍDA</span>
              <select
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
                className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              >
                {profiles.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">SAMPLE RATE</span>
              <select
                value={targetSr}
                onChange={(e) => setTargetSr(e.target.value)}
                className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              >
                <option value="">Preservar origem</option>
                <option value="44100">44100 Hz</option>
                <option value="48000">48000 Hz</option>
                <option value="96000">96000 Hz</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">CODEC ORIGEM</span>
              <input
                value={codec}
                onChange={(e) => setCodec(e.target.value)}
                className="px-2 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">BITRATE KBPS</span>
              <input
                value={bitrateKbps}
                onChange={(e) => setBitrateKbps(e.target.value)}
                placeholder="ex: 320"
                className="px-2 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-[10px] font-mono-tech text-slate-400">CLASSIFICAÇÃO</span>
              <select
                value={originCls}
                onChange={(e) => setOriginCls(e.target.value)}
                className="px-2 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
              >
                <option value="LOSSLESS_SOURCE">LOSSLESS_SOURCE</option>
                <option value="LOSSY_SOURCE">LOSSY_SOURCE</option>
                <option value="UNKNOWN_SOURCE">UNKNOWN_SOURCE</option>
              </select>
            </label>
          </div>

          <div className="flex flex-wrap gap-4 text-[11px] text-slate-300">
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={isPreview} onChange={(e) => setIsPreview(e.target.checked)} />
              Fonte é Preview
            </label>
            <label className="inline-flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={allowOverride} onChange={(e) => setAllowOverride(e.target.checked)} />
              Permitir conversão mesmo sem ganho de qualidade
            </label>
          </div>

          {upgradeCheck && (
            <div
              className={`rounded p-2.5 border text-xs space-y-1 ${
                upgradeCheck.is_justified
                  ? 'bg-emerald-500/10 border-emerald-500/40 text-emerald-200'
                  : 'bg-amber-500/10 border-amber-500/40 text-amber-200'
              }`}
            >
              <div className="font-mono-tech font-bold inline-flex items-center gap-1.5">
                {upgradeCheck.is_justified ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : (
                  <AlertTriangle className="w-4 h-4" />
                )}
                {upgradeCheck.decision}
              </div>
              <div>{upgradeCheck.reason}</div>
            </div>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              onClick={runUpgradeCheck}
              disabled={busy}
              className="flex-1 py-2 rounded font-semibold bg-[#151A25] border border-[#242C3D] text-cyan-300 hover:border-cyan-400 inline-flex items-center justify-center gap-1.5"
            >
              <ShieldCheck className="w-4 h-4" /> Verificar Upgrade
            </button>
            <button
              type="submit"
              disabled={busy}
              className="flex-1 py-2 rounded font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 inline-flex items-center justify-center gap-1.5"
            >
              <DownloadCloud className="w-4 h-4" /> Enfileirar Job Manual
            </button>
          </div>
        </form>
      )}

      {/* ALWAYS VISIBLE: PERSISTENT QUEUE + COMMERCIAL APPROVAL + PROVENANCE AUDIT */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        <div className="xl:col-span-8 studio-panel p-4 flex flex-col gap-3">
          <div className="text-xs font-bold text-white uppercase tracking-wide">
            Fila Persistente & Controle de Aquisições ({jobs.length})
          </div>
          {jobs.length === 0 ? (
            <div className="text-xs text-slate-500 py-6 text-center">
              Nenhum job na fila ainda. Pesquise uma música acima para iniciar a descoberta e aquisição automática.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
              {jobs.map((job) => {
                let logs: string[] = [];
                try {
                  logs = JSON.parse(job.logs_json || '[]');
                } catch {
                  logs = [];
                }
                const pct = Math.round((job.progress || 0) * 100);
                return (
                  <div key={job.id} className="bg-[#0B0D12] border border-[#1E2634] rounded p-3 space-y-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="text-xs font-bold text-white">
                          #{job.id} • {job.source_label || `Track #${job.track_id}`}
                        </div>
                        <div className="text-[10px] font-mono-tech text-slate-400">
                          Fonte: {job.provider} • Perfil: {job.profile} • Etapa: {job.current_stage}
                          {job.license_info ? ` • Licença: ${job.license_info}` : ''}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono-tech font-bold border ${
                            JOB_STATUS_COLOR[job.status] || 'border-slate-600 text-slate-300'
                          }`}
                        >
                          {job.status}
                        </span>
                        {job.status === 'AWAITING_APPROVAL' && (
                          <button
                            disabled={busy}
                            onClick={() => approveCommercialJob(job.id)}
                            className="px-2.5 py-1 rounded text-[11px] font-semibold bg-amber-400 text-[#0B0D12] hover:bg-amber-300 inline-flex items-center gap-1"
                          >
                            <ShieldAlert className="w-3.5 h-3.5" /> Aprovar Aquisição Comercial
                            {job.estimated_cost_label ? ` (${job.estimated_cost_label})` : ''}
                          </button>
                        )}
                        {job.status === 'DOWNLOADING' && (
                          <button
                            onClick={() => jobAction(job.id, 'pause')}
                            className="p-1 rounded bg-[#151A25] border border-[#242C3D] text-amber-300"
                            title="Pausar"
                          >
                            <Pause className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {job.status === 'PAUSED' && (
                          <button
                            onClick={() => jobAction(job.id, 'resume')}
                            className="p-1 rounded bg-[#151A25] border border-[#242C3D] text-emerald-300"
                            title="Retomar"
                          >
                            <Play className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {['QUEUED', 'DOWNLOADING', 'PAUSED', 'CONVERTING'].includes(job.status) && (
                          <button
                            onClick={() => jobAction(job.id, 'cancel')}
                            className="p-1 rounded bg-[#151A25] border border-[#242C3D] text-rose-400"
                            title="Cancelar"
                          >
                            <XCircle className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {['FAILED', 'CANCELLED'].includes(job.status) && (
                          <button
                            onClick={() => jobAction(job.id, 'retry')}
                            className="p-1 rounded bg-[#151A25] border border-[#242C3D] text-cyan-300"
                            title="Retry"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>

                    <div className="space-y-1">
                      <div className="h-1.5 bg-[#161B26] rounded overflow-hidden">
                        <div
                          className={`h-full transition-all ${
                            job.status === 'FAILED' ? 'bg-rose-500' : 'bg-cyan-400'
                          }`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="flex justify-between text-[10px] font-mono-tech text-slate-500">
                        <span>{pct}%</span>
                        <span>
                          {job.file_sha256 ? `SHA-256: ${job.file_sha256.slice(0, 12)}...` : ''}
                          {job.speed_bps ? ` • ${(job.speed_bps / 1024).toFixed(1)} KB/s` : ''}
                        </span>
                      </div>
                    </div>

                    {job.error_message && (
                      <div className="text-[11px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded px-2 py-1">
                        {job.error_message}
                      </div>
                    )}

                    {logs.length > 0 && (
                      <details className="text-[10px] font-mono-tech text-slate-400">
                        <summary className="cursor-pointer hover:text-slate-200">Logs ({logs.length})</summary>
                        <div className="mt-1 space-y-0.5 pl-2 border-l border-[#242C3D]">
                          {logs.slice(-6).map((l, idx) => (
                            <div key={idx}>{l}</div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="xl:col-span-4 studio-panel p-4 flex flex-col gap-2.5">
          <div className="text-xs font-bold text-white uppercase tracking-wide">
            Histórico de Decisão & Proveniência ({records.length})
          </div>
          {records.length === 0 ? (
            <div className="text-xs text-slate-500 py-6 text-center">
              Nenhuma decisão registrada ainda.
            </div>
          ) : (
            <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1 text-[11px]">
              {records.map((rec) => {
                let summary: { query?: string; reason?: string } = {};
                if (rec.comparison_summary_json) {
                  try {
                    summary = JSON.parse(rec.comparison_summary_json);
                  } catch {
                    summary = {};
                  }
                }
                return (
                  <div key={rec.id} className="bg-[#0B0D12] border border-[#1E2634] rounded p-2.5 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-white truncate">
                        {summary.query || `Job #${rec.download_job_id ?? rec.id}`}
                      </span>
                      <span className="font-mono-tech text-[10px] text-cyan-300">{rec.status}</span>
                    </div>
                    <div className="text-[10px] font-mono-tech text-slate-400">
                      {rec.provider_id} • {rec.acquisition_mode}
                      {rec.was_paid ? ' • Pago' : ''}
                      {rec.file_sha256 ? ` • ${rec.file_sha256.slice(0, 10)}...` : ''}
                    </div>
                    {(summary.reason || rec.error_message) && (
                      <div className="text-slate-300">{summary.reason || rec.error_message}</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
