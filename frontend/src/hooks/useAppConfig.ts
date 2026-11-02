import { useState, useEffect } from "react";
import { apiRequest } from "../api/client";

interface AppConfig {
  bot_username: string;
  webapp_url: string;
}

const DEFAULT_CONFIG: AppConfig = {
  bot_username: (import.meta as any).env?.VITE_BOT_USERNAME || "PlayGame_robot",
  webapp_url: "https://football.idev.wtf",
};

export function useAppConfig() {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);

  useEffect(() => {
    apiRequest<AppConfig>("/api/auth/config")
      .then((data) => {
        if (data && data.bot_username) {
          setConfig(data);
        }
      })
      .catch(() => {});
  }, []);

  return config;
}
