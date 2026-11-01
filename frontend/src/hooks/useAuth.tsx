// frontend/src/hooks/useAuth.tsx
import React, { createContext, useContext, useState, useEffect } from "react";
import { apiRequest, setToken, clearToken, getToken } from "../api/client";
import { useTelegram } from "./useTelegram";

export interface User {
  telegram_id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  role: "player" | "admin";
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAdmin: boolean;
  loginWithWidget: (data: any) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const { isTma, initData, hapticNotification } = useTelegram();

  const refreshUser = async () => {
    try {
      const userData = await apiRequest<User>("/api/auth/me");
      setUser(userData);
    } catch (e) {
      setUser(null);
      clearToken();
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const initAuth = async () => {
      // 1. If in Telegram Mini App and initData present, auto authenticate!
      if (isTma && initData) {
        try {
          const res = await apiRequest<{ access_token: string; user: User }>("/api/auth/tma", {
            method: "POST",
            body: JSON.stringify({ init_data: initData }),
          });
          setToken(res.access_token);
          setUser(res.user);
          setLoading(false);
          return;
        } catch (err) {
          console.error("TMA auth failed", err);
        }
      }

      // 2. If token in localStorage, verify with /api/auth/me
      if (getToken()) {
        await refreshUser();
      } else {
        setLoading(false);
      }
    };

    initAuth();
  }, [isTma, initData]);

  const loginWithWidget = async (data: any) => {
    setLoading(true);
    try {
      const res = await apiRequest<{ access_token: string; user: User }>("/api/auth/widget", {
        method: "POST",
        body: JSON.stringify(data),
      });
      setToken(res.access_token);
      setUser(res.user);
      hapticNotification("success");
    } catch (err) {
      hapticNotification("error");
      throw err;
    } finally {
      setLoading(false);
    }
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAdmin: user?.role === "admin",
        loginWithWidget,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
