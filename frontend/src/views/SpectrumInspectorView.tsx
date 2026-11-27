import React, { useEffect, useRef, useState } from 'react';
import { Activity, Cpu, Gauge, RotateCcw, ShieldCheck, Waves } from 'lucide-react';
import { apiClient } from '../api/client';
import { djAudioEngine } from '../audio/djAudioEngine';
import { AudioQualityPanel } from '../components/AudioQualityPanel';
import type { DeckState, QualityReport, UnifiedTrack } from '../types/music';

interface SpectrumInspectorViewProps {
  tracks: UnifiedTrack[];
  deckA: DeckState;
  deckB: DeckState;
  onRefreshTracks: () => void;
}

type SpectrumMode = 'fft' | '6band' | 'waterfall';
type WindowMode = 'hann' | 'blackman';

const FREQ_GRID = [30, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
const DB_GRID = [0, -12, -24, -36, -48, -60, -72, -84, -96];
const SIX_BANDS = [
  { label: 'Subgrave', range: '20–60 Hz', min: 20, max: 60, color: '#22C55E' },
  { label: 'Grave', range: '60–250 Hz', min: 60, max: 250, color: '#10B981' },
  { label: 'Médio-Grave', range: '250–500 Hz', min: 250, max: 500, color: '#06B6D4' },
  { label: 'Médio', range: '500–2k Hz', min: 500, max: 2000, color: '#3B82F6' },
  { label: 'Médio-Agudo', range: '2–6 kHz', min: 2000, max: 6000, color: '#A855F7' },
  { label: 'Agudo', range: '6–20 kHz', min: 6000, max: 20000, color: '#EC4899' },
];

export const SpectrumInspectorView: React.FC<SpectrumInspectorViewProps> = ({
  tracks,
  deckA,
  deckB,
  onRefreshTracks,
}) => {
  const [mode, setMode] = useState<SpectrumMode>('fft');
  const [windowMode, setWindowMode] = useState<WindowMode>('blackman');
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(
    deckA.track?.id || deckB.track?.id || tracks[0]?.id || null,
  );
  const [crosshair, setCrosshair] = useState<{ x: number; y: number; hz: number; db: number } | null>(
    null,
  );
  const [meters, setMeters] = useState({ rmsL: 0, rmsR: 0, correlation: 1.0, stereoWidth: 0.0 });
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [qualityReport, setQualityReport] = useState<QualityReport | null>(null);
  const [loadingQuality, setLoadingQuality] = useState(false);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const peakHoldRef = useRef<Float32Array | null>(null);
  const waterfallBufferRef = useRef<ImageData | null>(null);
  const crosshairRef = useRef(crosshair);
  crosshairRef.current = crosshair;

  const selectedTrack =
    tracks.find((t) => t.id === selectedTrackId) || deckA.track || deckB.track || tracks[0] || null;

  useEffect(() => {
    if (!selectedTrackId && (deckA.track?.id || deckB.track?.id || tracks[0]?.id)) {
      setSelectedTrackId(deckA.track?.id || deckB.track?.id || tracks[0]?.id || null);
    }
  }, [deckA.track?.id, deckB.track?.id, tracks, selectedTrackId]);

  useEffect(() => {
    if (!selectedTrack?.id) {
      setQualityReport(null);
      return;
    }
    apiClient
      .getTrackQuality(selectedTrack.id)
      .then(setQualityReport)
      .catch(() => setQualityReport(null));
  }, [selectedTrack?.id, selectedTrack?.quality_analyzed_at]);

  const resetPeakHold = () => {
    peakHoldRef.current = null;
  };

  useEffect(() => {
    let rafId = 0;

    const renderFrame = () => {
      const canvas = canvasRef.current;
      const spec = djAudioEngine.getMasterSpectrumData();
      if (spec) {
        setMeters({
          rmsL: spec.rmsL,
          rmsR: spec.rmsR,
          correlation: spec.correlation,
          stereoWidth: spec.stereoWidth,
        });
      }

      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          const w = canvas.width;
          const h = canvas.height;
          const minHz = 25;
          const maxHz = 20000;
          const minDb = -96;
          const maxDb = 0;

          const hzToX = (hz: number) =>
            ((Math.log10(Math.max(minHz, hz)) - Math.log10(minHz)) /
              (Math.log10(maxHz) - Math.log10(minHz))) *
            w;
          const dbToY = (db: number) => ((maxDb - Math.max(minDb, Math.min(maxDb, db))) / (maxDb - minDb)) * h;

          if (mode === 'waterfall') {
            if (!waterfallBufferRef.current || waterfallBufferRef.current.width !== w || waterfallBufferRef.current.height !== h) {
              ctx.fillStyle = '#07090D';
              ctx.fillRect(0, 0, w, h);
              waterfallBufferRef.current = ctx.getImageData(0, 0, w, h);
            }
            // Shift down by 2px
            const prev = ctx.getImageData(0, 0, w, h - 2);
            ctx.putImageData(prev, 0, 2);

            // Draw new top row
            const sr = spec?.sampleRate || 44100;
            const fftSize = spec?.fftSize || 8192;
            const binHz = sr / fftSize;

            for (let x = 0; x < w; x += 2) {
              const hz = minHz * Math.pow(maxHz / minHz, x / w);
              const bin = Math.min((spec?.freqDb.length ?? 4096) - 1, Math.max(1, Math.round(hz / binHz)));
              const db = spec ? spec.freqDb[bin] : -96;
              const norm = Math.max(0, Math.min(1, (db - minDb) / (maxDb - minDb)));
              const r = Math.round(Math.min(255, norm * 380));
              const g = Math.round(Math.max(0, Math.min(255, (norm - 0.35) * 320)));
              const b = Math.round(Math.max(30, (1 - Math.abs(norm - 0.35)) * 220));
              ctx.fillStyle = `rgb(${r},${g},${b})`;
              ctx.fillRect(x, 0, 2, 2);
            }
          } else {
            ctx.fillStyle = '#07090D';
            ctx.fillRect(0, 0, w, h);

            // Grid lines (Hz)
            ctx.lineWidth = 1;
            ctx.font = '10px "JetBrains Mono", monospace';
            for (const hz of FREQ_GRID) {
              const x = hzToX(hz);
              ctx.strokeStyle = '#151B26';
              ctx.beginPath();
              ctx.moveTo(x, 0);
              ctx.lineTo(x, h);
              ctx.stroke();
              ctx.fillStyle = '#64748B';
              ctx.textAlign = 'center';
              ctx.fillText(hz >= 1000 ? `${hz / 1000}k` : `${hz}`, x, h - 6);
            }

            // Grid lines (dB)
            for (const db of DB_GRID) {
              const y = dbToY(db);
              ctx.strokeStyle = db === 0 ? '#334155' : '#151B26';
              ctx.beginPath();
              ctx.moveTo(0, y);
              ctx.lineTo(w, y);
              ctx.stroke();
              if (db < 0 && db > -96) {
                ctx.fillStyle = '#475569';
                ctx.textAlign = 'left';
                ctx.fillText(`${db} dB`, 6, y - 3);
              }
            }

            if (spec && mode === 'fft') {
              if (!peakHoldRef.current || peakHoldRef.current.length !== spec.freqDb.length) {
                peakHoldRef.current = new Float32Array(spec.freqDb.length).fill(-100);
              }
              const peakHold = peakHoldRef.current;
              const binHz = spec.sampleRate / spec.fftSize;
              const windowGain = windowMode === 'blackman' ? 0.96 : 1.0;

              // Update peak hold
              for (let i = 0; i < spec.freqDb.length; i++) {
                const val = spec.freqDb[i] * windowGain;
                peakHold[i] = Math.max(val, peakHold[i] - 0.08);
              }

              // Draw Peak Hold curve (Blue/Red gradient feel)
              ctx.strokeStyle = '#F43F5E';
              ctx.lineWidth = 1.5;
              ctx.beginPath();
              for (let x = 0; x < w; x += 2) {
                const hz = minHz * Math.pow(maxHz / minHz, x / w);
                const bin = Math.min(peakHold.length - 1, Math.max(1, Math.round(hz / binHz)));
                const y = dbToY(peakHold[bin]);
                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
              }
              ctx.stroke();

              // Draw Instant RMS Curve (Cyan/Magenta fill)
              ctx.strokeStyle = '#38BDF8';
              ctx.lineWidth = 2;
              ctx.beginPath();
              for (let x = 0; x < w; x += 2) {
                const hz = minHz * Math.pow(maxHz / minHz, x / w);
                const bin = Math.min(spec.freqDb.length - 1, Math.max(1, Math.round(hz / binHz)));
                const y = dbToY(spec.freqDb[bin] * windowGain);
                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
              }
              ctx.stroke();
              ctx.lineTo(w, h);
              ctx.lineTo(0, h);
              ctx.closePath();
              const grad = ctx.createLinearGradient(0, 0, 0, h);
              grad.addColorStop(0, 'rgba(56, 189, 248, 0.28)');
              grad.addColorStop(1, 'rgba(168, 85, 247, 0.03)');
              ctx.fillStyle = grad;
              ctx.fill();
            } else if (spec && mode === '6band') {
              const binHz = spec.sampleRate / spec.fftSize;
              const colW = (w - 80) / SIX_BANDS.length;
              SIX_BANDS.forEach((b, idx) => {
                const startBin = Math.max(1, Math.floor(b.min / binHz));
                const endBin = Math.min(spec.freqBytes.length - 1, Math.ceil(b.max / binHz));
                let sum = 0;
                for (let k = startBin; k <= endBin; k++) sum += spec.freqBytes[k];
                const avg = endBin >= startBin ? sum / ((endBin - startBin + 1) * 255) : 0;
                const barH = avg * (h - 48);
                const x = 40 + idx * colW + 10;
                const bw = colW - 20;
                ctx.fillStyle = `${b.color}33`;
                ctx.fillRect(x, 16, bw, h - 48);
                ctx.fillStyle = b.color;
                ctx.fillRect(x, h - 32 - barH, bw, barH);

                ctx.fillStyle = '#E2E8F0';
                ctx.font = 'bold 11px "JetBrains Mono", monospace';
                ctx.textAlign = 'center';
                ctx.fillText(b.label, x + bw / 2, h - 14);
              });
            }
          }

          // Crosshair Overlay
          const ch = crosshairRef.current;
          if (ch) {
            ctx.strokeStyle = 'rgba(226, 232, 240, 0.35)';
            ctx.setLineDash([4, 4]);
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(ch.x, 0);
            ctx.lineTo(ch.x, h);
            ctx.moveTo(0, ch.y);
            ctx.lineTo(w, ch.y);
            ctx.stroke();
            ctx.setLineDash([]);

            const label = `${ch.hz >= 1000 ? `${(ch.hz / 1000).toFixed(2)} kHz` : `${Math.round(ch.hz)} Hz`} | ${ch.db.toFixed(1)} dB`;
            ctx.fillStyle = '#0F172A';
            ctx.fillRect(Math.min(w - 150, ch.x + 8), Math.max(8, ch.y - 24), 142, 18);
            ctx.fillStyle = '#38BDF8';
            ctx.font = '10px "JetBrains Mono", monospace';
            ctx.textAlign = 'left';
            ctx.fillText(label, Math.min(w - 144, ch.x + 12), Math.max(20, ch.y - 11));
          }
        }
      }
      rafId = requestAnimationFrame(renderFrame);
    };

    rafId = requestAnimationFrame(renderFrame);
    return () => cancelAnimationFrame(rafId);
  }, [mode, windowMode]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const y = ((e.clientY - rect.top) / rect.height) * canvas.height;
    const hz = 25 * Math.pow(20000 / 25, x / canvas.width);
    const db = 0 - (y / canvas.height) * 96;
    setCrosshair({ x, y, hz, db });
  };

  const runAnalysis = async (kind: 'tech' | 'musical' | 'quality') => {
    if (!selectedTrack?.id) return;
    setBusyAction(kind);
    setStatusMsg(null);
    try {
      if (kind === 'tech') {
        await apiClient.analyzeTechnical(selectedTrack.id, true);
        setStatusMsg('Análise técnica FFmpeg/ffprobe concluída e salva no SQLite.');
      } else if (kind === 'musical') {
        await apiClient.analyzeMusical(selectedTrack.id, true);
        setStatusMsg('Análise musical Librosa concluída e salva no SQLite.');
      } else {
        setLoadingQuality(true);
        const rep = await apiClient.analyzeTrackQuality(selectedTrack.id, true);
        setQualityReport(rep);
        setStatusMsg('Audio Quality Intelligence v2.1 concluída (Proveniência + Fake Upscale + Car Score).');
      }
      onRefreshTracks();
    } catch (err) {
      setStatusMsg(`Erro: ${(err as Error).message}`);
    } finally {
      setBusyAction(null);
      setLoadingQuality(false);
    }
  };

  const dbL = meters.rmsL > 0.0001 ? Math.max(-60, 20 * Math.log10(meters.rmsL)) : -60;
  const dbR = meters.rmsR > 0.0001 ? Math.max(-60, 20 * Math.log10(meters.rmsR)) : -60;

  return (
    <div className="flex flex-col gap-3">
      {/* Top Toolbar */}
      <div className="studio-panel p-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Activity className="w-5 h-5 text-cyan-400" />
          <div>
            <h1 className="text-sm font-bold text-white uppercase tracking-wide">
              Spectrum & Audio Inspector (SIR Audio Tools Style)
            </h1>
            <p className="text-[11px] text-slate-400">
              FFT Master 8192-pt ao vivo (Web Audio API) + Telemetria estática real FFmpeg/Librosa
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {(['fft', '6band', 'waterfall'] as SpectrumMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`px-2.5 py-1 rounded text-xs font-mono-tech border ${
                mode === m
                  ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                  : 'bg-[#0B0D12] border-[#1E2634] text-slate-400 hover:text-white'
              }`}
            >
              {m === 'fft' ? 'FFT Analyzer' : m === '6band' ? '6-Band Studio' : 'Waterfall'}
            </button>
          ))}

          <select
            value={windowMode}
            onChange={(e) => setWindowMode(e.target.value as WindowMode)}
            className="px-2 py-1 rounded text-xs font-mono-tech bg-[#0B0D12] border border-[#1E2634] text-slate-300"
          >
            <option value="blackman">Janela Blackman</option>
            <option value="hann">Janela Hann</option>
          </select>

          <button
            onClick={resetPeakHold}
            className="px-2.5 py-1 rounded text-xs font-mono-tech bg-[#0B0D12] border border-[#1E2634] text-rose-400 hover:border-rose-400 inline-flex items-center gap-1"
          >
            <RotateCcw className="w-3 h-3" /> Reset Peak
          </button>
        </div>
      </div>

      {/* Main Analyzer + Side Technical Panel */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3">
        {/* FFT Canvas + Vertical L/R + Correlation */}
        <div className="xl:col-span-8 studio-panel p-3 flex flex-col gap-3">
          <div className="flex gap-3 items-stretch">
            <div className="flex-1 min-w-0">
              <canvas
                ref={canvasRef}
                width={900}
                height={380}
                onMouseMove={handleMouseMove}
                onMouseLeave={() => setCrosshair(null)}
                className="w-full h-[380px] rounded border border-[#1A202C] cursor-crosshair bg-[#07090D]"
              />
            </div>

            {/* Vertical L/R dB Meters */}
            <div className="w-16 bg-[#0B0D12] border border-[#1A202C] rounded p-2 flex flex-col justify-between items-center">
              <span className="text-[10px] font-mono-tech text-slate-400">MASTER</span>
              <div className="flex gap-2 h-[280px] items-end w-full justify-center">
                {[
                  { lbl: 'L', db: dbL },
                  { lbl: 'R', db: dbR },
                ].map((ch) => {
                  const pct = Math.max(0, Math.min(100, ((ch.db + 60) / 60) * 100));
                  return (
                    <div key={ch.lbl} className="flex flex-col items-center h-full justify-end gap-1">
                      <div className="w-3.5 flex-1 bg-[#12161F] rounded overflow-hidden flex items-end border border-[#1E2634]">
                        <div
                          className="w-full bg-gradient-to-t from-emerald-500 via-amber-400 to-rose-500 transition-all duration-75"
                          style={{ height: `${pct}%` }}
                        />
                      </div>
                      <span className="text-[10px] font-mono-tech text-slate-400">{ch.lbl}</span>
                    </div>
                  );
                })}
              </div>
              <span className="text-[9px] font-mono-tech text-cyan-400">{dbL.toFixed(0)} dB</span>
            </div>
          </div>

          {/* Phase Correlation & Stereo Width Bar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <div className="bg-[#0B0D12] border border-[#1A202C] rounded px-3 py-2 flex items-center justify-between gap-3">
              <span className="text-[11px] font-mono-tech text-slate-400 shrink-0">
                FASE (-1 ↔ +1)
              </span>
              <div className="flex-1 h-2 bg-[#161B26] rounded relative overflow-hidden">
                <div className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-slate-500" />
                <div
                  className={`absolute top-0 bottom-0 w-2 rounded ${
                    meters.correlation >= 0.15 ? 'bg-emerald-400' : 'bg-rose-500'
                  }`}
                  style={{ left: `calc(${((meters.correlation + 1) / 2) * 100}% - 4px)` }}
                />
              </div>
              <span className={`text-xs font-mono-tech w-12 text-right ${meters.correlation < 0.15 ? 'text-rose-400' : 'text-white'}`}>
                {meters.correlation.toFixed(2)}
              </span>
            </div>

            <div className="bg-[#0B0D12] border border-[#1A202C] rounded px-3 py-2 flex items-center justify-between gap-3">
              <span className="text-[11px] font-mono-tech text-slate-400 shrink-0">
                STEREO WIDTH (EST.)
              </span>
              <div className="flex-1 h-2 bg-[#161B26] rounded overflow-hidden">
                <div
                  className="h-full bg-cyan-400 transition-all duration-75"
                  style={{ width: `${Math.round(meters.stereoWidth * 100)}%` }}
                />
              </div>
              <span className="text-xs font-mono-tech text-cyan-300 w-12 text-right">
                {Math.round(meters.stereoWidth * 100)}%
              </span>
            </div>
          </div>
          {meters.correlation < 0.15 && (
            <div className="text-[11px] text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded px-2.5 py-1">
              Alerta de Compatibilidade Mono: correlação de fase baixa ({meters.correlation.toFixed(2)}); risco de cancelamento em sistemas mono.
            </div>
          )}
        </div>

        {/* Right Side: FFmpeg & Librosa Technical Telemetry */}
        <div className="xl:col-span-4 studio-panel p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-white uppercase tracking-wide inline-flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-emerald-400" />
              Telemetria FFmpeg & Librosa
            </span>
          </div>

          <select
            value={selectedTrack?.id || ''}
            onChange={(e) => setSelectedTrackId(Number(e.target.value))}
            className="w-full px-2.5 py-1.5 text-xs bg-[#0B0D12] border border-[#1E2634] rounded text-white"
          >
            {tracks.map((t) => (
              <option key={t.id} value={t.id}>
                {t.title} — {t.artist}
              </option>
            ))}
          </select>

          {selectedTrack && (
            <>
              <div className="flex gap-2">
                <button
                  onClick={() => runAnalysis('tech')}
                  disabled={busyAction !== null || !selectedTrack.local_path}
                  className="flex-1 py-1.5 px-2 rounded text-[11px] font-mono-tech font-semibold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25 disabled:opacity-40 inline-flex items-center justify-center gap-1"
                >
                  <Gauge className="w-3.5 h-3.5" />
                  {busyAction === 'tech' ? 'Analisando...' : 'Analisar FFmpeg'}
                </button>
                <button
                  onClick={() => runAnalysis('musical')}
                  disabled={busyAction !== null || !selectedTrack.local_path}
                  className="flex-1 py-1.5 px-2 rounded text-[11px] font-mono-tech font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30 hover:bg-purple-500/25 disabled:opacity-40 inline-flex items-center justify-center gap-1"
                >
                  <Waves className="w-3.5 h-3.5" />
                  {busyAction === 'musical' ? 'Analisando...' : 'Librosa'}
                </button>
                <button
                  onClick={() => runAnalysis('quality')}
                  disabled={busyAction !== null}
                  className="flex-1 py-1.5 px-2 rounded text-[11px] font-mono-tech font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 disabled:opacity-40 inline-flex items-center justify-center gap-1"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  {busyAction === 'quality' ? 'Analisando...' : 'Qualidade 2.1'}
                </button>
              </div>

              {statusMsg && (
                <div className="text-[11px] bg-[#0B0D12] border border-cyan-500/30 text-cyan-300 rounded px-2.5 py-1.5">
                  {statusMsg}
                </div>
              )}

              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 space-y-1.5 text-xs">
                <div className="text-[10px] font-mono-tech text-cyan-400 uppercase mb-1">
                  Medição Real • FFmpeg EBU R128 / ffprobe
                </div>
                {[
                  ['Codec / Taxa', `${selectedTrack.codec?.toUpperCase() || '—'} • ${selectedTrack.bitrate_kbps || '—'} kbps`],
                  ['Sample / Depth', `${selectedTrack.sample_rate_hz || '—'} Hz • ${selectedTrack.bit_depth || '—'} bit`],
                  ['LUFS Integrado', selectedTrack.integrated_lufs != null ? `${selectedTrack.integrated_lufs.toFixed(2)} LUFS` : 'Pendente'],
                  ['Momentâneo / Short', `${selectedTrack.momentary_lufs?.toFixed(1) ?? '—'} / ${selectedTrack.short_term_lufs?.toFixed(1) ?? '—'} LUFS`],
                  ['Loudness Range (LRA)', selectedTrack.loudness_range_lu != null ? `${selectedTrack.loudness_range_lu.toFixed(2)} LU` : '—'],
                  ['True Peak', selectedTrack.true_peak_dbfs != null ? `${selectedTrack.true_peak_dbfs.toFixed(2)} dBFS` : '—'],
                  ['Dynamic Range / Crest', `${selectedTrack.dynamic_range_db?.toFixed(1) ?? '—'} dB / ${selectedTrack.crest_factor_db?.toFixed(1) ?? '—'} dB`],
                  ['ReplayGain', selectedTrack.replay_gain != null ? `${selectedTrack.replay_gain > 0 ? '+' : ''}${selectedTrack.replay_gain.toFixed(2)} dB` : '—'],
                  ['Clipping Count', selectedTrack.clipping_count != null ? `${selectedTrack.clipping_count} amostras` : '—'],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-[#151B26] py-0.5">
                    <span className="text-slate-400">{k}</span>
                    <span className="font-mono-tech text-slate-100">{v}</span>
                  </div>
                ))}
              </div>

              <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 space-y-1.5 text-xs">
                <div className="text-[10px] font-mono-tech text-purple-400 uppercase mb-1">
                  Estimativa Algorítmica • Librosa / Essentia.js
                </div>
                {[
                  ['BPM / Estabilidade', `${selectedTrack.bpm?.toFixed(1) ?? '—'} BPM (${selectedTrack.bpm_stability != null ? `${Math.round(selectedTrack.bpm_stability * 100)}%` : '—'})`],
                  ['Tonalidade / Camelot', `${selectedTrack.key || '—'} / ${selectedTrack.camelot_code || '—'}`],
                  ['Energia / Danceability', `${selectedTrack.energy != null ? `${Math.round(selectedTrack.energy * 100)}%` : '—'} / ${selectedTrack.danceability != null ? `${Math.round(selectedTrack.danceability * 100)}%` : '—'}`],
                  ['Confiança', selectedTrack.musical_analysis_confidence != null ? `${Math.round(selectedTrack.musical_analysis_confidence * 100)}%` : '—'],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between border-b border-[#151B26] py-0.5">
                    <span className="text-slate-400">{k}</span>
                    <span className="font-mono-tech text-slate-100">{v}</span>
                  </div>
                ))}
              </div>

              <AudioQualityPanel
                report={qualityReport}
                loading={loadingQuality}
                onRunAnalyze={() => runAnalysis('quality')}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
};
