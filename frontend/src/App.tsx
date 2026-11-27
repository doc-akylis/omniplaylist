import { useCallback, useEffect, useState } from 'react';
import { apiClient } from './api/client';
import { djAudioEngine } from './audio/djAudioEngine';
import { Sidebar } from './components/Sidebar';
import type { AppView, DeckId, DeckState, OmniSearchResult, UnifiedTrack } from './types/music';
import { buildHotCuesFromSections } from './utils/camelot';
import { DjModeProView } from './views/DjModeProView';
import { DownloadStudioView } from './views/DownloadStudioView';
import { LibraryManagerView } from './views/LibraryManagerView';
import { OmniSearchView } from './views/OmniSearchView';
import { PlaylistsStudioView } from './views/PlaylistsStudioView';
import { ProvidersStatusView } from './views/ProvidersStatusView';
import { QualityDashboardView } from './views/QualityDashboardView';
import { SpectrumInspectorView } from './views/SpectrumInspectorView';

const makeInitialDeck = (deck: DeckId): DeckState => ({
  deck,
  track: null,
  audioUrl: null,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  pitchRate: 1.0,
  pitchRange: 0.08,
  keyLock: true,
  cuePoint: 0,
  eqLow: 0,
  eqMid: 0,
  eqHigh: 0,
  filter: 0,
  trimGain: 1.0,
  hotCues: buildHotCuesFromSections(null, null),
  waveform: null,
  rmsL: 0,
  rmsR: 0,
  peakL: 0,
  peakR: 0,
});

const VIEW_ROUTES: Record<string, AppView> = {
  '/': 'dj-mode',
  '/dj-mode': 'dj-mode',
  '/audio-inspector': 'spectrum',
  '/spectrum': 'spectrum',
  '/quality-dashboard': 'quality-dashboard',
  '/playlists': 'playlists',
  '/download-studio': 'downloads',
  '/downloads': 'downloads',
  '/search': 'search',
  '/discovery': 'search',
  '/library': 'library',
  '/metadata-editor': 'library',
  '/settings': 'providers',
};

