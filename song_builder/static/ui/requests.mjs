// Keep the exact request until its outcome is known; retries reuse its ID.
export class PendingRequests {
  constructor(storage, scope) { this.storage=storage; this.key=`song-builder:pending:${scope}`; }
  get() { const raw=this.storage.getItem(this.key); return raw ? JSON.parse(raw) : null; }
  begin(body) {
    if(this.get()) throw new Error('Resolve the previous music request before submitting another.');
    this.storage.setItem(this.key,JSON.stringify(body));
    return this.get();
  }
  resolve(requestId) { if(this.get()?.requestId===requestId)this.storage.removeItem(this.key); }
  observe(jobs) { const pending=this.get();if(pending&&jobs.some(job=>job.requestId===pending.requestId))this.resolve(pending.requestId); }
}
