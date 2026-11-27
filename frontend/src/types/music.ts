export type DeckId = 'A' | 'B';

export type AppView =
  | 'dj-mode'
  | 'spectrum'
  | 'quality-dashboard'
  | 'playlists'
  | 'downloads'
  | 'search'
  | 'library'
  | 'providers';

export interface SectionSegment {
  label: string;
  start_sec: number;
  end_sec: number;
  relative_energy?: number;
  confidence?: number;
}

export interface BeatgridData {
  beats_sec: number[];
  downbeats_sec: number[];
  time_signature?: string;
  total_beats?: number;
}

export interface UnifiedTrack {
  id: number;
  isrc?: string | null;
  title: string;
  artist: string;
  album?: string | null;
  duration_ms?: number | null;
  genres_raw: string;
  cover_url?: string | null;
  hd_cover_url?: string | null;
  preview_url?: string | null;
  release_year?: number | null;
  local_path?: string | null;

  spotify_id?: string | null;
  ytmusic_id?: string | null;
  amazon_id?: string | null;
  deezer_id?: string | null;
  musicbrainz_recording_id?: string | null;
  acoustid_id?: string | null;

  bpm?: number | null;
  key?: string | null;
  camelot_code?: string | null;
  bpm_stability?: number | null;
  danceability?: number | null;
  energy?: number | null;
  beatgrid_json?: string | null;
  sections_json?: string | null;
  musical_analysis_confidence?: number | null;
  musical_analyzed_at?: string | null;

  codec?: string | null;
  bitrate_kbps?: number | null;
  sample_rate_hz?: number | null;
  bit_depth?: number | null;
  channels?: number | null;
  file_size_bytes?: number | null;
  is_corrupted?: boolean;
  quality_warning?: string | null;

  integrated_lufs?: number | null;
  momentary_lufs?: number | null;
  short_term_lufs?: number | null;
  loudness_range_lu?: number | null;
  true_peak_dbfs?: number | null;
  dynamic_range_db?: number | null;
  crest_factor_db?: number | null;
  replay_gain?: number | null;
  clipping_count?: number | null;
  silence_start_ms?: number | null;
  silence_end_ms?: number | null;
  analyzed_at?: string | null;

  lyrics_synced?: string | null;
  lyrics_plain?: string | null;
  lastfm_tags?: string | null;
  metadata_enriched_at?: string | null;

  // Audio Quality Intelligence (v2.1)
  is_preview?: boolean;
  source_classification?: string | null;
  spectral_cutoff_hz?: number | null;
  upscale_status?: string | null;
  upscale_confidence?: number | null;
  is_fake_upscale?: boolean;
  sub_bass_energy?: number | null;
  mid_bass_energy?: number | null;
  midrange_energy?: number | null;
  high_freq_energy?: number | null;
  car_audio_score?: number | null;
  car_audio_status?: string | null;
  car_audio_ready?: boolean;
  quality_intelligence_json?: string | null;
  quality_analyzed_at?: string | null;
}

export interface AudioProvenance {
  id: number;
  track_id: number;
  acquisition_source: string;
  provider?: string | null;
  source_url?: string | null;
  original_codec?: string | null;
  original_bitrate_kbps?: number | null;
  original_sample_rate_hz?: number | null;
  original_bit_depth?: number | null;
  origin_classification: string;
  current_container?: string | null;
  current_codec?: string | null;
  requested_profile?: string | null;
  evidence_json?: string | null;
  engine_name: string;
  engine_version: string;
  acquired_at?: string | null;
  analyzed_at?: string | null;
}

export interface AudioProcessingHistoryItem {
  id: number;
  track_id: number;
  operation: string;
  from_codec?: string | null;
  to_codec?: string | null;
  from_bitrate_kbps?: number | null;
  to_bitrate_kbps?: number | null;
  profile?: string | null;
  source_path?: string | null;
  dest_path?: string | null;
  backup_path?: string | null;
  was_lossy_to_lossless: boolean;
  warnings_json?: string | null;
  engine_name: string;
  created_at: string;
}

