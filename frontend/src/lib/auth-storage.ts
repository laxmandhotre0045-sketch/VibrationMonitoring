const ACCESS_KEY = "sv_access_token";
const REFRESH_KEY = "sv_refresh_token";

export const authStorage = {
  setTokens(access: string, refresh: string) {
    sessionStorage.setItem(ACCESS_KEY, access);
    sessionStorage.setItem(REFRESH_KEY, refresh);
  },

  updateTokens(access: string, refresh: string) {
    sessionStorage.setItem(ACCESS_KEY, access);
    sessionStorage.setItem(REFRESH_KEY, refresh);
  },

  getAccessToken(): string | null {
    return sessionStorage.getItem(ACCESS_KEY);
  },

  getRefreshToken(): string | null {
    return sessionStorage.getItem(REFRESH_KEY);
  },

  hasTokens(): boolean {
    return !!(authStorage.getAccessToken() || authStorage.getRefreshToken());
  },

  clear() {
    sessionStorage.removeItem(ACCESS_KEY);
    sessionStorage.removeItem(REFRESH_KEY);
  },
};
