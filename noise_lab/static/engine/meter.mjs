/** Passive sampled-level display. No routing to speakers, DSP, uploads or storage.
 * Analyser time-domain data: https://www.w3.org/TR/webaudio/#AnalyserNode
 * This is a sampled visual aid, not continuous true-peak or calibrated loudness.
 */
export function samplePeak(samples) {
  let peak = 0;
  for (let i = 0; i < samples.length; i++) {
    if (!Number.isFinite(samples[i])) return null;
    peak = Math.max(peak, Math.abs(samples[i]));
  }
  return peak;
}
export function decibels(peak) {
  return Number.isFinite(peak) && peak > 0 ? 20 * Math.log10(peak) : -Infinity;
}
export class StereoMeter {
  constructor(context) {
    // Match the worklet's explicit stereo/speakers upmix for mono sources.
    this.input = context.createGain();
    this.input.gain.value = 1;
    this.input.channelCount = 2;
    this.input.channelCountMode = 'explicit';
    this.input.channelInterpretation = 'speakers';
    this.splitter = context.createChannelSplitter(2);
    this.input.connect(this.splitter);
    // At least 50 ms of recent PCM, sampled by the visible UI at most 30 Hz.
    const size = Math.min(16384, Math.max(2048, 2 ** Math.ceil(Math.log2(context.sampleRate / 20))));
    this.channels = [0, 1].map(index => {
      const analyser = context.createAnalyser();
      analyser.fftSize = size;
      this.splitter.connect(analyser, index);
      // The analyser's output is deliberately unconnected (per Web Audio spec).
      return {analyser, samples: new Float32Array(size)};
    });
  }
  read() {
    return this.channels.map(({analyser, samples}) => {
      analyser.getFloatTimeDomainData(samples);
      return samplePeak(samples);
    });
  }
  dispose() {
    this.input.disconnect(); this.splitter.disconnect();
    for (const {analyser} of this.channels) analyser.disconnect();
  }
}
