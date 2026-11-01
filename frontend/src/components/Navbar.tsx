// frontend/src/components/Navbar.tsx
import React, { useState } from "react";
import { useAuth } from "../hooks/useAuth";
import { LogIn, LogOut, Shield, User as UserIcon, Calendar, AppWindow } from "lucide-react";

interface NavbarProps {
  currentTab: "schedule" | "cabinet";
  onTabChange: (tab: "schedule" | "cabinet") => void;
}

export function Navbar({ currentTab, onTabChange }: NavbarProps) {
  const { user, loading, logout, loginWithWidget } = useAuth();
  const [showLoginModal, setShowLoginModal] = useState(false);

  const handleDemoLogin = (role: "player" | "admin") => {
    // For direct web testing if Telegram widget is blocked by browser/localhost
    const mockId = role === "admin" ? 99999999 : 12345678;
    loginWithWidget({
      id: mockId,
      first_name: role === "admin" ? "Организатор" : "Игрок Тест",
      username: role === "admin" ? "admin_demo" : "player_demo",
      auth_date: Math.floor(Date.now() / 1000),
      hash: "demo",
    }).catch(() => {
      // Demo fallback if backend strictly requires hash
    });
  };

  return (
    <header className="sticky top-0 z-50 bg-slate-900/90 backdrop-blur-md border-b border-slate-800">
      <div className="max-w-4xl mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center text-xl shadow-lg shadow-emerald-500/20">
            ⚽
          </div>
          <div>
            <h1 className="font-bold text-base leading-tight tracking-tight text-white flex items-center gap-1.5">
              Футбол 5х5
            </h1>
            <p className="text-xs text-slate-400">football.idev.wtf</p>
          </div>
        </div>

        {/* Tab switch */}
        <div className="flex items-center bg-slate-800/80 p-1 rounded-xl border border-slate-700/60 text-xs font-medium">
          <button
            onClick={() => onTabChange("schedule")}
            className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
              currentTab === "schedule"
                ? "bg-emerald-500 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Calendar className="w-3.5 h-3.5" />
            Афиша
          </button>
          <button
            onClick={() => onTabChange("cabinet")}
            className={`px-3 py-1.5 rounded-lg flex items-center gap-1.5 transition-all ${
              currentTab === "cabinet"
                ? "bg-emerald-500 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <AppWindow className="w-3.5 h-3.5" />
            Кабинет
          </button>
        </div>

        {/* User profile / Login */}
        <div>
          {loading ? (
            <div className="w-8 h-8 rounded-full border-2 border-emerald-500/20 border-t-emerald-500 animate-spin" />
          ) : user ? (
            <div className="flex items-center gap-2">
              <div className="text-right hidden sm:block">
                <p className="text-xs font-semibold text-slate-200 flex items-center justify-end gap-1">
                  {user.role === "admin" && <Shield className="w-3 h-3 text-emerald-400" />}
                  {user.first_name}
                </p>
                <p className="text-[10px] text-slate-400 uppercase tracking-wider">{user.role}</p>
              </div>
              <button
                onClick={logout}
                title="Выйти"
                className="p-2 rounded-xl bg-slate-800 text-slate-400 hover:text-red-400 hover:bg-slate-700/60 transition"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => onTabChange("cabinet")}
              className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 text-white text-xs font-semibold hover:brightness-110 active:scale-95 transition shadow-sm flex items-center gap-1.5"
            >
              <LogIn className="w-3.5 h-3.5" />
              Войти
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
