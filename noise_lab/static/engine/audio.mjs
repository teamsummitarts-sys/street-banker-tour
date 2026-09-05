export const MAX_FILE_BYTES = 20 * 1024 * 1024;
export const MAX_DECODED_BYTES = 64 * 1024 * 1024;
export const MAX_DURATION = 30;
export const LOOPS = Object.freeze([
  Object.freeze({id: 'harmonic-pluck', name: 'Harmonic pluck · synthetic', description: 'Original eight-second clean, procedurally synthesized pluck sequence. No recorded guitar or third-party sample.'}),
  Object.freeze({id: 'pulse-bass', name: 'Pulse bass · synthetic', description: 'Original eight-second clean, procedurally synthesized bass sequence. No recording or third-party sample.'}),
]);

const fourCC = (view, offset) => String.fromCharCode(...new Uint8Array(view.buffer, view.byteOffset + offset, 4));

/** Strict uncompressed RIFF/WAVE parser: no browser codec/decoder is invoked. */
export function inspectWav(arrayBuffer) {
  if (!(arrayBuffer instanceof ArrayBuffer) || arrayBuffer.byteLength < 44 || arrayBuffer.byteLength > MAX_FILE_BYTES) {
    throw new RangeError('Choose an uncompressed WAV file no larger than 20 MiB.');
  }
  const view = new DataView(arrayBuffer);
  if (fourCC(view, 0) !== 'RIFF' || fourCC(view, 8) !== 'WAVE' || view.getUint32(4, true) + 8 !== view.byteLength) {
    throw new TypeError('This file is not a supported RIFF WAV. Compressed audio, RF64, and other formats are not supported yet.');
  }
  let format; let data;
  let position = 12;
  while (position + 8 <= view.byteLength) {
    const tag = fourCC(view, position);
    const length = view.getUint32(position + 4, true);
    const start = position + 8;
    const end = start + length;
    if (end > view.byteLength) throw new RangeError('The WAV file contains a truncated chunk.');
    if (tag === 'fmt ') {
      if (format || length < 16) throw new TypeError('The WAV format header is invalid.');
      format = {
        encoding: view.getUint16(start, true), channels: view.getUint16(start + 2, true),
        sampleRate: view.getUint32(start + 4, true), byteRate: view.getUint32(start + 8, true),
        blockAlign: view.getUint16(start + 12, true), bits: view.getUint16(start + 14, true),
      };
    }
    if (tag === 'data') {
      if (data) throw new TypeError('Multiple WAV data chunks are not supported.');
      data = {offset: start, length};
    }
    position = end + (length % 2);
  }
  if (position !== view.byteLength || !format || !data || data.length === 0) throw new TypeError('The WAV file is incomplete or empty.');
  const {encoding, channels, sampleRate, bits, byteRate, blockAlign} = format;
  if (![1, 2].includes(channels) || sampleRate < 8000 || sampleRate > 192000 ||
      !((encoding === 1 && [16, 24, 32].includes(bits)) || (encoding === 3 && bits === 32))) {
    throw new TypeError('Use a mono/stereo WAV at 8–192 kHz: PCM 16/24/32-bit or IEEE float 32-bit. WAV extensible and compressed codecs are not supported yet.');
  }
  if (blockAlign !== channels * bits / 8 || byteRate !== sampleRate * blockAlign || data.length % blockAlign !== 0) {
    throw new TypeError('The WAV sample layout is inconsistent.');
  }
  const frames = data.length / blockAlign;
  const duration = frames / sampleRate;
  if (duration > MAX_DURATION || frames * channels * 4 > MAX_DECODED_BYTES) {
    throw new RangeError('Choose a loop of 30 seconds or less; decoded audio must fit within 64 MiB.');
  }
  return {...format, ...data, frames, duration};
}

