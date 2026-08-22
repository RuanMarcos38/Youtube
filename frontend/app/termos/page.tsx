import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Termos de Uso | ShortsFlow AI",
  description: "Termos de Uso do ShortsFlow AI.",
};

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-[#f8faf5] px-6 py-12 text-[#111815]">
      <article className="mx-auto max-w-4xl rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-12">
        <a href="/" className="text-sm font-bold text-[#5f8500]">← Voltar ao ShortsFlow AI</a>
        <p className="mt-8 text-xs font-bold uppercase tracking-[0.22em] text-[#75a900]">ShortsFlow AI</p>
        <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Termos de Uso</h1>
        <p className="mt-4 text-sm text-[#6d776f]">Última atualização: 22 de agosto de 2026.</p>

        <div className="mt-10 space-y-8 leading-7 text-[#303934]">
          <section>
            <h2 className="text-xl font-bold text-[#111815]">1. Serviço</h2>
            <p className="mt-2">O ShortsFlow AI oferece ferramentas para auxiliar na criação, revisão, organização e publicação de Shorts, incluindo recursos de inteligência artificial e integração autorizada com o YouTube.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">2. Conta e acesso</h2>
            <p className="mt-2">Cada usuário é responsável pela segurança de sua conta e pelas ações realizadas por meio de seu acesso. O uso de integrações externas depende de autorização expressa do titular da respectiva conta.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">3. Conteúdo e responsabilidade do usuário</h2>
            <p className="mt-2">O usuário declara possuir os direitos e autorizações necessários sobre os conteúdos enviados, processados ou publicados por meio da plataforma e é responsável por revisar o material antes da publicação.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">4. Inteligência artificial</h2>
            <p className="mt-2">Resultados gerados por inteligência artificial, como cortes sugeridos, títulos, descrições, tags e legendas, são recursos de apoio. O desempenho, alcance, posicionamento, monetização ou viralização de conteúdos não é garantido.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">5. YouTube e Google</h2>
            <p className="mt-2">Ao conectar uma Conta Google/YouTube e utilizar recursos dos Serviços de API do YouTube, o usuário concorda também em obedecer aos <a className="font-bold text-[#5f8500] underline" href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">Termos de Serviço do YouTube</a> e às políticas aplicáveis do Google.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">6. Planos, limites e pagamentos</h2>
            <p className="mt-2">O acesso a funcionalidades pode variar conforme o plano contratado, limites de uso, disponibilidade técnica e condições comerciais vigentes. Pagamentos e liberações de acesso seguem as informações apresentadas no checkout e na plataforma.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">7. Uso aceitável</h2>
            <p className="mt-2">É proibido utilizar o serviço para violar direitos autorais, direitos de terceiros, políticas do YouTube/Google, leis aplicáveis, ou para praticar fraude, abuso, automação enganosa ou atividades que prejudiquem terceiros ou a infraestrutura do serviço.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">8. Privacidade e encerramento</h2>
            <p className="mt-2">O tratamento de dados é descrito na <a className="font-bold text-[#5f8500] underline" href="/privacidade">Política de Privacidade</a>. O usuário pode desconectar integrações e solicitar exclusão de dados conforme os procedimentos informados pela plataforma.</p>
          </section>
        </div>
      </article>
    </main>
  );
}
