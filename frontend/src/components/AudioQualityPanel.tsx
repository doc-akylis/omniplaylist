import React from 'react';
import { AlertTriangle, Car, CheckCircle2, History, Loader2, ShieldAlert, Sparkles } from 'lucide-react';
import type { QualityReport } from '../types/music';

interface AudioQualityPanelProps {
  report: QualityReport | null;
  loading?: boolean;
  onRunAnalyze?: () => void;
}

const STATUS_BADGE: Record<string, string> = {
  EXCELLENT: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  GOOD: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40',
  ACCEPTABLE: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  REVIEW_REQUIRED: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  POOR: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
};

export const AudioQualityPanel: React.FC<AudioQualityPanelProps> = ({
  report,
  loading = false,
  onRunAnalyze,
}) => {
  if (loading) {
    return (
      <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-3 flex items-center gap-2 text-xs text-cyan-300">
        <Loader2 className="w-4 h-4 animate-spin" /> Executando Audio Quality Intelligence...
      </div>
    );
  }

  if (!report) {
    return (
      <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-3 text-xs text-slate-400 flex items-center justify-between">
        <span>Análise de qualidade v2.1 ainda não executada para esta faixa.</span>
        {onRunAnalyze && (
          <button
            onClick={onRunAnalyze}
            className="px-2.5 py-1 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 font-mono-tech text-[11px]"
          >
            Analisar Qualidade
          </button>
        )}
      </div>
    );
  }

  const qi = report.quality_intelligence;
  const penalties = qi.details?.car_audio?.penalties || [];
  const positives = qi.details?.car_audio?.positives || [];
  const evidence = qi.details?.spectral?.evidence || [];
  const bass = qi.bass_profile;

  return (
    <div className="flex flex-col gap-2.5 text-xs">
      {/* Header Score + Car Audio */}
      <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Car className="w-4 h-4 text-cyan-400" />
          <div>
            <div className="text-[10px] font-mono-tech text-slate-400 uppercase">Car Audio Intelligence</div>
            <div className="flex items-center gap-2">
              <span className="text-base font-mono-tech font-bold text-white">
                {qi.car_audio_score !== null && qi.car_audio_score !== undefined ? `${qi.car_audio_score}/100` : '—'}
              </span>
              {qi.car_audio_status && (
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono-tech font-bold border ${
                    STATUS_BADGE[qi.car_audio_status] || 'border-slate-600 text-slate-300'
                  }`}
                >
                  {qi.car_audio_status}
                </span>
              )}
              <span className={`text-[10px] font-mono-tech ${qi.car_audio_ready ? 'text-emerald-400' : 'text-amber-400'}`}>
                {qi.car_audio_ready ? '● CAR READY' : '○ REVISAR'}
              </span>
            </div>
          </div>
        </div>
        {onRunAnalyze && (
          <button
            onClick={onRunAnalyze}
            className="px-2 py-1 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 text-[10px] font-mono-tech inline-flex items-center gap-1"
          >
            <Sparkles className="w-3 h-3" /> Reanalisar
          </button>
        )}
      </div>

      {/* Provenance & Fake Upscale */}
      <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 space-y-1.5">
        <div className="flex justify-between">
          <span className="text-slate-400">Origem Real</span>
          <span className="font-mono-tech font-bold text-white">{qi.source_classification}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Detector Fake Upscale</span>
          <span
            className={`font-mono-tech font-bold ${
              qi.is_fake_upscale
                ? 'text-rose-400'
                : qi.upscale_status === 'VERIFIED_LOSSLESS_SOURCE'
                  ? 'text-emerald-400'
                  : 'text-slate-300'
            }`}
          >
            {qi.upscale_status} ({qi.upscale_confidence != null ? `${Math.round(qi.upscale_confidence * 100)}%` : '—'})
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-slate-400">Corte Espectral (STFT)</span>
          <span className="font-mono-tech text-cyan-300">
            {qi.spectral_cutoff_hz ? `${Math.round(qi.spectral_cutoff_hz)} Hz` : 'Desconhecido'}
          </span>
        </div>
        {report.provenance && (
          <div className="flex justify-between">
            <span className="text-slate-400">Aquisição / Container Original</span>
            <span className="font-mono-tech text-slate-300">
              {report.provenance.acquisition_source} • {report.provenance.original_codec || '?'}
            </span>
          </div>
        )}
      </div>

      {/* 4-Band Bass Profile (Descritivo) */}
      <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 space-y-1.5">
        <div className="text-[10px] font-mono-tech text-slate-400 uppercase">
          Perfil Espectral Descritivo (não penaliza baixo subgrave)
        </div>
        {[
          { lbl: 'Sub-bass (20–60 Hz)', val: bass.sub_bass_20_60, color: '#22C55E' },
          { lbl: 'Mid-bass (60–250 Hz)', val: bass.mid_bass_60_250, color: '#10B981' },
          { lbl: 'Midrange (250–4k Hz)', val: bass.midrange_250_4000, color: '#38BDF8' },
          { lbl: 'Highs (4–20 kHz)', val: bass.high_freq_4000_20000, color: '#A855F7' },
        ].map((b) => {
          const pct = b.val != null ? Math.min(100, Math.round(b.val * 100)) : 0;
          return (
            <div key={b.lbl} className="space-y-0.5">
              <div className="flex justify-between text-[10px] font-mono-tech">
                <span className="text-slate-400">{b.lbl}</span>
                <span className="text-slate-200">{b.val != null ? `${pct}%` : '—'}</span>
              </div>
              <div className="h-1.5 bg-[#161B26] rounded overflow-hidden">
                <div className="h-full rounded" style={{ width: `${pct}%`, backgroundColor: b.color }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Penalties & Positives */}
      {(penalties.length > 0 || positives.length > 0 || evidence.length > 0) && (
        <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 space-y-1">
          {penalties.map((p, idx) => (
            <div key={idx} className="flex items-start gap-1.5 text-[11px] text-amber-300">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>
                <strong>{p.points} pts:</strong> {p.reason}
              </span>
            </div>
          ))}
          {positives.map((pos, idx) => (
            <div key={idx} className="flex items-start gap-1.5 text-[11px] text-emerald-300">
              <CheckCircle2 className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>{pos}</span>
            </div>
          ))}
          {evidence.slice(0, 2).map((ev, idx) => (
            <div key={idx} className="flex items-start gap-1.5 text-[10px] text-slate-400">
              <ShieldAlert className="w-3 h-3 shrink-0 mt-0.5" />
              <span>{ev}</span>
            </div>
          ))}
        </div>
      )}

      {/* Processing History */}
      {report.processing_history.length > 0 && (
        <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2.5 space-y-1">
          <div className="text-[10px] font-mono-tech text-slate-400 uppercase inline-flex items-center gap-1">
            <History className="w-3 h-3" /> Histórico de Processamento ({report.processing_history.length})
          </div>
          {report.processing_history.slice(0, 4).map((h) => (
            <div key={h.id} className="text-[10px] font-mono-tech text-slate-300 flex justify-between border-t border-[#151B26] pt-1">
              <span>{h.operation} ({h.from_codec || '?'} → {h.to_codec || '?'})</span>
              <span className="text-slate-500">{new Date(h.created_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
