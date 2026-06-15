import api, { authClient } from "./client";
import type { LoginRequest, TokenResponse, UserMeResponse } from "@/types/auth";

export async function loginApi(data: LoginRequest): Promise<TokenResponse> {
  const res = await authClient.post<TokenResponse>("/api/v1/auth/login", data);
  return res.data;
}

export async function getMeApi(): Promise<UserMeResponse> {
  const res = await api.get<UserMeResponse>("/api/v1/auth/me");
  return res.data;
}

export async function refreshApi(refresh_token: string): Promise<TokenResponse> {
  const res = await authClient.post<TokenResponse>("/api/v1/auth/refresh", {
    refresh_token,
  });
  return res.data;
}

export async function logoutApi(refresh_token: string): Promise<void> {
  await authClient.post("/api/v1/auth/logout", { refresh_token });
}
