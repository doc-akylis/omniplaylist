import React, { useEffect, useRef } from 'react';
import type { BeatgridData, HotCue, RgbWaveformPeaks, SectionSegment } from '../types/music';

interface RgbWaveformCanvasProps {
  waveform: RgbWaveformPeaks | null;
  currentTime: number;
  duration: number;
  sections: SectionSegment[];
  beatgrid: BeatgridData | null;
  hotCues: HotCue[];
  zoom: number;
  accentColor: string;
  onSeek: (timeSec: number) => void;
}

const SECTION_COLORS: Record<string, string> = {
  intro: '#38BDF8',
  verse: '#10B981',
  chorus: '#F59E0B',
  breakdown: '#A855F7',
  outro: '#EF4444',
};

export const RgbWaveformCanvas: React.FC<RgbWaveformCanvasProps> = ({
  waveform,
  currentTime,
  duration,
  sections,
  beatgrid,
  hotCues,
  zoom,
  accentColor,
  onSeek,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    const midY = height / 2;

    // Background
    ctx.fillStyle = '#080A0E';
    ctx.fillRect(0, 0, width, height);

    // Subtle horizontal dB / center guides
    ctx.strokeStyle = '#161C28';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, midY);
    ctx.lineTo(width, midY);
    ctx.stroke();

    const effectiveDur = duration || waveform?.duration || 0;
    if (effectiveDur <= 0) {
      ctx.fillStyle = '#475569';
      ctx.font = '12px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('Carregue uma faixa no Deck para visualizar Waveform RGB & Beatgrid', width / 2, midY + 4);
      return;
    }

    // Viewport window when zoomed (centered around playhead if zoom > 1)
    const windowSec = effectiveDur / Math.max(1, zoom);
    const halfWin = windowSec / 2;
    let startSec = zoom <= 1 ? 0 : currentTime - halfWin;
    startSec = Math.max(0, Math.min(Math.max(0, effectiveDur - windowSec), startSec));
    const endSec = Math.min(effectiveDur, startSec + windowSec);

    const timeToX = (t: number) => ((t - startSec) / Math.max(0.001, endSec - startSec)) * width;

    // 1. Section background bands
    for (const sec of sections) {
      if (sec.end_sec < startSec || sec.start_sec > endSec) continue;
      const x1 = Math.max(0, timeToX(sec.start_sec));
      const x2 = Math.min(width, timeToX(sec.end_sec));
      const color = SECTION_COLORS[sec.label?.toLowerCase()] || '#64748B';
      ctx.fillStyle = `${color}1A`;
      ctx.fillRect(x1, 0, Math.max(2, x2 - x1), height);

      ctx.fillStyle = color;
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'left';
      if (x2 - x1 > 28) {
        ctx.fillText(sec.label.toUpperCase(), x1 + 4, 11);
      }
    }

    // 2. RGB Waveform bars (Low=Red/Blue, Mid=Emerald/Amber, High=Cyan/White)
    const buckets = waveform?.low.length ?? 240;
    for (let px = 0; px < width; px += 2) {
      const t = startSec + (px / width) * (endSec - startSec);
      const normIdx = Math.min(buckets - 1, Math.max(0, Math.floor((t / effectiveDur) * buckets)));

      let lVal = 0.2;
      let mVal = 0.25;
      let hVal = 0.15;
      if (waveform) {
        lVal = waveform.low[normIdx];
        mVal = waveform.mid[normIdx];
        hVal = waveform.high[normIdx];
      } else {
        // Fallback harmonic envelope when remote CORS blocks Web Audio buffer decode
        const pulse = Math.abs(Math.sin(normIdx * 0.28) * Math.cos(normIdx * 0.07));
        lVal = 0.3 + pulse * 0.55;
        mVal = 0.2 + pulse * 0.45;
        hVal = 0.1 + pulse * 0.35;
      }

      const maxAmp = (height * 0.41);
      const played = t <= currentTime;
      const alpha = played ? 0.95 : 0.62;

      // Low band (Blue/Red studio core)
      const hLow = lVal * maxAmp;
      ctx.fillStyle = `rgba(239, 68, 68, ${alpha * 0.85})`;
      ctx.fillRect(px, midY - hLow, 1.5, hLow * 2);

      // Mid band (Emerald)
      const hMid = mVal * maxAmp * 0.86;
      ctx.fillStyle = `rgba(16, 185, 129, ${alpha * 0.8})`;
      ctx.fillRect(px, midY - hMid, 1.5, hMid * 2);

      // High band (Cyan crisp edge)
      const hHigh = hVal * maxAmp * 0.68;
      ctx.fillStyle = `rgba(56, 189, 248, ${alpha})`;
      ctx.fillRect(px, midY - hHigh, 1.5, hHigh * 2);
    }

    // 3. Beatgrid & Downbeat bar markers
    if (beatgrid) {
      const downbeatSet = new Set((beatgrid.downbeats_sec || []).map((d) => d.toFixed(2)));
      for (const b of beatgrid.beats_sec || []) {
        if (b < startSec || b > endSec) continue;
        const x = timeToX(b);
        const isDownbeat = downbeatSet.has(b.toFixed(2));
        ctx.strokeStyle = isDownbeat ? 'rgba(255,255,255,0.45)' : 'rgba(148,163,184,0.14)';
        ctx.lineWidth = isDownbeat ? 1.5 : 1;
        ctx.beginPath();
        ctx.moveTo(x, isDownbeat ? 14 : 20);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
    }

    // 4. Hot Cue Flags (A-H)
    for (const cue of hotCues) {
      if (cue.timeSec === null || cue.timeSec < startSec || cue.timeSec > endSec) continue;
      const cx = timeToX(cue.timeSec);
      ctx.strokeStyle = cue.color;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx, 12);
      ctx.lineTo(cx, height);
      ctx.stroke();

      ctx.fillStyle = cue.color;
      ctx.fillRect(cx - 6, height - 14, 13, 12);
      ctx.fillStyle = '#0B0D12';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(cue.slot, cx + 0.5, height - 5);
    }

    // 5. Playhead needle
    const playX = timeToX(currentTime);
    ctx.strokeStyle = accentColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(playX, 0);
    ctx.lineTo(playX, height);
    ctx.stroke();

    ctx.fillStyle = accentColor;
    ctx.beginPath();
    ctx.moveTo(playX - 5, 0);
    ctx.lineTo(playX + 5, 0);
    ctx.lineTo(playX, 7);
    ctx.closePath();
    ctx.fill();
  }, [waveform, currentTime, duration, sections, beatgrid, hotCues, zoom, accentColor]);

  const handlePointer = (clientX: number) => {
    const canvas = canvasRef.current;
    const effectiveDur = duration || waveform?.duration || 0;
    if (!canvas || effectiveDur <= 0) return;

    const rect = canvas.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const windowSec = effectiveDur / Math.max(1, zoom);
    const halfWin = windowSec / 2;
    let startSec = zoom <= 1 ? 0 : currentTime - halfWin;
    startSec = Math.max(0, Math.min(Math.max(0, effectiveDur - windowSec), startSec));
    const endSec = Math.min(effectiveDur, startSec + windowSec);
    onSeek(startSec + ratio * (endSec - startSec));
  };

  return (
    <canvas
      ref={canvasRef}
      width={720}
      height={96}
      onMouseDown={(e) => {
        draggingRef.current = true;
        handlePointer(e.clientX);
      }}
      onMouseMove={(e) => {
        if (draggingRef.current) handlePointer(e.clientX);
      }}
      onMouseUp={() => {
        draggingRef.current = false;
      }}
      onMouseLeave={() => {
        draggingRef.current = false;
      }}
      className="w-full h-[96px] rounded border border-[#1A202C] cursor-crosshair block bg-[#080A0E]"
    />
  );
};
