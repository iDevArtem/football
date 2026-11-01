// frontend/src/App.tsx
import React, { useState, useEffect } from "react";
import { AuthProvider } from "./hooks/useAuth";
import { useTelegram } from "./hooks/useTelegram";
import { Navbar } from "./components/Navbar";
import { PublicSchedule } from "./pages/PublicSchedule";
import { CabinetPage } from "./pages/CabinetPage";

function AppContent() {
  const { isTma } = useTelegram();
  const [currentTab, setCurrentTab] = useState<"schedule" | "cabinet">("schedule");
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);

  useEffect(() => {
    // If inside Telegram Mini App or path is /app, open cabinet directly!
    const path = window.location.pathname;
    if (isTma || path.startsWith("/app")) {
      setCurrentTab("cabinet");
    }

    const handlePopState = () => {
      if (window.location.pathname.startsWith("/app")) {
        setCurrentTab("cabinet");
      } else {
        setCurrentTab("schedule");
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [isTma]);

  const handleTabChange = (tab: "schedule" | "cabinet") => {
    setCurrentTab(tab);
    const newPath = tab === "cabinet" ? "/app" : "/";
    if (window.location.pathname !== newPath) {
      window.history.pushState({}, "", newPath);
    }
  };

  const handleGoToCabinet = (gameId?: string) => {
    if (gameId) {
      setSelectedGameId(gameId);
    }
    handleTabChange("cabinet");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <Navbar currentTab={currentTab} onTabChange={handleTabChange} />

      <main className="flex-1 pb-16">
        {currentTab === "schedule" ? (
          <PublicSchedule onGoToCabinet={handleGoToCabinet} />
        ) : (
          <CabinetPage initialGameId={selectedGameId} />
        )}
      </main>

      <footer className="py-6 border-t border-slate-900 text-center text-xs text-slate-500">
        <p>⚽ football.idev.wtf • Football Telegram Bot & Mini App</p>
      </footer>
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;
