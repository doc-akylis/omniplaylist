import React from 'react';
import { GitCompare, X } from 'lucide-react';
import type { AbComparisonResponse } from '../types/music';

interface AbComparisonModalProps {
  data: AbComparisonResponse | null;
  onClose: () => void;
}

export const AbComparisonModal: React.FC<AbComparisonModalProps> = ({ data, onClose }) => {
  if (!data) return null;

  const fields = [
    ['Codec', 'codec'],
    ['Bitrate (kbps)', 'bitrate_kbps'],
    ['Sample Rate (Hz)', 'sample_rate_hz'],
    ['Bit Depth', 'bit_depth'],
    ['LUFS Integrado', 'integrated_lufs'],
    ['True Peak (dBFS)', 'true_peak_dbfs'],
    ['Dynamic Range (dB)', 'dynamic_range_db'],
    ['Corte Espectral (Hz)', 'spectral_cutoff_hz'],
    ['Clipping', 'clipping_count'],
    ['Proveniência', 'source_classification'],
    ['Upscale Status', 'upscale_status'],
    ['Car Audio Score', 'car_audio_score'],
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
      <div className="studio-panel-elevated w-full max-w-3xl max-h-[85vh] flex flex-col">
        <div className="p-3 border-b border-[#242C3D] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitCompare className="w-4 h-4 text-cyan-400" />
            <span className="text-sm font-bold text-white">Comparação Técnica A/B de Versões</span>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-[#242C3D] text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-4 overflow-y-auto space-y-3 text-xs">
          <div className="bg-cyan-500/10 border border-cyan-500/30 rounded p-2.5 text-cyan-200">
            {data.summary}
          </div>

          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-[#242C3D] text-[10px] font-mono-tech text-slate-400 uppercase">
                <th className="py-2 px-2">Métrica</th>
                <th className="py-2 px-2 text-cyan-300">
                  Versão A: {String(data.version_a.title)}
                  {data.recommended_track_id === data.version_a.track_id ? ' ★' : ''}
                </th>
                <th className="py-2 px-2 text-amber-300">
                  Versão B: {String(data.version_b.title)}
                  {data.recommended_track_id === data.version_b.track_id ? ' ★' : ''}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1A202C] font-mono-tech">
              {fields.map(([label, key]) => (
                <tr key={key}>
                  <td className="py-1.5 px-2 text-slate-400 font-sans">{label}</td>
                  <td className="py-1.5 px-2 text-slate-200">{String(data.version_a[key] ?? '—')}</td>
                  <td className="py-1.5 px-2 text-slate-200">{String(data.version_b[key] ?? '—')}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.differences.length > 0 && (
            <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-3 space-y-1">
              <div className="text-[10px] font-mono-tech text-slate-400 uppercase">Diferenças Detectadas</div>
              {data.differences.map((d, idx) => (
                <div key={idx} className="text-[11px] text-slate-300">
                  • {d}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
