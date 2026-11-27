import React, { useEffect, useMemo, useState } from 'react';
import {
  CopyCheck,
  Database,
  Fingerprint,
  Gauge,
  GitCompare,
  Layers,
  Loader2,
  Save,
  ShieldCheck,
  Sparkles,
  Waves,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { AbComparisonModal } from '../components/AbComparisonModal';
import type { AbComparisonResponse, DuplicateGroup, UnifiedTrack } from '../types/music';
import { getCamelotColor } from '../utils/camelot';

interface LibraryManagerViewProps {
  tracks: UnifiedTrack[];
  wsLastEvent: Record<string, unknown> | null;
  qualityFilter?: string;
  onClearQualityFilter?: () => void;
  onRefreshTracks: () => void;
}

export const LibraryManagerView: React.FC<LibraryManagerViewProps> = ({
  tracks,
  wsLastEvent,
  qualityFilter = 'ALL',
  onClearQualityFilter,
  onRefreshTracks,
}) => {
  const [selected, setSelected] = useState<UnifiedTrack | null>(tracks[0] || null);
  const [compareTrackId, setCompareTrackId] = useState<string>('');
  const [abCompare, setAbCompare] = useState<AbComparisonResponse | null>(null);
  const [form, setForm] = useState({
    title: '',
    artist: '',
    album: '',
    genres_raw: '',
    release_year: '',
    isrc: '',
    bpm: '',
    key: '',
  });
  const [duplicates, setDuplicates] = useState<DuplicateGroup[]>([]);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const displayedTracks = useMemo(() => {
    if (!qualityFilter || qualityFilter === 'ALL') return tracks;
    return tracks.filter((t) => {
      if (qualityFilter === 'COMPLETE') return Boolean(t.local_path && !t.is_preview);
      if (qualityFilter === 'PREVIEW') return Boolean(t.is_preview || (!t.local_path && t.preview_url));
      if (qualityFilter === 'LOSSLESS_SOURCE') return t.source_classification === 'LOSSLESS_SOURCE';
      if (qualityFilter === 'LOSSY_SOURCE') return t.source_classification === 'LOSSY_SOURCE';
      if (qualityFilter === 'UNKNOWN_SOURCE') return (t.source_classification || 'UNKNOWN_SOURCE') === 'UNKNOWN_SOURCE';
      if (qualityFilter === 'FAKE_UPSCALE') return Boolean(t.is_fake_upscale || t.upscale_status === 'LIKELY_UPSCALE' || t.upscale_status === 'SUSPECTED_UPSCALE');
      if (qualityFilter === 'CORRUPTED') return Boolean(t.is_corrupted);
      if (qualityFilter === 'CLIPPING') return (t.clipping_count || 0) > 0;
      if (qualityFilter === 'CRITICAL_PEAK') return t.true_peak_dbfs != null && t.true_peak_dbfs > -0.1;
      if (qualityFilter === 'UNANALYZED') return !t.quality_analyzed_at;
      if (qualityFilter === 'UPGRADE_AVAILABLE') return Boolean(t.is_preview || t.is_fake_upscale || (t.bitrate_kbps != null && t.bitrate_kbps > 0 && t.bitrate_kbps < 256));
      return true;
    });
  }, [tracks, qualityFilter]);

  useEffect(() => {
    if (!selected && tracks.length > 0) {
      setSelected(tracks[0]);
    } else if (selected) {
      const updated = tracks.find((t) => t.id === selected.id);
      if (updated) setSelected(updated);
    }
  }, [tracks, selected?.id]);

  useEffect(() => {
    if (!selected) return;
    setForm({
      title: selected.title || '',
      artist: selected.artist || '',
      album: selected.album || '',
      genres_raw: selected.genres_raw || '',
      release_year: selected.release_year ? String(selected.release_year) : '',
      isrc: selected.isrc || '',
      bpm: selected.bpm ? String(selected.bpm) : '',
      key: selected.key || selected.camelot_code || '',
    });
  }, [selected]);

  const handleSaveMetadata = async () => {
    if (!selected) return;
    setBusy('save');
    setFeedback(null);
    try {
      await apiClient.updateTrack(selected.id, {
        title: form.title,
        artist: form.artist,
        album: form.album || null,
        genres_raw: form.genres_raw,
        release_year: form.release_year ? Number(form.release_year) : null,
        isrc: form.isrc || null,
        bpm: form.bpm ? Number(form.bpm) : null,
        key: form.key || null,
      });
      setFeedback('Metadados atualizados no SQLite.');
      onRefreshTracks();
    } catch (err) {
      setFeedback(`Erro ao salvar: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleSingleAction = async (kind: 'enrich' | 'acoustid' | 'tech' | 'musical' | 'quality') => {
    if (!selected) return;
    setBusy(kind);
    setFeedback(null);
    try {
      if (kind === 'enrich') {
        const res = await apiClient.enrichTrack(selected.id, true);
        const sources = Array.isArray(res.sources_used) ? res.sources_used.join(', ') : '';
        setFeedback(`Enriquecido via: ${sources || 'cache/sem novas fontes'}`);
      } else if (kind === 'acoustid') {
        const res = await apiClient.identifyAcoustId(selected.id);
        setFeedback(
          res.identified
            ? `AcoustID identificado (${Math.round((res.score || 0) * 100)}%): ${res.artist} - ${res.title}`
            : res.reason || 'Sem correspondência AcoustID',
        );
      } else if (kind === 'tech') {
        await apiClient.analyzeTechnical(selected.id, true);
        setFeedback('Análise técnica FFmpeg concluída.');
      } else if (kind === 'musical') {
        await apiClient.analyzeMusical(selected.id, true);
        setFeedback('Análise musical Librosa concluída.');
      } else {
        const rep = await apiClient.analyzeTrackQuality(selected.id, true);
        setFeedback(
          `Qualidade v2.1: ${rep.quality_intelligence.source_classification} • Car Score ${rep.quality_intelligence.car_audio_score ?? '—'}/100`,
        );
      }
      onRefreshTracks();
    } catch (err) {
      setFeedback(`Erro: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleBatch = async (kind: 'enrich' | 'tech' | 'musical' | 'quality') => {
    setBusy(`batch_${kind}`);
    setFeedback(null);
    try {
      if (kind === 'enrich') {
        const res = await apiClient.enrichLibrary(false);
        setFeedback(res.message);
      } else if (kind === 'tech') {
        const res = await apiClient.analyzeLibraryTechnical(false);
        setFeedback(res.message);
      } else if (kind === 'musical') {
        const res = await apiClient.analyzeLibraryMusical(false);
        setFeedback(res.message);
      } else {
        const res = await apiClient.analyzeLibraryQuality(false);
        setFeedback(res.message);
      }
    } catch (err) {
      setFeedback(`Erro em lote: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const scanDuplicates = async () => {
    setBusy('dups');
    try {
      const res = await apiClient.getDuplicates();
      setDuplicates(res.duplicate_groups || []);
      setShowDuplicates(true);
    } finally {
      setBusy(null);
    }
  };

  const mergeGroup = async (group: DuplicateGroup) => {
    setBusy('merge');
    try {
      await apiClient.mergeDuplicates(
        group.primary.id,
        group.candidates.map((c) => c.id),
      );
      onRefreshTracks();
      await scanDuplicates();
      setFeedback(`Mescladas ${group.candidates.length} duplicatas em "${group.primary.title}".`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Batch Toolbar */}
      <div className="studio-panel p-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <Database className="w-5 h-5 text-cyan-400" />
          <div>
            <h1 className="text-sm font-bold text-white uppercase tracking-wide">
              Biblioteca Unificada & Beets-Style Metadata Manager
            </h1>
            <p className="text-[11px] text-slate-400">
              Deduplicação por ISRC/metadata, identificação AcoustID, MusicBrainz/CAA, e processamento em lote FFmpeg + Librosa
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {qualityFilter !== 'ALL' && onClearQualityFilter && (
            <button
              onClick={onClearQualityFilter}
              className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-rose-500/15 text-rose-300 border border-rose-500/30"
            >
              Filtro: {qualityFilter} ({displayedTracks.length}) ×
            </button>
          )}
          <button
            onClick={() => handleBatch('quality')}
            disabled={busy !== null}
            className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 inline-flex items-center gap-1"
          >
            <ShieldCheck className="w-3.5 h-3.5" /> Qualidade Lote
          </button>
          <button
            onClick={() => handleBatch('enrich')}
            disabled={busy !== null}
            className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-sky-500/15 text-sky-300 border border-sky-500/30 hover:bg-sky-500/25 inline-flex items-center gap-1"
          >
            <Sparkles className="w-3.5 h-3.5" /> Enriquecer Lote
          </button>
          <button
            onClick={() => handleBatch('tech')}
            disabled={busy !== null}
            className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 inline-flex items-center gap-1"
          >
            <Gauge className="w-3.5 h-3.5" /> FFmpeg Lote
          </button>
          <button
            onClick={() => handleBatch('musical')}
            disabled={busy !== null}
            className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-purple-500/15 text-purple-300 border border-purple-500/30 hover:bg-purple-500/25 inline-flex items-center gap-1"
          >
            <Waves className="w-3.5 h-3.5" /> Librosa Lote
          </button>
          <button
            onClick={scanDuplicates}
            disabled={busy !== null}
            className="px-2.5 py-1.5 rounded text-xs font-mono-tech bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 inline-flex items-center gap-1"
          >
            <CopyCheck className="w-3.5 h-3.5" /> Duplicatas
          </button>
        </div>
      </div>

      {/* Live WebSocket Batch Event Banner */}
      {(wsLastEvent || feedback) && (
        <div className="studio-panel px-3 py-2 flex items-center justify-between text-xs font-mono-tech border-l-4 border-l-cyan-400">
          <span className="text-cyan-300">{feedback || `Evento WS: ${JSON.stringify(wsLastEvent)}`}</span>
          {busy && <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />}
        </div>
      )}

      {/* Duplicate Clusters Panel */}
      {showDuplicates && (
        <div className="studio-panel p-3 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-amber-300 uppercase">
              Grupos de Duplicatas Detectados ({duplicates.length})
            </span>
            <button
              onClick={() => setShowDuplicates(false)}
              className="text-xs text-slate-400 hover:text-white"
            >
              Fechar
            </button>
          </div>
          {duplicates.length === 0 ? (
            <div className="text-xs text-emerald-400">Nenhuma duplicata encontrada na biblioteca.</div>
          ) : (
            <div className="space-y-2">
              {duplicates.map((g) => (
                <div
                  key={g.primary.id}
                  className="bg-[#0B0D12] border border-[#1E2634] rounded p-2.5 flex items-center justify-between gap-2"
                >
                  <div className="text-xs">
                    <span className="font-bold text-white">{g.primary.title}</span> —{' '}
                    <span className="text-slate-400">{g.primary.artist}</span>{' '}
                    <span className="text-amber-400 font-mono-tech">({g.count} cópias)</span>
                  </div>
                  <button
                    onClick={() => mergeGroup(g)}
                    className="px-2.5 py-1 rounded text-[11px] font-semibold bg-amber-500 text-[#0B0D12] hover:bg-amber-400"
                  >
                    Mesclar no Principal
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Split Layout: Library Table + Beets Inspector */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        <div className="xl:col-span-7 studio-panel p-3 overflow-x-auto max-h-[540px] overflow-y-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead className="bg-[#0B0D12] sticky top-0 text-[10px] font-mono-tech text-slate-400 uppercase border-b border-[#1A202C]">
              <tr>
                <th className="py-2 px-2">Faixa</th>
                <th className="py-2 px-2">ISRC</th>
                <th className="py-2 px-2">BPM</th>
                <th className="py-2 px-2">Camelot</th>
                <th className="py-2 px-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1A202C]">
              {displayedTracks.map((t) => {
                const isSel = selected?.id === t.id;
                return (
                  <tr
                    key={t.id}
                    onClick={() => setSelected(t)}
                    className={`cursor-pointer transition-colors ${
                      isSel ? 'bg-cyan-500/12' : 'hover:bg-[#171D29]'
                    }`}
                  >
                    <td className="py-2 px-2 max-w-[240px]">
                      <div className="font-semibold text-white truncate">{t.title}</div>
                      <div className="text-[10px] text-slate-400 truncate">
                        {t.artist} {t.album ? `• ${t.album}` : ''}
                      </div>
                    </td>
                    <td className="py-2 px-2 font-mono-tech text-[11px] text-slate-400">
                      {t.isrc || '—'}
                    </td>
                    <td className="py-2 px-2 font-mono-tech text-slate-200">
                      {t.bpm ? t.bpm.toFixed(1) : '—'}
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech font-bold text-[#0B0D12]"
                        style={{ backgroundColor: getCamelotColor(t.camelot_code) }}
                      >
                        {t.camelot_code || '—'}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-[10px] font-mono-tech">
                      <div className="flex gap-1">
                        {t.analyzed_at && <span className="text-cyan-400">FF</span>}
                        {t.musical_analyzed_at && <span className="text-purple-400">LB</span>}
                        {t.quality_analyzed_at && <span className="text-sky-400">Q21</span>}
                        {t.metadata_enriched_at && <span className="text-emerald-400">EN</span>}
                        {t.acoustid_id && <span className="text-amber-400">FP</span>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Right Side: Beets Tag Editor & Enrichment Actions */}
        <div className="xl:col-span-5 studio-panel p-3 flex flex-col gap-3">
          {!selected ? (
            <div className="text-xs text-slate-500 py-8 text-center">
              Selecione uma faixa à esquerda para inspecionar e editar metadados.
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 pb-2 border-b border-[#1A202C]">
                <img
                  src={
                    selected.hd_cover_url ||
                    selected.cover_url ||
                    'https://placehold.co/56x56/12161F/38BDF8?text=%E2%99%AB'
                  }
                  alt={selected.title}
                  className="w-14 h-14 rounded object-cover border border-[#242C3D]"
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-bold text-white truncate">{selected.title}</div>
                  <div className="text-xs text-slate-400 truncate">{selected.artist}</div>
                  <div className="text-[10px] font-mono-tech text-slate-500 truncate">
                    MBID: {selected.musicbrainz_recording_id || '—'} • AcoustID: {selected.acoustid_id || '—'}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => handleSingleAction('enrich')}
                  disabled={busy !== null}
                  className="py-1.5 px-2 rounded text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 inline-flex items-center justify-center gap-1"
                >
                  <Sparkles className="w-3.5 h-3.5" /> MusicBrainz + LRCLIB
                </button>
                <button
                  onClick={() => handleSingleAction('acoustid')}
                  disabled={busy !== null || !selected.local_path}
                  className="py-1.5 px-2 rounded text-[11px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 disabled:opacity-40 inline-flex items-center justify-center gap-1"
                >
                  <Fingerprint className="w-3.5 h-3.5" /> Identificar AcoustID
                </button>
                <button
                  onClick={() => handleSingleAction('tech')}
                  disabled={busy !== null || !selected.local_path}
                  className="py-1.5 px-2 rounded text-[11px] font-semibold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 disabled:opacity-40 inline-flex items-center justify-center gap-1"
                >
                  <Gauge className="w-3.5 h-3.5" /> Analisar FFmpeg
                </button>
                <button
                  onClick={() => handleSingleAction('musical')}
                  disabled={busy !== null || !selected.local_path}
                  className="py-1.5 px-2 rounded text-[11px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30 hover:bg-purple-500/25 disabled:opacity-40 inline-flex items-center justify-center gap-1"
                >
                  <Layers className="w-3.5 h-3.5" /> Analisar Librosa
                </button>
                <button
                  onClick={() => handleSingleAction('quality')}
                  disabled={busy !== null}
                  className="col-span-2 py-1.5 px-2 rounded text-[11px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30 hover:bg-sky-500/25 inline-flex items-center justify-center gap-1"
                >
                  <ShieldCheck className="w-3.5 h-3.5" /> Analisar Qualidade 2.1 (Proveniência + Fake Upscale + Car Score)
                </button>
              </div>

              <div className="flex items-center gap-2">
                <select
                  value={compareTrackId}
                  onChange={(e) => setCompareTrackId(e.target.value)}
                  className="flex-1 px-2 py-1 rounded bg-[#0B0D12] border border-[#1E2634] text-xs text-slate-300"
                >
                  <option value="">Comparar A/B com outra faixa...</option>
                  {tracks
                    .filter((t) => t.id !== selected.id)
                    .map((t) => (
                      <option key={t.id} value={t.id}>
                        #{t.id} • {t.title} ({t.codec || '?'})
                      </option>
                    ))}
                </select>
                <button
                  onClick={async () => {
                    if (!compareTrackId) return;
                    const res = await apiClient.compareTracks(selected.id, Number(compareTrackId));
                    setAbCompare(res);
                  }}
                  disabled={!compareTrackId}
                  className="px-2.5 py-1 rounded text-[11px] font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-cyan-300 disabled:opacity-40 inline-flex items-center gap-1"
                >
                  <GitCompare className="w-3.5 h-3.5" /> A/B
                </button>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                {[
                  { key: 'title', label: 'Título', span: 2 },
                  { key: 'artist', label: 'Artista', span: 2 },
                  { key: 'album', label: 'Álbum', span: 1 },
                  { key: 'release_year', label: 'Ano', span: 1 },
                  { key: 'isrc', label: 'ISRC', span: 1 },
                  { key: 'genres_raw', label: 'Gêneros / Tags', span: 1 },
                  { key: 'bpm', label: 'BPM', span: 1 },
                  { key: 'key', label: 'Clave / Key', span: 1 },
                ].map((f) => (
                  <label key={f.key} className={`flex flex-col gap-1 ${f.span === 2 ? 'col-span-2' : ''}`}>
                    <span className="text-[10px] font-mono-tech text-slate-400 uppercase">{f.label}</span>
                    <input
                      type="text"
                      value={form[f.key as keyof typeof form]}
                      onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                      className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech text-xs focus:outline-none focus:border-cyan-500"
                    />
                  </label>
                ))}
              </div>

              <button
                onClick={handleSaveMetadata}
                disabled={busy !== null}
                className="w-full py-2 rounded font-semibold text-xs bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 inline-flex items-center justify-center gap-2"
              >
                <Save className="w-4 h-4" /> Salvar Alterações (Beets Tagging)
              </button>
            </>
          )}
        </div>
      </div>
      <AbComparisonModal data={abCompare} onClose={() => setAbCompare(null)} />
    </div>
  );
};