export interface QualityReport {
  track_id: number;
  title: string;
  artist: string;
  file: Record<string, unknown>;
  technical: Record<string, unknown>;
  quality_intelligence: {
    source_classification: string;
    spectral_cutoff_hz?: number | null;
    upscale_status: string;
    upscale_confidence?: number | null;
    is_fake_upscale: boolean;
    bass_profile: {
      sub_bass_20_60?: number | null;
      mid_bass_60_250?: number | null;
      midrange_250_4000?: number | null;
      high_freq_4000_20000?: number | null;
    };
    car_audio_score?: number | null;
    car_audio_status?: string | null;
    car_audio_ready: boolean;
    details?: {
      car_audio?: {
        penalties?: Array<{ criterion: string; points: number; reason: string }>;
        positives?: string[];
        note?: string;
      };
      spectral?: {
        evidence?: string[];
        limitations?: string[];
        nyquist_hz?: number;
      };
    };
    quality_analyzed_at?: string | null;
  };
  provenance: AudioProvenance | null;
  processing_history: AudioProcessingHistoryItem[];
}

export interface QualityDashboardData {
  total_tracks: number;
  complete_files: number;
  previews: number;
  missing_files: number;
  lossless_source: number;
  lossy_source: number;
  unknown_source: number;
  suspected_fake_upscale: number;
  corrupted: number;
  clipping: number;
  critical_true_peak: number;
  unanalyzed: number;
  upgrades_available: number;
  avg_car_audio_score: number | null;
  codec_distribution: Record<string, number>;
  bitrate_distribution: Record<string, number>;
  sample_rate_distribution: Record<string, number>;
  car_audio_status_distribution: Record<string, number>;
}

export interface AudioProfile {
  id: string;
  name: string;
  format?: string | null;
  codec?: string | null;
  bitrate?: string | null;
  sample_rate?: number | null;
  lossy?: boolean | null;
  description: string;
}

export interface CandidateSourcePayload {
  provider: string;
  source_url?: string | null;
  local_source_path?: string | null;
  title: string;
  artist: string;
  isrc?: string | null;
  duration_ms?: number | null;
  codec?: string | null;
  bitrate_kbps?: number | null;
  sample_rate_hz?: number | null;
  bit_depth?: number | null;
  is_preview: boolean;
  origin_classification: string;
  verified_source: boolean;
}

export interface UpgradeCheckResult {
  decision: string;
  is_justified: boolean;
  reason: string;
  warnings: string[];
  existing_rank: number;
  candidate_rank: number;
}

