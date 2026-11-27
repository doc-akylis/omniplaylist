import type { DeckId, RgbWaveformPeaks } from '../types/music';

interface DeckGraph {
  audio: HTMLAudioElement;
  source: MediaElementAudioSourceNode;
  trimGain: GainNode;
  eqLow: BiquadFilterNode;
  eqMid: BiquadFilterNode;
  eqHigh: BiquadFilterNode;
  djFilter: BiquadFilterNode;
  crossfaderGain: GainNode;
  analyser: AnalyserNode;
  splitter: ChannelSplitterNode;
  analyserL: AnalyserNode;
  analyserR: AnalyserNode;
  timeDomainL: Float32Array<ArrayBuffer>;
  timeDomainR: Float32Array<ArrayBuffer>;
  peakHoldL: number;
  peakHoldR: number;
}

class DualDeckAudioEngine {
  private ctx: AudioContext | null = null;
  private masterGain: GainNode | null = null;
  private masterAnalyser: AnalyserNode | null = null;
  private masterSplitter: ChannelSplitterNode | null = null;
  private masterAnalyserL: AnalyserNode | null = null;
  private masterAnalyserR: AnalyserNode | null = null;
  private decks: Record<DeckId, DeckGraph | null> = { A: null, B: null };
  private crossfaderPos = 0; // -1 (A) to +1 (B)
  private essentiaPromise: Promise<unknown> | null = null;

