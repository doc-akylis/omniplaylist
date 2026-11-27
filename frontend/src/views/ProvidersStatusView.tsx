import React, { useEffect, useState } from 'react';
import { CheckCircle2, KeyRound, PlugZap, RefreshCw, Save, Sparkles } from 'lucide-react';
import { apiClient } from '../api/client';
import type { ProvidersHealthResponse, UnifiedTrack } from '../types/music';

interface ProvidersStatusViewProps {
  tracks: UnifiedTrack[];
}

export const ProvidersStatusView: React.FC<ProvidersStatusViewProps> = ({ tracks }) => {
  const [health, setHealth] = useState<ProvidersHealthResponse | null>(null);
  const [keys, setKeys] = useState({
    LISTENBRAINZ_TOKEN: '',
    LASTFM_API_KEY: '',
    ACOUSTID_API_KEY: '',
  });
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [discovery, setDiscovery] = useState<{
    lastfm_similar: Array<{ title: string; artist: string; match: number }>;
    tags: string[];
  } | null>(null);

  const loadHealth = async () => {
    const res = await apiClient.getProvidersHealth();
    setHealth(res);
  };

  useEffect(() => {
    void loadHealth();
    if (tracks[0]?.id) {
      apiClient
        .getDiscovery(tracks[0].id)
        .then((d) => setDiscovery({ lastfm_similar: d.lastfm_similar, tags: d.tags }))
        .catch(() => setDiscovery(null));
    }
  }, [tracks[0]?.id]);

  const handleSaveKeys = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    try {
      const res = await apiClient.saveProviderSettings(keys);
      setHealth(res.health);
      setSaveMsg('Chaves salvas em .env e provedores recarregados.');
    } catch (err) {
      setSaveMsg(`Erro ao salvar: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="studio-panel p-4 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <PlugZap className="w-5 h-5 text-cyan-400" />
          <div>
            <h1 className="text-sm font-bold text-white uppercase tracking-wide">
              Status & Integrações (8 APIs + Motores DSP)
            </h1>
            <p className="text-[11px] text-slate-400">
              5 provedores abertos funcionam sem chave por padrão; os 3 opcionais degradam graciosamente até serem configurados
            </p>
          </div>
        </div>
        <button
          onClick={loadHealth}
          className="px-3 py-1.5 rounded text-xs font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-slate-300 hover:text-white inline-flex items-center gap-1.5"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Verificar Saúde
        </button>
      </div>

      {/* 8 APIs Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {(health?.providers || []).map((p) => {
          const isActive = p.status === 'active';
          return (
            <div key={p.id} className="studio-panel p-3 flex flex-col justify-between gap-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs font-bold text-white">{p.name}</div>
                  <div className="text-[10px] font-mono-tech text-slate-500">
                    {p.requires_key ? 'Chave Opcional' : 'Sem Chave (Público)'}
                  </div>
                </div>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono-tech font-bold border ${
                    isActive
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-amber-500/15 text-amber-300 border-amber-500/30'
                  }`}
                >
                  {isActive ? 'ATIVO' : 'OPCIONAL'}
                </span>
              </div>
              <div className="text-[11px] text-slate-400">{p.detail}</div>
            </div>
          );
        })}
      </div>

      {/* Local DSP Engines + Optional Key Form */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        <form onSubmit={handleSaveKeys} className="lg:col-span-7 studio-panel p-4 flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-amber-400" />
            <span className="text-xs font-bold text-white uppercase">
              Configurar Chaves Opcionais (.env)
            </span>
          </div>

          <div className="grid grid-cols-1 gap-2.5 text-xs">
            {[
              {
                key: 'LISTENBRAINZ_TOKEN',
                label: 'LISTENBRAINZ_TOKEN',
                placeholder: 'Token de usuário ListenBrainz para gravações semelhantes',
              },
              {
                key: 'LASTFM_API_KEY',
                label: 'LASTFM_API_KEY',
                placeholder: 'Chave de API Last.fm para tags de gênero e faixas similares',
              },
              {
                key: 'ACOUSTID_API_KEY',
                label: 'ACOUSTID_API_KEY',
                placeholder: 'Chave AcoustID para identificação por impressão digital (fpcalc)',
              },
            ].map((item) => (
              <label key={item.key} className="flex flex-col gap-1">
                <span className="text-[10px] font-mono-tech text-slate-400">{item.label}</span>
                <input
                  type="password"
                  value={keys[item.key as keyof typeof keys]}
                  onChange={(e) => setKeys({ ...keys, [item.key]: e.target.value })}
                  placeholder={item.placeholder}
                  className="px-3 py-2 rounded bg-[#0B0D12] border border-[#1E2634] text-white font-mono-tech text-xs focus:outline-none focus:border-cyan-500"
                />
              </label>
            ))}
          </div>

          {saveMsg && (
            <div className="text-xs bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 rounded px-3 py-1.5">
              {saveMsg}
            </div>
          )}

          <button
            type="submit"
            disabled={saving}
            className="self-start px-4 py-2 rounded text-xs font-semibold bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 inline-flex items-center gap-2"
          >
            <Save className="w-4 h-4" /> {saving ? 'Salvando...' : 'Salvar Chaves no .env'}
          </button>
        </form>

        <div className="lg:col-span-5 studio-panel p-4 flex flex-col gap-3">
          <div className="text-xs font-bold text-white uppercase">Motores Locais de Análise DSP</div>
          <div className="space-y-2 text-xs font-mono-tech">
            <div className="flex justify-between p-2 rounded bg-[#0B0D12] border border-[#1A202C]">
              <span className="text-slate-300">FFmpeg + ffprobe</span>
              <span className={health?.engines.ffmpeg ? 'text-emerald-400 inline-flex items-center gap-1' : 'text-rose-400'}>
                <CheckCircle2 className="w-3.5 h-3.5" /> {health?.engines.ffmpeg ? 'PRONTO' : 'AUSENTE'}
              </span>
            </div>
            <div className="flex justify-between p-2 rounded bg-[#0B0D12] border border-[#1A202C]">
              <span className="text-slate-300">Librosa (Python DSP)</span>
              <span className={health?.engines.librosa ? 'text-emerald-400' : 'text-rose-400'}>
                {health?.engines.librosa ? `v${health.engines.librosa}` : 'AUSENTE'}
              </span>
            </div>
            <div className="flex justify-between p-2 rounded bg-[#0B0D12] border border-[#1A202C]">
              <span className="text-slate-300">Web Audio + Essentia.js WASM</span>
              <span className="text-cyan-400">BROWSER DSP</span>
            </div>
          </div>

          {discovery && (discovery.tags.length > 0 || discovery.lastfm_similar.length > 0) && (
            <div className="pt-2 border-t border-[#1A202C]">
              <div className="text-[11px] font-bold text-slate-300 mb-1 inline-flex items-center gap-1">
                <Sparkles className="w-3.5 h-3.5 text-purple-400" /> Descoberta Ativa (Last.fm / ListenBrainz)
              </div>
              <div className="flex flex-wrap gap-1">
                {discovery.tags.slice(0, 6).map((t) => (
                  <span key={t} className="px-1.5 py-0.5 rounded bg-[#0B0D12] border border-[#1E2634] text-[10px] text-slate-400">
                    #{t}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
