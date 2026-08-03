/**
 * 登录鉴权接口客户端
 * 封装 /api/auth/login（登录拿 token）与 /api/auth/me（校验当前用户）。
 */
import { getToken, setToken } from "./auth";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ?? "";

export type CurrentUser = {
  id: number;
  username: string;
  email: string | null;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
};

export async function login(username: string, password: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.detail ?? `登录失败：HTTP ${response.status}`);
  }

  const result = (await response.json()) as LoginResponse;
  setToken(result.access_token);
}

export async function fetchMe(): Promise<CurrentUser> {
  const token = getToken();
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    throw new Error(`获取用户信息失败：HTTP ${response.status}`);
  }
  return response.json();
}
