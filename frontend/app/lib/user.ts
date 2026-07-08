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
