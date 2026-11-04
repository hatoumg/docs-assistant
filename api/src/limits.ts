/**
 * Counts events per key inside a sliding time window, in memory.
 * Used to slow down password guessing and to stop one user running up the model bill.
 * It resets when the API restarts, and it is per process: fine for one server, not for several.
 */
export class RateLimiter {
  private readonly events = new Map<string, number[]>();

  constructor(
    private readonly max: number,
    private readonly windowMs: number,
    private readonly now: () => number = Date.now,
  ) {}

  private recent(key: string): number[] {
    const cutoff = this.now() - this.windowMs;
    const kept = (this.events.get(key) ?? []).filter((time) => time > cutoff);
    if (kept.length) this.events.set(key, kept);
    else this.events.delete(key);
    return kept;
  }

  /** True when the key has already used up its allowance. */
  isBlocked(key: string): boolean {
    return this.recent(key).length >= this.max;
  }

  record(key: string): void {
    const kept = this.recent(key);
    kept.push(this.now());
    this.events.set(key, kept);
    if (this.events.size > 10_000) for (const other of [...this.events.keys()]) this.recent(other);
  }

  /** Record one use, unless the allowance is spent. Returns whether it was allowed. */
  take(key: string): boolean {
    if (this.isBlocked(key)) return false;
    this.record(key);
    return true;
  }

  reset(key: string): void {
    this.events.delete(key);
  }
}
