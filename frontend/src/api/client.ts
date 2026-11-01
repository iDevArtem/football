// frontend/src/api/client.ts

export const API_BASE = "";

export function getToken(): string | null {
  return localStorage.getItem("football_jwt");
}

export function setToken(token: string) {
  localStorage.setItem("football_jwt", token);
}

export function clearToken() {
  localStorage.removeItem("football_jwt");
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    clearToken();
  }

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(errorData.detail || `Request failed with status ${res.status}`);
  }

  return res.json();
}
