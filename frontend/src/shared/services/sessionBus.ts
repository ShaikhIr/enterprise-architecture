/**
 * Cross-tab session synchronization.
 *
 * All tabs of the same browser share one HttpOnly refresh cookie, so they
 * represent a single browser session. This bus keeps the in-memory auth state
 * of every open tab consistent:
 *   - When one tab logs in (or a different user logs in), other tabs re-bootstrap
 *     from the shared cookie and converge on the same identity.
 *   - When one tab logs out, all other tabs clear their session immediately.
 *
 * Uses BroadcastChannel where available, with a localStorage-event fallback for
 * older browsers.
 */

export type SessionEvent = { type: 'login' } | { type: 'logout' };

type Listener = (event: SessionEvent) => void;

const CHANNEL_NAME = 'auth-session';
const FALLBACK_KEY = '__auth_session_event__';

const listeners = new Set<Listener>();

let channel: BroadcastChannel | null = null;

if (typeof BroadcastChannel !== 'undefined') {
  channel = new BroadcastChannel(CHANNEL_NAME);
  channel.onmessage = (e: MessageEvent<SessionEvent>) => {
    if (e.data && typeof e.data.type === 'string') {
      listeners.forEach((l) => l(e.data));
    }
  };
} else if (typeof window !== 'undefined') {
  // Fallback: use the storage event, which fires in *other* tabs only.
  window.addEventListener('storage', (e) => {
    if (e.key === FALLBACK_KEY && e.newValue) {
      try {
        const event = JSON.parse(e.newValue) as SessionEvent;
        listeners.forEach((l) => l(event));
      } catch {
        /* ignore malformed payloads */
      }
    }
  });
}

function post(event: SessionEvent): void {
  if (channel) {
    channel.postMessage(event);
  } else if (typeof window !== 'undefined') {
    // Write a unique payload so repeated identical events still fire.
    localStorage.setItem(FALLBACK_KEY, JSON.stringify({ ...event, _ts: Date.now() }));
  }
}

export const sessionBus = {
  /** Notify other tabs that this tab has authenticated (or switched user). */
  broadcastLogin: (): void => post({ type: 'login' }),

  /** Notify other tabs that this tab has logged out / session ended. */
  broadcastLogout: (): void => post({ type: 'logout' }),

  /** Subscribe to session events coming from OTHER tabs. Returns an unsubscribe fn. */
  subscribe: (listener: Listener): (() => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