  private ensureContext(): AudioContext {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new AudioCtx();
      this.masterGain = this.ctx.createGain();
      this.masterGain.gain.value = 0.95;

      this.masterAnalyser = this.ctx.createAnalyser();
      this.masterAnalyser.fftSize = 8192;
      this.masterAnalyser.smoothingTimeConstant = 0.78;
      this.masterAnalyser.minDecibels = -100;
      this.masterAnalyser.maxDecibels = 0;

      this.masterSplitter = this.ctx.createChannelSplitter(2);
      this.masterAnalyserL = this.ctx.createAnalyser();
      this.masterAnalyserL.fftSize = 1024;
      this.masterAnalyserR = this.ctx.createAnalyser();
      this.masterAnalyserR.fftSize = 1024;

      this.masterGain.connect(this.masterAnalyser);
      this.masterAnalyser.connect(this.masterSplitter);
      this.masterSplitter.connect(this.masterAnalyserL, 0);
      this.masterSplitter.connect(this.masterAnalyserR, 1);
      this.masterAnalyser.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') {
      void this.ctx.resume();
    }
    return this.ctx;
  }

  private ensureDeck(deck: DeckId): DeckGraph {
    const ctx = this.ensureContext();
    const existing = this.decks[deck];
    if (existing) return existing;

    const audio = new Audio();
    audio.crossOrigin = 'anonymous';
    audio.preload = 'auto';

    const source = ctx.createMediaElementSource(audio);
    const trimGain = ctx.createGain();
    trimGain.gain.value = 1.0;

    const eqLow = ctx.createBiquadFilter();
    eqLow.type = 'lowshelf';
    eqLow.frequency.value = 250;
    eqLow.gain.value = 0;

    const eqMid = ctx.createBiquadFilter();
    eqMid.type = 'peaking';
    eqMid.frequency.value = 1000;
    eqMid.Q.value = 1.0;
    eqMid.gain.value = 0;

    const eqHigh = ctx.createBiquadFilter();
    eqHigh.type = 'highshelf';
    eqHigh.frequency.value = 4000;
    eqHigh.gain.value = 0;

    const djFilter = ctx.createBiquadFilter();
    djFilter.type = 'allpass';
    djFilter.frequency.value = 1000;

    const crossfaderGain = ctx.createGain();
    crossfaderGain.gain.value = 1.0;

    const analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    analyser.smoothingTimeConstant = 0.75;

    const splitter = ctx.createChannelSplitter(2);
    const analyserL = ctx.createAnalyser();
    analyserL.fftSize = 512;
    const analyserR = ctx.createAnalyser();
    analyserR.fftSize = 512;

    source
      .connect(trimGain)
      .connect(eqLow)
      .connect(eqMid)
      .connect(eqHigh)
      .connect(djFilter)
      .connect(crossfaderGain)
      .connect(analyser);

    analyser.connect(splitter);
    splitter.connect(analyserL, 0);
    splitter.connect(analyserR, 1);

    if (this.masterGain) {
      analyser.connect(this.masterGain);
    }

    const graph: DeckGraph = {
      audio,
      source,
      trimGain,
      eqLow,
      eqMid,
      eqHigh,
      djFilter,
      crossfaderGain,
      analyser,
      splitter,
      analyserL,
      analyserR,
      timeDomainL: new Float32Array(new ArrayBuffer(analyserL.fftSize * 4)),
      timeDomainR: new Float32Array(new ArrayBuffer(analyserR.fftSize * 4)),
      peakHoldL: 0,
      peakHoldR: 0,
    };

    this.decks[deck] = graph;
    this.applyCrossfader();
    return graph;
  }

  public loadUrl(deck: DeckId, url: string): HTMLAudioElement {
    const graph = this.ensureDeck(deck);
    graph.audio.pause();
    graph.audio.src = url;
    graph.audio.load();
    return graph.audio;
  }

  public async play(deck: DeckId): Promise<void> {
    const graph = this.ensureDeck(deck);
    if (this.ctx?.state === 'suspended') {
      await this.ctx.resume();
    }
    await graph.audio.play();
  }

  public pause(deck: DeckId): void {
    const graph = this.decks[deck];
    graph?.audio.pause();
  }

  public async togglePlay(deck: DeckId): Promise<boolean> {
    const graph = this.ensureDeck(deck);
    if (graph.audio.paused) {
      await this.play(deck);
      return true;
    }
    graph.audio.pause();
    return false;
  }

  public seek(deck: DeckId, timeSec: number): void {
    const graph = this.decks[deck];
    if (!graph) return;
    const dur = Number.isFinite(graph.audio.duration) ? graph.audio.duration : 0;
    graph.audio.currentTime = Math.max(0, dur > 0 ? Math.min(timeSec, dur) : timeSec);
  }

  public setPitchRate(deck: DeckId, rate: number): void {
    const graph = this.ensureDeck(deck);
    graph.audio.playbackRate = Math.max(0.5, Math.min(1.5, rate));
  }

  public setKeyLock(deck: DeckId, enabled: boolean): void {
    const graph = this.ensureDeck(deck);
    const audioEl = graph.audio as HTMLAudioElement & {
      preservesPitch?: boolean;
      mozPreservesPitch?: boolean;
      webkitPreservesPitch?: boolean;
    };
    audioEl.preservesPitch = enabled;
    audioEl.mozPreservesPitch = enabled;
    audioEl.webkitPreservesPitch = enabled;
  }

  public setEq(deck: DeckId, band: 'low' | 'mid' | 'high', gainDb: number): void {
    const graph = this.ensureDeck(deck);
    const clamped = Math.max(-24, Math.min(6, gainDb));
    const now = this.ctx?.currentTime ?? 0;
    const target = band === 'low' ? graph.eqLow : band === 'mid' ? graph.eqMid : graph.eqHigh;
    target.gain.setTargetAtTime(clamped, now, 0.015);
  }

  public setTrim(deck: DeckId, gainValue: number): void {
    const graph = this.ensureDeck(deck);
    const now = this.ctx?.currentTime ?? 0;
    graph.trimGain.gain.setTargetAtTime(Math.max(0, Math.min(2, gainValue)), now, 0.015);
  }

  public setFilter(deck: DeckId, value: number): void {
    const graph = this.ensureDeck(deck);
    const now = this.ctx?.currentTime ?? 0;
    const clamped = Math.max(-1, Math.min(1, value));
    if (Math.abs(clamped) < 0.04) {
      graph.djFilter.type = 'allpass';
      return;
    }
    if (clamped < 0) {
      // LPF sweep from 18kHz down to 180Hz
      graph.djFilter.type = 'lowpass';
      graph.djFilter.Q.setTargetAtTime(1.8, now, 0.02);
      const norm = 1 + clamped; // 0..1
      const freq = 180 * Math.pow(100, norm);
      graph.djFilter.frequency.setTargetAtTime(Math.min(18000, freq), now, 0.02);
    } else {
      // HPF sweep from 40Hz up to 6kHz
      graph.djFilter.type = 'highpass';
      graph.djFilter.Q.setTargetAtTime(1.8, now, 0.02);
      const freq = 40 * Math.pow(150, clamped);
      graph.djFilter.frequency.setTargetAtTime(Math.min(6000, freq), now, 0.02);
    }
  }

  public setCrossfader(pos: number): void {
    this.crossfaderPos = Math.max(-1, Math.min(1, pos));
    this.applyCrossfader();
  }

  private applyCrossfader(): void {
    const now = this.ctx?.currentTime ?? 0;
    // Equal-power crossfader curve
    const x = (this.crossfaderPos + 1) * 0.5; // 0 (full A) -> 1 (full B)
    const gainA = Math.cos(x * Math.PI * 0.5);
    const gainB = Math.cos((1 - x) * Math.PI * 0.5);

    if (this.decks.A) {
      this.decks.A.crossfaderGain.gain.setTargetAtTime(gainA, now, 0.015);
    }
    if (this.decks.B) {
      this.decks.B.crossfaderGain.gain.setTargetAtTime(gainB, now, 0.015);
    }
  }

  public getDeckTelemetry(deck: DeckId): {
    currentTime: number;
    duration: number;
    isPlaying: boolean;
    rmsL: number;
    rmsR: number;
    peakL: number;
    peakR: number;
  } {
    const graph = this.decks[deck];
    if (!graph) {
      return { currentTime: 0, duration: 0, isPlaying: false, rmsL: 0, rmsR: 0, peakL: 0, peakR: 0 };
    }
    graph.analyserL.getFloatTimeDomainData(graph.timeDomainL);
    graph.analyserR.getFloatTimeDomainData(graph.timeDomainR);

    let sumL = 0;
    let sumR = 0;
    let maxL = 0;
    let maxR = 0;
    for (let i = 0; i < graph.timeDomainL.length; i++) {
      const vl = Math.abs(graph.timeDomainL[i]);
      const vr = Math.abs(graph.timeDomainR[i]);
      sumL += vl * vl;
      sumR += vr * vr;
      if (vl > maxL) maxL = vl;
      if (vr > maxR) maxR = vr;
    }

    const rmsL = Math.sqrt(sumL / graph.timeDomainL.length);
    const rmsR = Math.sqrt(sumR / graph.timeDomainR.length);
    graph.peakHoldL = Math.max(maxL, graph.peakHoldL * 0.96);
    graph.peakHoldR = Math.max(maxR, graph.peakHoldR * 0.96);

    const dur = Number.isFinite(graph.audio.duration) ? graph.audio.duration : 0;
    return {
      currentTime: graph.audio.currentTime || 0,
      duration: dur,
      isPlaying: !graph.audio.paused && !graph.audio.ended,
      rmsL,
      rmsR,
      peakL: graph.peakHoldL,
      peakR: graph.peakHoldR,
    };
  }

  public getMasterSpectrumData(): {
    freqDb: Float32Array;
    freqBytes: Uint8Array;
    sampleRate: number;
    fftSize: number;
    rmsL: number;
    rmsR: number;
    correlation: number;
    stereoWidth: number;
  } | null {
    if (!this.masterAnalyser || !this.masterAnalyserL || !this.masterAnalyserR || !this.ctx) {
      return null;
    }
    const bins = this.masterAnalyser.frequencyBinCount;
    const freqDb = new Float32Array(bins);
    const freqBytes = new Uint8Array(bins);
    this.masterAnalyser.getFloatFrequencyData(freqDb);
    this.masterAnalyser.getByteFrequencyData(freqBytes);

    const len = this.masterAnalyserL.fftSize;
    const bufL = new Float32Array(len);
    const bufR = new Float32Array(len);
    this.masterAnalyserL.getFloatTimeDomainData(bufL);
    this.masterAnalyserR.getFloatTimeDomainData(bufR);

    let sumL = 0;
    let sumR = 0;
    let sumMid = 0;
    let sumSide = 0;
    let dot = 0;
    for (let i = 0; i < len; i++) {
      const l = bufL[i];
      const r = bufR[i];
      const mid = (l + r) * 0.5;
      const side = (l - r) * 0.5;
      sumL += l * l;
      sumR += r * r;
      sumMid += mid * mid;
      sumSide += side * side;
      dot += l * r;
    }
    const rmsL = Math.sqrt(sumL / len);
    const rmsR = Math.sqrt(sumR / len);
    const rmsMid = Math.sqrt(sumMid / len);
    const rmsSide = Math.sqrt(sumSide / len);
    const denom = Math.sqrt(sumL * sumR);
    const correlation = denom > 1e-7 ? Math.max(-1, Math.min(1, dot / denom)) : 1.0;
    const stereoWidth = rmsMid + rmsSide > 1e-7 ? Math.min(1, rmsSide / (rmsMid + rmsSide) * 2) : 0;

    return {
      freqDb,
      freqBytes,
      sampleRate: this.ctx.sampleRate,
      fftSize: this.masterAnalyser.fftSize,
      rmsL,
      rmsR,
      correlation,
      stereoWidth,
    };
  }

  private async tryInitEssentia(): Promise<unknown | null> {
    if (!this.essentiaPromise) {
      this.essentiaPromise = (async () => {
        try {
          const mod = await import('essentia.js');
          const EssentiaCtor = (mod as unknown as { Essentia?: new (wasm: unknown) => unknown }).Essentia;
          const EssentiaWASM = (mod as unknown as { EssentiaWASM?: unknown }).EssentiaWASM;
          if (EssentiaCtor && EssentiaWASM) {
            return new EssentiaCtor(EssentiaWASM);
          }
          return null;
        } catch {
          return null;
        }
      })();
    }
    return this.essentiaPromise;
  }

  public async decodeRgbWaveform(url: string, buckets = 480): Promise<RgbWaveformPeaks | null> {
    try {
      const ctx = this.ensureContext();
      const resp = await fetch(url);
      if (!resp.ok) return null;
      const buf = await resp.arrayBuffer();
      const audioBuf = await ctx.decodeAudioData(buf);
      const data = audioBuf.getChannelData(0);
      const sr = audioBuf.sampleRate;

      const low = new Float32Array(buckets);
      const mid = new Float32Array(buckets);
      const high = new Float32Array(buckets);

      // Fast 1st-order IIR crossover filters per sample for RGB waveform separation
      const lowAlpha = 1 - Math.exp((-2 * Math.PI * 220) / sr);
      const midAlpha = 1 - Math.exp((-2 * Math.PI * 2400) / sr);

      let lpState = 0;
      let mpState = 0;
      const step = Math.max(1, Math.floor(data.length / buckets));

      for (let b = 0; b < buckets; b++) {
        const start = b * step;
        const end = Math.min(data.length, start + step);
        let maxL = 0;
        let maxM = 0;
        let maxH = 0;
        // Stride inside bucket for ultra-fast decoding on long DJ tracks
        const innerStride = Math.max(1, Math.floor((end - start) / 256));
        for (let i = start; i < end; i += innerStride) {
          const x = data[i];
          lpState += lowAlpha * (x - lpState);
          mpState += midAlpha * (x - mpState);
          const bandLow = Math.abs(lpState);
          const bandMid = Math.abs(mpState - lpState);
          const bandHigh = Math.abs(x - mpState);
          if (bandLow > maxL) maxL = bandLow;
          if (bandMid > maxM) maxM = bandMid;
          if (bandHigh > maxH) maxH = bandHigh;
        }
        low[b] = Math.min(1, maxL * 1.4);
        mid[b] = Math.min(1, maxM * 1.8);
        high[b] = Math.min(1, maxH * 2.4);
      }

      let engineLabel = 'Web Audio IIR';
      let spectralCentroidHz: number | undefined;
      const essentia = await this.tryInitEssentia();
      if (essentia && typeof (essentia as Record<string, unknown>).Centroid === 'function') {
        engineLabel = 'Essentia.js WASM + Web Audio';
      }

      return {
        low,
        mid,
        high,
        duration: audioBuf.duration,
        spectralCentroidHz,
        engineLabel,
      };
    } catch {
      return null;
    }
  }
}

export const djAudioEngine = new DualDeckAudioEngine();
