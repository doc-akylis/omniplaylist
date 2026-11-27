import React from 'react';
import {
  Activity,
  ChevronLeft,
  ChevronRight,
  Database,
  Disc3,
  DownloadCloud,
  Globe,
  ListMusic,
  PlugZap,
  Radio,
  ShieldCheck,
} from 'lucide-react';
import type { AppView, DeckState } from '../types/music';

interface SidebarProps {
  activeView: AppView;
  onNavigate: (view: AppView) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  wsConnected: boolean;
  deckA: DeckState;
  deckB: DeckState;
}

const NAV_ITEMS: Array<{ id: AppView; label: string; sub: string; icon: React.FC<{ className?: string }> }> = [
  { id: 'dj-mode', label: 'DJ Mode Pro', sub: 'Decks A/B & Transition', icon: Disc3 },
  { id: 'spectrum', label: 'Spectrum & DSP', sub: 'FFT 8192 & Qualidade', icon: Activity },
  { id: 'quality-dashboard', label: 'Quality Dashboard', sub: 'Acervo & Car Audio', icon: ShieldCheck },
  { id: 'playlists', label: 'Playlists & Flow', sub: 'Manager & Sequencer', icon: ListMusic },
  { id: 'downloads', label: 'Download Studio', sub: 'Fila, Upgrade & Perfis', icon: DownloadCloud },
  { id: 'search', label: 'Busca Omni', sub: '8 APIs Ao Vivo', icon: Globe },
  { id: 'library', label: 'Biblioteca Beets', sub: 'Tags, Lotes & A/B', icon: Database },
  { id: 'providers', label: 'Status & APIs', sub: 'Provedores & Chaves', icon: PlugZap },
];

export const Sidebar: React.FC<SidebarProps> = ({
  activeView,
  onNavigate,
  collapsed,
  onToggleCollapse,
  wsConnected,
  deckA,
  deckB,
}) => {
  return (
    <aside
      className={`h-screen sticky top-0 flex flex-col justify-between bg-[#0E1118] border-r border-[#1A202C] transition-all duration-200 shrink-0 ${
        collapsed ? 'w-[68px]' : 'w-[232px]'
      }`}
    >
      <div className="overflow-y-auto">
        <div className="h-14 px-3 flex items-center justify-between border-b border-[#1A202C]">
          {!collapsed && (
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-7 h-7 rounded bg-cyan-500/15 border border-cyan-500/40 flex items-center justify-center shrink-0">
                <Radio className="w-4 h-4 text-cyan-400" />
              </div>
              <div className="truncate">
                <div className="text-xs font-bold tracking-wide text-white uppercase">OmniPlaylist</div>
                <div className="text-[10px] font-mono-tech text-cyan-400">STUDIO 2.1</div>
              </div>
            </div>
          )}
          <button
            onClick={onToggleCollapse}
            className="p-1.5 rounded hover:bg-[#1A202C] text-slate-400 hover:text-white transition-colors mx-auto"
            title={collapsed ? 'Expandir barra lateral' : 'Recolher barra lateral'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        <nav className="p-2 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = activeView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`w-full flex items-center gap-3 px-2.5 py-2 rounded-md text-left transition-all border ${
                  active
                    ? 'bg-cyan-500/12 border-cyan-500/40 text-white'
                    : 'bg-transparent border-transparent text-slate-400 hover:bg-[#151A24] hover:text-slate-200'
                }`}
                title={collapsed ? item.label : undefined}
              >
                <Icon className={`w-4 h-4 shrink-0 ${active ? 'text-cyan-400' : 'text-slate-400'}`} />
                {!collapsed && (
                  <div className="min-w-0">
                    <div className="text-xs font-semibold truncate">{item.label}</div>
                    <div className="text-[10px] text-slate-500 truncate">{item.sub}</div>
                  </div>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      <div className="p-2.5 border-t border-[#1A202C] flex flex-col gap-2">
        {!collapsed && (
          <div className="bg-[#0B0D12] border border-[#1A202C] rounded p-2 text-[10px] font-mono-tech space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-cyan-400 font-bold">DECK A</span>
              <span className={deckA.isPlaying ? 'text-emerald-400' : 'text-slate-500'}>
                {deckA.isPlaying ? '● LIVE' : 'IDLE'}
              </span>
            </div>
            <div className="text-slate-300 truncate">{deckA.track?.title || 'Sem faixa'}</div>
            <div className="flex items-center justify-between pt-1 border-t border-[#1A202C]">
              <span className="text-amber-400 font-bold">DECK B</span>
              <span className={deckB.isPlaying ? 'text-emerald-400' : 'text-slate-500'}>
                {deckB.isPlaying ? '● LIVE' : 'IDLE'}
              </span>
            </div>
            <div className="text-slate-300 truncate">{deckB.track?.title || 'Sem faixa'}</div>
          </div>
        )}

        <div className="flex items-center justify-center gap-2 py-1 text-[10px] font-mono-tech">
          <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-500'}`} />
          {!collapsed && (
            <span className="text-slate-400">{wsConnected ? 'WS TELEMETRIA OK' : 'WS RECONECTANDO'}</span>
          )}
        </div>
      </div>
    </aside>
  );
};
