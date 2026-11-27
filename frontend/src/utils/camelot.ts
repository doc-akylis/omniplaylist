import type { BeatgridData, HotCue, SectionSegment } from '../types/music';

const CAMELOT_COLORS: Record<number, string> = {
  1: '#06B6D4',
  2: '#0EA5E9',
  3: '#3B82F6',
  4: '#6366F1',
  5: '#8B5CF6',
  6: '#A855F7',
  7: '#D946EF',
  8: '#EC4899',
  9: '#F43F5E',
  10: '#F97316',
  11: '#EAB308',
  12: '#10B981',
};

const HOT_CUE_COLORS = [
  '#38BDF8', // A
  '#10B981', // B
  '#F59E0B', // C
  '#A855F7', // D
  '#EF4444', // E
  '#EC4899', // F
  '#06B6D4', // G
  '#84CC16', // H
];

export function getCamelotColor(code?: string | null): string {
  if (!code) return '#475569';
  const match = /^(\d{1,2})([AB])$/i.exec(code.trim());
  if (!match) return '#64748B';
  const num = Number(match[1]);
  return CAMELOT_COLORS[num] || '#38BDF8';
}

export function areCamelotCompatible(c1?: string | null, c2?: string | null): boolean {
  if (!c1 || !c2) return false;
  const m1 = /^(\d{1,2})([AB])$/i.exec(c1.trim());
  const m2 = /^(\d{1,2})([AB])$/i.exec(c2.trim());
  if (!m1 || !m2) return false;
  const n1 = Number(m1[1]);
  const l1 = m1[2].toUpperCase();
  const n2 = Number(m2[1]);
  const l2 = m2[2].toUpperCase();
  if (n1 === n2) return true;
  if (l1 === l2) {
    const diff = Math.abs(n1 - n2);
    return diff === 1 || diff === 11;
  }
  return false;
}

export function formatTimecode(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00.0';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const tenths = Math.floor((seconds % 1) * 10);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}.${tenths}`;
}

export function parseJsonSafe<T>(raw: string | null | undefined, fallback: T): T {
  if (!raw) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function buildHotCuesFromSections(
  sectionsJson?: string | null,
  beatgridJson?: string | null,
): HotCue[] {
  const slots = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'];
  const sections = parseJsonSafe<SectionSegment[]>(sectionsJson, []);
  const beatgrid = parseJsonSafe<BeatgridData | null>(beatgridJson, null);
  const downbeats = beatgrid?.downbeats_sec || [];

  const cues: HotCue[] = slots.map((slot, idx) => ({
    slot,
    timeSec: null,
    label: `Cue ${slot}`,
    color: HOT_CUE_COLORS[idx],
  }));

  sections.slice(0, 8).forEach((sec, idx) => {
    let snapped = sec.start_sec;
    if (downbeats.length > 0) {
      snapped = downbeats.reduce((best, db) =>
        Math.abs(db - sec.start_sec) < Math.abs(best - sec.start_sec) ? db : best,
      );
    }
    cues[idx] = {
      slot: slots[idx],
      timeSec: Number(snapped.toFixed(2)),
      label: sec.label.toUpperCase(),
      color: HOT_CUE_COLORS[idx],
    };
  });

  return cues;
}
