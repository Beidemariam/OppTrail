import { vi } from "vitest";

/**
 * A stand-in for the browser's `EventSource`, for ADR 0003's stream
 * (milestone 3.4).
 *
 * jsdom implements no server-sent events at all, so without this
 * `lib/liveUpdates.ts` takes its `typeof EventSource === "undefined"` branch
 * and a test can only assert that nothing broke. This installs a fake the
 * hook opens for real, and hands the test the one thing worth driving: the
 * server's side of the connection.
 *
 * It is not a fake of the transport — no parsing, no reconnect timer, no
 * `retry` handling. Those are the browser's, and `e2e/20-live-updates.spec.ts`
 * is where a real one runs. What this fakes is the seam: a named event
 * arrives, and the app refetches.
 */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  private listeners = new Map<string, Set<() => void>>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  // Only the three methods `lib/liveUpdates.ts` actually calls. A fuller
  // imitation of `EventSource` would be code nothing exercises.
  addEventListener(type: string, listener: () => void) {
    const forType = this.listeners.get(type) ?? new Set();
    forType.add(listener);
    this.listeners.set(type, forType);
  }

  close() {
    this.closed = true;
  }

  /** The server pushing one named event down this connection. */
  emit(type: string) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener();
    }
  }
}

/**
 * Install the fake for one test and return the streams opened during it.
 *
 * Paired with `vi.unstubAllGlobals()` in the suite's `afterEach`, which every
 * test file here already calls.
 */
export function stubEventSource(): typeof FakeEventSource.instances {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  return FakeEventSource.instances;
}
