import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Termos de Uso | ShortsFlow AI",
  description: "Termos de Uso do ShortsFlow AI para criação, revisão e publicação em YouTube e TikTok.",
};

export default function TermsPage() {
  return (
    <main className="min-h-screen bg-[#f8faf5] px-6 py-12 text-[#111815]">
      <article className="mx-auto max-w-4xl rounded-[28px] border border-black/5 bg-white p-8 shadow-sm md:p-12">
        <a href="/integracoes" className="text-sm font-bold text-[#5f8500]">← Voltar às integrações do ShortsFlow AI</a>
        <p className="mt-8 text-xs font-bold uppercase tracking-[0.22em] text-[#75a900]">ShortsFlow AI</p>
        <h1 className="mt-3 text-4xl font-black tracking-tight md:text-5xl">Termos de Uso</h1>
        <p className="mt-4 text-sm text-[#6d776f]">Última atualização: 5 de setembro de 2026.</p>

        <div className="mt-10 space-y-8 leading-7 text-[#303934]">
          <section>
            <h2 className="text-xl font-bold text-[#111815]">1. Serviço</h2>
            <p className="mt-2">O ShortsFlow AI oferece ferramentas para criação, revisão, organização e publicação de vídeos curtos, incluindo recursos de inteligência artificial e integrações autorizadas com YouTube, Google e TikTok.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">2. Conta e acesso</h2>
            <p className="mt-2">Cada usuário é responsável pela segurança de sua conta e pelas ações realizadas por meio de seu acesso. Integrações externas dependem de autorização expressa do titular da respectiva conta e podem ser revogadas a qualquer momento.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">3. Conteúdo e responsabilidade do usuário</h2>
            <p className="mt-2">O usuário declara possuir direitos, licenças e autorizações necessários sobre os conteúdos enviados, processados ou publicados por meio da plataforma. O usuário é responsável por revisar o material, título, descrição, privacidade e demais opções antes de confirmar uma publicação.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">4. Inteligência artificial</h2>
            <p className="mt-2">Resultados gerados por inteligência artificial, como cortes sugeridos, títulos, descrições, tags e legendas, são recursos de apoio. Desempenho, alcance, posicionamento, monetização ou viralização não são garantidos.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">5. YouTube e Google</h2>
            <p className="mt-2">Ao conectar uma Conta Google/YouTube e utilizar os Serviços de API do YouTube, o usuário concorda também em obedecer aos <a className="font-bold text-[#5f8500] underline" href="https://www.youtube.com/t/terms" target="_blank" rel="noreferrer">Termos de Serviço do YouTube</a> e às políticas aplicáveis do Google.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">6. TikTok</h2>
            <p className="mt-2">Ao conectar uma conta TikTok, o usuário autoriza o ShortsFlow AI somente por meio do fluxo oficial OAuth do TikTok. O ShortsFlow AI utiliza produtos e escopos aprovados para o aplicativo, como Login Kit e Content Posting API, conforme disponibilizados pelo TikTok.</p>
            <p className="mt-2">O envio de conteúdo ao TikTok ocorre somente após ação explícita do usuário. A plataforma deve respeitar as opções de privacidade e publicação devolvidas pelo TikTok para a conta conectada.</p>
            <p className="mt-2">A disponibilidade de publicação pública, métricas, limites de uso, revisão de conteúdo e outros recursos depende das regras, auditorias, escopos e disponibilidade técnica do TikTok. O ShortsFlow AI não pode garantir aprovação, publicação pública ou permanência de conteúdo quando houver restrições impostas pelo TikTok.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">7. Planos, limites e pagamentos</h2>
            <p className="mt-2">O acesso a funcionalidades pode variar conforme o plano contratado, limites de uso, disponibilidade técnica e condições comerciais vigentes. Pagamentos e liberações de acesso seguem as informações apresentadas no checkout e na plataforma.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">8. Uso aceitável</h2>
            <p className="mt-2">É proibido utilizar o serviço para violar direitos autorais, direitos de terceiros, políticas do YouTube/Google/TikTok, leis aplicáveis ou para praticar fraude, spam, abuso, automação enganosa ou atividades que prejudiquem terceiros ou a infraestrutura do serviço.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">9. Serviços de terceiros</h2>
            <p className="mt-2">YouTube, Google e TikTok são serviços independentes do ShortsFlow AI. Alterações de API, disponibilidade, auditorias, bloqueios, limites diários, moderação, suspensão de contas ou mudanças de políticas dessas plataformas podem afetar recursos integrados.</p>
          </section>

          <section>
            <h2 className="text-xl font-bold text-[#111815]">10. Privacidade e encerramento</h2>
            <p className="mt-2">O tratamento de dados é descrito na <a className="font-bold text-[#5f8500] underline" href="/privacidade">Política de Privacidade</a>. O usuário pode desconectar integrações e solicitar exclusão de dados conforme <a className="font-bold text-[#5f8500] underline" href="/exclusao-de-dados">Exclusão de Dados</a>.</p>
          </section>
        </div>
      </article>
    </main>
  );
}
