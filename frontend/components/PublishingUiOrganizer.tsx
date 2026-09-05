"use client";

import { useEffect } from "react";

export default function PublishingUiOrganizer() {
  useEffect(() => {
    let raf = 0;

    const sync = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const root = document.querySelector<HTMLElement>("#cortes [data-publishing-enhancements-host]");
        if (!root) return;

        // O dashboard do TikTok agora possui um menu próprio. Mantemos o
        // componente original intacto e apenas retiramos o bloco visual da aba
        // Publicações para não misturar métricas com a fila de envio.
        const dashboardTitle = Array.from(root.querySelectorAll<HTMLElement>("div"))
          .find((element) => element.textContent?.trim() === "Dashboard TikTok");
        const dashboardCard = dashboardTitle?.parentElement?.parentElement?.parentElement as HTMLElement | null;
        if (dashboardCard && dashboardCard.dataset.metricsMoved !== "true") {
          dashboardCard.dataset.metricsMoved = "true";
          dashboardCard.style.display = "none";
        }

        // O TikTok exige que a aplicação use somente opções devolvidas pelo
        // Creator Info. Se PUBLIC_TO_EVERYONE ainda não vier da API, mostramos
        // a opção como indisponível em vez de fingir que o envio público está
        // liberado. Quando a API liberar, a opção real aparece automaticamente.
        const privacyLabel = Array.from(root.querySelectorAll<HTMLLabelElement>("label"))
          .find((label) => label.textContent?.includes("Privacidade do TikTok"));
        const select = privacyLabel?.querySelector<HTMLSelectElement>("select");
        if (select) {
          const publicAvailable = Array.from(select.options).some((option) => option.value === "PUBLIC_TO_EVERYONE");
          const placeholder = select.querySelector<HTMLOptionElement>('option[data-public-placeholder="true"]');
          if (publicAvailable && placeholder) placeholder.remove();
          if (!publicAvailable && !placeholder) {
            const option = document.createElement("option");
            option.value = "__PUBLIC_PENDING__";
            option.disabled = true;
            option.dataset.publicPlaceholder = "true";
            option.textContent = "Público (aguardando liberação do TikTok)";
            select.appendChild(option);
          }
        }
      });
    };

    sync();
    const observer = new MutationObserver(sync);
    observer.observe(document.body, { childList: true, subtree: true });
    window.addEventListener("hashchange", sync);
    const timer = window.setInterval(sync, 1200);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      window.removeEventListener("hashchange", sync);
      window.clearInterval(timer);
    };
  }, []);

  return null;
}
