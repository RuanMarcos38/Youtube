"use client";

import { useState } from "react";

export default function ConexaoAutomatica() {
  const [code, setCode] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function pair() {
    setBusy(true);
    setCode("");
    setMessage("");
    try {
      const response = await fetch("/api/admin/residential-proxy/pair", {
        method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persistent: true }),
      });
      if (!response.ok) {
        setMessage(response.status === 401 || response.status === 403
          ? "Entre como administrador nas Configurações para autorizar este computador."
          : "Não foi possível parear. Desconecte o cliente atual antes de tentar novamente.");
        return;
      }
      const result = await response.json();
      if (result.persistent !== true || !/^[A-Za-z0-9_-]{43}$/.test(result.code || "")) {
        setMessage("O servidor ainda não oferece pareamento automático. Aguarde a atualização.");
        return;
      }
      setCode(result.code);
      setMessage("Autorização gerada. Copie para o instalador deste computador. Ela será protegida pelo Windows.");
    } catch {
      setMessage("Sem conexão com o servidor. Tente novamente.");
    } finally {
      setBusy(false);
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setMessage("Código copiado. Use somente no instalador local do ShortsFlow.");
    } catch {
      setMessage("Copie o código selecionando o campo e pressionando Ctrl+C.");
    }
  }
  return <main className="mx-auto max-w-xl p-8">
    <h1 className="text-2xl font-bold">Conexão automática do computador</h1>
    <p className="my-4">Autorize este computador para conectar ao ShortsFlow ao entrar no Windows e reconectar após quedas de internet. O computador precisa estar ligado e conectado à internet.</p>
    <p className="my-4">A autorização permanece válida até ser revogada em Configurações → Desativar conexão residencial. Apenas os destinos HTTPS permitidos do YouTube podem usar esta conexão. As contas e chaves existentes são preservadas.</p>
    <button className="sf-button sf-button-primary" disabled={busy} onClick={() => void pair()}>{busy ? "Preparando…" : "Autorizar conexão automática deste computador"}</button>
    {code && <div className="my-4"><label htmlFor="device-code">Código de pareamento</label><input id="device-code" type="password" readOnly value={code} autoComplete="off" className="my-2 w-full border p-3" onFocus={e => e.currentTarget.select()} /><button className="sf-button sf-button-outline" onClick={() => void copy()}>Copiar código para o instalador</button></div>}
    <p role="status" aria-live="polite" className="my-4">{message}</p>
    <a href="/configuracoes">Voltar às configurações</a>
  </main>;
}
