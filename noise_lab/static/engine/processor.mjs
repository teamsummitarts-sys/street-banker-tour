import {NoiseDSP} from './dsp.mjs';

/** The module URL is owned by the application, never supplied by a recipe/model. */
class StreetBankerNoiseProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.recipe = options.processorOptions.recipe;
    this.bypass = Boolean(options.processorOptions.bypass);
    this.dsp = new NoiseDSP(sampleRate, this.recipe, this.bypass);
    this.reportedFault = false;
    this.port.onmessage = ({data}) => {
      try {
        if (data.type === 'recipe') {
          this.dsp.setRecipe(data.recipe); this.recipe = this.dsp.recipe;
        } else if (data.type === 'bypass') {
          this.dsp.setBypass(data.value); this.bypass = data.value;
        } else if (data.type === 'reset') {
          this.dsp = new NoiseDSP(sampleRate, this.recipe, this.bypass);
          this.reportedFault = false;
        } else if (data.type === 'dispose') {
          this.dsp.fault(); this.disposed = true;
        }
      } catch {
        this.port.postMessage({type: 'rejected', message: 'Invalid audio settings were rejected; the working patch was retained.'});
      }
    };
  }

  process(inputs, outputs) {
    try {
      if (this.disposed) return false;
      this.dsp.processBlock(inputs[0] || [], outputs[0]);
      if (this.dsp.faulted && !this.reportedFault) {
        this.reportedFault = true;
        this.port.postMessage({type: 'fault', message: 'Playback stopped because the audio processor received an invalid signal. Reload the lab to reset safely.'});
      }
    } catch {
      for (const output of outputs[0] || []) output.fill(0);
      this.dsp.fault();
      if (!this.reportedFault) {
        this.reportedFault = true;
        this.port.postMessage({type: 'fault', message: 'The audio processor stopped safely. Reload the lab before continuing.'});
      }
    }
    return true;
  }
}
registerProcessor('street-banker-noise-lab-v1', StreetBankerNoiseProcessor);
