import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { authStorage } from "@/lib/auth-storage";
import { authLog } from "@/lib/auth-debug";
import type { TokenResponse } from "@/types/auth";

/**
 * An explicitly empty VITE_API_BASE_URL means "same origin": nginx proxies
 * /api/ to the backend, so the page and the API share a scheme and host. That
 * is what lets the dashboard work over HTTPS — a secure page may not call an
 * http:// API — and it removes the CORS preflight at the same time.
 *
 * Compared with `??`, a plain `||` would treat that empty string as unset and
 * fall back to the absolute localhost URL, which is exactly the value we are
 * trying to override.
 */
const configuredBase = import.meta.env.VITE_API_BASE_URL;
const baseURL = configuredBase === undefined ? "http://localhost:8000" : configuredBase;

const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

/** Bare client for auth endpoints — no interceptors to prevent refresh loops */
export const authClient = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

const AUTH_SKIP = ["/auth/login", "/auth/logout", "/auth/refresh"];

function shouldSkipRefresh(url?: string): boolean {
  return AUTH_SKIP.some((segment) => url?.includes(segment));
}

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null = null) {
  failedQueue.forEach((promise) => {
    if (error) {
      promise.reject(error);
    } else {
      promise.resolve(token!);
    }
  });
  failedQueue = [];
}

export function emitSessionExpired() {
  window.dispatchEvent(new CustomEvent("auth:session-expired"));
}

async function performRefresh(): Promise<string> {
  const refreshToken = authStorage.getRefreshToken();
  if (!refreshToken) {
    throw new Error("No refresh token");
  }

  const res = await authClient.post<TokenResponse>("/api/v1/auth/refresh", {
    refresh_token: refreshToken,
  });

  const { access_token, refresh_token } = res.data;
  authStorage.updateTokens(access_token, refresh_token);
  authLog("Refresh success");
  return access_token;
}

api.interceptors.request.use((config) => {
  const token = authStorage.getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryConfig | undefined;

    if (
      !originalRequest ||
      error.response?.status !== 401 ||
      originalRequest._retry ||
      shouldSkipRefresh(originalRequest.url)
    ) {
      return Promise.reject(error);
    }

    if (isRefreshing) {
      return new Promise<string>((resolve, reject) => {
        failedQueue.push({ resolve, reject });
      }).then((token) => {
        originalRequest.headers.Authorization = `Bearer ${token}`;
        return api(originalRequest);
      });
    }

    originalRequest._retry = true;
    isRefreshing = true;

    try {
      const newToken = await performRefresh();
      processQueue(null, newToken);
      originalRequest.headers.Authorization = `Bearer ${newToken}`;
      return api(originalRequest);
    } catch (refreshError) {
      processQueue(refreshError, null);
      authLog("Refresh failure", refreshError);
      authStorage.clear();
      emitSessionExpired();
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  }
);

export default api;
