// Stable anonymous painter id, persisted in localStorage, so the backend's
// Adaptive Painter Profile can accumulate critique history across sessions
// without any login. Browser-only: call from event handlers, never during
// render (SSR has no localStorage and it would desync hydration).
const KEY = "painter_user_id";

export function painterUserId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    let id = window.localStorage.getItem(KEY);
    if (!id) {
      id = crypto.randomUUID();
      window.localStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    return null; // private mode / storage denied — profile simply stays off
  }
}

/**
 * Append the painter id to a project-scoped API url.
 *
 * The backend returns only this painter's projects, and 404s anyone else's, so
 * several people can share one instance without seeing each other's paintings
 * or critiques. This is separation, not authentication — the lock on the door
 * is Cloudflare Access in front of the tunnel (docs/SHARING.md).
 *
 * Omitting the id would ask for the unscoped view, so callers must use this
 * rather than building the url by hand.
 */
export function withUserId(url: string): string {
  const id = painterUserId();
  if (!id) return url;
  return `${url}${url.includes("?") ? "&" : "?"}user_id=${encodeURIComponent(id)}`;
}
