/**
 * OmniPlaylist DJ Mode 2.0 — Real-Time AudioWorkletProcessor
 * Captura samples reais do stream reproduzido pelo player (128 samples/quantum)
 * e calcula RMS, Peak e detecção de clipping ao vivo sem simular dados.
 */
class DjAudioMeterProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._sumSq = 0.0;
        this._maxAbs = 0.0;
        this._clipCount = 0;
        this._sampleCount = 0;
        this._reportIntervalSamples = 1024; // ~43 fps a 44.1 kHz
    }

    process(inputs, outputs) {
        const input = inputs[0];
        const output = outputs[0];

        if (!input || input.length === 0) {
            return true;
        }

        const channels = input.length;
        const frameLength = input[0].length;

        for (let i = 0; i < frameLength; i++) {
            let monoSum = 0.0;
            for (let ch = 0; ch < channels; ch++) {
                const sample = input[ch][i] || 0.0;
                if (output && output[ch]) {
                    output[ch][i] = sample;
                }
                const absVal = Math.abs(sample);
                if (absVal > this._maxAbs) {
                    this._maxAbs = absVal;
                }
                if (absVal >= 0.999) {
                    this._clipCount += 1;
                }
                monoSum += sample;
            }
            const mono = monoSum / channels;
            this._sumSq += mono * mono;
            this._sampleCount += 1;
        }

        if (this._sampleCount >= this._reportIntervalSamples) {
            const rms = Math.sqrt(this._sumSq / this._sampleCount);
            const rmsDb = rms > 1e-6 ? 20.0 * Math.log10(rms) : -96.0;
            const peakDb = this._maxAbs > 1e-6 ? 20.0 * Math.log10(this._maxAbs) : -96.0;

            this.port.postMessage({
                rmsDb: Number(rmsDb.toFixed(2)),
                peakDb: Number(peakDb.toFixed(2)),
                clipping: this._clipCount > 0,
                clipCount: this._clipCount,
                sampleRate: sampleRate,
            });

            this._sumSq = 0.0;
            this._maxAbs = 0.0;
            this._clipCount = 0;
            this._sampleCount = 0;
        }

        return true;
    }
}

registerProcessor("dj-audio-meter-processor", DjAudioMeterProcessor);
