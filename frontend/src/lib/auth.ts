/**
 * 登录态存储
 * JWT token 存 localStorage，刷新页面不丢失登录状态。
 */

const TOKEN_KEY = "datasprite_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}
