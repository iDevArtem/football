// frontend/src/hooks/useTelegram.ts
import { useEffect, useMemo } from "react";

export function useTelegram() {
  const tg = useMemo(() => {
    return typeof window !== "undefined" ? (window as any).Telegram?.WebApp : null;
  }, []);

  useEffect(() => {
    if (tg) {
      try {
        tg.ready();
        tg.expand();
      } catch (e) {
        // ignore
      }
    }
  }, [tg]);

  const hapticImpact = (style: "light" | "medium" | "heavy" | "rigid" | "soft" = "medium") => {
    try {
      tg?.HapticFeedback?.impactOccurred(style);
    } catch (e) {}
  };

  const hapticNotification = (type: "error" | "success" | "warning" = "success") => {
    try {
      tg?.HapticFeedback?.notificationOccurred(type);
    } catch (e) {}
  };

  const isTma = Boolean(tg && tg.initData && tg.initData.length > 0);

  return {
    tg,
    isTma,
    initData: tg?.initData || "",
    initDataUnsafe: tg?.initDataUnsafe || null,
    hapticImpact,
    hapticNotification,
    themeParams: tg?.themeParams || {},
  };
}
