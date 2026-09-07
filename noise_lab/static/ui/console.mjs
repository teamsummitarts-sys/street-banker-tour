import {decibels} from '../engine/meter.mjs';

/** Finite, bounded presentation coordinates; not a change to the audio signal. */
export function meterPercent(peak) {
  return Math.max(0, Math.min(100, (decibels(peak) + 60) / 60 * 100));
}
export class PeakHold {
  peak = 0; until = 0;
  update(peak, now, active) {
    if (!active || !Number.isFinite(peak) || peak < 0) { this.peak = 0; this.until = 0; }
    else if (peak >= this.peak || now >= this.until) { this.peak = peak; this.until = now + 1200; }
    return this.peak;
  }
}
export function createConsoleUI() {
  const $ = id => document.getElementById(id);
  let lastPaint = -Infinity;
  const holds = Object.fromEntries(['input', 'output'].map(side => [side, [new PeakHold(), new PeakHold()]]));
  const view = mode => {
    document.body.dataset.view = mode;
    $('view-studio').setAttribute('aria-pressed', String(mode === 'studio'));
    $('view-club').setAttribute('aria-pressed', String(mode === 'club'));
    // Collapsing a native details element keeps setup available in Club view.
    $('prompt-details').open = mode === 'studio';
  };
  $('view-studio').addEventListener('click', () => view('studio'));
  $('view-club').addEventListener('click', () => view('club'));
  $('display-brightness').addEventListener('change', () => {
    const value = $('display-brightness').value;
    document.body.dataset.display = ['dim', 'bright'].includes(value) ? value : 'standard';
  });
  const phone = window.matchMedia?.('(max-width: 600px)');
  const drawer = $('library-drawer');
  let modalActive = false;
  // One library DOM and one set of handlers across desktop and mobile.
  const syncDrawer = () => {
    if (!drawer?.showModal) return;
    if (modalActive) {
      modalActive = false;
      drawer.close();
    }
    // Attribute-only desktop visibility avoids stealing focus on page load.
    drawer.open = !phone.matches;
  };
  if (phone && drawer?.showModal) {
    syncDrawer();
    phone.addEventListener('change', syncDrawer);
    if (phone.matches) $('prompt-details').open = false;
    $('close-library').addEventListener('click', () => drawer.close());
    drawer.addEventListener('close', () => {
      if (modalActive && phone.matches) $('open-library').focus({preventScroll: true});
      modalActive = false;
    });
  }
  const reveal = id => {
    if (phone?.matches && drawer?.showModal && !drawer.open) {
      drawer.showModal();
      modalActive = true;
    }
    $(id).scrollIntoView({behavior: 'instant', block: 'start'});
    $(id).focus({preventScroll: true});
  };
  $('open-library').addEventListener('click', () => reveal('patch-library'));
  $('open-export').addEventListener('click', () => reveal('output'));
  return {
    render(engine, force = false) {
      const now = performance.now();
      const active = Boolean(engine?.getInfo().playing) && !document.hidden;
      if (active && !force && now - lastPaint < 33) return;
      lastPaint = now;
      const levels = active ? engine.getLevels() : null;
      $('meter-state').textContent = active ? 'Monitoring' : 'Stopped';
      for (const side of ['input', 'output']) {
        const values = levels?.[side] || [0, 0];
        let peak = 0; let invalid = false;
        for (let index = 0; index < 2; index++) {
          const value = values[index];
          const valid = Number.isFinite(value) && value >= 0;
          invalid ||= !valid;
          peak = Math.max(peak, valid ? value : 0);
          const id = `${side}-${index ? 'r' : 'l'}`;
          const percent = meterPercent(valid ? value : 0);
          $(id + '-fill').style.clipPath = `inset(0 ${100 - percent}% 0 0)`;
          const held = holds[side][index].update(value, now, active);
          $(id + '-hold').hidden = held === 0;
          $(id + '-hold').style.left = `${Math.min(99, meterPercent(held))}%`;
          const db = decibels(value);
          $(id + '-meter').setAttribute('aria-valuenow', String(Number.isFinite(db) ? Math.max(-60, Math.min(0, db)).toFixed(1) : -60));
          $(id + '-meter').setAttribute('aria-valuetext', !active ? 'Stopped' : !valid ? 'Unavailable' : value === 0 ? 'Silence' : `${db.toFixed(1)} dBFS sample peak`);
        }
        $(side + '-reading').textContent = !active || invalid ? '—' : peak > 0 ? decibels(peak).toFixed(1) : '−∞';
        $(side + '-warning').hidden = !active || invalid || peak < 10 ** (-1 / 20);
      }
    },
  };
}
