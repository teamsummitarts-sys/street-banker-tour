import test from 'node:test';
import assert from 'node:assert/strict';
import {sendUpload, previewWav} from '../../song_builder/static/ui/analysis-upload.mjs';

function wav(amplitude = 8192) {
  const frames = 8000, data = new ArrayBuffer(44 + frames * 2), v = new DataView(data);
  const word = (at, s) => [...s].forEach((c, i) => v.setUint8(at + i, c.charCodeAt(0)));
  word(0, 'RIFF'); v.setUint32(4, data.byteLength - 8, true); word(8, 'WAVE');
  word(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, 8000, true); v.setUint32(28, 16000, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); word(36, 'data');
  v.setUint32(40, frames * 2, true);
  for (let i = 0; i < frames; i++) v.setInt16(44 + i * 2, i % 2 ? amplitude : -amplitude, true);
  return new File([data], 'authorized.wav', {type: 'audio/wav'});
}

function transport() {
  return {upload: {}, sends: 0, headers: {}, status: 201, responseText: '{"track":{"id":"saved-1"}}',
    open(method, url) {this.method = method; this.url = url;},
    setRequestHeader(k, v) {this.headers[k] = v;},
    send(body) {this.sends++; this.body = body;},
    getResponseHeader() {return 'application/json';}};
}

test('100% transferred waits for server confirmation; progress is based on byte events', async () => {
  const xhr = transport(), progress = []; let ready = false;
  const result = sendUpload({url: '/upload', csrf: 'csrf-test', file: wav(), onProgress: n => progress.push(n), xhrFactory: () => xhr});
  result.then(() => ready = true);
  xhr.upload.onprogress({lengthComputable: true, loaded: 50, total: 100});
  xhr.upload.onload();
  await Promise.resolve();
  assert.equal(ready, false);
  assert.deepEqual(progress, [.5, 1]);
  assert.equal(xhr.headers['X-Song-Builder-CSRF'], 'csrf-test');
  assert.equal(xhr.withCredentials, true);
  assert.equal(xhr.body.get('authorized'), 'true');
  xhr.onload();
  assert.deepEqual(await result, {id: 'saved-1'});
  assert.equal(xhr.sends, 1);
});

test('interrupted or unconfirmed uploads never retry automatically', async () => {
  for (const fail of [xhr => xhr.onerror(), xhr => {xhr.responseText = '{}'; xhr.onload();}, xhr => {xhr.getResponseHeader = () => 'text/html'; xhr.onload();}]) {
    const xhr = transport();
    const result = sendUpload({url: '/upload', csrf: 'csrf-test', file: wav(), onProgress: () => {}, xhrFactory: () => xhr});
    const rejection = assert.rejects(result, /check your inbox/i);
    fail(xhr); await rejection;
    assert.equal(xhr.sends, 1);
  }
});

test('preview preserves sampled amplitude, silence and duration without invented waveform', async () => {
  const sample = await previewWav(wav());
  assert.equal(sample.duration, 1);
  assert.equal(sample.peaks.length, 120);
  assert.ok(sample.peaks.every(n => n === .25));
  assert.ok((await previewWav(wav(0))).peaks.every(n => n === 0));
  await assert.rejects(previewWav(new File(['bad'], 'broken.wav')), /readable WAV/);
  await assert.rejects(previewWav(new File(['bad'], 'wrong.mp3')), /16-bit WAV/);
  const truncated = new File([(await wav().arrayBuffer()).slice(0, 100)], 'incomplete.wav');
  await assert.rejects(previewWav(truncated), /incomplete/);
});