export function App() {
  const [activeView, setActiveView] = useState<AppView>(() => VIEW_ROUTES[window.location.pathname] || 'dj-mode');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [tracks, setTracks] = useState<UnifiedTrack[]>([]);
  const [qualityFilter, setQualityFilter] = useState<string>('ALL');
  const [djPlaylistTracks, setDjPlaylistTracks] = useState<UnifiedTrack[] | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsLastEvent, setWsLastEvent] = useState<Record<string, unknown> | null>(null);
  const [crossfader, setCrossfader] = useState(0);
  const [deckA, setDeckA] = useState<DeckState>(() => makeInitialDeck('A'));
  const [deckB, setDeckB] = useState<DeckState>(() => makeInitialDeck('B'));

  const refreshTracks = useCallback(async () => {
    try {
      const list = await apiClient.getTracks(500);
      setTracks(list);
    } catch {
      // Backend might be restarting
    }
  }, []);

  useEffect(() => {
    void refreshTracks();
  }, [refreshTracks]);

  // Live WebSocket Telemetry for background batch jobs
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: number | undefined;

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${window.location.host}/api/ws/progress`);
      ws.onopen = () => setWsConnected(true);
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(ev.data) as Record<string, unknown>;
          setWsLastEvent(parsed);
          void refreshTracks();
        } catch {
          // ignore malformed payload
        }
      };
      ws.onclose = () => {
        setWsConnected(false);
        retryTimer = window.setTimeout(connect, 3500);
      };
    };

    connect();
    return () => {
      if (retryTimer) window.clearTimeout(retryTimer);
      ws?.close();
    };
  }, [refreshTracks]);

  // 60 FPS Deck Telemetry & Meter Polling
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const telA = djAudioEngine.getDeckTelemetry('A');
      const telB = djAudioEngine.getDeckTelemetry('B');
      setDeckA((prev) =>
        prev.audioUrl
          ? {
              ...prev,
              currentTime: telA.currentTime,
              duration: telA.duration || prev.duration,
              isPlaying: telA.isPlaying,
              rmsL: telA.rmsL,
              rmsR: telA.rmsR,
              peakL: telA.peakL,
              peakR: telA.peakR,
            }
          : prev,
      );
      setDeckB((prev) =>
        prev.audioUrl
          ? {
              ...prev,
              currentTime: telB.currentTime,
              duration: telB.duration || prev.duration,
              isPlaying: telB.isPlaying,
              rmsL: telB.rmsL,
              rmsR: telB.rmsR,
              peakL: telB.peakL,
              peakR: telB.peakR,
            }
          : prev,
      );
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const updateDeck = (deck: DeckId, updater: (prev: DeckState) => DeckState) => {
    if (deck === 'A') setDeckA(updater);
    else setDeckB(updater);
  };

  const handleLoadTrack = async (deck: DeckId, track: UnifiedTrack, autoPlay = false) => {
    const audioUrl = track.local_path
      ? `/api/audio/stream/${track.id}`
      : track.preview_url || null;
    if (!audioUrl) return;

    djAudioEngine.loadUrl(deck, audioUrl);
    djAudioEngine.setPitchRate(deck, 1.0);
    djAudioEngine.setKeyLock(deck, true);

    const hotCues = buildHotCuesFromSections(track.sections_json, track.beatgrid_json);
    updateDeck(deck, (prev) => ({
      ...prev,
      track,
      audioUrl,
      isPlaying: false,
      currentTime: 0,
      duration: track.duration_ms ? track.duration_ms / 1000 : 0,
      pitchRate: 1.0,
      cuePoint: 0,
      hotCues,
      waveform: null,
    }));

    if (autoPlay) {
      try {
        await djAudioEngine.play(deck);
      } catch {
        // Autoplay policy guard
      }
    }

    const wf = await djAudioEngine.decodeRgbWaveform(audioUrl);
    if (wf) {
      updateDeck(deck, (prev) => (prev.track?.id === track.id ? { ...prev, waveform: wf } : prev));
    }
  };

  const handleLoadPreviewToDeck = async (deck: DeckId, item: OmniSearchResult) => {
    const tempTrack: UnifiedTrack = {
      id: item.local_track_id || Date.now(),
      title: item.title,
      artist: item.artist,
      album: item.album,
      duration_ms: item.duration_ms || 30000,
      genres_raw: item.genres_raw,
      cover_url: item.cover_url,
      hd_cover_url: item.hd_cover_url,
      preview_url: item.preview_url,
      bpm: item.bpm,
      camelot_code: item.camelot_code,
    };
    await handleLoadTrack(deck, tempTrack, true);
    setActiveView('dj-mode');
  };

  const handleTogglePlay = async (deck: DeckId) => {
    await djAudioEngine.togglePlay(deck);
  };

  const handleCue = (deck: DeckId) => {
    const cur = deck === 'A' ? deckA : deckB;
    if (!cur.audioUrl) return;
    if (cur.isPlaying) {
      djAudioEngine.pause(deck);
      djAudioEngine.seek(deck, cur.cuePoint);
    } else {
      updateDeck(deck, (prev) => ({ ...prev, cuePoint: prev.currentTime }));
      djAudioEngine.seek(deck, cur.currentTime);
    }
  };

  const handleSync = (targetDeck: DeckId) => {
    const target = targetDeck === 'A' ? deckA : deckB;
    const master = targetDeck === 'A' ? deckB : deckA;
    if (!target.track?.bpm || !master.track?.bpm) return;

    const masterBpm = master.track.bpm * master.pitchRate;
    let ratio = masterBpm / target.track.bpm;
    if (ratio > 1.45) ratio /= 2;
    if (ratio < 0.65) ratio *= 2;
    const clamped = Math.max(1 - target.pitchRange, Math.min(1 + target.pitchRange, ratio));
    djAudioEngine.setPitchRate(targetDeck, clamped);
    updateDeck(targetDeck, (prev) => ({ ...prev, pitchRate: clamped }));
  };

  const handleSeek = (deck: DeckId, sec: number) => {
    djAudioEngine.seek(deck, sec);
    updateDeck(deck, (prev) => ({ ...prev, currentTime: sec }));
  };

  const handlePitchChange = (deck: DeckId, rate: number) => {
    djAudioEngine.setPitchRate(deck, rate);
    updateDeck(deck, (prev) => ({ ...prev, pitchRate: rate }));
  };

  const handleTogglePitchRange = (deck: DeckId) => {
    updateDeck(deck, (prev) => ({ ...prev, pitchRange: prev.pitchRange === 0.08 ? 0.16 : 0.08 }));
  };

  const handleToggleKeyLock = (deck: DeckId) => {
    const cur = deck === 'A' ? deckA : deckB;
    const next = !cur.keyLock;
    djAudioEngine.setKeyLock(deck, next);
    updateDeck(deck, (prev) => ({ ...prev, keyLock: next }));
  };

  const handleEqChange = (deck: DeckId, band: 'low' | 'mid' | 'high', val: number) => {
    djAudioEngine.setEq(deck, band, val);
    updateDeck(deck, (prev) => ({
      ...prev,
      ...(band === 'low' ? { eqLow: val } : band === 'mid' ? { eqMid: val } : { eqHigh: val }),
    }));
  };

  const handleFilterChange = (deck: DeckId, val: number) => {
    djAudioEngine.setFilter(deck, val);
    updateDeck(deck, (prev) => ({ ...prev, filter: val }));
  };

  const handleHotCueClick = (deck: DeckId, idx: number, shiftKey: boolean) => {
    const cur = deck === 'A' ? deckA : deckB;
    const cue = cur.hotCues[idx];
    if (!cue) return;
    if (shiftKey || cue.timeSec === null) {
      updateDeck(deck, (prev) => {
        const nextCues = [...prev.hotCues];
        nextCues[idx] = { ...nextCues[idx], timeSec: Number(prev.currentTime.toFixed(2)) };
        return { ...prev, hotCues: nextCues };
      });
    } else {
      djAudioEngine.seek(deck, cue.timeSec);
    }
  };

  const handleCrossfaderChange = (pos: number) => {
    setCrossfader(pos);
    djAudioEngine.setCrossfader(pos);
  };

  return (
    <div className="min-h-screen flex bg-[#0B0D12] text-slate-200">
      <Sidebar
        activeView={activeView}
        onNavigate={setActiveView}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        wsConnected={wsConnected}
        deckA={deckA}
        deckB={deckB}
      />

      <main className="flex-1 min-w-0 p-3 md:p-4 overflow-y-auto">
        {activeView === 'dj-mode' && (
          <DjModeProView
            tracks={tracks}
            playlistFilterTracks={djPlaylistTracks}
            onClearPlaylistFilter={() => setDjPlaylistTracks(null)}
            deckA={deckA}
            deckB={deckB}
            crossfader={crossfader}
            onLoadTrack={handleLoadTrack}
            onTogglePlay={handleTogglePlay}
            onCue={handleCue}
            onSync={handleSync}
            onSeek={handleSeek}
            onPitchChange={handlePitchChange}
            onTogglePitchRange={handleTogglePitchRange}
            onToggleKeyLock={handleToggleKeyLock}
            onEqChange={handleEqChange}
            onFilterChange={handleFilterChange}
            onHotCueClick={handleHotCueClick}
            onCrossfaderChange={handleCrossfaderChange}
            onRefreshTracks={refreshTracks}
          />
        )}

        {activeView === 'spectrum' && (
          <SpectrumInspectorView
            tracks={tracks}
            deckA={deckA}
            deckB={deckB}
            onRefreshTracks={refreshTracks}
          />
        )}

        {activeView === 'quality-dashboard' && (
          <QualityDashboardView
            onNavigateToFilteredLibrary={(filterKey) => {
              setQualityFilter(filterKey);
              setActiveView('library');
            }}
          />
        )}

        {activeView === 'playlists' && (
          <PlaylistsStudioView
            tracks={tracks}
            onOpenPlaylistInDj={(plTracks) => {
              setDjPlaylistTracks(plTracks);
              setActiveView('dj-mode');
            }}
          />
        )}

        {activeView === 'downloads' && (
          <DownloadStudioView
            tracks={tracks}
            wsLastEvent={wsLastEvent}
            onRefreshTracks={refreshTracks}
          />
        )}

        {activeView === 'search' && (
          <OmniSearchView
            onLoadPreviewToDeck={handleLoadPreviewToDeck}
            onTrackImported={refreshTracks}
          />
        )}

        {activeView === 'library' && (
          <LibraryManagerView
            tracks={tracks}
            wsLastEvent={wsLastEvent}
            qualityFilter={qualityFilter}
            onClearQualityFilter={() => setQualityFilter('ALL')}
            onRefreshTracks={refreshTracks}
          />
        )}

        {activeView === 'providers' && <ProvidersStatusView tracks={tracks} />}
      </main>
    </div>
  );
}

export default App;
