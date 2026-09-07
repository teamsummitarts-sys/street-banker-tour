/** Text-to-audio is separate from text-to-settings; never auto-replace a source. */
export function createSoundEffects({getRevision, loadAudio, prepareDownload}) {
  const $ = id => document.getElementById(id);
  let available = false, busy = false, sequence = 0, controller = null, candidate = null;
  const status = (text, error = false) => {
    $('sfx-status').textContent = text;
    $('sfx-status').setAttribute('role', error ? 'alert' : 'status');
  };
  const render = () => {
    $('generate-audio').disabled = !available || busy;
    $('cancel-audio-generation').hidden = !busy;
    $('load-generated-audio').hidden = !candidate;
    $('save-generated-audio').hidden = !candidate;
    $('load-generated-audio').disabled = busy;
    $('generate-audio').setAttribute('aria-busy', String(busy));
  };
  const cancel = () => {
    sequence++; controller?.abort(); controller = null; busy = false;
    status('Cancelled. Your current source is retained. A submitted request may still use ElevenLabs credits.');
    render();
  };
  $('cancel-audio-generation').addEventListener('click', cancel);
  $('generate-audio').addEventListener('click', async () => {
    if (!available || busy) return;
    const prompt = $('audio-prompt').value.trim();
    const seconds = Number($('audio-duration').value);
    if (!prompt || prompt.length > 500 || ![5,8,10].includes(seconds)) {
      status('Enter a description and choose 5, 8 or 10 seconds.', true); return;
    }
    const token = ++sequence;
    const scope = document.body.dataset.csrf;
    const abort = controller = new AbortController();
    const timer = setTimeout(() => abort.abort(), 125000);
    busy = true; render(); status('Generating audio with ElevenLabs. Your current source stays available.');
    try {
      const response = await fetch('/noise-lab/api/sound-effects', {
        method:'POST', credentials:'same-origin', cache:'no-store', signal:abort.signal,
        headers:{'Content-Type':'application/json','X-Noise-Lab-CSRF':scope},
        body:JSON.stringify({requestId:crypto.randomUUID(),prompt,seconds,loop:$('audio-loop').checked}),
      });
      if (token !== sequence || scope !== document.body.dataset.csrf) return;
      if (response.redirected || [401,403].includes(response.status)) throw new Error('Check your sign-in and ElevenLabs access, then reload.');
      if (!response.ok) {
        const result = await response.json();
        throw new Error(typeof result.message === 'string' && result.message.length < 300 ? result.message : 'Audio generation failed.');
      }
      if (!response.headers.get('Content-Type')?.startsWith('audio/mpeg')) throw new Error('Unsupported audio response.');
      const bytes = await response.arrayBuffer();
      if (token !== sequence || scope !== document.body.dataset.csrf) return;
      if (bytes.byteLength < 128 || bytes.byteLength > 2*1024*1024) throw new Error('Unsupported audio size.');
      candidate = bytes;
      status('Audio ready. Load it into the knobs, then press Play. Download the original to keep it.');
    } catch (error) {
      if (token === sequence) status(error?.name === 'AbortError'
        ? 'Generation timed out. No automatic retry was made; ElevenLabs may still count the request.'
        : error.message || 'Generation failed. Your current sound is retained.', true);
    } finally {
      clearTimeout(timer);
      if (token === sequence) { busy = false; controller = null; render(); }
    }
  });
  $('load-generated-audio').addEventListener('click', async () => {
    if (!candidate || busy) return;
    const token = sequence, revision = getRevision(), bytes = candidate;
    busy = true; render();
    try {
      await loadAudio(bytes.slice(0), () => token === sequence && revision === getRevision());
      if (token === sequence) status('Generated audio loaded. Press Play. Knobs and A/B compare effects on this source; Save patch stores settings only.');
    } catch {
      if (token === sequence) status('Audio could not be loaded, or newer edits took priority. Your previous source is retained.', true);
    } finally { if (token === sequence) {busy = false; render();} }
  });
  $('save-generated-audio').addEventListener('click', () => {
    if (candidate) prepareDownload(new Blob([candidate], {type:'audio/mpeg'}), 'noise-lab-original.mp3');
  });
  render();
  return {
    setAvailability(value, reason) {
      available = value === true;
      if (!available) { cancel(); candidate = null; status(reason === 'key_missing' ? 'Add the ElevenLabs key to V2 to enable audio generation.' : reason === 'storage_unavailable' ? 'Persistent storage is unavailable. Audio generation is paused.' : 'Audio generation is unavailable. Check the ElevenLabs configuration.'); }
      else if (!candidate && !busy) status('Create a new sound from text. Uses ElevenLabs credits.');
      render();
    },
    reset() { cancel(); candidate = null; $('audio-prompt').value = ''; render(); },
  };
}
