/**
 * OmniPlaylist DJ Mode 2.0 — Real-Time Web Audio Engine
 * Conecta o <audio> real do player via AudioWorklet + AnalyserNode (FFT 4096)
 * e renderiza Waveform+Beatgrid+Seções, Espectro 6 Bandas, Espectrograma e Peak/RMS.
 */
(function (global) {
    "use strict";

    const SIX_BANDS = [
        { key: "sub_bass", label: "Subgrave", range: "20–60 Hz", minHz: 20, maxHz: 60, color: "#22c55e" },
        { key: "bass", label: "Grave", range: "60–250 Hz", minHz: 60, maxHz: 250, color: "#10b981" },
        { key: "low_mid", label: "Médio-grave", range: "250–500 Hz", minHz: 250, maxHz: 500, color: "#06b6d4" },
        { key: "mid", label: "Médio", range: "500 Hz–2 kHz", minHz: 500, maxHz: 2000, color: "#3b82f6" },
        { key: "high_mid", label: "Médio-agudo", range: "2–6 kHz", minHz: 2000, maxHz: 6000, color: "#a855f7" },
        { key: "high", label: "Agudo", range: "6–20 kHz", minHz: 6000, maxHz: 20000, color: "#ec4899" },
    ];

    const SECTION_COLORS = {
        intro: "rgba(59, 130, 246, 0.22)",
        verse: "rgba(16, 185, 129, 0.18)",
        chorus: "rgba(234, 179, 8, 0.24)",
        breakdown: "rgba(168, 85, 247, 0.22)",
        outro: "rgba(107, 114, 128, 0.22)",
    };

    function computeSixBandLevels(freqBytes, sampleRate, fftSize) {
        if (!freqBytes || !sampleRate || !fftSize) {
            return SIX_BANDS.map((b) => ({ ...b, level: 0 }));
        }
        const binHz = sampleRate / fftSize;
        const maxBin = freqBytes.length - 1;

        return SIX_BANDS.map((band) => {
            const startBin = Math.max(1, Math.floor(band.minHz / binHz));
            const endBin = Math.min(maxBin, Math.ceil(band.maxHz / binHz));
            let sum = 0;
            let count = 0;
            for (let i = startBin; i <= endBin; i++) {
                sum += freqBytes[i];
                count += 1;
            }
            const level = count > 0 ? sum / (count * 255.0) : 0.0;
            return { ...band, level: Math.min(1.0, Math.max(0.0, level)) };
        });
    }

    function formatTime(sec) {
        if (!isFinite(sec) || sec < 0) return "00:00";
        const m = Math.floor(sec / 60);
        const s = Math.floor(sec % 60);
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    const state = {
        profile: null,
        beatgrid: { beats_sec: [], downbeats_sec: [] },
        sections: [],
        rmsDb: -96.0,
        peakDb: -96.0,
        clipping: false,
        liveClipCount: 0,
        rafId: null,
        freqData: null,
        timeData: null,
        waveformBound: false,
    };

    async function ensureAudioGraph() {
        const audioEl = document.querySelector("audio");
        if (!audioEl) return null;

        if (!audioEl.getAttribute("crossorigin")) {
            audioEl.setAttribute("crossorigin", "anonymous");
        }

        if (!global.__omniAudioGraph) {
            const AudioCtx = global.AudioContext || global.webkitAudioContext;
            if (!AudioCtx) return null;

            const ctx = new AudioCtx();
            const source = ctx.createMediaElementSource(audioEl);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 4096;
            analyser.smoothingTimeConstant = 0.75;

            let workletNode = null;
            if (ctx.audioWorklet) {
                try {
                    await ctx.audioWorklet.addModule("/static/js/dj_audio_worklet.js");
                    workletNode = new AudioWorkletNode(ctx, "dj-audio-meter-processor");
                    workletNode.port.onmessage = (event) => {
                        const d = event.data;
                        state.rmsDb = d.rmsDb;
                        state.peakDb = d.peakDb;
                        state.clipping = d.clipping;
                        if (d.clipping) {
                            state.liveClipCount += d.clipCount || 1;
                        }
                    };
                    source.connect(workletNode);
                    workletNode.connect(analyser);
                } catch (err) {
                    console.warn("[OmniDJ] AudioWorklet fallback to AnalyserNode:", err);
                    source.connect(analyser);
                }
            } else {
                source.connect(analyser);
            }

            analyser.connect(ctx.destination);
            global.__omniAudioGraph = { ctx, audioEl, source, analyser, workletNode };
        }

        const graph = global.__omniAudioGraph;
        if (graph.ctx.state === "suspended" && !audioEl.paused) {
            graph.ctx.resume().catch(() => {});
        }
        if (!state.freqData || state.freqData.length !== graph.analyser.frequencyBinCount) {
            state.freqData = new Uint8Array(graph.analyser.frequencyBinCount);
            state.timeData = new Uint8Array(graph.analyser.fftSize);
        }
        return graph;
    }

    function setTrackProfile(profile) {
        state.profile = profile || null;
        state.liveClipCount = 0;

        try {
            state.beatgrid = profile && profile.beatgrid_json
                ? JSON.parse(profile.beatgrid_json)
                : { beats_sec: [], downbeats_sec: [] };
        } catch (_) {
            state.beatgrid = { beats_sec: [], downbeats_sec: [] };
        }

        try {
            state.sections = profile && profile.sections_json
                ? JSON.parse(profile.sections_json)
                : [];
        } catch (_) {
            state.sections = [];
        }
    }

    function bindWaveformSeek() {
        const wfCanvas = document.getElementById("dj-waveform-canvas");
        if (!wfCanvas || state.waveformBound) return;
        state.waveformBound = true;
        wfCanvas.addEventListener("click", (evt) => {
            const audioEl = document.querySelector("audio");
            if (!audioEl || !isFinite(audioEl.duration) || audioEl.duration <= 0) return;
            const rect = wfCanvas.getBoundingClientRect();
            const ratio = Math.min(1, Math.max(0, (evt.clientX - rect.left) / rect.width));
            audioEl.currentTime = ratio * audioEl.duration;
        });
    }

    function drawWaveform(audioEl) {
        const canvas = document.getElementById("dj-waveform-canvas");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const w = canvas.width;
        const h = canvas.height;
        ctx.clearRect(0, 0, w, h);

        ctx.fillStyle = "#111317";
        ctx.fillRect(0, 0, w, h);

        const dur = audioEl && isFinite(audioEl.duration) && audioEl.duration > 0
            ? audioEl.duration
            : (state.profile && state.profile.duration_ms ? state.profile.duration_ms / 1000 : 0);
        const cur = audioEl ? audioEl.currentTime || 0 : 0;

        // 1. Sections background bands
        if (dur > 0 && state.sections.length > 0) {
            for (const sec of state.sections) {
                const x1 = (sec.start_sec / dur) * w;
                const x2 = (sec.end_sec / dur) * w;
                ctx.fillStyle = SECTION_COLORS[sec.label] || "rgba(255,255,255,0.08)";
                ctx.fillRect(x1, 0, Math.max(1, x2 - x1), h);
                ctx.fillStyle = "#9ca3af";
                ctx.font = "10px sans-serif";
                if (x2 - x1 > 34) {
                    ctx.fillText(sec.label.toUpperCase(), x1 + 4, 12);
                }
            }
        }

        // 2. Beatgrid & 4/4 Downbeats
        if (dur > 0 && state.beatgrid && Array.isArray(state.beatgrid.beats_sec)) {
            const downSet = new Set((state.beatgrid.downbeats_sec || []).map((t) => t.toFixed(2)));
            for (const bt of state.beatgrid.beats_sec) {
                const x = (bt / dur) * w;
                const isDown = downSet.has(bt.toFixed(2));
                ctx.strokeStyle = isDown ? "rgba(29, 185, 84, 0.55)" : "rgba(255, 255, 255, 0.12)";
                ctx.lineWidth = isDown ? 1.5 : 1;
                ctx.beginPath();
                ctx.moveTo(x, 16);
                ctx.lineTo(x, h);
                ctx.stroke();
            }
        }

        // 3. Real-time oscilloscope trace from AnalyserNode
        if (state.timeData && state.timeData.length > 0) {
            ctx.strokeStyle = "#1DB954";
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            const step = Math.max(1, Math.floor(state.timeData.length / w));
            for (let x = 0; x < w; x++) {
                const v = (state.timeData[x * step] - 128) / 128.0;
                const y = h / 2 + v * (h * 0.35);
                if (x === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        // 4. Playhead cursor
        if (dur > 0) {
            const px = Math.min(w, Math.max(0, (cur / dur) * w));
            ctx.fillStyle = "rgba(29, 185, 84, 0.12)";
            ctx.fillRect(0, 0, px, h);
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(px, 0);
            ctx.lineTo(px, h);
            ctx.stroke();
        }

        // Update time & current section labels
        const timeEl = document.getElementById("dj-time-display");
        if (timeEl) {
            const rem = dur > cur ? dur - cur : 0;
            timeEl.textContent = `${formatTime(cur)} / -${formatTime(rem)}`;
        }
        const secEl = document.getElementById("dj-current-section");
        if (secEl && state.sections.length > 0) {
            const active = state.sections.find((s) => cur >= s.start_sec && cur <= s.end_sec);
            secEl.textContent = active ? active.label.toUpperCase() : "—";
        }
    }

    function drawSpectrumAndSpectrogram(bands) {
        // Spectrum 6-band bar + curve
        const specCanvas = document.getElementById("dj-spectrum-canvas");
        if (specCanvas) {
            const ctx = specCanvas.getContext("2d");
            const w = specCanvas.width;
            const h = specCanvas.height;
            ctx.clearRect(0, 0, w, h);
            ctx.fillStyle = "#111317";
            ctx.fillRect(0, 0, w, h);

            const barW = w / bands.length;
            bands.forEach((b, idx) => {
                const barH = b.level * (h - 24);
                const x = idx * barW + 8;
                const bw = Math.max(12, barW - 16);
                ctx.fillStyle = b.color;
                ctx.fillRect(x, h - 18 - barH, bw, barH);
                ctx.fillStyle = "#d1d5db";
                ctx.font = "10px sans-serif";
                ctx.fillText(b.label, x, h - 4);
            });
        }

        // Spectrogram waterfall (scrolling left)
        const sgCanvas = document.getElementById("dj-spectrogram-canvas");
        if (sgCanvas && state.freqData) {
            const ctx = sgCanvas.getContext("2d");
            const w = sgCanvas.width;
            const h = sgCanvas.height;
            const prev = ctx.getImageData(1, 0, w - 1, h);
            ctx.putImageData(prev, 0, 0);

            for (let y = 0; y < h; y++) {
                const normY = 1.0 - y / h;
                const bin = Math.min(
                    state.freqData.length - 1,
                    Math.floor(Math.pow(normY, 2.0) * (state.freqData.length * 0.65))
                );
                const val = state.freqData[bin];
                const hue = 240 - (val / 255.0) * 200;
                const light = Math.max(8, (val / 255.0) * 60);
                ctx.fillStyle = `hsl(${hue}, 90%, ${light}%)`;
                ctx.fillRect(w - 1, y, 1, 1);
            }
        }

        // Update 6-band DOM meters
        bands.forEach((b) => {
            const bar = document.getElementById(`dj-band-bar-${b.key}`);
            const val = document.getElementById(`dj-band-val-${b.key}`);
            const pct = Math.round(b.level * 100);
            if (bar) bar.style.width = `${pct}%`;
            if (val) val.textContent = `${pct}%`;
        });
    }

    function updateMetersAndPulse(audioEl) {
        const rmsBar = document.getElementById("dj-rms-bar");
        const peakBar = document.getElementById("dj-peak-bar");
        const rmsVal = document.getElementById("dj-rms-val");
        const peakVal = document.getElementById("dj-peak-val");
        const clipEl = document.getElementById("dj-clip-indicator");

        const rmsPct = Math.min(100, Math.max(0, ((state.rmsDb + 60) / 60) * 100));
        const peakPct = Math.min(100, Math.max(0, ((state.peakDb + 60) / 60) * 100));

        if (rmsBar) rmsBar.style.width = `${rmsPct}%`;
        if (peakBar) peakBar.style.width = `${peakPct}%`;
        if (rmsVal) rmsVal.textContent = `${state.rmsDb.toFixed(1)} dBFS`;
        if (peakVal) peakVal.textContent = `${state.peakDb.toFixed(1)} dBFS`;
        if (clipEl) {
            clipEl.textContent = state.liveClipCount > 0 ? `CLIP (${state.liveClipCount})` : "SEM CLIPPING";
            clipEl.style.color = state.liveClipCount > 0 ? "#ef4444" : "#22c55e";
        }

        // Beat sync pulse indicator
        const pulseEl = document.getElementById("dj-beat-pulse");
        if (pulseEl && audioEl && !audioEl.paused && state.beatgrid && Array.isArray(state.beatgrid.beats_sec)) {
            const cur = audioEl.currentTime || 0;
            const nearBeat = state.beatgrid.beats_sec.some((bt) => Math.abs(bt - cur) < 0.06);
            pulseEl.style.opacity = nearBeat ? "1.0" : "0.25";
            pulseEl.style.transform = nearBeat ? "scale(1.25)" : "scale(1.0)";
        }
    }

    function tick() {
        const graph = global.__omniAudioGraph;
        const audioEl = document.querySelector("audio");

        if (graph && state.freqData) {
            graph.analyser.getByteFrequencyData(state.freqData);
            graph.analyser.getByteTimeDomainData(state.timeData);
            const bands = computeSixBandLevels(state.freqData, graph.ctx.sampleRate, graph.analyser.fftSize);
            drawSpectrumAndSpectrogram(bands);
        }

        drawWaveform(audioEl);
        updateMetersAndPulse(audioEl);

        state.rafId = global.requestAnimationFrame(tick);
    }

    function start() {
        bindWaveformSeek();
        ensureAudioGraph();
        if (!state.rafId) {
            state.rafId = global.requestAnimationFrame(tick);
        }
    }

    function stop() {
        if (state.rafId) {
            global.cancelAnimationFrame(state.rafId);
            state.rafId = null;
        }
    }

    global.addEventListener("play", () => ensureAudioGraph(), true);

    global.OmniDjRealtime = {
        SIX_BANDS,
        computeSixBandLevels,
        setTrackProfile,
        start,
        stop,
        ensureAudioGraph,
    };
})(window);
