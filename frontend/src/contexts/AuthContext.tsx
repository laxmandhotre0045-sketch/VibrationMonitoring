import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import { getMeApi, loginApi, logoutApi, refreshApi } from "@/api/auth";
import { authStorage } from "@/lib/auth-storage";
import { authLog } from "@/lib/auth-debug";
import { hasAnyRole } from "@/lib/role-access";
import { useToast } from "@/components/ui/Toast";
import type { UserMeResponse } from "@/types/auth";

interface AuthContextValue {
  user: UserMeResponse | null;
  roles: string[];
  plants: string[];
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<UserMeResponse>;
  logout: () => Promise<void>;
  refreshSession: () => Promise<void>;
  hasRole: (role: string | readonly string[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function applyMe(
  me: UserMeResponse,
  setters: {
    setUser: (u: UserMeResponse) => void;
    setRoles: (r: string[]) => void;
    setPlants: (p: string[]) => void;
    setAccessToken: (t: string | null) => void;
    setRefreshToken: (t: string | null) => void;
    setIsAuthenticated: (v: boolean) => void;
  }
) {
  setters.setUser(me);
  setters.setRoles(me.roles);
  setters.setPlants(me.plants);
  setters.setAccessToken(authStorage.getAccessToken());
  setters.setRefreshToken(authStorage.getRefreshToken());
  setters.setIsAuthenticated(true);
}

function clearSession(setters: {
  setUser: (u: UserMeResponse | null) => void;
  setRoles: (r: string[]) => void;
  setPlants: (p: string[]) => void;
  setAccessToken: (t: string | null) => void;
  setRefreshToken: (t: string | null) => void;
  setIsAuthenticated: (v: boolean) => void;
}) {
  authStorage.clear();
  setters.setUser(null);
  setters.setRoles([]);
  setters.setPlants([]);
  setters.setAccessToken(null);
  setters.setRefreshToken(null);
  setters.setIsAuthenticated(false);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserMeResponse | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [plants, setPlants] = useState<string[]>([]);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState<string | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const navigate = useNavigate();
  const { showToast } = useToast();

  const setters = useMemo(
    () => ({
      setUser,
      setRoles,
      setPlants,
      setAccessToken,
      setRefreshToken,
      setIsAuthenticated,
    }),
    []
  );

  const hasRole = useCallback(
    (role: string | readonly string[]) => {
      const required = Array.isArray(role) ? role : [role];
      return hasAnyRole(roles, required);
    },
    [roles]
  );

  const refreshSession = useCallback(async () => {
    const token = authStorage.getRefreshToken();
    if (!token) throw new Error("No refresh token");

    const tokens = await refreshApi(token);
    authStorage.updateTokens(tokens.access_token, tokens.refresh_token);
    const me = await getMeApi();
    applyMe(me, setters);
    authLog("Session refreshed", me.email);
  }, [setters]);

  const login = useCallback(
    async (email: string, password: string): Promise<UserMeResponse> => {
      const tokens = await loginApi({ email, password });
      authStorage.setTokens(tokens.access_token, tokens.refresh_token);
      const me = await getMeApi();
      applyMe(me, setters);
      authLog("Login success", me.email);
      return me;
    },
    [setters]
  );

  const logout = useCallback(async () => {
    const token = authStorage.getRefreshToken();
    try {
      if (token) await logoutApi(token);
    } catch {
      // Best-effort logout
    }
    clearSession(setters);
    authLog("Logout");
    navigate("/login", { replace: true });
  }, [navigate, setters]);

  useEffect(() => {
    async function bootstrap() {
      if (!authStorage.hasTokens()) {
        setIsLoading(false);
        return;
      }

      authLog("Auth initialization from sessionStorage");

      try {
        const me = await getMeApi();
        applyMe(me, setters);
        authLog("Auth initialization success", me.email);
      } catch {
        const refresh = authStorage.getRefreshToken();
        if (refresh) {
          try {
            await refreshSession();
            authLog("Auth initialization via refresh success");
          } catch {
            clearSession(setters);
            authLog("Auth initialization failed — cleared storage");
          }
        } else {
          clearSession(setters);
          authLog("Auth initialization failed — no refresh token");
        }
      } finally {
        setIsLoading(false);
      }
    }

    bootstrap();
  }, [refreshSession, setters]);

  useEffect(() => {
    const handler = () => {
      clearSession(setters);
      showToast("Session expired", "error");
      navigate("/login", { replace: true });
    };
    window.addEventListener("auth:session-expired", handler);
    return () => window.removeEventListener("auth:session-expired", handler);
  }, [navigate, setters, showToast]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      roles,
      plants,
      accessToken,
      refreshToken,
      isAuthenticated,
      isLoading,
      login,
      logout,
      refreshSession,
      hasRole,
    }),
    [
      user,
      roles,
      plants,
      accessToken,
      refreshToken,
      isAuthenticated,
      isLoading,
      login,
      logout,
      refreshSession,
      hasRole,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
