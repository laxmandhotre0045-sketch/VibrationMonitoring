const ACCESS_KEY = "sv_access_token";
const REFRESH_KEY = "sv_refresh_token";

/**
 * The two tokens are deliberately kept in different stores.
 *
 * The access token is short-lived (30 minutes) and is replayable for as long as
 * it lives, so it stays in sessionStorage: the browser drops it when the tab
 * closes and it is never written to disk.
 *
 * The refresh token is what makes a session survive, and the backend issues it
 * with a seven-day lifetime (`jwt_refresh_expire_days`). Keeping it in
 * sessionStorage threw all seven of those days away at the first tab close --
 * the bootstrap below would find nothing, and the user was sent back to the
 * login page every time they opened the dashboard in a new tab or reopened the
 * browser. It lives in localStorage so the lifetime the backend grants is the
 * lifetime the user actually gets.
 *
 * A stored refresh token is not a standing grant: it is single-use, revoked by
 * the server the moment it is exchanged, and cleared here on logout.
 */
export const authStorage = {
  setTokens(access: string, refresh: string) {
    sessionStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },

  updateTokens(access: string, refresh: string) {
    authStorage.setTokens(access, refresh);
  },

  getAccessToken(): string | null {
    return sessionStorage.getItem(ACCESS_KEY);
  },

  getRefreshToken(): string | null {
    // Sessions created before the refresh token moved stores still have it in
    // sessionStorage. Read it there once and promote it, so an open session is
    // not signed out by the upgrade itself.
    const stored = localStorage.getItem(REFRESH_KEY);
    if (stored) return stored;

    const legacy = sessionStorage.getItem(REFRESH_KEY);
    if (legacy) {
      localStorage.setItem(REFRESH_KEY, legacy);
      sessionStorage.removeItem(REFRESH_KEY);
      return legacy;
    }
    return null;
  },

  hasTokens(): boolean {
    return !!(authStorage.getAccessToken() || authStorage.getRefreshToken());
  },

  clear() {
    sessionStorage.removeItem(ACCESS_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};
