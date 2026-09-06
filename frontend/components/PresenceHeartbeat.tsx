"use client";

import { useEffect } from "react";
import { authMe } from "@/lib/api";

export default function PresenceHeartbeat() {
  useEffect(() => {
    let stopped = false;
    let interval: number | null = null;

    async function ping() {
      if (stopped || document.visibilityState === "hidden") return;
      try {
        await fetch("/api/presence/heartbeat", {
          method: "POST",
          credentials: "include",
          cache: "no-store",
          headers: { "Content-Type": "application/json" },
        });
      } catch {
        // Oscilações de rede não devem interferir na UI nem na autenticação.
      }
    }

    const onVisibility = () => {
      if (document.visibilityState === "visible") void ping();
    };

    authMe()
      .then(() => {
        if (stopped) return;
        void ping();
        interval = window.setInterval(() => void ping(), 30_000);
        document.addEventListener("visibilitychange", onVisibility);
      })
      .catch(() => undefined);

    return () => {
      stopped = true;
      if (interval != null) window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return null;
}
