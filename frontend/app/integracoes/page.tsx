import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Integrações | ShortsFlow AI",
  description: "Como o ShortsFlow AI integra YouTube, Google e TikTok para criação, revisão e publicação de vídeos curtos.",
};

const integrations = [
  {
    title: "YouTube",
    description: "Conexão autorizada via Google OAuth para identificar o canal, acompanhar dados disponíveis e publicar Shorts após revisão do usuário.",
  },
  {
    title: "TikTok Login Kit",
    description: "Permite que o usuário conecte sua própria conta TikTok usando o fluxo oficial de autorização. O ShortsFlow AI nunca solicita a senha da conta TikTok.",
  },
  {
    title: "TikTok Content Posting API",
    description: "Permite enviar um vídeo escolhido pelo usuário para o TikTok. Antes do envio, o usuário seleciona a privacidade disponibilizada pelo TikTok e confirma explicitamente a publicação.",
  },
  {
    title: "TikTok Display API",
    description: "Quando o aplicativo e o usuário possuem os escopos aprovados e autorizados, o ShortsFlow AI pode exibir dados de perfil e desempenho disponibilizados pelo TikTok.",
  },
];

export default function IntegrationsPage() {
  return (
    <main className="min-h-screen bg-[#f7f7f7] px-5 py-10 text-[#111] md:px-8 md:py-14">
      <div className="mx-auto max-w-6xl">
        <header className="rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-12">
          <a href="/" className="text-sm font-bold text-[#5f8500]">ShortsFlow AI</a>
          <p className="mt-10 text-xs font-black uppercase tracking-[0.2em] text-red-600">Site público oficial · Plataforma de automação de vídeos curtos</p>
          <h1 className="mt-4 max-w-4xl text-4xl font-black tracking-tight md:text-6xl">Crie, revise e publique Shorts em um único fluxo.</h1>
          <p className="mt-6 max-w-3xl text-base leading-8 text-[#5f6762]">O ShortsFlow AI transforma vídeos em cortes verticais, organiza a revisão e conecta contas autorizadas do YouTube e TikTok para publicação. O usuário mantém controle sobre a conta conectada, os vídeos selecionados e as opções de publicação.</p>

          <nav className="mt-8 flex flex-wrap gap-3 text-sm font-bold">
            <a href="/privacidade" className="rounded-xl border border-black/10 bg-white px-4 py-3 hover:bg-[#f5f5f5]">Política de Privacidade</a>
            <a href="/termos" className="rounded-xl border border-black/10 bg-white px-4 py-3 hover:bg-[#f5f5f5]">Termos de Uso</a>
            <a href="/exclusao-de-dados" className="rounded-xl border border-black/10 bg-white px-4 py-3 hover:bg-[#f5f5f5]">Exclusão de Dados</a>
            <a href="/" className="rounded-xl bg-[#111] px-4 py-3 text-white">Acessar ShortsFlow</a>
          </nav>
        </header>

        <section className="mt-6 grid gap-4 md:grid-cols-2">
          {integrations.map((item) => (
            <article key={item.title} className="rounded-2xl border border-black/5 bg-white p-6 shadow-sm">
              <h2 className="text-xl font-black">{item.title}</h2>
              <p className="mt-3 text-sm leading-7 text-[#606863]">{item.description}</p>
            </article>
          ))}
        </section>

        <section className="mt-6 rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-10">
          <p className="text-xs font-black uppercase tracking-[0.18em] text-red-600">Fluxo TikTok</p>
          <h2 className="mt-3 text-3xl font-black">Como a integração é utilizada</h2>
          <ol className="mt-6 grid gap-4 text-sm leading-7 text-[#505853]">
            <li><strong className="text-[#111]">1. Conectar conta.</strong> O usuário inicia a conexão no ShortsFlow e autoriza o aplicativo na página oficial do TikTok.</li>
            <li><strong className="text-[#111]">2. Selecionar conteúdo.</strong> O usuário escolhe quais Shorts deseja enviar; o sistema não publica toda a biblioteca automaticamente.</li>
            <li><strong className="text-[#111]">3. Consultar opções permitidas.</strong> O ShortsFlow consulta as opções de privacidade e recursos devolvidos pelo TikTok para a conta conectada.</li>
            <li><strong className="text-[#111]">4. Confirmar publicação.</strong> O usuário escolhe a privacidade disponível, configura opções permitidas e confirma expressamente o envio.</li>
            <li><strong className="text-[#111]">5. Acompanhar status.</strong> O ShortsFlow acompanha a fila e só considera o conteúdo publicado quando o TikTok confirma o estado final.</li>
          </ol>
        </section>

        <section className="mt-6 grid gap-4 lg:grid-cols-2">
          <article className="rounded-2xl border border-black/5 bg-white p-7 shadow-sm">
            <h2 className="text-xl font-black">Permissões TikTok</h2>
            <p className="mt-3 text-sm leading-7 text-[#606863]">A conexão principal utiliza permissões compatíveis com Login Kit e publicação, como <code>user.info.basic</code> e <code>video.publish</code>, quando aprovadas e autorizadas. Recursos de métricas somente utilizam escopos adicionais após aprovação do TikTok e autorização do usuário.</p>
          </article>
          <article className="rounded-2xl border border-black/5 bg-white p-7 shadow-sm">
            <h2 className="text-xl font-black">Controle do usuário</h2>
            <p className="mt-3 text-sm leading-7 text-[#606863]">O usuário pode trocar/desconectar a conta conectada e revogar permissões nas plataformas de origem. O ShortsFlow não solicita senhas do Google, YouTube ou TikTok.</p>
          </article>
        </section>

        <footer className="py-10 text-center text-xs leading-6 text-[#737b76]">
          ShortsFlow AI · R2R Marketing Digital · <a className="font-bold underline" href="/privacidade">Privacidade</a> · <a className="font-bold underline" href="/termos">Termos</a> · <a className="font-bold underline" href="/exclusao-de-dados">Exclusão de Dados</a>
        </footer>
      </div>
    </main>
  );
}
