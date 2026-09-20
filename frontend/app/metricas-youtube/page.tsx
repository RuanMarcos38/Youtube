import type { Metadata } from "next";
import VidiqMetricsChat from "@/components/VidiqMetricsChat";

export const metadata: Metadata = {
  title: "Métricas YouTube + vidIQ | ShortsFlow AI",
  description: "Chat de inteligência do YouTube com dados reais do vidIQ.",
};

export default function YoutubeMetricsPage() {
  return <VidiqMetricsChat />;
}
