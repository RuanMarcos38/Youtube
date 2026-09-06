"use client";

import { useEffect } from "react";

export default function PresenceHeartbeat() {
  useEffect(() => {
    let stopped = false;

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
        // Páginas públicas e oscilações de rede não devem interferir na UI.
      }
    }

    void ping();
    const interval = window.setInterval(() => void ping(), 30_000);
    const onVisibility = () => {
      if (document.visibilityState === "visible") void ping();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      stopped = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return null;
}
