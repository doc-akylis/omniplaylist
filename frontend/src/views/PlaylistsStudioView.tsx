import React, { useEffect, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  Copy,
  Disc3,
  Download,
  ListMusic,
  Plus,
  RotateCcw,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type {
  PlaylistDetailsResponse,
  PlaylistModel,
  SequencerPreviewResponse,
  UnifiedTrack,
} from '../types/music';
import { getCamelotColor } from '../utils/camelot';

interface PlaylistsStudioViewProps {
  tracks: UnifiedTrack[];
  onOpenPlaylistInDj: (playlistTracks: UnifiedTrack[]) => void;
}

export const PlaylistsStudioView: React.FC<PlaylistsStudioViewProps> = ({
  tracks,
  onOpenPlaylistInDj,
}) => {
  const [playlists, setPlaylists] = useState<PlaylistModel[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [details, setDetails] = useState<PlaylistDetailsResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [sortBy, setSortBy] = useState<string>('manual');
  const [newName, setNewName] = useState('');
  const [addTrackId, setAddTrackId] = useState<string>('');
  const [feedback, setFeedback] = useState<string | null>(null);

  // Smart Sequencer state
  const [seqMode, setSeqMode] = useState<string>('balanced_dj_flow');
  const [harmonicPriority, setHarmonicPriority] = useState<number>(0.85);
  const [bpmTolerance, setBpmTolerance] = useState<number>(6);
  const [allowHalfTime, setAllowHalfTime] = useState<boolean>(true);
  const [allowRepeatedArtists, setAllowRepeatedArtists] = useState<boolean>(false);
  const [seqPreview, setSeqPreview] = useState<SequencerPreviewResponse | null>(null);

  const loadPlaylists = async (selectId?: number) => {
    const list = await apiClient.getPlaylists();
    setPlaylists(list);
    const target = selectId ?? selectedId ?? list[0]?.id ?? null;
    setSelectedId(target);
    if (target) {
      const det = await apiClient.getPlaylistDetails(target, statusFilter);
      setDetails(det);
    } else {
      setDetails(null);
    }
  };

  useEffect(() => {
    void loadPlaylists();
  }, []);

  useEffect(() => {
    if (selectedId) {
      void apiClient.getPlaylistDetails(selectedId, statusFilter).then(setDetails);
      setSeqPreview(null);
    }
  }, [selectedId, statusFilter]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    const pl = await apiClient.createPlaylist({ name: newName.trim() });
    setNewName('');
    setFeedback(`Playlist "${pl.name}" criada.`);
    await loadPlaylists(pl.id);
  };

  const handleDuplicate = async () => {
    if (!selectedId) return;
    const dup = await apiClient.duplicatePlaylist(selectedId);
    setFeedback(`Playlist duplicada como "${dup.name}".`);
    await loadPlaylists(dup.id);
  };

  const handleDelete = async () => {
    if (!selectedId) return;
    if (!window.confirm('Excluir esta playlist? As faixas permanecerão na biblioteca.')) return;
    await apiClient.deletePlaylist(selectedId);
    setSelectedId(null);
    setFeedback('Playlist excluída.');
    await loadPlaylists();
  };

  const handleAddTrack = async () => {
    if (!selectedId || !addTrackId) return;
    await apiClient.addTracksToPlaylist(selectedId, [Number(addTrackId)]);
    setAddTrackId('');
    const det = await apiClient.getPlaylistDetails(selectedId, statusFilter);
    setDetails(det);
  };

  const handleRemoveTrack = async (tid: number) => {
    if (!selectedId) return;
    await apiClient.removeTracksFromPlaylist(selectedId, [tid]);
    const det = await apiClient.getPlaylistDetails(selectedId, statusFilter);
    setDetails(det);
  };

  const moveTrack = async (index: number, delta: number) => {
    if (!selectedId || !details) return;
    const ids = details.tracks.map((entry) => entry.track.id);
    const targetIdx = index + delta;
    if (targetIdx < 0 || targetIdx >= ids.length) return;
    [ids[index], ids[targetIdx]] = [ids[targetIdx], ids[index]];
    await apiClient.reorderPlaylist(selectedId, ids);
    const det = await apiClient.getPlaylistDetails(selectedId, statusFilter);
    setDetails(det);
  };

  const handleSort = async (mode: string) => {
    setSortBy(mode);
    if (!selectedId) return;
    await apiClient.sortPlaylist(selectedId, mode, true);
    const det = await apiClient.getPlaylistDetails(selectedId, statusFilter);
    setDetails(det);
    setFeedback(`Ordenação "${mode}" aplicada e salva.`);
  };

  const handleExportM3u = async (fmt: 'm3u' | 'm3u8') => {
    if (!selectedId) return;
    const res = await apiClient.exportPlaylistM3u(selectedId, fmt);
    setFeedback(
      `Exportado ${res.format.toUpperCase()} (${res.exported_local_count}/${res.total_tracks} locais): ${res.exported_file}` +
        (res.missing_files.length > 0 ? ` • ${res.missing_files.length} ausente(s)` : ''),
    );
  };

  const runSmartSequencer = async () => {
    if (!selectedId) return;
    const res = await apiClient.previewSmartSequence(selectedId, {
      mode: seqMode,
      harmonic_priority: harmonicPriority,
      bpm_tolerance_pct: bpmTolerance,
      allow_half_time: allowHalfTime,
      allow_double_time: allowHalfTime,
      allow_repeated_artists: allowRepeatedArtists,
    });
    setSeqPreview(res);
  };

  const applySmartSequence = async () => {
    if (!selectedId || !seqPreview) return;
    await apiClient.applySmartSequence(
      selectedId,
      seqPreview.ordered_tracks.map((t) => t.id),
    );
    const det = await apiClient.getPlaylistDetails(selectedId, statusFilter);
    setDetails(det);
    setFeedback('Sequência inteligente aplicada à playlist (ordem original preservada para restauração).');
  };

  const restoreOriginalOrder = async () => {
    if (!selectedId) return;
    await apiClient.restoreSmartSequence(selectedId);
    const det = await apiClient.getPlaylistDetails(selectedId, statusFilter);
    setDetails(det);
    setSeqPreview(null);
    setFeedback('Ordem manual original restaurada.');
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Top Bar */}
      <div className="studio-panel p-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <ListMusic className="w-5 h-5 text-cyan-400" />
          <div>
            <h1 className="text-sm font-bold text-white uppercase tracking-wide">
              Playlist Manager & Smart Sequencer
            </h1>
            <p className="text-[11px] text-slate-400">
              CRUD completo N:N persistente, métricas reais, exportação M3U/M3U8 e otimizador harmônico reversível
            </p>
          </div>
        </div>

        <form onSubmit={handleCreate} className="flex gap-2">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Nova playlist..."
            className="px-3 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-xs text-white"
          />
          <button
            type="submit"
            className="px-3 py-1.5 rounded text-xs font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 inline-flex items-center gap-1"
          >
            <Plus className="w-3.5 h-3.5" /> Criar
          </button>
        </form>
      </div>

      {feedback && (
        <div className="studio-panel px-3 py-2 text-xs font-mono-tech text-cyan-300 border-l-4 border-l-cyan-400">
          {feedback}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        {/* Left: Playlist Selector + Metrics + Smart Sequencer Controls */}
        <div className="xl:col-span-4 flex flex-col gap-3">
          <div className="studio-panel p-3 space-y-2">
            <div className="text-xs font-bold text-white uppercase">Suas Playlists ({playlists.length})</div>
            <div className="space-y-1 max-h-[200px] overflow-y-auto">
              {playlists.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setSelectedId(p.id)}
                  className={`w-full text-left px-2.5 py-2 rounded text-xs border transition-colors ${
                    selectedId === p.id
                      ? 'bg-cyan-500/15 border-cyan-500/40 text-white'
                      : 'bg-[#0B0D12] border-[#1A202C] text-slate-300 hover:border-slate-600'
                  }`}
                >
                  <div className="font-semibold truncate">{p.name}</div>
                  {p.description && <div className="text-[10px] text-slate-500 truncate">{p.description}</div>}
                </button>
              ))}
            </div>

            {selectedId && (
              <div className="flex flex-wrap gap-1.5 pt-2 border-t border-[#1A202C]">
                <button
                  onClick={handleDuplicate}
                  className="px-2 py-1 rounded text-[11px] bg-[#0B0D12] border border-[#242C3D] text-slate-300 hover:text-white inline-flex items-center gap-1"
                >
                  <Copy className="w-3 h-3" /> Duplicar
                </button>
                <button
                  onClick={() => details && onOpenPlaylistInDj(details.tracks.map((e) => e.track))}
                  className="px-2 py-1 rounded text-[11px] bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 inline-flex items-center gap-1"
                >
                  <Disc3 className="w-3 h-3" /> Abrir no DJ Mode
                </button>
                <button
                  onClick={handleDelete}
                  className="px-2 py-1 rounded text-[11px] bg-rose-500/15 border border-rose-500/30 text-rose-300 inline-flex items-center gap-1 ml-auto"
                >
                  <Trash2 className="w-3 h-3" /> Excluir
                </button>
              </div>
            )}
          </div>

          {details && (
            <div className="studio-panel p-3 space-y-1.5 text-xs">
              <div className="text-xs font-bold text-white uppercase">Métricas Reais da Playlist</div>
              {[
                ['Faixas / Duração', `${details.metrics.total_tracks} • ${Math.round(details.metrics.total_duration_ms / 60000)} min`],
                ['BPM Médio (Min–Max)', details.metrics.avg_bpm ? `${details.metrics.avg_bpm} (${details.metrics.min_bpm}–${details.metrics.max_bpm})` : '—'],
                ['Energy Média', details.metrics.avg_energy != null ? `${Math.round(details.metrics.avg_energy * 100)}%` : '—'],
                ['LUFS Médio', details.metrics.avg_lufs != null ? `${details.metrics.avg_lufs} LUFS` : '—'],
                ['Qualidade Média', details.metrics.avg_quality_score != null ? `${details.metrics.avg_quality_score}/100` : '—'],
                ['Completas / Previews / Ausentes', `${details.metrics.complete_count} / ${details.metrics.preview_count} / ${details.metrics.missing_count}`],
                ['Upgrades / Fake Upscale', `${details.metrics.upgrades_available_count} / ${details.metrics.fake_upscale_count}`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-[#151B26] py-0.5">
                  <span className="text-slate-400">{k}</span>
                  <span className="font-mono-tech text-white">{v}</span>
                </div>
              ))}
              {details.metrics.metrics_notes.map((n, idx) => (
                <div key={idx} className="text-[10px] text-slate-500">
                  • {n}
                </div>
              ))}
            </div>
          )}

          {/* Smart Sequencer Config */}
          {selectedId && (
            <div className="studio-panel p-3 space-y-2.5 text-xs">
              <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-300 uppercase">
                <Sparkles className="w-4 h-4" /> Smart Playlist Sequencer
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-[10px] font-mono-tech text-slate-400">MODO DE SEQUÊNCIA</span>
                <select
                  value={seqMode}
                  onChange={(e) => setSeqMode(e.target.value)}
                  className="px-2 py-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-white"
                >
                  <option value="balanced_dj_flow">Balanced DJ Flow (40/35/15/10)</option>
                  <option value="harmonic_flow">Harmonic Flow (Camelot)</option>
                  <option value="bpm_progression">BPM Progression (Crescente)</option>
                  <option value="energy_progression">Energy Progression</option>
                </select>
              </label>

              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono-tech text-slate-400">
                    PRIOR. HARMÔNICA ({Math.round(harmonicPriority * 100)}%)
                  </span>
                  <input
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={harmonicPriority}
                    onChange={(e) => setHarmonicPriority(Number(e.target.value))}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[10px] font-mono-tech text-slate-400">
                    TOL. BPM (±{bpmTolerance}%)
                  </span>
                  <input
                    type="range"
                    min={2}
                    max={20}
                    step={1}
                    value={bpmTolerance}
                    onChange={(e) => setBpmTolerance(Number(e.target.value))}
                  />
                </label>
              </div>

              <div className="flex flex-wrap gap-3 text-[11px] text-slate-300">
                <label className="inline-flex items-center gap-1">
                  <input type="checkbox" checked={allowHalfTime} onChange={(e) => setAllowHalfTime(e.target.checked)} />
                  Half/Double-Time
                </label>
                <label className="inline-flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={allowRepeatedArtists}
                    onChange={(e) => setAllowRepeatedArtists(e.target.checked)}
                  />
                  Repetir Artistas
                </label>
              </div>

              <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={runSmartSequencer}
                  className="flex-1 py-1.5 rounded font-semibold bg-emerald-500 text-[#0B0D12] hover:bg-emerald-400"
                >
                  Gerar Sequência
                </button>
                {seqPreview && (
                  <button
                    onClick={applySmartSequence}
                    className="flex-1 py-1.5 rounded font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400"
                  >
                    Salvar Ordem
                  </button>
                )}
                {details?.has_original_order_snapshot && (
                  <button
                    onClick={restoreOriginalOrder}
                    className="px-2.5 py-1.5 rounded bg-[#0B0D12] border border-[#242C3D] text-amber-300 inline-flex items-center gap-1"
                    title="Restaurar ordem original"
                  >
                    <RotateCcw className="w-3.5 h-3.5" /> Restaurar
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right: Track List + Sort + Export + Sequencer Explainability */}
        <div className="xl:col-span-8 flex flex-col gap-3">
          {details && (
            <div className="studio-panel p-3 flex flex-col gap-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <select
                    value={addTrackId}
                    onChange={(e) => setAddTrackId(e.target.value)}
                    className="px-2 py-1 rounded bg-[#0B0D12] border border-[#1E2634] text-xs text-white max-w-[240px]"
                  >
                    <option value="">Adicionar faixa da biblioteca...</option>
                    {tracks.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.title} — {t.artist}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleAddTrack}
                    disabled={!addTrackId}
                    className="px-2.5 py-1 rounded text-xs bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 disabled:opacity-40"
                  >
                    + Adicionar
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 text-xs">
                  <select
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="px-2 py-1 rounded bg-[#0B0D12] border border-[#1E2634] text-xs text-slate-300"
                  >
                    <option value="ALL">Status: Todos</option>
                    <option value="COMPLETE">Completas</option>
                    <option value="PREVIEW">Previews</option>
                    <option value="MISSING">Ausentes</option>
                    <option value="CORRUPTED">Corrompidas</option>
                    <option value="SUSPECTED_FAKE_UPSCALE">Fake Upscale</option>
                    <option value="UPGRADE_AVAILABLE">Upgrade Disponível</option>
                  </select>

                  <select
                    value={sortBy}
                    onChange={(e) => handleSort(e.target.value)}
                    className="px-2 py-1 rounded bg-[#0B0D12] border border-[#1E2634] text-xs text-slate-300"
                  >
                    <option value="manual">Ordem Manual</option>
                    <option value="bpm_asc">BPM Crescente</option>
                    <option value="bpm_desc">BPM Decrescente</option>
                    <option value="energy_asc">Energy Crescente</option>
                    <option value="energy_desc">Energy Decrescente</option>
                    <option value="camelot">Camelot</option>
                    <option value="artist">Artista</option>
                    <option value="quality">Qualidade (Car Score)</option>
                    <option value="loudness">Loudness (LUFS)</option>
                  </select>

                  <button
                    onClick={() => handleExportM3u('m3u8')}
                    className="px-2.5 py-1 rounded bg-[#0B0D12] border border-[#242C3D] text-emerald-300 hover:border-emerald-400 inline-flex items-center gap-1"
                  >
                    <Download className="w-3.5 h-3.5" /> M3U8
                  </button>
                  <button
                    onClick={() => handleExportM3u('m3u')}
                    className="px-2.5 py-1 rounded bg-[#0B0D12] border border-[#242C3D] text-slate-300 hover:text-white inline-flex items-center gap-1"
                  >
                    M3U
                  </button>
                </div>
              </div>

              <div className="overflow-x-auto max-h-[340px] overflow-y-auto border border-[#1A202C] rounded">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-[#0B0D12] sticky top-0 text-[10px] font-mono-tech text-slate-400 uppercase border-b border-[#1A202C]">
                    <tr>
                      <th className="py-2 px-2">#</th>
                      <th className="py-2 px-2">Faixa</th>
                      <th className="py-2 px-2">BPM</th>
                      <th className="py-2 px-2">Camelot</th>
                      <th className="py-2 px-2">Qualidade / Status</th>
                      <th className="py-2 px-2 text-right">Ordem / Remover</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#1A202C]">
                    {details.tracks.map((entry, idx) => (
                      <tr key={entry.track.id} className="hover:bg-[#171D29]">
                        <td className="py-1.5 px-2 font-mono-tech text-slate-500">{idx + 1}</td>
                        <td className="py-1.5 px-2">
                          <div className="font-semibold text-white">{entry.track.title}</div>
                          <div className="text-[10px] text-slate-400">{entry.track.artist}</div>
                        </td>
                        <td className="py-1.5 px-2 font-mono-tech text-slate-200">
                          {entry.track.bpm ? entry.track.bpm.toFixed(1) : '—'}
                        </td>
                        <td className="py-1.5 px-2">
                          <span
                            className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech font-bold text-[#0B0D12]"
                            style={{ backgroundColor: getCamelotColor(entry.track.camelot_code) }}
                          >
                            {entry.track.camelot_code || '—'}
                          </span>
                        </td>
                        <td className="py-1.5 px-2">
                          <div className="flex flex-wrap gap-1">
                            {entry.quality_statuses.slice(0, 3).map((st) => (
                              <span
                                key={st}
                                className="px-1.5 py-0.5 rounded text-[9px] font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-slate-300"
                              >
                                {st}
                              </span>
                            ))}
                          </div>
                        </td>
                        <td className="py-1.5 px-2 text-right whitespace-nowrap">
                          <button
                            onClick={() => moveTrack(idx, -1)}
                            disabled={idx === 0}
                            className="p-1 text-slate-400 hover:text-white disabled:opacity-30"
                          >
                            <ArrowUp className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => moveTrack(idx, 1)}
                            disabled={idx === details.tracks.length - 1}
                            className="p-1 text-slate-400 hover:text-white disabled:opacity-30"
                          >
                            <ArrowDown className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => handleRemoveTrack(entry.track.id)}
                            className="p-1 text-rose-400 hover:text-rose-300 ml-1"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Smart Sequencer Explainable Transitions Preview */}
          {seqPreview && (
            <div className="studio-panel p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-emerald-300 uppercase">
                  Prévia do Smart Sequencer • Score Médio {Math.round(seqPreview.average_score * 100)}%
                </span>
                <span className="text-[11px] font-mono-tech text-slate-400">
                  {seqPreview.transitions.length} transições avaliadas
                </span>
              </div>

              <div className="space-y-1.5 max-h-[260px] overflow-y-auto">
                {seqPreview.transitions.map((tr, idx) => (
                  <div
                    key={`${tr.track_a_id}-${tr.track_b_id}-${idx}`}
                    className="bg-[#0B0D12] border border-[#1E2634] rounded p-2.5 text-xs space-y-1"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-semibold text-white">
                        {idx + 1}. {tr.title_a} ({tr.camelot_a || '—'} • {tr.bpm_a?.toFixed(1) ?? '—'}) →{' '}
                        {tr.title_b} ({tr.camelot_b || '—'} • {tr.bpm_b?.toFixed(1) ?? '—'})
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono-tech font-bold ${
                          tr.compatibility
                            ? 'bg-emerald-500/20 text-emerald-300'
                            : 'bg-amber-500/20 text-amber-300'
                        }`}
                      >
                        {Math.round(tr.score * 100)}% • Out {tr.mix_out_sec.toFixed(0)}s / In {tr.mix_in_sec.toFixed(0)}s
                      </span>
                    </div>
                    <div className="text-[11px] text-slate-300">{tr.justification}</div>
                    {tr.alerts.length > 0 && (
                      <div className="text-[10px] text-amber-400">Alertas: {tr.alerts.join(' • ')}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
