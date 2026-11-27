import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Loader2,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { QualityDashboardData } from '../types/music';

interface QualityDashboardViewProps {
  onNavigateToFilteredLibrary: (filterKey: string) => void;
}

export const QualityDashboardView: React.FC<QualityDashboardViewProps> = ({
  onNavigateToFilteredLibrary,
}) => {
  const [data, setData] = useState<QualityDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [batchMsg, setBatchMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadDashboard = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await apiClient.getQualityDashboard();
      setData(res);
    } catch (err) {
      setErrorMsg((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  const runBatchQuality = async () => {
    setBatchMsg('Iniciando análise de qualidade em lote...');
    try {
      const res = await apiClient.analyzeLibraryQuality(false);
      setBatchMsg(res.message);
    } catch (err) {
      setBatchMsg(`Erro: ${(err as Error).message}`);
    }
  };

  const renderDistBars = (title: string, dist: Record<string, number>, barColor: string) => {
    const entries = Object.entries(dist);
    const maxVal = Math.max(1, ...entries.map(([, v]) => v));
    return (
      <div className="studio-panel p-3 flex flex-col gap-2">
        <div className="text-xs font-bold text-white uppercase tracking-wide inline-flex items-center gap-1.5">
          <BarChart3 className="w-3.5 h-3.5 text-cyan-400" /> {title}
        </div>
        {entries.length === 0 ? (
          <div className="text-xs text-slate-500">Sem dados analisados.</div>
        ) : (
          <div className="space-y-1.5">
            {entries.map(([k, v]) => (
              <div key={k} className="space-y-0.5 text-xs">
                <div className="flex justify-between font-mono-tech text-[11px]">
                  <span className="text-slate-300">{k}</span>
                  <span className="text-white">{v}</span>
                </div>
                <div className="h-2 bg-[#0B0D12] rounded overflow-hidden border border-[#1A202C]">
                  <div
                    className="h-full rounded"
                    style={{ width: `${Math.round((v / maxVal) * 100)}%`, backgroundColor: barColor }}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="studio-panel p-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
          <div>
            <h1 className="text-sm font-bold text-white uppercase tracking-wide">
              Quality Dashboard — Saúde Técnica & Car Audio Intelligence
            </h1>
            <p className="text-[11px] text-slate-400">
              Visão agregada real do acervo. Clique em qualquer indicador para abrir as faixas filtradas na Biblioteca.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={runBatchQuality}
            className="px-3 py-1.5 rounded text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/25 inline-flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" /> Analisar Acervo v2.1
          </button>
          <button
            onClick={loadDashboard}
            className="px-3 py-1.5 rounded text-xs font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-slate-300 hover:text-white inline-flex items-center gap-1.5"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Atualizar
          </button>
        </div>
      </div>

      {batchMsg && (
        <div className="studio-panel px-3 py-2 text-xs font-mono-tech text-cyan-300 border-l-4 border-l-cyan-400">
          {batchMsg}
        </div>
      )}

      {errorMsg && (
        <div className="studio-panel px-3 py-2 text-xs text-rose-300 border-l-4 border-l-rose-500">
          {errorMsg}
        </div>
      )}

      {loading || !data ? (
        <div className="studio-panel p-8 flex items-center justify-center gap-2 text-xs text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin text-cyan-400" /> Carregando métricas reais do acervo...
        </div>
      ) : (
        <>
          {/* Clickable Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
            {[
              { label: 'Total de Músicas', val: data.total_tracks, filter: 'ALL', color: 'text-white' },
              { label: 'Arquivos Completos', val: data.complete_files, filter: 'COMPLETE', color: 'text-emerald-400' },
              { label: 'Previews (30s)', val: data.previews, filter: 'PREVIEW', color: 'text-amber-400' },
              { label: 'Lossless Source', val: data.lossless_source, filter: 'LOSSLESS_SOURCE', color: 'text-cyan-400' },
              { label: 'Lossy Source', val: data.lossy_source, filter: 'LOSSY_SOURCE', color: 'text-sky-400' },
              { label: 'Origem Desconhecida', val: data.unknown_source, filter: 'UNKNOWN_SOURCE', color: 'text-slate-400' },
              { label: 'Fake Upscale Suspeito', val: data.suspected_fake_upscale, filter: 'FAKE_UPSCALE', color: 'text-rose-400' },
              { label: 'Corrompidos', val: data.corrupted, filter: 'CORRUPTED', color: 'text-rose-500' },
              { label: 'Com Clipping', val: data.clipping, filter: 'CLIPPING', color: 'text-amber-300' },
              { label: 'True Peak Crítico', val: data.critical_true_peak, filter: 'CRITICAL_PEAK', color: 'text-orange-400' },
              { label: 'Sem Análise', val: data.unanalyzed, filter: 'UNANALYZED', color: 'text-slate-300' },
              { label: 'Upgrades Disponíveis', val: data.upgrades_available, filter: 'UPGRADE_AVAILABLE', color: 'text-purple-400' },
            ].map((card) => (
              <button
                key={card.label}
                onClick={() => onNavigateToFilteredLibrary(card.filter)}
                className="studio-panel p-3 text-left hover:border-cyan-500/50 transition-colors flex flex-col justify-between gap-1"
              >
                <span className="text-[10px] font-mono-tech text-slate-400 uppercase">{card.label}</span>
                <span className={`text-xl font-mono-tech font-bold ${card.color}`}>{card.val}</span>
              </button>
            ))}
          </div>

          {/* Highlight Average Score */}
          <div className="studio-panel p-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              {data.suspected_fake_upscale > 0 || data.corrupted > 0 ? (
                <ShieldAlert className="w-5 h-5 text-amber-400" />
              ) : (
                <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              )}
              <div className="text-xs">
                <span className="text-slate-400">Score Médio Car Audio Intelligence: </span>
                <span className="font-mono-tech font-bold text-white text-sm">
                  {data.avg_car_audio_score !== null ? `${data.avg_car_audio_score} / 100` : 'Aguardando análise'}
                </span>
              </div>
            </div>
            <div className="text-[11px] text-slate-400 inline-flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5 text-slate-500" />
              Ausentes no disco: <strong className="font-mono-tech text-white">{data.missing_files}</strong>
            </div>
          </div>

          {/* Distributions */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            {renderDistBars('Distribuição de Codecs', data.codec_distribution, '#38BDF8')}
            {renderDistBars('Distribuição de Bitrate', data.bitrate_distribution, '#10B981')}
            {renderDistBars('Sample Rates', data.sample_rate_distribution, '#A855F7')}
            {renderDistBars('Status Car Audio', data.car_audio_status_distribution, '#F59E0B')}
          </div>
        </>
      )}
    </div>
  );
};
