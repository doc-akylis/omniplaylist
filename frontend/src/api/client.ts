import type {
  AbComparisonResponse,
  AcquisitionRecordItem,
  AudioProfile,
  CandidateSourcePayload,
  DiscoverySearchResponse,
  DJRecommendation,
  DownloadJob,
  DuplicateGroup,
  MusicSourceInfo,
  OmniSearchResult,
  PlaylistDetailsResponse,
  PlaylistModel,
  ProvidersHealthResponse,
  QualityDashboardData,
  QualityReport,
  SequencerPreviewResponse,
  TransitionAnalysisResponse,
  UnifiedTrack,
  UpgradeCheckResult,
} from '../types/music';

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(`HTTP ${res.status}: ${msg}`);
  }
  return res.json() as Promise<T>;
}

export const apiClient = {
  getTracks: (limit = 500) => requestJson<UnifiedTrack[]>(`/api/tracks?limit=${limit}`),

  getDjProfile: (trackId: number) =>
    requestJson<{ track: UnifiedTrack; technical: Record<string, unknown>; musical: Record<string, unknown> }>(
      `/api/tracks/${trackId}/dj-profile`,
    ),

  analyzeTechnical: (trackId: number, force = true) =>
    requestJson<{ status: string; analyzed: boolean }>(`/api/tracks/${trackId}/analyze?force=${force}`, {
      method: 'POST',
    }),

  analyzeMusical: (trackId: number, force = true) =>
    requestJson<{ status: string; analyzed: boolean; bpm?: number; camelot_code?: string }>(
      `/api/tracks/${trackId}/analyze-musical?force=${force}`,
      { method: 'POST' },
    ),

  enrichTrack: (trackId: number, force = true) =>
    requestJson<Record<string, unknown>>(`/api/tracks/${trackId}/enrich?force=${force}`, {
      method: 'POST',
    }),

  identifyAcoustId: (trackId: number) =>
    requestJson<{
      identified: boolean;
      available: boolean;
      reason?: string;
      acoustid_id?: string;
      musicbrainz_recording_id?: string;
      title?: string;
      artist?: string;
      score?: number;
    }>(`/api/tracks/${trackId}/identify-acoustid`, { method: 'POST' }),

  getNextRecommendations: (trackId: number, limit = 8) =>
    requestJson<{ track_id: number; recommendations: DJRecommendation[] }>(
      `/api/tracks/${trackId}/next-recommendations?limit=${limit}`,
    ),

  analyzeLibraryTechnical: (force = false) =>
    requestJson<{ status: string; message: string }>(`/api/library/analyze?force=${force}`, {
      method: 'POST',
    }),

  analyzeLibraryMusical: (force = false) =>
    requestJson<{ status: string; message: string }>(`/api/library/analyze-musical?force=${force}`, {
      method: 'POST',
    }),

  enrichLibrary: (force = false) =>
    requestJson<{ status: string; message: string }>(`/api/library/enrich?force=${force}`, {
      method: 'POST',
    }),

  omniSearch: (q: string, mode: 'all' | 'local' | 'online' = 'all') =>
    requestJson<{ query: string; mode: string; count: number; results: OmniSearchResult[] }>(
      `/api/search/omni?q=${encodeURIComponent(q)}&mode=${mode}`,
    ),

  importOnlineTrack: (item: OmniSearchResult, enrich = true) =>
    requestJson<{ status: string; track: UnifiedTrack; enrichment?: Record<string, unknown> }>(
      '/api/tracks/import-online',
      {
        method: 'POST',
        body: JSON.stringify({
          title: item.title,
          artist: item.artist,
          album: item.album,
          isrc: item.isrc,
          duration_ms: item.duration_ms,
          cover_url: item.cover_url,
          hd_cover_url: item.hd_cover_url,
          preview_url: item.preview_url,
          release_year: item.release_year,
          deezer_id: item.deezer_id,
          musicbrainz_recording_id: item.musicbrainz_recording_id,
          genres_raw: item.genres_raw,
          lyrics_synced: item.lyrics_synced,
          lyrics_plain: item.lyrics_plain,
          enrich,
        }),
      },
    ),

  updateTrack: (trackId: number, patch: Partial<UnifiedTrack>) =>
    requestJson<UnifiedTrack>(`/api/tracks/${trackId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  getDuplicates: () =>
    requestJson<{ total_tracks: number; duplicate_groups: DuplicateGroup[] }>('/api/library/duplicates'),

  mergeDuplicates: (primary_id: number, duplicate_ids: number[]) =>
    requestJson<{ merged: number; primary: UnifiedTrack }>('/api/library/merge-duplicates', {
      method: 'POST',
      body: JSON.stringify({ primary_id, duplicate_ids }),
    }),

  getDiscovery: (trackId?: number) =>
    requestJson<{
      seed_track: UnifiedTrack | null;
      local_dj_recommendations: DJRecommendation[];
      lastfm_similar: Array<{ title: string; artist: string; match: number }>;
      listenbrainz_similar: Array<Record<string, unknown>>;
      tags: string[];
    }>(`/api/discovery/recommendations${trackId ? `?track_id=${trackId}` : ''}`),

  getProvidersHealth: () => requestJson<ProvidersHealthResponse>('/api/health/providers'),

  saveProviderSettings: (payload: {
    LISTENBRAINZ_TOKEN: string;
    LASTFM_API_KEY: string;
    ACOUSTID_API_KEY: string;
  }) =>
    requestJson<{ status: string; health: ProvidersHealthResponse }>('/api/settings/providers', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // ============ v2.1 Audio Quality Intelligence & Dashboard ============
  analyzeTrackQuality: (trackId: number, force = true) =>
    requestJson<QualityReport>(`/api/tracks/${trackId}/analyze-quality?force=${force}`, {
      method: 'POST',
    }),

  analyzeLibraryQuality: (force = false) =>
    requestJson<{ status: string; message: string }>(`/api/library/analyze-quality?force=${force}`, {
      method: 'POST',
    }),

  getTrackQuality: (trackId: number) =>
    requestJson<QualityReport>(`/api/tracks/${trackId}/quality`),

  getQualityDashboard: () => requestJson<QualityDashboardData>('/api/quality/dashboard'),

  compareTracks: (trackAId: number, trackBId: number) =>
    requestJson<AbComparisonResponse>(
      `/api/tracks/compare?track_a_id=${trackAId}&track_b_id=${trackBId}`,
    ),

  // ============ v2.1 Download Studio ============
  getAudioProfiles: () => requestJson<{ profiles: AudioProfile[] }>('/api/downloads/profiles'),

  checkUpgrade: (trackId: number | null, candidate: CandidateSourcePayload, profile: string) =>
    requestJson<UpgradeCheckResult>('/api/downloads/check-upgrade', {
      method: 'POST',
      body: JSON.stringify({ track_id: trackId, candidate, profile }),
    }),

  enqueueDownloadJob: (payload: {
    track_id: number | null;
    candidate: CandidateSourcePayload;
    profile: string;
    target_sample_rate_hz?: number | null;
    allow_downgrade_or_same?: boolean;
  }) =>
    requestJson<DownloadJob>('/api/downloads/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getDownloadJobs: () => requestJson<{ jobs: DownloadJob[] }>('/api/downloads/jobs'),

  cancelDownloadJob: (jobId: number) =>
    requestJson<DownloadJob>(`/api/downloads/jobs/${jobId}/cancel`, { method: 'POST' }),

  pauseDownloadJob: (jobId: number) =>
    requestJson<DownloadJob>(`/api/downloads/jobs/${jobId}/pause`, { method: 'POST' }),

  resumeDownloadJob: (jobId: number) =>
    requestJson<DownloadJob>(`/api/downloads/jobs/${jobId}/resume`, { method: 'POST' }),

  retryDownloadJob: (jobId: number) =>
    requestJson<DownloadJob>(`/api/downloads/jobs/${jobId}/retry`, { method: 'POST' }),

  // ============ v2.1 Playlist Manager & Smart Sequencer ============
  getPlaylists: () => requestJson<PlaylistModel[]>('/api/playlists'),

  createPlaylist: (payload: { name: string; description?: string; track_ids?: number[] }) =>
    requestJson<PlaylistModel>('/api/playlists', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  updatePlaylist: (playlistId: number, payload: { name?: string; description?: string }) =>
    requestJson<PlaylistModel>(`/api/playlists/${playlistId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  deletePlaylist: (playlistId: number) =>
    requestJson<{ deleted: boolean }>(`/api/playlists/${playlistId}`, { method: 'DELETE' }),

  duplicatePlaylist: (playlistId: number, name?: string) =>
    requestJson<PlaylistModel>(`/api/playlists/${playlistId}/duplicate`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  getPlaylistDetails: (playlistId: number, statusFilter?: string) =>
    requestJson<PlaylistDetailsResponse>(
      `/api/playlists/${playlistId}/details${statusFilter && statusFilter !== 'ALL' ? `?status_filter=${statusFilter}` : ''}`,
    ),

  addTracksToPlaylist: (playlistId: number, trackIds: number[]) =>
    requestJson<{ added: number }>(`/api/playlists/${playlistId}/tracks`, {
      method: 'POST',
      body: JSON.stringify({ track_ids: trackIds }),
    }),

  removeTracksFromPlaylist: (playlistId: number, trackIds: number[]) =>
    requestJson<{ removed: number }>(`/api/playlists/${playlistId}/tracks`, {
      method: 'DELETE',
      body: JSON.stringify({ track_ids: trackIds }),
    }),

  reorderPlaylist: (playlistId: number, orderedTrackIds: number[]) =>
    requestJson<{ count: number }>(`/api/playlists/${playlistId}/reorder`, {
      method: 'PUT',
      body: JSON.stringify({ ordered_track_ids: orderedTrackIds }),
    }),

  sortPlaylist: (playlistId: number, sortBy: string, persist = true) =>
    requestJson<{ tracks: UnifiedTrack[] }>(`/api/playlists/${playlistId}/sort`, {
      method: 'POST',
      body: JSON.stringify({ sort_by: sortBy, persist }),
    }),

  exportPlaylistM3u: (playlistId: number, format: 'm3u' | 'm3u8' = 'm3u8') =>
    requestJson<{
      exported_file: string;
      format: string;
      total_tracks: number;
      exported_local_count: number;
      missing_files: Array<{ track_id: number; title: string; artist: string; reason: string }>;
    }>(`/api/playlists/${playlistId}/export-m3u`, {
      method: 'POST',
      body: JSON.stringify({ format }),
    }),

  previewSmartSequence: (playlistId: number, config: Record<string, unknown>) =>
    requestJson<SequencerPreviewResponse>(`/api/playlists/${playlistId}/sequence/preview`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  applySmartSequence: (playlistId: number, orderedTrackIds: number[]) =>
    requestJson<{ applied: boolean; can_restore: boolean }>(
      `/api/playlists/${playlistId}/sequence/apply`,
      {
        method: 'POST',
        body: JSON.stringify({ ordered_track_ids: orderedTrackIds }),
      },
    ),

  restoreSmartSequence: (playlistId: number) =>
    requestJson<{ restored: boolean }>(`/api/playlists/${playlistId}/sequence/restore`, {
      method: 'POST',
    }),

  // ============ v2.1 DJ Technical Analyzer ============
  analyzeDjTransition: (
    trackAId: number,
    trackBId: number,
    deckAPitch = 1.0,
    deckBPitch = 1.0,
  ) =>
    requestJson<TransitionAnalysisResponse>('/api/dj/transition-analysis', {
      method: 'POST',
      body: JSON.stringify({
        track_a_id: trackAId,
        track_b_id: trackBId,
        deck_a_pitch: deckAPitch,
        deck_b_pitch: deckBPitch,
      }),
    }),

  // ============ v2.2 Multi-Source Discovery & Automatic Acquisition ============
  getMusicSources: () =>
    requestJson<{ total: number; providers: MusicSourceInfo[]; credential_keys: string[] }>(
      '/api/sources',
    ),

  updateMusicSource: (providerId: string, body: { enabled?: boolean; priority?: number }) =>
    requestJson<{ provider_id: string; enabled: boolean; priority: number }>(
      `/api/sources/${providerId}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),

  healthCheckMusicSource: (providerId: string) =>
    requestJson<{ provider_id: string; status: string; detail: string; latency_ms?: number }>(
      `/api/sources/${providerId}/health-check`,
      { method: 'POST' },
    ),

  saveSourceCredentials: (credentials: Record<string, string>) =>
    requestJson<{ updated_keys: string[]; providers: MusicSourceInfo[] }>(
      '/api/sources/credentials',
      { method: 'POST', body: JSON.stringify({ credentials }) },
    ),

  discoverySearch: (payload: {
    query: string;
    search_type?: string;
    artist?: string;
    title?: string;
    album?: string;
    isrc?: string;
    provider_ids?: string[] | null;
    only_downloadable?: boolean;
    limit_per_provider?: number;
  }) =>
    requestJson<DiscoverySearchResponse>('/api/discovery/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  acquireAuto: (payload: {
    query?: string;
    mode: string;
    profile: string;
    target_sample_rate_hz?: number | null;
    track_id?: number | null;
    preferred_provider_id?: string | null;
    preferred_source_item_id?: string | null;
    group_payload?: Record<string, unknown> | null;
    allow_downgrade_or_same?: boolean;
  }) =>
    requestJson<{
      accepted: boolean;
      status: string;
      reason: string;
      requires_approval?: boolean;
      job?: DownloadJob | null;
    }>('/api/acquisition/auto', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  approveAcquisitionJob: (jobId: number) =>
    requestJson<{ approved: boolean; job: DownloadJob }>(
      `/api/acquisition/jobs/${jobId}/approve`,
      { method: 'POST' },
    ),

  getAcquisitionRecords: (limit = 30) =>
    requestJson<{ total: number; records: AcquisitionRecordItem[] }>(
      `/api/acquisition/records?limit=${limit}`,
    ),
};
