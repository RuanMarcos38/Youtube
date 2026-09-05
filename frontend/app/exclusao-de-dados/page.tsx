import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Exclusão de Dados | ShortsFlow AI",
  description: "Como desconectar YouTube e TikTok e solicitar a exclusão de dados armazenados pelo ShortsFlow AI.",
};

export default function DataDeletionPage() {
  return (
    <main className="min-h-screen bg-[#f8faf5] px-6 py-12 text-[#111815]">
      <article className="mx-auto max-w-4xl rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-12">
        <a href="/integracoes" className="text-sm font-bold text-[#5f8500]">← Voltar às integrações do ShortsFlow AI</a>
        <p className="mt-8 text-xs font-bold uppercase tracking-[0.22em] text-[#75a900]">Privacidade</p>
        <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Exclusão de Dados</h1>
        <p className="mt-4 text-sm text-[#6d776f]">Última atualização: 5 de setembro de 2026.</p>

        <div className="mt-10 space-y-8 leading-7 text-[#303934]">
          <section>
            <h2 className="text-xl font-bold text-[#111815]">Desconectar o YouTube</h2>
            <p className="mt-2">Dentro do ShortsFlow AI, utilize a opção de desconexão/troca de conta do YouTube. Isso interrompe o uso da autorização pelo perfil correspondente.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">Revogar o acesso no Google</h2>
            <p className="mt-2">Você também pode remover o acesso do ShortsFlow AI diretamente nas configurações de segurança da sua Conta Google em <a className="font-bold text-[#5f8500] underline" href="https://security.google.com/settings/security/permissions" target="_blank" rel="noreferrer">Apps e serviços conectados</a>.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">Desconectar o TikTok</h2>
            <p className="mt-2">Dentro do ShortsFlow AI, utilize a opção de troca/desconexão da conta TikTok. Isso interrompe o uso do token associado ao perfil e impede novas operações pela integração até uma nova autorização.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">Revogar o acesso no TikTok</h2>
            <p className="mt-2">O usuário também pode remover a autorização diretamente pelos controles de segurança e aplicativos conectados disponibilizados pelo próprio TikTok. Após a revogação, o ShortsFlow AI não conseguirá acessar os recursos protegidos pela autorização revogada.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">Solicitar exclusão dos dados armazenados</h2>
            <p className="mt-2">Para solicitar a exclusão da conta e dos dados armazenados pelo ShortsFlow AI, entre em contato pelos canais oficiais de suporte da R2R Marketing Digital informando o e-mail cadastrado na plataforma. A solicitação será tratada conforme as obrigações aplicáveis e as políticas das integrações utilizadas.</p>
            <p className="mt-2">A exclusão de dados no ShortsFlow AI não remove automaticamente vídeos ou outros conteúdos já armazenados/publicados diretamente no YouTube ou TikTok. Para remover conteúdo nessas plataformas, utilize as ferramentas oficiais de cada serviço.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">Dados de integração</h2>
            <p className="mt-2">Quando tecnicamente aplicável, a exclusão da conta no ShortsFlow AI inclui a remoção dos registros de conexão, tokens e dados de integração armazenados pela própria plataforma, ressalvadas obrigações legais de retenção.</p>
          </section>
        </div>
      </article>
    </main>
  );
}