export interface DownloadJob {
  id: number;
  track_id?: number | null;
  provider: string;
  source_url?: string | null;
  source_path?: string | null;
  source_label?: string | null;
  status: string;
  profile: string;
  target_sample_rate_hz?: number | null;
  dest_path?: string | null;
  backup_path?: string | null;
  progress: number;
  speed_bps?: number | null;
  eta_sec?: number | null;
  estimated_bytes?: number | null;
  final_bytes?: number | null;
  current_stage: string;
  logs_json: string;
  error_message?: string | null;
  attempts: number;
  max_attempts: number;
  upgrade_decision?: string | null;
  upgrade_reason?: string | null;
  requires_approval?: boolean;
  approved_by_user?: boolean;
  estimated_cost_label?: string | null;
  license_info?: string | null;
  file_sha256?: string | null;
  source_item_id?: string | null;
  acquisition_mode?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface PlaylistModel {
  id: number;
  name: string;
  description?: string | null;
  cover_url?: string | null;
  original_order_json?: string | null;
  source_provider: string;
  created_at: string;
  updated_at: string;
}

export interface PlaylistMetrics {
  total_tracks: number;
  total_duration_ms: number;
  avg_bpm?: number | null;
  min_bpm?: number | null;
  max_bpm?: number | null;
  avg_energy?: number | null;
  camelot_distribution: Record<string, number>;
  avg_lufs?: number | null;
  avg_quality_score?: number | null;
  complete_count: number;
  preview_count: number;
  missing_count: number;
  corrupted_count: number;
  upgrades_available_count: number;
  fake_upscale_count: number;
  metrics_notes: string[];
}

export interface PlaylistTrackEntry {
  position: number;
  track: UnifiedTrack;
  quality_statuses: string[];
}

export interface PlaylistDetailsResponse {
  playlist: PlaylistModel;
  metrics: PlaylistMetrics;
  tracks: PlaylistTrackEntry[];
  has_original_order_snapshot: boolean;
}

export interface SequencerTransition {
  track_a_id: number;
  track_b_id: number;
  title_a: string;
  title_b: string;
  artist_a: string;
  artist_b: string;
  bpm_a?: number | null;
  bpm_b?: number | null;
  delta_bpm?: number | null;
  delta_bpm_pct?: number | null;
  camelot_a?: string | null;
  camelot_b?: string | null;
  energy_a?: number | null;
  energy_b?: number | null;
  compatibility: boolean;
  score: number;
  justification: string;
  alerts: string[];
  mix_out_sec: number;
  mix_in_sec: number;
}

export interface SequencerPreviewResponse {
  ordered_tracks: UnifiedTrack[];
  transitions: SequencerTransition[];
  average_score: number;
  warnings: string[];
}

export interface EqSuggestion {
  id: string;
  target_deck: 'A' | 'B';
  band: 'low' | 'mid' | 'high';
  suggested_db: number;
  reason: string;
}

export interface TransitionAnalysisResponse {
  track_a_id: number;
  track_b_id: number;
  effective_bpm_a?: number | null;
  effective_bpm_b?: number | null;
  delta_bpm?: number | null;
  delta_bpm_pct?: number | null;
  bpm_relation: string;
  bpm_score: number;
  camelot_a?: string | null;
  camelot_b?: string | null;
  harmonic_score: number;
  harmonic_reason: string;
  is_harmonic_compatible: boolean;
  delta_energy?: number | null;
  delta_lufs?: number | null;
  true_peak_a?: number | null;
  true_peak_b?: number | null;
  bass_overlap_score?: number | null;
  conflicting_bands: string[];
  estimated_combined_peak_dbfs?: number | null;
  combined_clipping_is_estimate: boolean;
  clipping_risk_note: string;
  mix_out_sec: number;
  mix_in_sec: number;
  risk_level: string;
  alerts: string[];
  eq_suggestions: EqSuggestion[];
}

export interface AbComparisonResponse {
  version_a: Record<string, unknown>;
  version_b: Record<string, unknown>;
  differences: string[];
  recommended_track_id: number;
  summary: string;
}

export interface TransitionPoints {
  mix_out_sec: number;
  mix_out_label: string;
  mix_in_sec: number;
  mix_in_label: string;
}

export interface DJRecommendation {
  track_id: number;
  title: string;
  artist: string;
  bpm?: number | null;
  camelot_code?: string | null;
  score: number;
  harmonic_score: number;
  harmonic_reason: string;
  is_harmonic_compatible: boolean;
  bpm_score: number;
  bpm_delta_pct: number;
  bpm_relation: string;
  energy_delta: number;
  tag_affinity: number;
  transition_points: TransitionPoints;
}

export interface OmniSearchResult {
  id: string;
  local_track_id?: number | null;
  in_library: boolean;
  title: string;
  artist: string;
  album?: string | null;
  isrc?: string | null;
  duration_ms?: number | null;
  cover_url?: string | null;
  hd_cover_url?: string | null;
  preview_url?: string | null;
  release_year?: number | null;
  deezer_id?: string | null;
  musicbrainz_recording_id?: string | null;
  genres_raw: string;
  has_synced_lyrics: boolean;
  lyrics_synced?: string | null;
  lyrics_plain?: string | null;
  bpm?: number | null;
  camelot_code?: string | null;
  sources: string[];
}

export interface ProviderHealth {
  id: string;
  name: string;
  requires_key: boolean;
  status: string;
  configured?: boolean;
  fpcalc_installed?: boolean;
  detail: string;
}

export interface ProvidersHealthResponse {
  providers: ProviderHealth[];
  engines: {
    ffmpeg: boolean;
    ffprobe: boolean;
    librosa: string | null;
  };
}

export interface DuplicateGroup {
  primary: UnifiedTrack;
  candidates: UnifiedTrack[];
  count: number;
}

export interface RgbWaveformPeaks {
  low: Float32Array;
  mid: Float32Array;
  high: Float32Array;
  duration: number;
  spectralCentroidHz?: number;
  engineLabel: string;
}

export interface HotCue {
  slot: string;
  timeSec: number | null;
  label: string;
  color: string;
}

export interface DeckState {
  deck: DeckId;
  track: UnifiedTrack | null;
  audioUrl: string | null;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  pitchRate: number;
  pitchRange: 0.08 | 0.16;
  keyLock: boolean;
  cuePoint: number;
  eqLow: number;
  eqMid: number;
  eqHigh: number;
  filter: number;
  trimGain: number;
  hotCues: HotCue[];
  waveform: RgbWaveformPeaks | null;
  rmsL: number;
  rmsR: number;
  peakL: number;
  peakR: number;
}

// ============ v2.2 Universal Music Discovery & Automatic Acquisition ============
export type ProviderCategory =
  | 'DISCOVERY'
  | 'PREVIEW_STREAMING'
  | 'AUTHORIZED_DOWNLOAD'
  | 'COMMERCIAL_DELIVERY';

export type PermissionStatus =
  | 'ALLOWED_FREE'
  | 'ALLOWED_COMMERCIAL_REQUIRES_APPROVAL'
  | 'PREVIEW_ONLY'
  | 'STREAMING_ONLY'
  | 'NOT_DOWNLOADABLE'
  | 'REQUIRES_CREDENTIALS'
  | 'UNAVAILABLE';

export interface MusicSourceInfo {
  provider_id: string;
  name: string;
  category: ProviderCategory;
  requires_auth: boolean;
  auth_configured: boolean;
  missing_credentials: string[];
  supports_search_tracks: boolean;
  supports_search_artists: boolean;
  supports_search_albums: boolean;
  supports_streaming: boolean;
  supports_download: boolean;
  formats: string[];
  rate_limit_info: string;
  cost_info: string;
  restrictions: string;
  docs_verified: boolean;
  enabled: boolean;
  priority: number;
  last_health_status?: string | null;
  last_health_checked_at?: string | null;
}

export interface ProviderSearchStatus {
  provider_id: string;
  provider_name: string;
  category: ProviderCategory;
  status: string;
  count: number;
  latency_ms: number;
  error?: string | null;
}

export interface CandidateScoreBreakdown {
  provider_id: string;
  provider_name: string;
  category: ProviderCategory;
  source_item_id: string;
  title: string;
  artist: string;
  version_type: string;
  downloadable: boolean;
  permission_status: PermissionStatus;
  requires_payment: boolean;
  requires_credentials: boolean;
  estimated_cost_label?: string | null;
  license_info?: string | null;
  declared_codec?: string | null;
  declared_bitrate_kbps?: number | null;
  declared_sample_rate_hz?: number | null;
  declared_bit_depth?: number | null;
  origin_classification: string;
  suspected_transcode: boolean;
  identity_score: number;
  technical_score: number;
  reliability_score: number;
  total_score: number;
  download_url?: string | null;
  preview_url?: string | null;
  explanation: string[];
}

export interface SourceComparisonResult {
  group_key: string;
  best_authorized?: CandidateScoreBreakdown | null;
  best_free?: CandidateScoreBreakdown | null;
  best_commercial?: CandidateScoreBreakdown | null;
  best_quality_overall?: CandidateScoreBreakdown | null;
  has_authorized_download: boolean;
  selection_reason: string;
  ranked_candidates: CandidateScoreBreakdown[];
}

export interface GroupedRecording {
  group_key: string;
  title: string;
  artist: string;
  album?: string | null;
  duration_ms?: number | null;
  isrc?: string | null;
  mbid?: string | null;
  version_type: string;
  cover_url?: string | null;
  match_confidence: number;
  match_strategy: string;
  has_downloadable_source: boolean;
  has_free_download: boolean;
  has_commercial_download: boolean;
  candidates: Array<Record<string, unknown>>;
  comparison?: SourceComparisonResult | null;
}

export interface DiscoverySearchResponse {
  query: string;
  search_type: string;
  cached: boolean;
  total_raw_results: number;
  total_groups: number;
  downloadable_groups: number;
  provider_statuses: ProviderSearchStatus[];
  groups: GroupedRecording[];
}

export interface AcquisitionRecordItem {
  id: number;
  search_session_id?: number | null;
  download_job_id?: number | null;
  track_id?: number | null;
  provider_id: string;
  source_item_id?: string | null;
  acquisition_mode: string;
  status: string;
  license_info?: string | null;
  was_paid: boolean;
  approved_by_user: boolean;
  file_sha256?: string | null;
  comparison_summary_json?: string | null;
  error_message?: string | null;
  created_at: string;
}
