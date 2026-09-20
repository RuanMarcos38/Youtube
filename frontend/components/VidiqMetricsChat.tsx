"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { vidiqChat, vidiqStatus, type VidiqChatResult, type VidiqStatus } from "@/lib/api";

type Message = {
  role: "user" | "assistant";
  text: string;
  tool?: string;
  data?: Record<string, unknown>;
};

const QUICK_PROMPTS = [
  "Quais palavras-chave têm melhor oportunidade para meu próximo Short?",
  "Quais Shorts estão em alta no Brasil agora?",
  "Mostre meus vídeos com melhor desempenho.",
  "Quais são minhas principais fontes de tráfego?",
  "Compare Shorts com vídeos longos no meu canal.",
];

export default function VidiqMetricsChat() {
  const [status, setStatus] = useState<VidiqStatus | null>(null);
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      text: "Pergunte sobre palavras-chave, score de título, tendências, canal, vídeos ou Analytics. O chat consulta o vidIQ e interpreta os dados para você.",
    },
  ]);
  const [message, setMessage] = useState("");
  const [channelId, setChannelId] = useState("");
  const [videoId, setVideoId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    vidiqStatus()
      .then((value) => {
        setStatus(value);
        const firstChannel = value.channels?.[0]?.channelId;
        if (firstChannel) setChannelId(firstChannel);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Não foi possível consultar o status do vidIQ."));
  }, []);

  const creditText = useMemo(() => {
    const value = status?.credits?.totalCredits;
    return typeof value === "number" ? `${value} créditos` : "Créditos não carregados";
  }, [status]);

  async function ask(text: string) {
    const clean = text.trim();
    if (!clean || loading) return;
    setMessages((current) => [...current, { role: "user", text: clean }]);
    setMessage("");
    setError("");
    setLoading(true);
    try {
      const result: VidiqChatResult = await vidiqChat({
        message: clean,
        channel_id: channelId || undefined,
        video_id: videoId || undefined,
      });
      setMessages((current) => [
        ...current,
        { role: "assistant", text: result.answer, tool: result.tool, data: result.data },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível consultar o vidIQ.");
    } finally {
      setLoading(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(message);
  }

  const configured = status?.configured === true;
  const connected = status?.connected === true;

  return (
    <main className="min-h-screen bg-[#f7f7f7] px-4 py-8 text-[#111] md:px-8 md:py-10">
      <div className="mx-auto max-w-7xl">
        <header className="rounded-[28px] border border-[#e6e6e6] bg-white p-6 shadow-sm md:p-8">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-black uppercase tracking-[0.16em] text-[#ff0000]">YouTube Intelligence</div>
              <h1 className="mt-2 text-3xl font-black tracking-tight md:text-4xl">Chat + Métricas vidIQ</h1>
              <p className="mt-3 max-w-3xl text-sm leading-7 text-[#667085]">
                Consulte dados reais de palavras-chave, títulos, tendências, canais, vídeos e Analytics do YouTube diretamente dentro do ShortsFlow.
              </p>
            </div>
            <div className="rounded-2xl border border-[#e5e7eb] bg-[#fafafa] px-4 py-3 text-xs">
              <div className="font-black">{connected ? "vidIQ conectado" : configured ? "vidIQ configurado, aguardando conexão" : "vidIQ não configurado"}</div>
              <div className="mt-1 text-[#667085]">{creditText}</div>
            </div>
          </div>
        </header>

        {!configured && status && (
          <section className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-950">
            <div className="font-black">Falta apenas adicionar a chave MCP do vidIQ no EasyPanel.</div>
            <p className="mt-2 leading-6">
              Gere a chave no vidIQ em Account Settings → MCP e salve no serviço como <code className="rounded bg-white px-1.5 py-0.5 font-bold">VIDIQ_MCP_API_KEY</code>.
              O segredo não aparece no navegador e não é salvo no GitHub.
            </p>
            <a href="https://app.vidiq.com/account/settings/mcp" target="_blank" rel="noreferrer" className="mt-3 inline-flex rounded-xl bg-[#111] px-4 py-2.5 text-xs font-black text-white">
              Abrir configurações MCP do vidIQ
            </a>
          </section>
        )}

        <section className="mt-5 grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="rounded-[24px] border border-[#e6e6e6] bg-white p-5 shadow-sm">
            <h2 className="text-sm font-black">Contexto da consulta</h2>
            <label className="mt-4 block text-xs font-bold text-[#555]">
              Canal / @handle
              <input value={channelId} onChange={(e) => setChannelId(e.target.value)} placeholder="@seucanal ou UC..." className="mt-2 w-full rounded-xl border border-[#ddd] px-3 py-2.5 text-sm outline-none focus:border-[#ff0000]" />
            </label>
            <label className="mt-4 block text-xs font-bold text-[#555]">
              Vídeo / URL
              <input value={videoId} onChange={(e) => setVideoId(e.target.value)} placeholder="ID ou URL do vídeo" className="mt-2 w-full rounded-xl border border-[#ddd] px-3 py-2.5 text-sm outline-none focus:border-[#ff0000]" />
            </label>

            <div className="mt-6 text-xs font-black uppercase tracking-[0.1em] text-[#777]">Perguntas rápidas</div>
            <div className="mt-3 grid gap-2">
              {QUICK_PROMPTS.map((prompt) => (
                <button key={prompt} type="button" onClick={() => void ask(prompt)} disabled={!configured || loading} className="rounded-xl border border-[#e5e5e5] bg-[#fafafa] px-3 py-2.5 text-left text-xs font-semibold leading-5 hover:border-[#ff0000] hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50">
                  {prompt}
                </button>
              ))}
            </div>
          </aside>

          <section className="flex min-h-[640px] flex-col overflow-hidden rounded-[24px] border border-[#e6e6e6] bg-white shadow-sm">
            <div className="border-b border-[#ededed] px-5 py-4">
              <div className="text-sm font-black">Assistente de Métricas</div>
              <div className="mt-1 text-xs text-[#777]">IA + dados ao vivo do vidIQ</div>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-5">
              {messages.map((item, index) => (
                <div key={`${item.role}-${index}`} className={item.role === "user" ? "ml-auto max-w-[85%]" : "mr-auto max-w-[92%]"}>
                  <div className={item.role === "user" ? "rounded-2xl rounded-br-md bg-[#111] px-4 py-3 text-sm leading-6 text-white" : "rounded-2xl rounded-bl-md border border-[#e5e5e5] bg-[#fafafa] px-4 py-3 text-sm leading-6 text-[#222]"}>
                    {item.text}
                  </div>
                  {item.tool && <div className="mt-1 px-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#999]">{item.tool}</div>}
                  {item.data && (
                    <details className="mt-2 rounded-xl border border-[#ededed] bg-white p-3 text-xs">
                      <summary className="cursor-pointer font-black">Ver dados brutos do vidIQ</summary>
                      <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-[#555]">{JSON.stringify(item.data, null, 2)}</pre>
                    </details>
                  )}
                </div>
              ))}
              {loading && <div className="mr-auto rounded-2xl border border-[#e5e5e5] bg-[#fafafa] px-4 py-3 text-sm font-semibold text-[#666]">Consultando vidIQ e analisando...</div>}
            </div>

            {error && <div className="mx-5 mb-3 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700">{error}</div>}

            <form onSubmit={submit} className="border-t border-[#ededed] p-4">
              <div className="flex gap-2">
                <textarea value={message} onChange={(e) => setMessage(e.target.value)} disabled={!configured || loading} rows={2} placeholder="Ex.: Quais palavras-chave para marketing digital têm score acima de 60 no Brasil?" className="min-h-[54px] flex-1 resize-none rounded-xl border border-[#ddd] px-3 py-3 text-sm outline-none focus:border-[#ff0000] disabled:bg-[#f5f5f5]" />
                <button disabled={!configured || loading || !message.trim()} className="self-stretch rounded-xl bg-[#ff0000] px-5 text-sm font-black text-white hover:bg-[#e60000] disabled:cursor-not-allowed disabled:opacity-40">
                  Enviar
                </button>
              </div>
            </form>
          </section>
        </section>
      </div>
    </main>
  );
}
