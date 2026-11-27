import React, { useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  Download,
  FileText,
  Globe,
  Loader2,
  Pause,
  Play,
  Search,
  Sparkles,
  X,
} from 'lucide-react';
import { apiClient } from '../api/client';
import type { DeckId, OmniSearchResult, UnifiedTrack } from '../types/music';

interface OmniSearchViewProps {
  onLoadPreviewToDeck: (deck: DeckId, item: OmniSearchResult) => void;
  onTrackImported: () => void;
}

type FilterTab = 'all' | 'local' | 'itunes_deezer' | 'musicbrainz' | 'lrclib';

const SOURCE_STYLE: Record<string, string> = {
  local: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  itunes: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  deezer: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  musicbrainz: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  cover_art_archive: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
  lrclib: 'bg-pink-500/20 text-pink-300 border-pink-500/40',
};

export const OmniSearchView: React.FC<OmniSearchViewProps> = ({
  onLoadPreviewToDeck,
  onTrackImported,
}) => {
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<FilterTab>('all');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<OmniSearchResult[]>([]);
  const [importingId, setImportingId] = useState<string | null>(null);
  const [importedIds, setImportedIds] = useState<Set<string>>(new Set());
  const [playingPreviewId, setPlayingPreviewId] = useState<string | null>(null);
  const [lyricsModal, setLyricsModal] = useState<OmniSearchResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const runSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const mode = tab === 'local' ? 'local' : 'all';
      const data = await apiClient.omniSearch(q, mode);
      setResults(data.results || []);
    } catch (err) {
      setErrorMsg((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const filteredResults = useMemo(() => {
    if (tab === 'all') return results;
    if (tab === 'local') return results.filter((r) => r.in_library || r.sources.includes('local'));
    if (tab === 'itunes_deezer') {
      return results.filter((r) => r.sources.includes('itunes') || r.sources.includes('deezer'));
    }
    if (tab === 'musicbrainz') {
      return results.filter(
        (r) => r.sources.includes('musicbrainz') || r.sources.includes('cover_art_archive'),
      );
    }
    if (tab === 'lrclib') {
      return results.filter((r) => r.sources.includes('lrclib') || r.has_synced_lyrics);
    }
    return results;
  }, [results, tab]);

  const toggleMiniPreview = (item: OmniSearchResult) => {
    if (!item.preview_url) return;
    if (!audioRef.current) {
      audioRef.current = new Audio();
    }
    const audio = audioRef.current;
    if (playingPreviewId === item.id) {
      audio.pause();
      setPlayingPreviewId(null);
    } else {
      audio.src = item.preview_url;
      void audio.play();
      setPlayingPreviewId(item.id);
      audio.onended = () => setPlayingPreviewId(null);
    }
  };

  const handleImport = async (item: OmniSearchResult) => {
    setImportingId(item.id);
    try {
      const res = await apiClient.importOnlineTrack(item, true);
      setImportedIds((prev) => new Set(prev).add(item.id));
      const importedTrack: UnifiedTrack = res.track;
      setResults((prev) =>
        prev.map((r) =>
          r.id === item.id
            ? {
                ...r,
                in_library: true,
                local_track_id: importedTrack.id,
                isrc: importedTrack.isrc || r.isrc,
                hd_cover_url: importedTrack.hd_cover_url || r.hd_cover_url,
                has_synced_lyrics: Boolean(importedTrack.lyrics_synced || r.has_synced_lyrics),
                lyrics_synced: importedTrack.lyrics_synced || r.lyrics_synced,
                lyrics_plain: importedTrack.lyrics_plain || r.lyrics_plain,
              }
            : r,
        ),
      );
      onTrackImported();
    } catch (err) {
      setErrorMsg(`Falha ao importar: ${(err as Error).message}`);
    } finally {
      setImportingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {/* Search Bar & Tabs */}
      <div className="studio-panel p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <Globe className="w-5 h-5 text-cyan-400" />
            <div>
              <h1 className="text-sm font-bold text-white uppercase tracking-wide">
                Busca Omnichannel Ao Vivo (SQLite + iTunes + Deezer + MusicBrainz + CAA + LRCLIB)
              </h1>
              <p className="text-[11px] text-slate-400">
                Consulta paralela com deduplicação por ISRC, prévia de áudio 30s nos decks, letras .LRC e importação enriquecida
              </p>
            </div>
          </div>
        </div>

        <form onSubmit={runSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Buscar artista, música, álbum ou ISRC (ex: Daft Punk One More Time)..."
              className="w-full pl-9 pr-4 py-2 text-sm bg-[#0B0D12] border border-[#242C3D] rounded text-white focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 rounded font-semibold text-xs bg-cyan-500 text-[#0B0D12] hover:bg-cyan-400 disabled:opacity-50 inline-flex items-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            Buscar Agora
          </button>
        </form>

        <div className="flex flex-wrap gap-1.5">
          {[
            { id: 'all', label: 'Todas as Fontes' },
            { id: 'local', label: 'Biblioteca Local' },
            { id: 'itunes_deezer', label: 'iTunes & Deezer' },
            { id: 'musicbrainz', label: 'MusicBrainz & ISRC' },
            { id: 'lrclib', label: 'Letras LRCLIB' },
          ].map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id as FilterTab)}
              className={`px-3 py-1 rounded text-xs font-medium border ${
                tab === t.id
                  ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300'
                  : 'bg-[#0B0D12] border-[#1E2634] text-slate-400 hover:text-white'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {errorMsg && (
          <div className="text-xs bg-rose-500/10 border border-rose-500/40 text-rose-300 rounded px-3 py-2">
            {errorMsg}
          </div>
        )}
      </div>

      {/* Results Grid */}
      {filteredResults.length === 0 ? (
        <div className="studio-panel p-8 text-center text-xs text-slate-500">
          {loading
            ? 'Consultando provedores simultaneamente...'
            : 'Digite um termo de busca acima para pesquisar em todas as fontes musicais.'}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {filteredResults.map((item) => {
            const isImported = item.in_library || importedIds.has(item.id);
            const cover =
              item.hd_cover_url ||
              item.cover_url ||
              'https://placehold.co/120x120/12161F/38BDF8?text=%E2%99%AB';
            return (
              <div key={item.id} className="studio-panel p-3 flex flex-col justify-between gap-3">
                <div className="flex gap-3">
                  <img
                    src={cover}
                    alt={item.title}
                    className="w-20 h-20 rounded object-cover border border-[#242C3D] shrink-0 bg-[#0B0D12]"
                  />
                  <div className="min-w-0 flex-1 flex flex-col justify-between">
                    <div>
                      <div className="text-sm font-bold text-white truncate">{item.title}</div>
                      <div className="text-xs text-slate-300 truncate">{item.artist}</div>
                      <div className="text-[11px] text-slate-500 truncate">
                        {item.album || 'Single'} {item.release_year ? `• ${item.release_year}` : ''}
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {item.sources.map((src) => (
                        <span
                          key={src}
                          className={`px-1.5 py-0.5 rounded text-[9px] font-mono-tech uppercase border ${
                            SOURCE_STYLE[src] || 'bg-slate-700/30 text-slate-300 border-slate-600'
                          }`}
                        >
                          {src}
                        </span>
                      ))}
                      {item.isrc && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-mono-tech bg-[#0B0D12] text-slate-400 border border-[#1E2634]">
                          {item.isrc}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Action Footer */}
                <div className="flex flex-wrap items-center justify-between gap-1.5 pt-2 border-t border-[#1A202C]">
                  <div className="flex items-center gap-1">
                    {item.preview_url && (
                      <>
                        <button
                          onClick={() => toggleMiniPreview(item)}
                          className="px-2 py-1 rounded text-[11px] font-mono-tech bg-[#0B0D12] border border-[#242C3D] text-cyan-300 hover:border-cyan-400 inline-flex items-center gap-1"
                        >
                          {playingPreviewId === item.id ? (
                            <Pause className="w-3 h-3" />
                          ) : (
                            <Play className="w-3 h-3" />
                          )}
                          30s
                        </button>
                        <button
                          onClick={() => onLoadPreviewToDeck('A', item)}
                          className="px-2 py-1 rounded text-[10px] font-mono-tech font-bold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 hover:bg-cyan-500/25"
                        >
                          Deck A
                        </button>
                        <button
                          onClick={() => onLoadPreviewToDeck('B', item)}
                          className="px-2 py-1 rounded text-[10px] font-mono-tech font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25"
                        >
                          Deck B
                        </button>
                      </>
                    )}

                    {(item.lyrics_synced || item.lyrics_plain) && (
                      <button
                        onClick={() => setLyricsModal(item)}
                        className="px-2 py-1 rounded text-[11px] font-mono-tech bg-pink-500/15 text-pink-300 border border-pink-500/30 hover:bg-pink-500/25 inline-flex items-center gap-1"
                      >
                        <FileText className="w-3 h-3" />
                        {item.has_synced_lyrics ? '.LRC' : 'Letra'}
                      </button>
                    )}
                  </div>

                  {isImported ? (
                    <span className="px-2.5 py-1 rounded text-[11px] font-mono-tech bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 inline-flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Na Biblioteca
                    </span>
                  ) : (
                    <button
                      onClick={() => handleImport(item)}
                      disabled={importingId === item.id}
                      className="px-2.5 py-1 rounded text-[11px] font-semibold bg-emerald-500 text-[#0B0D12] hover:bg-emerald-400 disabled:opacity-50 inline-flex items-center gap-1"
                    >
                      {importingId === item.id ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Download className="w-3.5 h-3.5" />
                      )}
                      Importar & Enriquecer
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Synced Lyrics Viewer Modal */}
      {lyricsModal && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4">
          <div className="studio-panel-elevated w-full max-w-xl max-h-[80vh] flex flex-col">
            <div className="p-3 border-b border-[#242C3D] flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-pink-400" />
                <span className="text-sm font-bold text-white">
                  {lyricsModal.title} — {lyricsModal.artist}
                </span>
              </div>
              <button
                onClick={() => setLyricsModal(null)}
                className="p-1 rounded hover:bg-[#242C3D] text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <pre className="p-4 text-xs font-mono-tech text-slate-300 overflow-y-auto whitespace-pre-wrap leading-relaxed">
              {lyricsModal.lyrics_synced || lyricsModal.lyrics_plain}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
