import React, { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowDownUp,
  Disc3,
  GitCompare,
  Pause,
  Play,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { apiClient } from '../api/client';
import { AbComparisonModal } from '../components/AbComparisonModal';
import { RgbWaveformCanvas } from '../components/RgbWaveformCanvas';
import { RotaryControl } from '../components/RotaryControl';
import type {
  AbComparisonResponse,
  BeatgridData,
  DeckId,
  DeckState,
  DJRecommendation,
  SectionSegment,
  TransitionAnalysisResponse,
  UnifiedTrack,
} from '../types/music';
import {
  areCamelotCompatible,
  formatTimecode,
  getCamelotColor,
  parseJsonSafe,
} from '../utils/camelot';

interface DjModeProViewProps {
  tracks: UnifiedTrack[];
  playlistFilterTracks?: UnifiedTrack[] | null;
  onClearPlaylistFilter?: () => void;
  deckA: DeckState;
  deckB: DeckState;
  crossfader: number;
  onLoadTrack: (deck: DeckId, track: UnifiedTrack, autoPlay?: boolean) => void;
  onTogglePlay: (deck: DeckId) => void;
  onCue: (deck: DeckId) => void;
  onSync: (targetDeck: DeckId) => void;
  onSeek: (deck: DeckId, sec: number) => void;
  onPitchChange: (deck: DeckId, rate: number) => void;
  onTogglePitchRange: (deck: DeckId) => void;
  onToggleKeyLock: (deck: DeckId) => void;
  onEqChange: (deck: DeckId, band: 'low' | 'mid' | 'high', val: number) => void;
  onFilterChange: (deck: DeckId, val: number) => void;
  onHotCueClick: (deck: DeckId, idx: number, shiftKey: boolean) => void;
  onCrossfaderChange: (pos: number) => void;
  onRefreshTracks: () => void;
}

const LedMeter: React.FC<{ levelL: number; levelR: number }> = ({ levelL, levelR }) => {
  const segments = 14;
  const renderBar = (lvl: number, label: string) => {
    const db = lvl > 0.0001 ? 20 * Math.log10(lvl) : -60;
    const activeCount = Math.max(0, Math.min(segments, Math.round(((db + 48) / 48) * segments)));
    return (
      <div className="flex flex-col items-center gap-0.5">
        <div className="flex flex-col-reverse gap-[2px] bg-[#080A0E] p-1 rounded border border-[#1A202C]">
          {Array.from({ length: segments }).map((_, i) => {
            const lit = i < activeCount;
            const colorClass =
              i >= 12
                ? lit
                  ? 'bg-rose-500 shadow-[0_0_5px_#f43f5e]'
                  : 'bg-[#1D151B]'
                : i >= 9
                  ? lit
                    ? 'bg-amber-400 shadow-[0_0_5px_#fbbf24]'
                    : 'bg-[#1E1C14]'
                  : lit
                    ? 'bg-emerald-400 shadow-[0_0_5px_#34d399]'
                    : 'bg-[#111D1B]';
            return <div key={i} className={`w-2.5 h-1.5 rounded-[1px] ${colorClass}`} />;
          })}
        </div>
        <span className="text-[9px] font-mono-tech text-slate-500">{label}</span>
      </div>
    );
  };

  return (
    <div className="flex items-center gap-1">
      {renderBar(levelL, 'L')}
      {renderBar(levelR, 'R')}
    </div>
  );
};

export const DjModeProView: React.FC<DjModeProViewProps> = ({
  tracks,
  playlistFilterTracks,
  onClearPlaylistFilter,
  deckA,
  deckB,
  crossfader,
  onLoadTrack,
  onTogglePlay,
  onCue,
  onSync,
  onSeek,
  onPitchChange,
  onTogglePitchRange,
  onToggleKeyLock,
  onEqChange,
  onFilterChange,
  onHotCueClick,
  onCrossfaderChange,
  onRefreshTracks,
}) => {
  const [zoomA, setZoomA] = useState(1);
  const [zoomB, setZoomB] = useState(1);
  const [browserSearch, setBrowserSearch] = useState('');
  const [sortBy, setSortBy] = useState<'title' | 'bpm' | 'camelot' | 'energy'>('bpm');
  const [sortAsc, setSortAsc] = useState(true);
  const [recommendations, setRecommendations] = useState<DJRecommendation[]>([]);
  const [activeRecDeck, setActiveRecDeck] = useState<DeckId>('A');
  const [transitionAnalysis, setTransitionAnalysis] = useState<TransitionAnalysisResponse | null>(null);
  const [dismissedEqIds, setDismissedEqIds] = useState<Set<string>>(new Set());
  const [abCompare, setAbCompare] = useState<AbComparisonResponse | null>(null);

  const activeTrackForRecs = activeRecDeck === 'A' ? deckA.track || deckB.track : deckB.track || deckA.track;
  const sourceTracks = playlistFilterTracks && playlistFilterTracks.length > 0 ? playlistFilterTracks : tracks;

  useEffect(() => {
    let cancelled = false;
    if (!deckA.track?.id || !deckB.track?.id) {
      setTransitionAnalysis(null);
      return;
    }
    apiClient
      .analyzeDjTransition(deckA.track.id, deckB.track.id, deckA.pitchRate, deckB.pitchRate)
      .then((res) => {
        if (!cancelled) {
          setTransitionAnalysis(res);
          setDismissedEqIds(new Set());
        }
      })
      .catch(() => {
        if (!cancelled) setTransitionAnalysis(null);
      });
    return () => {
      cancelled = true;
    };
  }, [deckA.track?.id, deckB.track?.id, deckA.pitchRate, deckB.pitchRate]);

  useEffect(() => {
    let cancelled = false;
    if (!activeTrackForRecs?.id) {
      setRecommendations([]);
      return;
    }
    apiClient
      .getNextRecommendations(activeTrackForRecs.id, 6)
      .then((res) => {
        if (!cancelled) setRecommendations(res.recommendations || []);
      })
      .catch(() => {
        if (!cancelled) setRecommendations([]);
      });
    return () => {
      cancelled = true;
    };
  }, [activeTrackForRecs?.id]);

  const filteredTracks = useMemo(() => {
    const q = browserSearch.trim().toLowerCase();
    const list = sourceTracks.filter((t) => {
      if (!q) return true;
      return `${t.title} ${t.artist} ${t.album || ''} ${t.camelot_code || ''} ${t.genres_raw}`.toLowerCase().includes(q);
    });

    return [...list].sort((a, b) => {
      let cmp = 0;
      if (sortBy === 'title') cmp = a.title.localeCompare(b.title);
      else if (sortBy === 'bpm') cmp = (a.bpm || 0) - (b.bpm || 0);
      else if (sortBy === 'camelot') cmp = (a.camelot_code || '').localeCompare(b.camelot_code || '');
      else if (sortBy === 'energy') cmp = (a.energy || 0) - (b.energy || 0);
      return sortAsc ? cmp : -cmp;
    });
  }, [sourceTracks, browserSearch, sortBy, sortAsc]);

  const toggleSort = (col: 'title' | 'bpm' | 'camelot' | 'energy') => {
    if (sortBy === col) setSortAsc(!sortAsc);
    else {
      setSortBy(col);
      setSortAsc(true);
    }
  };

  const renderDeck = (state: DeckState, zoom: number, setZoom: (z: number) => void) => {
    const isA = state.deck === 'A';
    const accent = isA ? '#38BDF8' : '#F59E0B';
    const trk = state.track;
    const sections = parseJsonSafe<SectionSegment[]>(trk?.sections_json, []);
    const beatgrid = parseJsonSafe<BeatgridData | null>(trk?.beatgrid_json, null);
    const effectiveBpm = trk?.bpm ? (trk.bpm * state.pitchRate).toFixed(1) : '---.-';
    const pitchPct = ((state.pitchRate - 1) * 100).toFixed(2);
    const remaining = Math.max(0, (state.duration || 0) - state.currentTime);

    return (
      <div className="studio-panel p-3 flex flex-col gap-2.5 flex-1 min-w-0">
        {/* Deck Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div
              className={`w-8 h-8 rounded flex items-center justify-center font-mono-tech font-bold text-sm border shrink-0 ${
                isA
                  ? 'bg-cyan-500/15 border-cyan-500/40 text-cyan-400'
                  : 'bg-amber-500/15 border-amber-500/40 text-amber-400'
              }`}
            >
              {state.deck}
            </div>
            {(trk?.hd_cover_url || trk?.cover_url) && (
              <img
                src={trk.hd_cover_url || trk.cover_url || ''}
                alt={trk.title}
                className="w-9 h-9 rounded object-cover border border-[#242C3D] shrink-0"
              />
            )}
            <div className="min-w-0">
              <div className="text-sm font-bold text-white truncate">
                {trk ? trk.title : `Deck ${state.deck} — Vazio`}
              </div>
              <div className="text-[11px] text-slate-400 truncate">
                {trk ? `${trk.artist}${trk.album ? ` • ${trk.album}` : ''}` : 'Selecione uma faixa no Browser abaixo'}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {trk?.camelot_code && (
              <span
                className="px-2 py-0.5 rounded text-[11px] font-mono-tech font-bold text-[#0B0D12]"
                style={{ backgroundColor: getCamelotColor(trk.camelot_code) }}
              >
                {trk.camelot_code}
              </span>
            )}
            <div className="bg-[#080A0E] border border-[#1A202C] rounded px-2 py-1 text-right">
              <div className="text-sm font-mono-tech font-bold text-white leading-none">{effectiveBpm}</div>
              <div className="text-[9px] font-mono-tech text-slate-500">BPM</div>
            </div>
          </div>
        </div>

        {/* Timecode & Zoom Strip */}
        <div className="flex items-center justify-between text-[11px] font-mono-tech bg-[#0B0D12] px-2.5 py-1 rounded border border-[#1A202C]">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="text-white">{formatTimecode(state.currentTime)}</span>
            <span className="text-slate-500">REM -{formatTimecode(remaining)}</span>
            {trk?.integrated_lufs != null && (
              <span className="text-[10px] text-cyan-400">{trk.integrated_lufs.toFixed(1)} LUFS</span>
            )}
            {trk?.car_audio_score != null && (
              <span className="text-[10px] text-emerald-400">Car {trk.car_audio_score}</span>
            )}
            {trk?.is_preview && (
              <span className="px-1 rounded bg-amber-500/20 text-amber-300 text-[9px]">PREVIEW</span>
            )}
            {trk?.quality_warning && (
              <span className="px-1 rounded bg-rose-500/20 text-rose-300 text-[9px]" title={trk.quality_warning}>
                ALERTA
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setZoom(Math.max(1, zoom / 2))}
              className="p-1 rounded hover:bg-[#1A202C] text-slate-400 hover:text-white"
              title="Zoom Out"
            >
              <ZoomOut className="w-3.5 h-3.5" />
            </button>
            <span className="text-[10px] text-slate-300 w-7 text-center">{zoom}x</span>
            <button
              onClick={() => setZoom(Math.min(8, zoom * 2))}
              className="p-1 rounded hover:bg-[#1A202C] text-slate-400 hover:text-white"
              title="Zoom In"
            >
              <ZoomIn className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Parallel RGB Waveform */}
        <RgbWaveformCanvas
          waveform={state.waveform}
          currentTime={state.currentTime}
          duration={state.duration || (trk?.duration_ms ? trk.duration_ms / 1000 : 0)}
          sections={sections}
          beatgrid={beatgrid}
          hotCues={state.hotCues}
          zoom={zoom}
          accentColor={accent}
          onSeek={(t) => onSeek(state.deck, t)}
        />

        {/* 8 Colored Hot Cues A-H */}
        <div className="grid grid-cols-8 gap-1">
          {state.hotCues.map((cue, idx) => (
            <button
              key={cue.slot}
              onClick={(e) => onHotCueClick(state.deck, idx, e.shiftKey)}
              onContextMenu={(e) => {
                e.preventDefault();
                onHotCueClick(state.deck, idx, true);
              }}
              title={
                cue.timeSec !== null
                  ? `${cue.label} (${formatTimecode(cue.timeSec)}) • Shift+Click/Botão Direito para redefinir`
                  : `Cue ${cue.slot} vazio • Clique para marcar posição atual`
              }
              className="py-1 px-1 rounded border text-[10px] font-mono-tech font-bold truncate transition-all"
              style={{
                borderColor: cue.timeSec !== null ? cue.color : '#1E2634',
                backgroundColor: cue.timeSec !== null ? `${cue.color}22` : '#0B0D12',
                color: cue.timeSec !== null ? '#F8FAFC' : '#64748B',
              }}
            >
              {cue.slot}
              {cue.timeSec !== null ? `:${cue.label.slice(0, 3)}` : ''}
            </button>
          ))}
        </div>

        {/* Tactile Controls Row: Transport + Pitch + EQ + Filter + VU */}
        <div className="grid grid-cols-12 gap-2 items-center bg-[#0B0D12] p-2.5 rounded border border-[#1A202C]">
          {/* Transport + Sync */}
          <div className="col-span-12 sm:col-span-4 flex flex-col gap-1.5">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => onTogglePlay(state.deck)}
                disabled={!state.audioUrl}
                className={`flex-1 py-2 rounded font-bold text-xs flex items-center justify-center gap-1.5 border transition-all disabled:opacity-40 ${
                  state.isPlaying
                    ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300'
                    : isA
                      ? 'bg-cyan-500/15 border-cyan-500/50 text-cyan-300 hover:bg-cyan-500/25'
                      : 'bg-amber-500/15 border-amber-500/50 text-amber-300 hover:bg-amber-500/25'
                }`}
              >
                {state.isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                {state.isPlaying ? 'PAUSE' : 'PLAY'}
              </button>
              <button
                onClick={() => onCue(state.deck)}
                disabled={!state.audioUrl}
                className="px-3 py-2 rounded font-mono-tech font-bold text-xs bg-[#151A25] border border-[#242C3D] text-amber-400 hover:border-amber-400 disabled:opacity-40"
              >
                CUE
              </button>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => onSync(state.deck)}
                className="flex-1 py-1 rounded font-mono-tech font-bold text-[11px] bg-[#151A25] border border-[#242C3D] text-cyan-300 hover:border-cyan-400"
                title="Sincronizar BPM com o outro Deck"
              >
                SYNC BPM
              </button>
              <button
                onClick={() => onToggleKeyLock(state.deck)}
                className={`px-2.5 py-1 rounded font-mono-tech font-bold text-[11px] border ${
                  state.keyLock
                    ? 'bg-purple-500/20 border-purple-400 text-purple-300'
                    : 'bg-[#151A25] border-[#242C3D] text-slate-400'
                }`}
                title="Master Tempo / Key Lock"
              >
                MT
              </button>
            </div>
          </div>

          {/* 3-Band EQ + DJ Filter */}
          <div className="col-span-8 sm:col-span-5 flex items-center justify-around">
            <RotaryControl
              label="HIGH"
              value={state.eqHigh}
              min={-24}
              max={6}
              unit="dB"
              accent={accent}
              onChange={(v) => onEqChange(state.deck, 'high', v)}
            />
            <RotaryControl
              label="MID"
              value={state.eqMid}
              min={-24}
              max={6}
              unit="dB"
              accent={accent}
              onChange={(v) => onEqChange(state.deck, 'mid', v)}
            />
            <RotaryControl
              label="LOW"
              value={state.eqLow}
              min={-24}
              max={6}
              unit="dB"
              accent={accent}
              onChange={(v) => onEqChange(state.deck, 'low', v)}
            />
            <RotaryControl
              label="FLTR"
              value={state.filter}
              min={-1}
              max={1}
              accent="#A855F7"
              onChange={(v) => onFilterChange(state.deck, v)}
            />
          </div>

          {/* Pitch Slider + VU Meter */}
          <div className="col-span-4 sm:col-span-3 flex items-center justify-end gap-2">
            <div className="flex flex-col items-center gap-1 flex-1">
              <div className="flex items-center justify-between w-full text-[10px] font-mono-tech">
                <button
                  onClick={() => onTogglePitchRange(state.deck)}
                  className="text-slate-400 hover:text-white underline"
                >
                  ±{Math.round(state.pitchRange * 100)}%
                </button>
                <span className="text-slate-300">
                  {Number(pitchPct) > 0 ? `+${pitchPct}%` : `${pitchPct}%`}
                </span>
              </div>
              <input
                type="range"
                min={1 - state.pitchRange}
                max={1 + state.pitchRange}
                step={0.001}
                value={state.pitchRate}
                onChange={(e) => onPitchChange(state.deck, Number(e.target.value))}
                onDoubleClick={() => onPitchChange(state.deck, 1.0)}
                className={`w-full h-1.5 studio-fader ${!isA ? 'studio-fader-amber' : ''}`}
                title="Tempo / Pitch Fader (duplo clique reseta para 0%)"
              />
            </div>
            <LedMeter levelL={state.rmsL} levelR={state.rmsR} />
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Dual Decks A & B */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {renderDeck(deckA, zoomA, setZoomA)}
        {renderDeck(deckB, zoomB, setZoomB)}
      </div>

      {/* Center Hardware Crossfader + Layer 3 Next-Track Intelligence */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Crossfader */}
        <div className="lg:col-span-4 studio-panel p-3 flex flex-col justify-center gap-2">
          <div className="flex items-center justify-between text-[11px] font-mono-tech">
            <button
              onClick={() => onCrossfaderChange(-1)}
              className="px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/25"
            >
              DECK A
            </button>
            <button
              onClick={() => onCrossfaderChange(0)}
              className="text-slate-400 hover:text-white"
            >
              CROSSFADER ({crossfader === 0 ? 'CENTER' : crossfader.toFixed(2)})
            </button>
            <button
              onClick={() => onCrossfaderChange(1)}
              className="px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 hover:bg-amber-500/25"
            >
              DECK B
            </button>
          </div>
          <input
            type="range"
            min={-1}
            max={1}
            step={0.01}
            value={crossfader}
            onChange={(e) => onCrossfaderChange(Number(e.target.value))}
            onDoubleClick={() => onCrossfaderChange(0)}
            className="w-full h-2 studio-fader"
          />
        </div>

        {/* Layer 3 DJ Intelligence Next-Track Strip */}
        <div className="lg:col-span-8 studio-panel p-3 flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-bold text-white uppercase tracking-wide">
                Camada 3 • Sugestões Harmônicas & Pontos de Transição
              </span>
            </div>
            <div className="flex items-center gap-1 text-[10px] font-mono-tech">
              <span className="text-slate-400 mr-1">Base:</span>
              <button
                onClick={() => setActiveRecDeck('A')}
                className={`px-2 py-0.5 rounded border ${
                  activeRecDeck === 'A'
                    ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                    : 'border-[#242C3D] text-slate-400'
                }`}
              >
                Deck A
              </button>
              <button
                onClick={() => setActiveRecDeck('B')}
                className={`px-2 py-0.5 rounded border ${
                  activeRecDeck === 'B'
                    ? 'bg-amber-500/20 border-amber-400 text-amber-300'
                    : 'border-[#242C3D] text-slate-400'
                }`}
              >
                Deck B
              </button>
            </div>
          </div>

          {recommendations.length === 0 ? (
            <div className="text-xs text-slate-500 py-1">
              Carregue uma faixa em um Deck para receber recomendações Camelot, delta de BPM e pontos de Mix-Out / Mix-In.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {recommendations.slice(0, 3).map((rec) => {
                const targetTrack = tracks.find((t) => t.id === rec.track_id);
                const sign = rec.bpm_delta_pct > 0 ? '+' : '';
                return (
                  <div
                    key={rec.track_id}
                    className="bg-[#0B0D12] border border-[#1E2634] rounded p-2 flex flex-col justify-between gap-1.5"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-white truncate">{rec.title}</div>
                        <div className="text-[10px] text-slate-400 truncate">{rec.artist}</div>
                      </div>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-mono-tech font-bold shrink-0 ${
                          rec.is_harmonic_compatible
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                        }`}
                      >
                        {Math.round(rec.score * 100)}%
                      </span>
                    </div>
                    <div className="text-[10px] font-mono-tech text-slate-400 flex flex-wrap gap-x-2">
                      <span className="text-cyan-300">{rec.camelot_code || '—'}</span>
                      <span>
                        {sign}
                        {rec.bpm_delta_pct.toFixed(1)}% BPM
                      </span>
                      <span className="text-slate-500">
                        Out {rec.transition_points.mix_out_sec.toFixed(0)}s → In{' '}
                        {rec.transition_points.mix_in_sec.toFixed(0)}s
                      </span>
                    </div>
                    {targetTrack && (
                      <div className="flex gap-1 pt-0.5">
                        <button
                          onClick={() => onLoadTrack('A', targetTrack, false)}
                          className="flex-1 py-0.5 rounded text-[10px] font-mono-tech font-bold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25"
                        >
                          Load A
                        </button>
                        <button
                          onClick={() => onLoadTrack('B', targetTrack, false)}
                          className="flex-1 py-0.5 rounded text-[10px] font-mono-tech font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25"
                        >
                          Load B
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Phase 5: Transition Analysis + Non-Destructive EQ Assist + A/B Compare */}
      {transitionAnalysis && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
          <div className="lg:col-span-7 studio-panel p-3 space-y-2 text-xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-white uppercase tracking-wide">
                  Transition Analysis (Deck A ↔ Deck B)
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono-tech font-bold border ${
                    transitionAnalysis.risk_level === 'LOW'
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : transitionAnalysis.risk_level === 'MEDIUM'
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                        : 'bg-rose-500/20 text-rose-300 border-rose-500/40'
                  }`}
                >
                  RISCO {transitionAnalysis.risk_level}
                </span>
              </div>
              {deckA.track?.id && deckB.track?.id && (
                <button
                  onClick={async () => {
                    const res = await apiClient.compareTracks(deckA.track!.id, deckB.track!.id);
                    setAbCompare(res);
                  }}
                  className="px-2.5 py-1 rounded text-[11px] font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-cyan-300 hover:border-cyan-400 inline-flex items-center gap-1"
                >
                  <GitCompare className="w-3.5 h-3.5" /> Comparar Qualidade A/B
                </button>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 font-mono-tech text-[11px]">
              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2">
                <div className="text-[9px] text-slate-400">DELTA BPM</div>
                <div className="text-white font-bold">
                  {transitionAnalysis.delta_bpm_pct != null ? `${transitionAnalysis.delta_bpm_pct > 0 ? '+' : ''}${transitionAnalysis.delta_bpm_pct}%` : '—'}
                </div>
              </div>
              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2">
                <div className="text-[9px] text-slate-400">CAMELOT</div>
                <div className={transitionAnalysis.is_harmonic_compatible ? 'text-emerald-300 font-bold' : 'text-amber-300 font-bold'}>
                  {transitionAnalysis.camelot_a || '—'} → {transitionAnalysis.camelot_b || '—'}
                </div>
              </div>
              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2">
                <div className="text-[9px] text-slate-400">DELTA LUFS</div>
                <div className="text-white font-bold">
                  {transitionAnalysis.delta_lufs != null ? `${transitionAnalysis.delta_lufs > 0 ? '+' : ''}${transitionAnalysis.delta_lufs}` : '—'}
                </div>
              </div>
              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2">
                <div className="text-[9px] text-slate-400">BASS OVERLAP</div>
                <div className="text-white font-bold">
                  {transitionAnalysis.bass_overlap_score != null ? `${Math.round(transitionAnalysis.bass_overlap_score * 100)}%` : '—'}
                </div>
              </div>
              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2">
                <div className="text-[9px] text-slate-400">PICO EST. SOMA</div>
                <div className="text-white font-bold">
                  {transitionAnalysis.estimated_combined_peak_dbfs != null ? `${transitionAnalysis.estimated_combined_peak_dbfs} dBFS` : '—'}
                </div>
              </div>
            </div>

            <div className="text-[10px] text-slate-400">
              {transitionAnalysis.clipping_risk_note}
            </div>
            {transitionAnalysis.alerts.length > 0 && (
              <div className="text-[11px] text-amber-300 space-y-0.5">
                {transitionAnalysis.alerts.map((a, i) => (
                  <div key={i}>• {a}</div>
                ))}
              </div>
            )}
          </div>

          {/* Non-Destructive EQ Assist */}
          <div className="lg:col-span-5 studio-panel p-3 space-y-2 text-xs">
            <div className="flex items-center gap-2">
              <SlidersHorizontal className="w-4 h-4 text-purple-400" />
              <span className="font-bold text-white uppercase tracking-wide">
                EQ Assist (Não-Destrutivo)
              </span>
            </div>
            {transitionAnalysis.eq_suggestions.filter((s) => !dismissedEqIds.has(s.id)).length === 0 ? (
              <div className="text-xs text-slate-400">
                Nenhuma correção urgente de EQ sugerida para esta transição.
              </div>
            ) : (
              <div className="space-y-1.5">
                {transitionAnalysis.eq_suggestions
                  .filter((s) => !dismissedEqIds.has(s.id))
                  .map((s) => (
                    <div key={s.id} className="bg-[#0B0D12] border border-[#1E2634] rounded p-2 space-y-1.5">
                      <div className="text-[11px] text-slate-200">{s.reason}</div>
                      <div className="flex gap-1.5">
                        <button
                          onClick={() => {
                            onEqChange(s.target_deck, s.band, s.suggested_db);
                            setDismissedEqIds((prev) => new Set(prev).add(s.id));
                          }}
                          className="px-2.5 py-1 rounded text-[10px] font-mono-tech font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 hover:bg-purple-500/30"
                        >
                          Aplicar Deck {s.target_deck} {s.band.toUpperCase()} ({s.suggested_db} dB)
                        </button>
                        <button
                          onClick={() => setDismissedEqIds((prev) => new Set(prev).add(s.id))}
                          className="px-2 py-1 rounded text-[10px] font-mono-tech text-slate-400 hover:text-white"
                        >
                          Ignorar
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Rekordbox / Serato Style Bottom Collection Browser */}
      <div className="studio-panel p-3 flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Disc3 className="w-4 h-4 text-cyan-400" />
            <span className="text-xs font-bold text-white uppercase tracking-wide">
              Browser da Coleção ({filteredTracks.length} faixas)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {playlistFilterTracks && playlistFilterTracks.length > 0 && onClearPlaylistFilter && (
              <button
                onClick={onClearPlaylistFilter}
                className="px-2 py-1 rounded text-[10px] font-mono-tech bg-cyan-500/15 text-cyan-300 border border-cyan-500/30"
              >
                Filtro Playlist ({playlistFilterTracks.length}) ×
              </button>
            )}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={browserSearch}
                onChange={(e) => setBrowserSearch(e.target.value)}
                placeholder="Filtrar título, artista, Camelot..."
                className="pl-8 pr-3 py-1.5 text-xs bg-[#0B0D12] border border-[#1E2634] rounded text-slate-200 focus:outline-none focus:border-cyan-500 w-64"
              />
            </div>
            <button
              onClick={onRefreshTracks}
              className="p-1.5 rounded bg-[#0B0D12] border border-[#1E2634] text-slate-400 hover:text-white"
              title="Atualizar coleção"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="overflow-x-auto max-h-[290px] overflow-y-auto border border-[#1A202C] rounded">
          <table className="w-full text-left border-collapse">
            <thead className="bg-[#0B0D12] sticky top-0 z-10 text-[10px] font-mono-tech text-slate-400 uppercase border-b border-[#1A202C]">
              <tr>
                <th className="py-2 px-2.5">Ações</th>
                <th className="py-2 px-2.5 cursor-pointer hover:text-white" onClick={() => toggleSort('title')}>
                  <span className="inline-flex items-center gap-1">
                    Faixa <ArrowDownUp className="w-3 h-3" />
                  </span>
                </th>
                <th className="py-2 px-2.5">Preview</th>
                <th className="py-2 px-2.5 cursor-pointer hover:text-white" onClick={() => toggleSort('bpm')}>
                  <span className="inline-flex items-center gap-1">
                    BPM <ArrowDownUp className="w-3 h-3" />
                  </span>
                </th>
                <th className="py-2 px-2.5 cursor-pointer hover:text-white" onClick={() => toggleSort('camelot')}>
                  <span className="inline-flex items-center gap-1">
                    Camelot <ArrowDownUp className="w-3 h-3" />
                  </span>
                </th>
                <th className="py-2 px-2.5 cursor-pointer hover:text-white" onClick={() => toggleSort('energy')}>
                  Energia
                </th>
                <th className="py-2 px-2.5">LUFS</th>
                <th className="py-2 px-2.5">Fonte</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1A202C] text-xs">
              {filteredTracks.map((t) => {
                const refKey = activeTrackForRecs?.camelot_code || activeTrackForRecs?.key;
                const compat = refKey ? areCamelotCompatible(refKey, t.camelot_code || t.key) : false;
                const playable = Boolean(t.local_path || t.preview_url);
                const energyPct = Math.round((t.energy || 0.4) * 100);
                return (
                  <tr key={t.id} className="hover:bg-[#171D29] transition-colors">
                    <td className="py-1.5 px-2.5 whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => onLoadTrack('A', t, true)}
                          disabled={!playable}
                          className="px-2 py-0.5 rounded text-[10px] font-mono-tech font-bold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/30 disabled:opacity-35"
                        >
                          Load A
                        </button>
                        <button
                          onClick={() => onLoadTrack('B', t, true)}
                          disabled={!playable}
                          className="px-2 py-0.5 rounded text-[10px] font-mono-tech font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/30 disabled:opacity-35"
                        >
                          Load B
                        </button>
                      </div>
                    </td>
                    <td className="py-1.5 px-2.5 max-w-[260px]">
                      <div className="flex items-center gap-2">
                        <img
                          src={t.hd_cover_url || t.cover_url || 'https://placehold.co/32x32/12161F/38BDF8?text=%E2%99%AB'}
                          alt={t.title}
                          className="w-7 h-7 rounded object-cover shrink-0 bg-[#0B0D12]"
                        />
                        <div className="min-w-0">
                          <div className="font-semibold text-white truncate">{t.title}</div>
                          <div className="text-[10px] text-slate-400 truncate">{t.artist}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-1.5 px-2.5">
                      {/* Mini Waveform Energy Preview */}
                      <div className="flex items-end gap-[2px] h-4 w-16">
                        {[0.4, 0.7, 0.9, 0.6, 1.0, 0.8, 0.5, 0.85].map((m, idx) => (
                          <span
                            key={idx}
                            className="w-1.5 rounded-t bg-cyan-500/70"
                            style={{ height: `${Math.max(20, Math.round(energyPct * m))}%` }}
                          />
                        ))}
                      </div>
                    </td>
                    <td className="py-1.5 px-2.5 font-mono-tech text-slate-200">
                      {t.bpm ? t.bpm.toFixed(1) : '—'}
                    </td>
                    <td className="py-1.5 px-2.5">
                      <div className="flex items-center gap-1.5">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono-tech font-bold text-[#0B0D12]"
                          style={{ backgroundColor: getCamelotColor(t.camelot_code) }}
                        >
                          {t.camelot_code || t.key || '—'}
                        </span>
                        {compat && (
                          <span className="text-[9px] font-mono-tech text-emerald-400" title="Compatível com o Deck ativo">
                            ● HARMONIA
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-1.5 px-2.5 font-mono-tech text-slate-300">
                      {t.energy !== null && t.energy !== undefined ? `${energyPct}%` : '—'}
                    </td>
                    <td className="py-1.5 px-2.5 font-mono-tech text-slate-400">
                      {t.integrated_lufs !== null && t.integrated_lufs !== undefined
                        ? `${t.integrated_lufs.toFixed(1)}`
                        : '—'}
                    </td>
                    <td className="py-1.5 px-2.5 text-[10px] font-mono-tech text-slate-400">
                      {t.local_path ? (
                        <span className="text-emerald-400">LOCAL</span>
                      ) : t.preview_url ? (
                        <span className="text-cyan-400">PREVIEW</span>
                      ) : (
                        <span className="text-slate-600">META</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <AbComparisonModal data={abCompare} onClose={() => setAbCompare(null)} />
    </div>
  );
};
