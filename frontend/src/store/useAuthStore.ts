import { create } from "zustand";

/**
 * In-memory auth token store.
 *
 * The backend uses role-based bearer-token authentication (see backend/app/api/auth.py):
 *   - viewer    → GET routes + WebSocket (public when VIEWER_AUTH_TOKEN is unset)
 *   - commander → operational control: start/pause, approve, isolate, override, fairness, ...
 *   - admin     → destructive/test tooling: reset, step, event injection
 *
 * In dev mode (ENV=dev, the default), if no separate ADMIN_AUTH_TOKEN is set,
 * the COMMANDER_AUTH_TOKEN acts as admin too. Viewer routes are public by default.
 *
 * The token is kept strictly in memory — never persisted to localStorage or cookies.
 */
export interface AuthStoreState {
  /** The bearer token (COMMANDER_AUTH_TOKEN or ADMIN_AUTH_TOKEN value). */
  token: string;
  /** Whether the token has been set by the user. */
  isAuthenticated: boolean;
  /** Set the auth token. */
  setToken: (token: string) => void;
  /** Clear the auth token. */
  clearToken: () => void;
}

export const useAuthStore = create<AuthStoreState>((set) => ({
  token: "",
  isAuthenticated: false,
  setToken: (token: string) =>
    set({ token, isAuthenticated: token.trim().length > 0 }),
  clearToken: () => set({ token: "", isAuthenticated: false }),
}));