export function decodeWav(arrayBuffer, targetRate) {
  const info = inspectWav(arrayBuffer);
  if (!Number.isInteger(targetRate) || targetRate < 8000 || targetRate > 192000) throw new RangeError('Unsupported playback sample rate.');
  const frames = Math.max(1, Math.round(info.duration * targetRate));
  if (frames * info.channels * 4 > MAX_DECODED_BYTES) throw new RangeError('Resampled audio exceeds the 64 MiB limit.');
  const view = new DataView(arrayBuffer);
  const bytes = info.bits / 8;
  const read = (frame, channel) => {
    const offset = info.offset + Math.min(info.frames - 1, frame) * info.blockAlign + channel * bytes;
    let value;
    if (info.encoding === 3) value = view.getFloat32(offset, true);
    else if (info.bits === 16) value = view.getInt16(offset, true) / 32768;
    else if (info.bits === 32) value = view.getInt32(offset, true) / 2147483648;
    else {
      let number = view.getUint8(offset) | view.getUint8(offset + 1) << 8 | view.getUint8(offset + 2) << 16;
      if (number & 0x800000) number -= 0x1000000;
      value = number / 8388608;
    }
    if (!Number.isFinite(value)) throw new TypeError('The WAV contains nonfinite samples; the previous source has been retained.');
    return Math.max(-1, Math.min(1, value));
  };
  // Check every stored float sample, including samples skipped by downsampling.
  if (info.encoding === 3) for (let frame = 0; frame < info.frames; frame++) {
    for (let channel = 0; channel < info.channels; channel++) read(frame, channel);
  }
  const channels = Array.from({length: info.channels}, () => new Float32Array(frames));
  // Deliberately simple linear resampling for this validation prototype; not archival SRC.
  for (let i = 0; i < frames; i++) {
    const position = i * info.sampleRate / targetRate;
    const lower = Math.floor(position); const fraction = position - lower;
    for (let ch = 0; ch < info.channels; ch++) {
      channels[ch][i] = read(lower, ch) * (1 - fraction) + read(lower + 1, ch) * fraction;
    }
  }
  applyLoopEdges(channels, targetRate);
  return {channels, sampleRate: targetRate, duration: frames / targetRate};
}

/** Five-ms edge fades avoid abrupt imported-loop seams; the source file is unchanged. */
export function applyLoopEdges(channels, sampleRate) {
  const frames = channels[0].length;
  const edge = Math.min(Math.ceil(sampleRate * 0.005), Math.floor(frames / 2));
  for (const samples of channels) {
    for (let i = 0; i < edge; i++) {
      const gain = 0.5 - 0.5 * Math.cos(Math.PI * i / edge);
      samples[i] *= gain; samples[frames - 1 - i] *= gain;
    }
    samples[0] = 0; samples[frames - 1] = 0;
  }
}

export function createDemo(loopId, sampleRate) {
  const definition = LOOPS.find(loop => loop.id === loopId);
  if (!definition) throw new RangeError('Unknown demonstration loop.');
  if (!Number.isInteger(sampleRate) || sampleRate < 8000 || sampleRate > 192000) throw new RangeError('Unsupported sample rate.');
  const duration = 8; const frames = duration * sampleRate;
  const samples = new Float32Array(frames);
  const notes = loopId === 'harmonic-pluck' ? [164.8138, 195.9977, 246.9417, 220, 164.8138, 293.6648, 246.9417, 195.9977] :
    [82.4069, 82.4069, 110, 98, 82.4069, 123.4708, 110, 98];
  for (let i = 0; i < frames; i++) {
    const t = i / sampleRate;
    const note = Math.floor(t); const local = t - note;
    const frequency = notes[note];
    const attack = Math.min(1, local / 0.009);
    const release = Math.min(1, (1 - local) / 0.06);
    const envelope = attack * release * Math.exp(-local * (loopId === 'harmonic-pluck' ? 4.8 : 2.8));
    let voice = 0;
    const harmonics = loopId === 'harmonic-pluck' ? 5 : 3;
    for (let harmonic = 1; harmonic <= harmonics; harmonic++) {
      if (frequency * harmonic < sampleRate * 0.45) voice += Math.sin(2 * Math.PI * frequency * harmonic * local) /
        (harmonic * harmonic) * Math.exp(-local * (harmonic - 1) * 2);
    }
    samples[i] = voice * envelope * 0.44;
  }
  const channels = [samples]; applyLoopEdges(channels, sampleRate);
  return {channels, sampleRate, duration, name: definition.name};
}

/** Interleaved little-endian PCM16 WAV; no metadata, original path, or prompt is embedded. */
export function encodeWav(channels, sampleRate) {
  if (![1, 2].includes(channels.length) || !channels[0]?.length ||
      channels.some(channel => channel.length !== channels[0].length)) throw new TypeError('Invalid render channels.');
  const frames = channels[0].length;
  const output = new ArrayBuffer(44 + frames * channels.length * 2);
  const view = new DataView(output);
  const writeText = (offset, text) => [...text].forEach((char, index) => view.setUint8(offset + index, char.charCodeAt(0)));
  writeText(0, 'RIFF'); view.setUint32(4, output.byteLength - 8, true); writeText(8, 'WAVE');
  writeText(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, channels.length, true); view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * channels.length * 2, true); view.setUint16(32, channels.length * 2, true);
  view.setUint16(34, 16, true); writeText(36, 'data'); view.setUint32(40, output.byteLength - 44, true);
  let offset = 44;
  for (let i = 0; i < frames; i++) for (const samples of channels) {
    if (!Number.isFinite(samples[i])) throw new TypeError('Invalid output sample; export was cancelled.');
    // Truncation towards zero ensures PCM quantization cannot exceed the input peak.
    view.setInt16(offset, Math.trunc(Math.max(-1, Math.min(1, samples[i])) * 32767), true); offset += 2;
  }
  return output;
}
